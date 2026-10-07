"""Meteor shower table load + per-night events (ARCHITECTURE.md §4).

The shower table is committed data derived from the IMO 2026 Meteor Shower
Calendar; see ``data/meteor_showers_2026.json`` for the source URL. No network.

``events_for_night`` keeps this module testable without the ephemeris: the
plan pipeline (T14) passes a closure over ``sky.radiant_up_hours`` as
``radiant_up_hours_fn``.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .models import ShowerEvent

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TABLE = _REPO_ROOT / "data" / "meteor_showers_2026.json"

_REQUIRED_KEYS = (
    "name",
    "peak_utc",
    "active_start",
    "active_end",
    "zhr",
    "radiant_ra_deg",
    "radiant_dec_deg",
    "parent",
)


class MeteorDataError(Exception):
    """Shower table is unreadable or malformed."""


def _parse_mmdd(mmdd: str, year: int, name: str) -> dt.datetime:
    """Parse 'MM-DD' into a UTC datetime at 00:00 on that date in `year`."""
    try:
        month, day = (int(p) for p in mmdd.split("-"))
        if month < 1 or month > 12 or day < 1 or day > 31:
            raise ValueError
    except (ValueError, AttributeError):
        raise MeteorDataError(f"shower {name!r}: bad MM-DD field {mmdd!r}") from None
    try:
        return dt.datetime(year, month, day, tzinfo=dt.timezone.utc)
    except ValueError:
        raise MeteorDataError(f"shower {name!r}: invalid date {mmdd!r}") from None


def _record_to_event(rec: dict, year: int) -> ShowerEvent:
    missing = [k for k in _REQUIRED_KEYS if k not in rec]
    if missing:
        raise MeteorDataError(f"shower record missing keys: {', '.join(missing)}")
    name = rec["name"]
    try:
        peak = dt.datetime.fromisoformat(rec["peak_utc"].replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise MeteorDataError(f"shower {name!r}: bad peak_utc {rec['peak_utc']!r}") from None
    if peak.tzinfo is None:
        peak = peak.replace(tzinfo=dt.timezone.utc)
    start = _parse_mmdd(rec["active_start"], peak.year, name)
    end = _parse_mmdd(rec["active_end"], peak.year, name)
    # Year wrap: each boundary lands on the side of the peak it belongs to.
    if start > peak:
        start = start.replace(year=start.year - 1)  # e.g. Quadrantids 12-28
    if end < peak:
        end = end.replace(year=end.year + 1)        # window crossing Dec 31
    return ShowerEvent(
        name=name,
        peak_utc=peak,
        active_start=start,
        active_end=end,
        zhr=rec["zhr"],
        radiant_ra_deg=rec["radiant_ra_deg"],
        radiant_dec_deg=rec["radiant_dec_deg"],
        parent_body=rec["parent"],
    )


def load_showers(path: Path | str | None = None) -> list[ShowerEvent]:
    """Load the shower table. Per-night fields are left at defaults."""
    table = Path(path) if path is not None else DEFAULT_TABLE
    try:
        raw = table.read_text(encoding="utf-8")
    except OSError as exc:
        raise MeteorDataError(f"cannot read shower table {table}: {exc}") from None
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MeteorDataError(f"shower table {table} is not valid JSON: {exc}") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("showers"), list):
        raise MeteorDataError(f"shower table {table}: expected {{'showers': [...]}}")
    return [_record_to_event(rec, doc.get("year", 2026)) for rec in doc["showers"]]


def _active_on(event: ShowerEvent, night_date: dt.date) -> bool:
    """Is the shower active on the local `night_date` (start/end inclusive)?"""
    start = event.active_start.date()
    end = event.active_end.date()
    if start <= end:
        return start <= night_date <= end
    return night_date >= start or night_date <= end  # wraps Dec 31


def events_for_night(
    showers: list[ShowerEvent],
    night_date: dt.date,
    radiant_up_hours_fn=None,
) -> list[ShowerEvent]:
    """Return showers active on `night_date`, with peak and radiant flags filled.

    `radiant_up_hours_fn(ra_deg, dec_deg) -> float` is supplied by the caller
    (T14 passes a closure over sky.radiant_up_hours); when absent the field
    stays at its loaded value.
    """
    out: list[ShowerEvent] = []
    for ev in showers:
        if not _active_on(ev, night_date):
            continue
        is_peak = abs((ev.peak_utc.date() - night_date).days) <= 1
        up_hours = ev.radiant_up_hours
        if radiant_up_hours_fn is not None:
            up_hours = radiant_up_hours_fn(ev.radiant_ra_deg, ev.radiant_dec_deg)
        out.append(ShowerEvent(
            name=ev.name,
            peak_utc=ev.peak_utc,
            active_start=ev.active_start,
            active_end=ev.active_end,
            zhr=ev.zhr,
            radiant_ra_deg=ev.radiant_ra_deg,
            radiant_dec_deg=ev.radiant_dec_deg,
            parent_body=ev.parent_body,
            radiant_up_hours=up_hours,
            is_peak_night=is_peak,
        ))
    return out
