"""Conditions: dew risk, pressure trend, forecast-vs-actual (pure, no IO).

Rules
-----
- Dew spread: the newest sensor reading with both temperature_c and dew_point_c
  wins (sensor-projected). Otherwise fall back to the forecast: mean(temperature)
  - mean(dew_point) over window_weather rows having both fields. When neither
  source is available, dew_spread_c is 0.0 and dew_risk is "high"; a 0.0 spread
  from missing data therefore labels "high". Renderers (T14/T15) surface the
  "no data" reason separately, so "high" here means "high or unknowable".
- Pressure trend: needs at least 2 pressure_hpa readings within the 6 h before
  the newest reading's timestamp. The delta is normalized to hPa per 3 h:
  > +1 "rising", < -1 "falling", else "flat". With insufficient readings the
  trend is "unknown" and trend_hpa_3h is 0.0 (0.0 is the None-safe placeholder;
  it must never be read as a real trend when the label is "unknown").
- forecast_vs_actual: newest reading with temperature_c vs the HourWeather whose
  time_utc hour matches (nearest earlier hour if no exact match). None when
  either side is missing.
"""

from __future__ import annotations

import datetime as dt

from .models import Conditions, HourWeather, Reading

_DEW_LOW_C = 8.0
_DEW_MODERATE_C = 3.0
_TREND_WINDOW_H = 6
_TREND_THRESHOLD_HPA = 1.0


def dew_risk_label(spread_c: float) -> str:
    if spread_c >= _DEW_LOW_C:
        return "low"
    if spread_c >= _DEW_MODERATE_C:
        return "moderate"
    return "high"


def _dew_spread(readings: list[Reading], window_weather: list[HourWeather]) -> float:
    for reading in reversed(readings):
        if reading.temperature_c is not None and reading.dew_point_c is not None:
            return round(reading.temperature_c - reading.dew_point_c, 1)
    temps = [w.temperature_c for w in window_weather if w.temperature_c is not None and w.dew_point_c is not None]
    dews = [w.dew_point_c for w in window_weather if w.temperature_c is not None and w.dew_point_c is not None]
    if temps:
        return round(sum(temps) / len(temps) - sum(dews) / len(dews), 1)
    return 0.0


def _pressure_trend(readings: list[Reading]) -> tuple[str, float]:
    if not readings:
        return "unknown", 0.0
    newest = readings[-1].timestamp_utc
    cutoff = newest - dt.timedelta(hours=_TREND_WINDOW_H)
    in_window = [
        r for r in readings
        if r.pressure_hpa is not None and cutoff <= r.timestamp_utc <= newest
    ]
    if len(in_window) < 2:
        return "unknown", 0.0
    first, last = in_window[0], in_window[-1]
    hours = (last.timestamp_utc - first.timestamp_utc).total_seconds() / 3600.0
    if hours <= 0:
        return "unknown", 0.0
    trend = (last.pressure_hpa - first.pressure_hpa) * 3.0 / hours
    trend = round(trend, 1)
    if trend > _TREND_THRESHOLD_HPA:
        label = "rising"
    elif trend < -_TREND_THRESHOLD_HPA:
        label = "falling"
    else:
        label = "flat"
    return label, trend


def _forecast_vs_actual(readings: list[Reading], window_weather: list[HourWeather]) -> str | None:
    window_weather = sorted(window_weather, key=lambda w: w.time_utc)
    newest = None
    for reading in reversed(readings):
        if reading.temperature_c is not None:
            newest = reading
            break
    if newest is None or not window_weather:
        return None
    hour_floor = newest.timestamp_utc.replace(minute=0, second=0, microsecond=0)
    weather = None
    for row in sorted(window_weather, key=lambda w: w.time_utc):
        if row.time_utc <= hour_floor:
            weather = row  # keep nearest earlier (or exact) hour
        else:
            break
    if weather is None or weather.temperature_c is None:
        return None
    delta = round(newest.temperature_c - weather.temperature_c, 1)
    return (
        f"sensor {newest.temperature_c:.1f}C vs forecast {weather.temperature_c:.1f}C ({delta:+.1f})"
    )


def assess(readings: list[Reading], window_weather: list[HourWeather]) -> Conditions:
    spread = _dew_spread(readings, window_weather)
    trend, trend_hpa = _pressure_trend(readings)
    return Conditions(
        dew_spread_c=spread,
        dew_risk=dew_risk_label(spread),
        pressure_trend=trend,
        trend_hpa_3h=trend_hpa,
        forecast_vs_actual=_forecast_vs_actual(readings, window_weather),
    )
