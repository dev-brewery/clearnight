"""Pure, deterministic night scoring (ARCHITECTURE.md §5, ratified D5 v2).

No I/O, no clock access: everything derives from the inputs. Weights, the
moon floor, breakpoints, the event cap, the overcast hard cap, and the
verdict bands are owner-ratified and must not be tweaked here.
"""

from __future__ import annotations

from clearnight.models import (
    DarkWindow,
    HourWeather,
    ISSPass,
    MoonInfo,
    Night,
    ShowerEvent,
    Verdict,
)


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _col(weather: list[HourWeather], attr: str) -> float | None:
    """Mean of a variable over window hours with non-None values; None if all missing."""
    vals = [getattr(h, attr) for h in weather if getattr(h, attr) is not None]
    return _mean([float(v) for v in vals])


def verdict_label(total: int) -> Verdict:
    """Verdict bands (§5 table); pure function of the final total."""
    if total >= 85:
        return "PRIME"
    if total >= 70:
        return "WORTH IT"
    if total >= 50:
        return "Marginal"
    if total >= 35:
        return "Poor"
    return "STAY IN BED"


def score_night(
    window: DarkWindow | None,
    moon: MoonInfo | None,
    weather: list[HourWeather],
    dew_spread_c: float,
    showers: list[ShowerEvent],
    iss_passes: list[ISSPass],
) -> "NightScore":
    from clearnight.models import NightScore  # local import avoids cycle

    reasons: list[str] = []

    # Empty-data rules (deterministic): return 0 with a reason.
    if window is None or window.start_utc >= window.end_utc:
        return NightScore(
            total=0, verdict=verdict_label(0), cloud_term=0.0, moon_term=0.0,
            transparency_term=0.0, dew_term=0.0, wind_term=0.0, base=0.0,
            meteor_bonus=0, iss_bonus=0, event_bonus=0,
            reasons=["no astronomical darkness"],
        )
    if not weather:
        return NightScore(
            total=0, verdict=verdict_label(0), cloud_term=0.0, moon_term=0.0,
            transparency_term=0.0, dew_term=0.0, wind_term=0.0, base=0.0,
            meteor_bonus=0, iss_bonus=0, event_bonus=0,
            reasons=["no forecast data"],
        )

    cloud = _col(weather, "cloud_total_pct")
    rh = _col(weather, "rh_pct")
    vis = _col(weather, "visibility_m")
    wind = _col(weather, "wind_kmh")
    if cloud is None:
        reasons.append("cloud data missing")
    if rh is None:
        reasons.append("humidity data missing")
    if vis is None:
        reasons.append("visibility data missing")
    if wind is None:
        reasons.append("wind data missing")

    cloud_term = (100.0 - cloud) / 100.0 if cloud is not None else 0.0

    illum = moon.illumination_frac if moon is not None else 0.0
    up_frac = moon.up_fraction if moon is not None else 0.0
    moon_term = 0.15 + 0.85 * (1.0 - illum * up_frac)

    hum_term = _clamp01((85.0 - rh) / 45.0) if rh is not None else 0.0
    vis_term = _clamp01((vis - 5000.0) / 19000.0) if vis is not None else 0.0
    trans_term = hum_term * vis_term

    dew_term = _clamp01((dew_spread_c - 2.0) / 8.0)

    wind_term = _clamp01((25.0 - wind) / 10.0) if wind is not None else 0.0

    base = 100.0 * (
        0.45 * cloud_term
        + 0.15 * moon_term
        + 0.15 * trans_term
        + 0.05 * dew_term
        + 0.20 * wind_term
    )

    meteor_bonus = 0
    if showers:
        peak = any(s.is_peak_night and s.radiant_up_hours >= 2.0 for s in showers)
        active_up = any(not s.is_peak_night and s.radiant_up_hours >= 2.0 for s in showers)
        if peak:
            meteor_bonus = 6
        elif active_up:
            meteor_bonus = 2
    iss_bonus = min(4, 2 * sum(1 for p in iss_passes if p.max_alt_deg >= 45.0))
    event_bonus = min(10, meteor_bonus + iss_bonus)

    total = round(_clamp01(base / 100.0 + event_bonus / 100.0) * 100)

    # HARD CAP — overcast. Cannot fire when cloud is entirely missing
    # (cloud is None -> the all-None rule above already zeroed the term).
    if cloud is not None and cloud >= 85.0:
        total = min(total, 15)
        reasons.append("overcast")

    return NightScore(
        total=total,
        verdict=verdict_label(total),
        cloud_term=cloud_term,
        moon_term=moon_term,
        transparency_term=trans_term,
        dew_term=dew_term,
        wind_term=wind_term,
        base=base,
        meteor_bonus=meteor_bonus,
        iss_bonus=iss_bonus,
        event_bonus=event_bonus,
        reasons=reasons,
    )


def rank(nights: list[Night]) -> list[Night]:
    """Descending NightScore.total; ties -> earlier date_local first.

    Nights with score None sort last (stable).
    """
    scored = [n for n in nights if n.score is not None]
    unscored = [n for n in nights if n.score is None]
    scored.sort(key=lambda n: (-n.score.total, n.date_local))
    return scored + unscored
