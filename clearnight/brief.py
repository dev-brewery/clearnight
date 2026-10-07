"""Brief generation (T18, ARCHITECTURE §6): prompt build + LLM call.

`build_prompt` turns the top-ranked nights into a [system, user] message
pair. The user payload is compact JSON containing ONLY computed values,
pre-rounded here — the model is explicitly told never to round or invent.

`generate_brief` POSTs to any OpenAI-compatible `{base_url}/chat/completions`
endpoint (one retry on transport error) and returns a `BriefResult`. Any
failure — transport error, bad reply — falls back to the labeled template
brief assembled from the same computed data (A7). The template reuses the
T14 renderer's template builder so both paths share one format.

`BriefResult` lives here (not models.py): it is the contract between the
brief stage and the T19 verifier/retry loop, so it stays next to the code
that produces it.

Failures are logged with the exception class only — never the URL and never
the API key.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from clearnight.models import Night
from clearnight.render import _template_brief, _wrapped_label

if TYPE_CHECKING:
    from clearnight.config import LLMCfg

logger = logging.getLogger(__name__)

TEMPLATE_BRIEF_LABEL = (
    "Template brief (LLM output unavailable or failed verification; "
    "all values are computed, not generated)."
)

SYSTEM_PROMPT = (
    "You write short stargazing briefs. Use ONLY facts present in the "
    "provided data. Every time, number, direction, and event name must come "
    "from the data, pre-rounded as given. Never invent or estimate. "
    "120 words or fewer. Structure: when to go out, which way to face, "
    "what to look for."
)


@dataclass(frozen=True)
class BriefResult:
    """Outcome of the brief stage (T18); consumed by the T19 verifier.

    text: the brief body (LLM reply or template). source: "llm" or
    "template". attempts: LLM calls made (0 when offline template).
    violations: verifier findings, filled by T19; always [] here.
    """

    text: str
    source: str  # "llm" | "template"
    attempts: int
    violations: list  # list[str], populated by clearnight.verify (T19)


def _fmt12(when: dt.datetime) -> str:
    """Site-local 12-hour clock, e.g. '8:14 pm' (rounding already done)."""
    h12 = when.hour % 12 or 12
    return f"{h12}:{when.minute:02d} {when.strftime('%p').lower()}"


def _infer_tz(night: Night) -> ZoneInfo:
    """Display-only fallback when no site timezone is supplied: pick the
    fixed half-hour offset (UTC-12..UTC+14) whose dark window lands most
    plausibly in local civil time (start nearest 20:30, end nearest 05:30,
    start on the night's local date). Deterministic; the real pipeline
    passes the site's ZoneInfo explicitly (T20), so this only covers brief
    calls made without a site object."""
    best, best_score = dt.timezone.utc, None
    for minutes in range(-12 * 60, 14 * 60 + 1, 30):
        start = night.dark.start_utc + dt.timedelta(minutes=minutes)
        end = night.dark.end_utc + dt.timedelta(minutes=minutes)
        if start.date() != night.date_local or not 17 <= start.hour <= 23:
            continue
        score = 3 * abs((start.hour * 60 + start.minute) - 20 * 60 - 30) \
            + abs((end.hour * 60 + end.minute) - 5 * 60 - 30)
        if best_score is None or score < best_score:
            best, best_score = dt.timezone(dt.timedelta(minutes=minutes)), score
    return best


def _mean(vals: list[float | None]) -> float | None:
    present = [v for v in vals if v is not None]
    return sum(present) / len(present) if present else None


def _night_payload(night: Night, tz: dt.tzinfo) -> dict:
    """Compact computed-only JSON for one night. Numbers are pre-rounded
    HERE; the LLM must never round."""
    ws = _fmt12(night.dark.start_utc.astimezone(tz))
    we = _fmt12(night.dark.end_utc.astimezone(tz))
    moon = night.moon
    rise = moon.rise_utc.astimezone(tz) if moon.rise_utc else None
    set_ = moon.set_utc.astimezone(tz) if moon.set_utc else None
    cloud = _mean([w.cloud_total_pct for w in night.weather])
    rh = _mean([w.rh_pct for w in night.weather])
    wind = _mean([w.wind_kmh for w in night.weather])
    vis_m = _mean([w.visibility_m for w in night.weather])
    s = night.score
    payload = {
        "date": night.date_local.isoformat(),
        "weekday": night.date_local.strftime("%A"),
        "dark_window": {"start": ws, "end": we},
        "moon": {
            "phase": moon.phase_name,
            "illum_pct": round(moon.illumination_frac * 100),
            "rise": _fmt12(rise) if rise else None,
            "set": _fmt12(set_) if set_ else None,
            "up_share": round(moon.up_fraction, 2),
        },
        "weather": {
            "cloud_pct": round(cloud),
            "humidity_pct": round(rh),
            "wind_kmh": round(wind, 1),
            "visibility_km": round(vis_m / 1000, 1) if vis_m is not None else None,
        },
        "dew_risk": night.conditions.dew_risk,
        "score": {
            "total": s.total,
            "verdict": s.verdict,
            "factors": {
                "cloud": round(s.cloud_term, 1),
                "moon": round(s.moon_term, 1),
                "transparency": round(s.transparency_term, 1),
                "dew": round(s.dew_term, 1),
                "wind": round(s.wind_term, 1),
                "base": round(s.base, 1),
                "meteor_bonus": s.meteor_bonus,
                "iss_bonus": s.iss_bonus,
                "event_bonus": s.event_bonus,
            },
        },
        "showers": [
            {
                "name": sh.name,
                "zhr": round(sh.zhr),
                "peak": sh.is_peak_night,
                "radiant_up_hours": round(sh.radiant_up_hours, 1),
            }
            for sh in night.showers
        ],
        "iss_passes": [
            {
                "start": _fmt12(p.start_utc.astimezone(tz)),
                "max": _fmt12(p.max_utc.astimezone(tz)),
                "end": _fmt12(p.end_utc.astimezone(tz)),
                "max_alt_deg": round(p.max_alt_deg),
                "directions": f"{p.start_dir}>{p.max_dir}>{p.end_dir}",
            }
            for p in night.iss_passes
        ],
    }
    return payload


def build_prompt(
    plan_nights: list[Night],
    site_name: str,
    tz: ZoneInfo | None = None,
) -> list[dict]:
    """[system, user] messages per ARCHITECTURE §6 for the top 3 nights."""
    tz = tz or _infer_tz(plan_nights[0])
    user = {
        "site": site_name,
        "nights": [_night_payload(n, tz) for n in plan_nights[:3]],
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user, separators=(",", ":"))},
    ]


def _template_result(plan_nights: list[Night], attempts: int) -> BriefResult:
    """Labeled template brief from computed data only (reuses the T14
    template builder; identical field discipline)."""
    if not plan_nights:
        # Empty plan (e.g. high-latitude summer, no astronomical darkness
        # in the window): render an honest one-liner under the SAME labeled
        # header. No tz-dependent lines — there is nothing to localize.
        lines = [*_wrapped_label(),
                 "No nights with astronomical darkness in the plan window."]
        return BriefResult(text="\n".join(lines), source="template",
                           attempts=attempts, violations=[])
    tz = _infer_tz(plan_nights[0])
    text = "\n".join(_template_brief(plan_nights, tz))
    return BriefResult(text=text, source="template", attempts=attempts,
                       violations=[])


def generate_brief(
    plan_nights: list[Night],
    site_name: str,
    llm: "LLMCfg",
    offline: bool = False,
    tz: ZoneInfo | None = None,
    messages: list[dict] | None = None,
) -> BriefResult:
    """Offline: labeled template immediately (no LLM call, attempts 0).

    Online: one POST to {base_url}/chat/completions with a single retry on
    transport error. Success -> BriefResult(source="llm", attempts=1).
    Any failure -> labeled template; failures log the exception class only
    (never the URL, never the API key)."""
    if offline or not plan_nights:
        return _template_result(plan_nights, attempts=0)

    # T19 verifier passes pre-built messages (original prompt + follow-up
    # user message with violations + allowed values); default builds fresh.
    messages = messages or build_prompt(plan_nights, site_name, tz)
    body = json.dumps({
        "model": llm.model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 400,
    }).encode("utf-8")
    url = llm.base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if llm.api_key:
        headers["Authorization"] = f"Bearer {llm.api_key}"

    attempts = 0
    last_exc: Exception | None = None
    for _ in range(2):  # one try + one transport retry
        attempts += 1
        req = urllib.request.Request(url, data=body, headers=headers,
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=llm.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            return BriefResult(text=content, source="llm", attempts=1,
                               violations=[])
        except (urllib.error.URLError, urllib.error.HTTPError, OSError,
                KeyError, IndexError, ValueError, TypeError) as exc:
            last_exc = exc
            logger.warning("LLM brief failed: %s", type(exc).__name__)

    del last_exc  # class already logged; details must never leak URL/key
    return _template_result(plan_nights, attempts=attempts)
