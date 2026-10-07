"""Claim extraction, verification, and the retry/fallback loop (T19,
ARCHITECTURE §6). This is the post's core AI story: every time, number,
name, and direction in an LLM brief is checked against the computed night
data before it is allowed through; anything unverifiable triggers a
re-prompt with the exact allowed values, and ultimately the labeled
template brief.

`extract_claims` and `check_claims` are pure functions over text + Night
objects — no IO, no network — so they are testable standalone.
`verified_brief` drives the loop: offline -> template immediately; else
generate, extract, check, re-prompt with violations + allowed values up to
`max_retries` extra attempts, then the labeled template.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from clearnight.brief import (
    _infer_tz,
    _mean,
    _template_result,
    build_prompt,
    generate_brief,
)
from clearnight.models import Night

VERDICT_BANDS = ("PRIME", "WORTH IT", "Marginal", "Poor", "STAY IN BED")

# Words that commonly begin sentences or name everyday sky things; they are
# NOT named events, so a capitalized occurrence alone is not a claim.
_COMMON_WORDS = frozenset("""
the a an and or but if it its this that these those you your when where
while with for from at on in to of by as is are was were be been
tonight today tomorrow tomorrow's tonight's
moon sun moonrise moonset sunrise sunset sky clouds cloud wind winds rain
look face watch expect bring dress note best skip plan planned
conditions seeing dew visibility pressure forecast dark window score
verdict zhr meteor meteors shower showers pass passes site park state
go out near over under above below high low clear
monday tuesday wednesday thursday friday saturday sunday
north northeast east southeast south southwest west northwest
straight overhead
""".split())

_TIME_RE = re.compile(
    r"\b(\d{1,2}):(\d{2})(?:\s*([ap])\.?m\.?)?", re.IGNORECASE)
_NUM_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(°C|celsius|km/h|kph|kmh|%|percent|degrees?|°)?",
    re.IGNORECASE)
_MULTI_NAME_RE = re.compile(r"\b([A-Z][a-zA-Z']+(?:\s+[A-Z][a-zA-Z']+)+)\b")
_SINGLE_NAME_RE = re.compile(r"\b([A-Z][a-zA-Z']+)\b")
_DAY_RE = re.compile(
    r"\b(tonight|today|tomorrow|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday)\b", re.IGNORECASE)
_SPELL_DIR_RE = re.compile(
    r"\b(north(?:east|west)?|south(?:east|west)?|east|west)\b",
    re.IGNORECASE)
_ABBR_DIR_RE = re.compile(
    r"\b(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW)\b")
_OVERHEAD_RE = re.compile(r"\b(overhead|straight up|up)\b", re.IGNORECASE)

_DIR_TO_ABBR = {
    "north": "N", "northeast": "NE", "east": "E", "southeast": "SE",
    "south": "S", "southwest": "SW", "west": "W", "northwest": "NW",
    "nne": "NNE", "ene": "ENE", "ese": "ESE", "sse": "SSE",
    "ssw": "SSW", "wnw": "WNW", "nnw": "NNW",
}


@dataclass(frozen=True)
class NumberClaim:
    value: float
    unit: str  # "percent" | "degrees" | "kmh" | "celsius" | "count" | ""
    raw: str


@dataclass(frozen=True)
class Claims:
    times: tuple  # tuple[(minutes_24h: int, raw: str)]
    numbers: tuple  # tuple[NumberClaim]
    names: tuple  # tuple[str]
    directions: tuple  # tuple[str]  (abbreviations; "OVERHEAD" special)
    day_words: tuple  # tuple[str], lowercased


def _time_minutes(h: int, mi: int, ampm: str | None) -> int:
    if ampm:
        ampm = ampm.lower()
        h = h % 12 + (12 if ampm == "p" else 0)
    return h * 60 + mi


def extract_claims(text: str) -> Claims:
    """Pull every checkable claim out of brief prose (pure function)."""
    times: list[tuple[int, str]] = []
    for m in _TIME_RE.finditer(text):
        times.append((_time_minutes(int(m.group(1)), int(m.group(2)),
                                    m.group(3)), m.group(0).strip()))
    # Strip matched times so their digits are not re-counted as numbers.
    without_times = _TIME_RE.sub(" ", text)

    numbers: list[NumberClaim] = []
    for m in _NUM_RE.finditer(without_times):
        unit = (m.group(2) or "").lower()
        if unit in ("%", "percent"):
            kind = "percent"
        elif unit in ("km/h", "kph", "kmh"):
            kind = "kmh"
        elif unit in ("°c", "celsius"):
            kind = "celsius"
        elif unit in ("degrees", "degree", "°"):
            kind = "degrees"
        else:
            kind = ""  # bare: percent-then-count at check time
        numbers.append(NumberClaim(float(m.group(1)), kind, m.group(0).strip()))

    names: list[str] = []
    spans = [m.span() for m in _MULTI_NAME_RE.finditer(text)]
    for m in _MULTI_NAME_RE.finditer(text):
        names.append(m.group(1))
    for m in _SINGLE_NAME_RE.finditer(text):
        if any(s <= m.start(1) and m.end(1) <= e for s, e in spans):
            continue  # already part of a matched multiword name
        if m.group(1).lower() not in _COMMON_WORDS:
            names.append(m.group(1))

    directions: set[str] = set()
    for m in _SPELL_DIR_RE.finditer(text):
        directions.add(_DIR_TO_ABBR[m.group(1).lower()])
    for m in _ABBR_DIR_RE.finditer(text):
        directions.add(m.group(1))
    if _OVERHEAD_RE.search(text):
        directions.add("OVERHEAD")

    day_words = tuple(dict.fromkeys(m.group(1).lower()
                                    for m in _DAY_RE.finditer(text)))
    return Claims(tuple(times), tuple(numbers), tuple(names),
                  tuple(sorted(directions)), day_words)


def _event_minutes(nights: list[Night], tz: dt.tzinfo) -> set[int]:
    """Minutes-of-day (site-local) of every computed event time."""
    out: set[int] = set()

    def add(when: dt.datetime | None) -> None:
        if when is not None:
            local = when.astimezone(tz)
            out.add(local.hour * 60 + local.minute)

    for n in nights:
        add(n.dark.start_utc)
        add(n.dark.end_utc)
        add(n.moon.rise_utc)
        add(n.moon.set_utc)
        for p in n.iss_passes:
            add(p.start_utc)
            add(p.max_utc)
            add(p.end_utc)
        for sh in n.showers:
            add(sh.peak_utc)
    return out


def _computed_values(nights: list[Night]) -> dict:
    """All numeric/name/direction values the brief is allowed to state."""
    percents: set[float] = set()
    degrees: set[float] = set()
    kmh: set[float] = set()
    celsius: set[float] = set()
    counts: set[int] = set()
    names: set[str] = set()
    dirs: set[str] = set()
    dates: set[dt.date] = set()
    weekdays: set[str] = set()
    for n in nights:
        percents.add(float(round(_mean([w.cloud_total_pct for w in n.weather]))))
        percents.add(float(round(_mean([w.rh_pct for w in n.weather]))))
        percents.add(round(n.moon.illumination_frac * 100))
        if n.score is not None:
            percents.add(float(n.score.total))
            names.add(n.score.verdict)
        degrees.add(round(n.moon.max_alt_deg))
        for p in n.iss_passes:
            degrees.add(round(p.max_alt_deg))
            dirs.update((p.start_dir, p.max_dir, p.end_dir))
        kmh.add(round(_mean([w.wind_kmh for w in n.weather]), 1))
        temps = [w.temperature_c for w in n.weather if w.temperature_c is not None]
        if temps:
            celsius.add(round(_mean(temps), 1))
        celsius.add(round(float(n.conditions.dew_spread_c), 1))
        for sh in n.showers:
            counts.add(round(sh.zhr))
            names.add(sh.name)
        names.add(n.moon.phase_name)
        dates.add(n.date_local)
        weekdays.add(n.date_local.strftime("%A"))
    return {"percent": percents, "degrees": degrees, "kmh": kmh,
            "celsius": celsius, "count": counts, "names": names,
            "dirs": dirs, "dates": dates, "weekdays": weekdays}


def _within(value: float, allowed: set[float], tol: float = 1.0) -> bool:
    return any(abs(value - a) <= tol + 1e-9 for a in allowed)


def _fmt_times(minutes: set[int]) -> str:
    return ", ".join(f"{m // 60:02d}:{m % 60:02d}" for m in sorted(minutes))


def _fmt_list(vals) -> str:
    return ", ".join(str(v) for v in sorted(vals))


def allowed_digest(nights: list[Night], site_name: str,
                   tz: dt.tzinfo | None = None) -> str:
    """Exact allowed values, for the re-prompt follow-up message."""
    tz = tz or _infer_tz(nights[0])
    v = _computed_values(nights)
    names = set(v["names"]) | {"ISS", "International Space Station", site_name}
    return (
        f"site: {site_name}\n"
        f"event times (site-local 24h): {_fmt_times(_event_minutes(nights, tz))}\n"
        f"percents: {_fmt_list(sorted(v['percent']))}\n"
        f"altitudes (deg): {_fmt_list(sorted(v['degrees']))}\n"
        f"wind (km/h): {_fmt_list(sorted(v['kmh']))}\n"
        f"temps (C): {_fmt_list(sorted(v['celsius']))}\n"
        f"citable counts (ZHR only): {_fmt_list(sorted(v['count']))}\n"
        f"allowed names: {_fmt_list(sorted(names))}\n"
        f"ISS pass directions: {_fmt_list(sorted(v['dirs']))}\n"
        f"night dates: {', '.join(d.isoformat() for d in sorted(v['dates']))}"
        f" ({', '.join(sorted(v['weekdays']))})"
    )


_DIR_NAMES = {v: k for k, v in _DIR_TO_ABBR.items()}


def check_claims(claims: Claims, nights: list[Night], site_name: str,
                 tz: dt.tzinfo | None = None) -> list[str]:
    """One human-readable line per violation, naming the claim and the
    allowed values (pure function)."""
    tz = tz or _infer_tz(nights[0])
    v = _computed_values(nights)
    out: list[str] = []

    event_times = _event_minutes(nights, tz)
    for minutes, raw in claims.times:
        if not any(abs(minutes - a) <= 1 for a in event_times):
            out.append(f"time '{raw}' is not within 1 minute of any computed "
                       f"event time; allowed: {_fmt_times(event_times)} "
                       "(site-local)")

    for num in claims.numbers:
        kind = num.unit
        if kind == "":  # bare number: percent context first, then count
            kind = ("percent" if _within(num.value, v["percent"])
                    else "count")
        if kind == "percent":
            if not _within(num.value, v["percent"]):
                out.append(f"'{num.raw}' does not match a computed percent "
                           f"(±1); allowed: {_fmt_list(sorted(v['percent']))}")
        elif kind == "degrees":
            if not _within(num.value, v["degrees"]):
                out.append(f"'{num.raw}' does not match a computed altitude "
                           f"(±1); allowed: {_fmt_list(sorted(v['degrees']))}")
        elif kind == "kmh":
            if not _within(num.value, v["kmh"]):
                out.append(f"'{num.raw}' does not match the computed wind "
                           f"(±1); allowed: {_fmt_list(sorted(v['kmh']))}")
        elif kind == "celsius":
            if not _within(num.value, v["celsius"]):
                out.append(f"'{num.raw}' does not match a computed "
                           f"temperature aggregate (±1); allowed: "
                           f"{_fmt_list(sorted(v['celsius']))}")
        else:  # count: the ONLY citable count is a quoted ZHR
            if int(num.value) not in v["count"]:
                out.append(
                    f"'{num.raw}' is a promise of visible meteors, which the "
                    "data cannot support; the only citable count is a "
                    f"shower's quoted ZHR; allowed ZHR: "
                    f"{_fmt_list(sorted(v['count']))}")

    allowed_names = (set(v["names"])
                     | {"ISS", "International Space Station", site_name})
    lowered = {n.lower() for n in allowed_names}
    for name in claims.names:
        # Ignore common-word padding (e.g. "The Waxing Crescent" -> the
        # phase name itself) and tokens made entirely of common words.
        parts = [p for p in name.split() if p.lower() not in _COMMON_WORDS]
        if not parts or " ".join(parts).lower() in lowered \
                or name.lower() in lowered:
            continue
        out.append(f"name '{name}' is not in the allowed set; allowed names: "
                   f"{_fmt_list(sorted(allowed_names))}")

    max_alt = max((p.max_alt_deg for n in nights for p in n.iss_passes),
                  default=0.0)
    for d in claims.directions:
        if d == "OVERHEAD":
            if max_alt < 60.0:
                out.append(f"'overhead'/'up' claimed but no ISS pass reaches "
                           f"60 deg; highest computed pass: {round(max_alt)} deg")
        elif d not in v["dirs"]:
            out.append(f"direction '{_DIR_NAMES.get(d, d)}' does not match "
                       f"any ISS pass "
                       f"direction that night; allowed: "
                       f"{_fmt_list(sorted(v['dirs']))}")

    for word in claims.day_words:
        if word in ("tonight", "today"):
            continue  # first night is always in the plan
        if word == "tomorrow":
            want = nights[0].date_local + dt.timedelta(days=1)
            if want not in v["dates"]:
                out.append(f"'tomorrow' would be {want.isoformat()}, which is "
                           f"not a planned night; planned dates: "
                           f"{', '.join(d.isoformat() for d in sorted(v['dates']))}")
        else:
            weekday = word.capitalize()
            if weekday not in v["weekdays"]:
                out.append(f"'{word}' does not match any planned night's "
                           f"weekday; planned: {_fmt_list(sorted(v['weekdays']))}")
    return out


def verified_brief(
    nights: list[Night],
    site_name: str,
    llm,
    tz: dt.tzinfo | None = None,
    offline: bool = False,
    max_retries: int = 2,
):
    """Generate, verify, re-prompt with violations + exact allowed values,
    and fall back to the labeled template brief (A6/A7).

    Offline (or empty plan): template immediately, attempts 0, no LLM call.
    Each iteration calls generate_brief; a template result (LLM failed)
    short-circuits. On violations the messages grow by a follow-up user
    message listing them plus the exact allowed values. After the budget
    is exhausted: labeled template with attempts and remaining violations.
    """
    if offline or not nights:
        return _template_result(nights, attempts=0)

    messages = build_prompt(nights, site_name, tz)
    attempts = 0
    violations: list[str] = []
    for _ in range(max_retries + 1):
        result = generate_brief(nights, site_name, llm, tz=tz,
                                messages=messages)
        attempts += result.attempts
        if result.source == "template":
            return type(result)(text=result.text, source="template",
                                attempts=attempts, violations=violations)
        claims = extract_claims(result.text)
        violations = check_claims(claims, nights, site_name, tz)
        if not violations:
            return type(result)(text=result.text, source="llm",
                                attempts=attempts, violations=[])
        followup = (
            "Your previous brief contained claims that are not in the data:\n"
            + "\n".join(f"- {v}" for v in violations)
            + "\nRewrite the brief using ONLY these exact allowed values:\n"
            + allowed_digest(nights, site_name, tz))
        messages = messages + [{"role": "user", "content": followup}]

    template = _template_result(nights, attempts=attempts)
    return type(template)(text=template.text, source="template",
                          attempts=attempts, violations=violations)
