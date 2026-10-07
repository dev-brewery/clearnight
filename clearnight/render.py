"""Plan renderers: red-on-black HTML + <=80-col text (T15, ARCHITECTURE §4).

`Plan` is the small render-input structure extracted from the T14 pipeline:
site, mode label, reference-date label, and the ranked night list. Renderers
are pure functions Plan -> str; no I/O here.

HTML contract: ONE self-contained file — inline CSS only, zero external
requests, no JS required for readability. Dark background (#000), red-spectrum
text (#ff3b30 family), large type for phone-in-the-dark use, print CSS. All
data-driven strings are HTML-escaped; provenance names appear as plain text
(no links).

Text contract: every line <= 80 columns including the template label — the
103-char A7 label wording is wrapped across two lines (exact wording wins,
wrapping allowed, never truncated).
"""

from __future__ import annotations

import datetime as dt
import html
import textwrap
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from clearnight.config import Site
from clearnight.models import FieldLogEntry, Night

TEMPLATE_BRIEF_LABEL = (
    "Template brief (LLM output unavailable or failed verification; "
    "all values are computed, not generated)."
)

VERDICTS = ("PRIME", "WORTH IT", "Marginal", "Poor", "STAY IN BED")


@dataclass(frozen=True)
class Plan:
    """Render input: what the T14 pipeline hands to the renderers."""

    site: Site
    mode: str            # e.g. "OFFLINE fixture epoch" / "ONLINE live"
    reference_label: str  # e.g. "2026-10-07"
    ranked: list[Night]
    notes: tuple[str, ...] = ()  # provenance/staleness footer lines
    field_log: dict = field(default_factory=dict)  # date_local -> FieldLogEntry
    # T20: the verified brief stage fills these; empty -> template fallback.
    brief_lines: tuple[str, ...] = ()  # pre-wrapped brief body (label first
    # when template); LLM text, or the labeled template lines
    brief_note: str = ""  # provenance line, e.g. "brief: local model, ..."


def _to_local(when: dt.datetime | None, tz: ZoneInfo) -> dt.datetime | None:
    if when is None:
        return None
    return when.astimezone(tz)


def _fmt_hms(when: dt.datetime) -> str:
    return when.strftime("%H:%M")


def _cloud_mean(night: Night) -> float | None:
    vals = [w.cloud_total_pct for w in night.weather
            if w.cloud_total_pct is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _breakdown_lines(score) -> list[str]:
    return [
        f"total {score.total} {score.verdict} | base {score.base:.1f}",
        f"cloud {score.cloud_term:.2f} moon {score.moon_term:.2f} "
        f"trans {score.transparency_term:.2f} dew {score.dew_term:.2f} "
        f"wind {score.wind_term:.2f}",
        f"meteor_bonus {score.meteor_bonus} iss_bonus {score.iss_bonus}",
    ]


def _shower_lines(night: Night) -> list[str]:
    if not night.showers:
        return ["showers: none active"]
    lines = []
    for s in night.showers:
        mark = " PEAK" if s.is_peak_night else ""
        lines.append(
            f"shower: {s.name} ZHR {s.zhr:g} radiant up {s.radiant_up_hours:.1f}h{mark}"
        )
    return lines


def _iss_lines(night: Night, tz: ZoneInfo) -> list[str]:
    if not night.iss_passes:
        return ["iss: no visible passes"]
    lines = []
    for p in night.iss_passes:
        s = _to_local(p.start_utc, tz)
        m = _to_local(p.max_utc, tz)
        e = _to_local(p.end_utc, tz)
        lines.append(
            f"iss: {_fmt_hms(s)}-{_fmt_hms(e)} max {_fmt_hms(m)} "
            f"{p.max_alt_deg:.0f}deg {p.start_dir}>{p.max_dir}>{p.end_dir}"
        )
    return lines


def _moon_line(night: Night, tz: ZoneInfo) -> str:
    moon = night.moon
    rise = _to_local(moon.rise_utc, tz)
    set_ = _to_local(moon.set_utc, tz)
    rs = (
        f"rise {_fmt_hms(rise) if rise else '-'} "
        f"set {_fmt_hms(set_) if set_ else '-'}"
    )
    return (
        f"moon: {moon.phase_name} illum {moon.illumination_frac * 100:.0f}% {rs}"
    )


def _night_block(night: Night, tz: ZoneInfo) -> list[str]:
    ws = _to_local(night.dark.start_utc, tz)
    we = _to_local(night.dark.end_utc, tz)
    cloud = _cloud_mean(night)
    lines = [f"night {night.date_local.isoformat()}"]
    lines.extend("  " + l for l in _breakdown_lines(night.score))
    lines.extend([
        f"  dark window (local): {_fmt_hms(ws)}-{_fmt_hms(we)}",
        "  " + _moon_line(night, tz),
        f"  clouds: mean {cloud if cloud is not None else 'n/a'}%"
        f" | dew risk: {night.conditions.dew_risk}"
        f" (spread {night.conditions.dew_spread_c:.1f}C)",
    ])
    if night.score.reasons:
        lines.append("  notes: " + ", ".join(night.score.reasons))
    lines.extend("  " + l for l in _shower_lines(night))
    lines.extend("  " + l for l in _iss_lines(night, tz))
    return lines


def _fieldlog_lines(entry: FieldLogEntry) -> list[str]:
    """The FIELD LOG block lines (without the 'FIELD LOG:' header)."""
    return [
        f"went out: {'yes' if entry.went_out else 'no'}"
        f" | clearness {entry.clearness}/5"
        f" | meteors counted: {entry.meteors_counted}"
        f" | ISS seen: {'yes' if entry.iss_seen else 'no'}",
        f"notes: {entry.notes}" if entry.notes else "notes: (none)",
        f"recorded-at: {entry.recorded_utc.isoformat()}",
    ]


def _wrap78(text: str) -> list[str]:
    return textwrap.wrap(text, width=78, subsequent_indent="  ",
                         break_long_words=False, break_on_hyphens=False)


def _wrapped_label() -> list[str]:
    """The 103-char A7 label, wrapped across two lines, wording intact."""
    return _wrap78(TEMPLATE_BRIEF_LABEL)


def _plan_brief_lines(plan: Plan) -> list[str]:
    """The TONIGHT'S BRIEF body: the verified brief stage's lines, or the
    template fallback for plans built before T20."""
    if plan.brief_lines:
        return list(plan.brief_lines)
    return _template_brief(plan.ranked, ZoneInfo(plan.site.tz_name))


def _template_brief(ranked: list[Night], tz: ZoneInfo) -> list[str]:
    """Template brief from computed data only (LLM lands T18/T20)."""
    lines = _wrapped_label()
    for night in ranked[:3]:
        ws = _to_local(night.dark.start_utc, tz)
        we = _to_local(night.dark.end_utc, tz)
        when = f"go {_fmt_hms(ws)}-{_fmt_hms(we)} local"
        peaks = [s.name for s in night.showers if s.is_peak_night]
        active = [s.name for s in night.showers if not s.is_peak_night]
        look: list[str] = []
        if peaks:
            look.append(f"{', '.join(peaks)} PEAK")
        if active:
            look.append(f"{', '.join(active)} active")
        if night.iss_passes:
            look.append(f"{len(night.iss_passes)} ISS pass(es)")
        if night.moon.illumination_frac * night.moon.up_fraction < 0.1:
            look.append("dark moon")
        line = (
            f"- {night.date_local.isoformat()} (score {night.score.total} "
            f"{night.score.verdict}): {when}; look for "
            + ("; ".join(look) if look else "deep-sky under dark skies")
            + "."
        )
        lines.extend(_wrap78(line))
    return lines


# ---------------------------------------------------------------- text -----


def render_text(plan: Plan) -> str:
    """Full plan as text, every line <= 80 columns."""
    cfg_site = plan.site
    tz = ZoneInfo(cfg_site.tz_name)
    lines: list[str] = []
    lines.append(f"stargazing plan - {cfg_site.name} ({plan.mode})")
    lines.append(
        f"site {cfg_site.lat:.2f}, {cfg_site.lon:.2f} | "
        f"{len(plan.ranked)} nights, ranked | reference {plan.reference_label}"
    )
    lines.append("")
    for night in plan.ranked:
        lines.extend(_night_block(night, tz))
        entry = plan.field_log.get(night.date_local)
        if entry is not None:
            lines.append("  FIELD LOG:")
            lines.extend("    " + l for l in _fieldlog_lines(entry))
        lines.append("")
    lines.append("TONIGHT'S BRIEF")
    lines.extend(_plan_brief_lines(plan))
    if plan.brief_note:
        lines.append(plan.brief_note)
    lines.append("")
    for row in _wrap78(
        "data: committed fixtures (Open-Meteo, CelesTrak, NASA JPL de421); "
        f"generated for reference date {plan.reference_label} ({plan.mode})"
    ):
        lines.append(row)
    for note in plan.notes:
        lines.extend(_wrap78("- " + note))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- html -----


_CSS = """\
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  background: #000;
  color: #ff3b30;
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 1.25rem;
  line-height: 1.5;
  margin: 0 auto;
  max-width: 42rem;
  padding: 1rem;
}
h1 { font-size: 1.9rem; }
h2 { font-size: 1.6rem; border-bottom: 2px solid #ff3b30; }
.verdict { font-weight: 700; }
dl dt { font-weight: 700; margin-top: 0.5rem; }
dl dd { margin: 0 0 0.25rem 1rem; }
footer { font-size: 1rem; margin-top: 2rem; border-top: 1px solid #ff3b30; }
@media print {
  body { background: #fff; color: #000; font-size: 10pt; max-width: none; }
  h2 { border-color: #000; page-break-after: avoid; }
  section { page-break-inside: avoid; }
  footer { border-color: #000; }
}
"""


def render_html(plan: Plan) -> str:
    """One self-contained red-on-black HTML page, no external requests."""
    esc = html.escape
    tz = ZoneInfo(plan.site.tz_name)
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>clearnight plan</title>",
        f"<style>{_CSS}</style></head><body>",
        f"<h1>Stargazing plan - {esc(plan.site.name)} ({esc(plan.mode)})</h1>",
        f"<p>site {esc(f'{plan.site.lat:.2f}')}, "
        f"{esc(f'{plan.site.lon:.2f}')}"
        f" | reference date {esc(plan.reference_label)}"
        f" | {len(plan.ranked)} nights, ranked</p>",
        "<p>verdict legend: " + " / ".join(esc(v) for v in VERDICTS) + "</p>",
    ]
    for night in plan.ranked:
        cloud = _cloud_mean(night)
        parts.append("<section>")
        parts.append(
            f"<h2>Night {esc(night.date_local.isoformat())} - "
            f"TOTAL {night.score.total} - "
            f'<span class="verdict">{esc(night.score.verdict)}</span></h2>'
        )
        parts.append("<dl>")
        parts.append("<dt>score breakdown</dt>")
        for line in _breakdown_lines(night.score):
            parts.append(f"<dd>{esc(line)}</dd>")
        ws = _to_local(night.dark.start_utc, tz)
        we = _to_local(night.dark.end_utc, tz)
        parts.append(
            f"<dt>dark window (local)</dt><dd>{esc(_fmt_hms(ws))}-"
            f"{esc(_fmt_hms(we))}</dd>"
        )
        parts.append(f"<dt>moon</dt><dd>{esc(_moon_line(night, tz))}</dd>")
        parts.append(
            "<dt>clouds</dt><dd>mean "
            f"{esc('n/a' if cloud is None else f'{cloud}%')} | dew risk: "
            f"{esc(night.conditions.dew_risk)} (spread "
            f"{esc(f'{night.conditions.dew_spread_c:.1f}C')})</dd>"
        )
        if night.score.reasons:
            parts.append(
                "<dt>notes</dt><dd>"
                + esc(", ".join(night.score.reasons)) + "</dd>"
            )
        for line in _shower_lines(night):
            parts.append(f"<dd>{esc(line)}</dd>")
        for line in _iss_lines(night, tz):
            parts.append(f"<dd>{esc(line)}</dd>")
        parts.append("</dl>")
        entry = plan.field_log.get(night.date_local)
        if entry is not None:
            parts.append('<p class="fieldlog">FIELD LOG:</p><ul>')
            for line in _fieldlog_lines(entry):
                parts.append(f"<li>{esc(line)}</li>")
            parts.append("</ul>")
        parts.append("</section>")
    parts.append("<h2>TONIGHT'S BRIEF</h2>")
    brief = _plan_brief_lines(plan)
    # Template source: render the exact A7 label as one contiguous paragraph,
    # the bullet lines as the list. LLM source: the whole text as the list.
    body = brief
    if brief and brief[0].startswith("Template brief ("):
        acc, k = "", 0
        while acc != TEMPLATE_BRIEF_LABEL and k < len(brief):
            acc = (acc + " " + brief[k].strip()).strip()
            k += 1
        if acc == TEMPLATE_BRIEF_LABEL:
            parts.append(f"<p>{esc(acc)}</p>")
            body = brief[k:]
    parts.append("<ul>")
    for line in body:
        parts.append(f"<li>{esc(line)}</li>")
    parts.append("</ul>")
    if plan.brief_note:
        parts.append(f"<p>{esc(plan.brief_note)}</p>")
    parts.append(
        "<footer>Data provenance: committed demo fixtures (Open-Meteo "
        "forecast, CelesTrak TLE, NASA JPL de421.bsp). Generated for pinned "
        f"reference date {esc(plan.reference_label)}. Mode: "
        f"{esc(plan.mode)}.</footer>"
    )
    if plan.notes:
        parts.append("<footer>" + "<br>".join(esc(n) for n in plan.notes)
                     + "</footer>")
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"
