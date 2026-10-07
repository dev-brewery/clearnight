"""All clearnight dataclasses (ARCHITECTURE.md §4).

Every model is a frozen dataclass. Datetimes stored in UTC must be
timezone-aware; a naive datetime on a required UTC field raises TypeError
at construction. Required fields are type-checked with a small helper —
intentionally lightweight, not a validation framework.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal


def _check(
    obj: object,
    types: type | tuple[type, ...],
    name: str,
    *,
    allow_none: bool = False,
) -> None:
    """Raise TypeError if obj is not of `types` (or None when allowed)."""
    if obj is None and allow_none:
        return
    if obj is None or not isinstance(obj, types):
        wanted = (
            types.__name__ if isinstance(types, type) else " | ".join(t.__name__ for t in types)
        )
        got = "None" if obj is None else type(obj).__name__
        raise TypeError(
            f"{name}: expected {wanted}, got {got}"
            + (" (naive datetime not allowed for a UTC field)" if isinstance(obj, dt.datetime) and obj.tzinfo is None else "")
        )


def _check_utc(value: object, name: str, *, allow_none: bool = False) -> None:
    _check(value, dt.datetime, name, allow_none=allow_none)
    if isinstance(value, dt.datetime) and value.tzinfo is None:
        raise TypeError(f"{name}: naive datetime not allowed for a UTC field")


@dataclass(frozen=True)
class Site:
    name: str
    lat: float
    lon: float
    elevation_m: float
    tz_name: str

    def __post_init__(self) -> None:
        _check(self.name, str, "Site.name")
        _check(self.lat, (int, float), "Site.lat")
        _check(self.lon, (int, float), "Site.lon")
        _check(self.elevation_m, (int, float), "Site.elevation_m")
        _check(self.tz_name, str, "Site.tz_name")


@dataclass(frozen=True)
class HourWeather:
    time_utc: dt.datetime
    cloud_total_pct: float | None = None
    cloud_low_pct: float | None = None
    cloud_mid_pct: float | None = None
    cloud_high_pct: float | None = None
    rh_pct: float | None = None
    dew_point_c: float | None = None
    temperature_c: float | None = None
    visibility_m: float | None = None
    wind_kmh: float | None = None

    def __post_init__(self) -> None:
        _check_utc(self.time_utc, "HourWeather.time_utc")
        for name in (
            "cloud_total_pct", "cloud_low_pct", "cloud_mid_pct", "cloud_high_pct",
            "rh_pct", "dew_point_c", "temperature_c", "visibility_m", "wind_kmh",
        ):
            _check(getattr(self, name), (int, float), f"HourWeather.{name}", allow_none=True)


@dataclass(frozen=True)
class DarkWindow:
    start_utc: dt.datetime
    end_utc: dt.datetime

    def __post_init__(self) -> None:
        _check_utc(self.start_utc, "DarkWindow.start_utc")
        _check_utc(self.end_utc, "DarkWindow.end_utc")


@dataclass(frozen=True)
class MoonInfo:
    phase_name: str
    illumination_frac: float
    rise_utc: dt.datetime | None
    set_utc: dt.datetime | None
    up_fraction: float
    max_alt_deg: float

    def __post_init__(self) -> None:
        _check(self.phase_name, str, "MoonInfo.phase_name")
        _check(self.illumination_frac, (int, float), "MoonInfo.illumination_frac")
        _check_utc(self.rise_utc, "MoonInfo.rise_utc", allow_none=True)
        _check_utc(self.set_utc, "MoonInfo.set_utc", allow_none=True)
        _check(self.up_fraction, (int, float), "MoonInfo.up_fraction")
        _check(self.max_alt_deg, (int, float), "MoonInfo.max_alt_deg")


@dataclass(frozen=True)
class ShowerEvent:
    name: str
    peak_utc: dt.datetime
    active_start: dt.datetime
    active_end: dt.datetime
    zhr: float
    radiant_ra_deg: float
    radiant_dec_deg: float
    parent_body: str
    radiant_up_hours: float = 0.0
    is_peak_night: bool = False

    def __post_init__(self) -> None:
        _check(self.name, str, "ShowerEvent.name")
        _check_utc(self.peak_utc, "ShowerEvent.peak_utc")
        _check_utc(self.active_start, "ShowerEvent.active_start")
        _check_utc(self.active_end, "ShowerEvent.active_end")
        _check(self.zhr, (int, float), "ShowerEvent.zhr")
        _check(self.radiant_ra_deg, (int, float), "ShowerEvent.radiant_ra_deg")
        _check(self.radiant_dec_deg, (int, float), "ShowerEvent.radiant_dec_deg")
        _check(self.parent_body, str, "ShowerEvent.parent_body")
        _check(self.radiant_up_hours, (int, float), "ShowerEvent.radiant_up_hours")
        _check(self.is_peak_night, bool, "ShowerEvent.is_peak_night")


@dataclass(frozen=True)
class ISSPass:
    start_utc: dt.datetime
    max_utc: dt.datetime
    end_utc: dt.datetime
    max_alt_deg: float
    start_dir: str
    max_dir: str
    end_dir: str  # directions: 8-point compass

    def __post_init__(self) -> None:
        for name in ("start_utc", "max_utc", "end_utc"):
            _check_utc(getattr(self, name), f"ISSPass.{name}")
        _check(self.max_alt_deg, (int, float), "ISSPass.max_alt_deg")
        for name in ("start_dir", "max_dir", "end_dir"):
            _check(getattr(self, name), str, f"ISSPass.{name}")


Verdict = Literal["PRIME", "WORTH IT", "Marginal", "Poor", "STAY IN BED"]


@dataclass(frozen=True)
class Conditions:
    dew_spread_c: float
    dew_risk: Literal["low", "moderate", "high"]
    pressure_trend: Literal["rising", "falling", "flat", "unknown"]
    trend_hpa_3h: float
    forecast_vs_actual: str | None = None

    def __post_init__(self) -> None:
        _check(self.dew_spread_c, (int, float), "Conditions.dew_spread_c")
        if self.dew_risk not in ("low", "moderate", "high"):
            raise TypeError(f"Conditions.dew_risk: expected low|moderate|high, got {self.dew_risk!r}")
        if self.pressure_trend not in ("rising", "falling", "flat", "unknown"):
            raise TypeError(
                f"Conditions.pressure_trend: expected rising|falling|flat|unknown, got {self.pressure_trend!r}"
            )
        _check(self.trend_hpa_3h, (int, float), "Conditions.trend_hpa_3h")
        _check(self.forecast_vs_actual, str, "Conditions.forecast_vs_actual", allow_none=True)


@dataclass(frozen=True)
class NightScore:
    total: int
    verdict: Verdict
    cloud_term: float
    moon_term: float
    transparency_term: float
    dew_term: float
    wind_term: float
    base: float
    meteor_bonus: int
    iss_bonus: int
    event_bonus: int
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _check(self.total, int, "NightScore.total")
        if self.verdict not in ("PRIME", "WORTH IT", "Marginal", "Poor", "STAY IN BED"):
            raise TypeError(f"NightScore.verdict: invalid band {self.verdict!r}")
        for name in ("cloud_term", "moon_term", "transparency_term", "dew_term", "wind_term", "base"):
            _check(getattr(self, name), (int, float), f"NightScore.{name}")
        for name in ("meteor_bonus", "iss_bonus", "event_bonus"):
            _check(getattr(self, name), int, f"NightScore.{name}")
        _check(self.reasons, list, "NightScore.reasons")


@dataclass(frozen=True)
class Night:
    date_local: dt.date
    dark: DarkWindow
    moon: MoonInfo
    weather: list[HourWeather]
    conditions: Conditions
    showers: list[ShowerEvent]
    iss_passes: list[ISSPass]
    score: NightScore | None = None

    def __post_init__(self) -> None:
        _check(self.date_local, dt.date, "Night.date_local")
        _check(self.dark, DarkWindow, "Night.dark")
        _check(self.moon, MoonInfo, "Night.moon")
        _check(self.weather, list, "Night.weather")
        _check(self.conditions, Conditions, "Night.conditions")
        _check(self.showers, list, "Night.showers")
        _check(self.iss_passes, list, "Night.iss_passes")
        _check(self.score, NightScore, "Night.score", allow_none=True)


@dataclass(frozen=True)
class Reading:
    timestamp_utc: dt.datetime
    temperature_c: float | None = None
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    dew_point_c: float | None = None

    def __post_init__(self) -> None:
        _check_utc(self.timestamp_utc, "Reading.timestamp_utc")
        for name in ("temperature_c", "humidity_pct", "pressure_hpa", "dew_point_c"):
            _check(getattr(self, name), (int, float), f"Reading.{name}", allow_none=True)


@dataclass(frozen=True)
class FieldLogEntry:
    date_local: dt.date
    went_out: bool
    clearness: int  # 0-5
    meteors_counted: int
    iss_seen: bool
    notes: str
    recorded_utc: dt.datetime

    def __post_init__(self) -> None:
        _check(self.date_local, dt.date, "FieldLogEntry.date_local")
        _check(self.went_out, bool, "FieldLogEntry.went_out")
        _check(self.clearness, int, "FieldLogEntry.clearness")
        _check(self.meteors_counted, int, "FieldLogEntry.meteors_counted")
        _check(self.iss_seen, bool, "FieldLogEntry.iss_seen")
        _check(self.notes, str, "FieldLogEntry.notes")
        _check_utc(self.recorded_utc, "FieldLogEntry.recorded_utc")
