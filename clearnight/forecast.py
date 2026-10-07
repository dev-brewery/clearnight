"""Open-Meteo hourly forecast client (ARCHITECTURE §4 forecast.py contract).

Fetch chain: fresh cache (1 h) -> stale cache -> network -> committed fixture.
Offline mode drops the network step. The fixture covers a fixed Oct 6-14 2026
range; hours outside the requested range are filtered out, and an empty list
is returned when nothing overlaps (the caller handles that).

Date window: start_date is start_utc's date; end_date is the date of
start_utc + hours (i.e. ceil to whole UTC days so the tail of the window is
never clipped by a partial-day boundary).
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.request

from .cache import Cache
from .fixtures import FIXTURES_DIR
from .models import DarkWindow, HourWeather, Site

HOURLY_VARS = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "visibility",
    "wind_speed_10m",
)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 15
MAX_AGE_S = 3600
FIXTURE_PATH = FIXTURES_DIR / "forecast.json"


def cache_key(site: Site, start_utc: dt.datetime) -> str:
    return f"forecast_{site.lat}_{site.lon}_{start_utc:%Y%m%d}.json"


def build_url(site: Site, start_utc: dt.datetime, hours: int) -> str:
    start_date = start_utc.date()
    end_date = (start_utc + dt.timedelta(hours=hours)).date()
    return (
        f"{FORECAST_URL}?latitude={site.lat}&longitude={site.lon}"
        f"&hourly={','.join(HOURLY_VARS)}"
        f"&start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
        "&timezone=UTC"
    )


def _parse_hourly(payload: bytes) -> list[HourWeather]:
    """Validate an Open-Meteo reply and map it to HourWeather.

    Missing individual values -> None; a variable missing entirely -> None
    for all its values. Arrays must be equal length and times must parse.
    """
    doc = json.loads(payload.decode("utf-8"))
    hourly = doc.get("hourly")
    if not isinstance(hourly, dict) or "time" not in hourly:
        raise ValueError("forecast reply has no hourly.time array")
    times_raw = hourly["time"]
    if not isinstance(times_raw, list):
        raise ValueError("hourly.time is not a list")
    n = len(times_raw)
    times: list[dt.datetime] = []
    for raw in times_raw:
        t = dt.datetime.fromisoformat(str(raw))
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        times.append(t.astimezone(dt.timezone.utc))

    def values(var: str) -> list:
        arr = hourly.get(var)
        if arr is None:
            return [None] * n
        if not isinstance(arr, list) or len(arr) != n:
            raise ValueError(f"hourly.{var} length mismatch")
        return arr

    cols = {var: values(var) for var in HOURLY_VARS}
    out: list[HourWeather] = []
    for i, t in enumerate(times):
        out.append(
            HourWeather(
                time_utc=t,
                temperature_c=cols["temperature_2m"][i],
                rh_pct=cols["relative_humidity_2m"][i],
                dew_point_c=cols["dew_point_2m"][i],
                cloud_total_pct=cols["cloud_cover"][i],
                cloud_low_pct=cols["cloud_cover_low"][i],
                cloud_mid_pct=cols["cloud_cover_mid"][i],
                cloud_high_pct=cols["cloud_cover_high"][i],
                visibility_m=cols["visibility"][i],
                wind_kmh=cols["wind_speed_10m"][i],
            )
        )
    return out


def _clip(weather: list[HourWeather], start_utc: dt.datetime,
         end_utc: dt.datetime) -> list[HourWeather]:
    return [h for h in weather if start_utc <= h.time_utc < end_utc]


def fetch_hourly(site: Site, start_utc: dt.datetime, hours: int,
                 cache: Cache, offline: bool) -> list[HourWeather]:
    key = cache_key(site, start_utc)
    end_utc = start_utc + dt.timedelta(hours=hours)
    url = build_url(site, start_utc, hours)

    payload = cache.get(key, MAX_AGE_S)
    if payload is not None:
        return _clip(_parse_hourly(payload), start_utc, end_utc)

    stale = cache.get(key, None)
    if stale is not None:
        return _clip(_parse_hourly(stale), start_utc, end_utc)

    if not offline:
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT_S) as resp:
                payload = resp.read()
            cache.put(key, payload)
            return _clip(_parse_hourly(payload), start_utc, end_utc)
        except Exception:
            pass

    # Committed fixture fallback.
    return _clip(_parse_hourly(FIXTURE_PATH.read_bytes()), start_utc, end_utc)


def slice_to_window(weather: list[HourWeather],
                    window: DarkWindow) -> list[HourWeather]:
    """Inclusive on both bounds by UTC hour timestamp."""
    return [h for h in weather if window.start_utc <= h.time_utc <= window.end_utc]
