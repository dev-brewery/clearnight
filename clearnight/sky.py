"""Dark windows, Moon info, radiant altitudes (ARCHITECTURE §4 sky.py).

Ephemeris: de421.bsp loaded via skyfield Loader rooted at the cache dir
(downloaded once, ~17 MB). Offline mode never touches the network: if the
bsp is absent from the cache it raises SkyUnavailable naming the cache path.

Dark windows: per LOCAL night (site tz) from start_date, the interval where
the Sun's altitude is below -18° (astronomical darkness). Nights without any
such interval (e.g. high-latitude summer) produce NO DarkWindow — nights
without darkness are simply absent from the returned list; callers must not
assume len(windows) == nights.

Sampling convention: all sampling (Sun/Moon/radiant altitude) uses a 5-minute
step. Pure sampling helpers (_up_fraction, _max_alt_deg, _crossings) take an
altitude callback so they are unit-testable offline with mocked geometry.
"""

from __future__ import annotations

import datetime as dt
from typing import Callable
from zoneinfo import ZoneInfo

from skyfield.api import Loader, Star, wgs84
from skyfield.timelib import Time, Timescale
from skyfield.units import Angle

from .cache import Cache
from .models import DarkWindow, MoonInfo, Site

BSP_NAME = "de421.bsp"
SAMPLE_STEP = dt.timedelta(minutes=5)
DARK_LIMIT_DEG = -18.0


class SkyUnavailable(Exception):
    """Raised when the ephemeris is needed but absent (offline mode)."""


def _ts() -> Timescale:
    # builtin=True: uses skyfield's bundled leap-seconds table, no download.
    from skyfield.api import load

    return load.timescale(builtin=True)


def load_ephemeris(cache: Cache, offline: bool):
    """Load de421.bsp from the cache (downloading once if online)."""
    from skyfield.api import load, load_file

    bsp = cache.path(BSP_NAME)
    if not bsp.is_file():
        if offline:
            raise SkyUnavailable(
                f"offline mode and {bsp} is not in the cache; "
                "run once online to download it, or use the recorded fixture"
            )
        loader = Loader(str(cache.root))
        loader.download(BSP_NAME)
    return load_file(str(bsp))


def _observer(site: Site, eph, ts: Timescale):
    return (eph["earth"] + wgs84.latlon(site.lat, site.lon)).at


def _alt_deg_fn(eph, ts: Timescale, target, site: Site) -> Callable[[dt.datetime], float]:
    """Altitude-above-horizon (deg) of target as a function of UTC datetime."""
    topo = _observer(site, eph, ts)

    def alt(when: dt.datetime) -> float:
        t = ts.from_datetime(when)
        el, _, _ = topo(t).observe(target).apparent().altaz()
        return el.degrees

    return alt


# ---------------------------------------------------------------------------
# Pure sampling helpers (unit-testable offline with a mocked altitude fn)
# ---------------------------------------------------------------------------

def _samples(start: dt.datetime, end: dt.datetime) -> list[dt.datetime]:
    t = start
    out = []
    while t <= end:
        out.append(t)
        t += SAMPLE_STEP
    if out and out[-1] < end:
        out.append(end)
    return out


def _up_fraction(alt_fn: Callable[[dt.datetime], float],
                 times: list[dt.datetime]) -> float:
    if not times:
        return 0.0
    up = sum(1 for t in times if alt_fn(t) > 0.0)
    return up / len(times)


def _max_alt_deg(alt_fn: Callable[[dt.datetime], float],
                 times: list[dt.datetime]) -> float:
    if not times:
        return -90.0
    return max(alt_fn(t) for t in times)


def _up_hours(alt_fn: Callable[[dt.datetime], float],
              times: list[dt.datetime]) -> float:
    """Hours above horizon, from a uniform 5-min sample grid."""
    if len(times) < 2:
        return 0.0
    up = sum(1 for t in times if alt_fn(t) > 0.0)
    # Each sample represents one grid step; the final sample closes the span.
    return (up - (1 if alt_fn(times[-1]) > 0.0 else 0)) * (SAMPLE_STEP.total_seconds() / 3600.0)


def _crossings(alt_fn: Callable[[dt.datetime], float],
               times: list[dt.datetime]) -> list[dt.datetime]:
    """Times where alt_fn crosses zero between consecutive samples,
    refined by bisection to ~1 s. Times list must be uniformly spaced."""
    out = []
    for a, b in zip(times, times[1:]):
        fa, fb = alt_fn(a), alt_fn(b)
        if fa == 0.0:
            out.append(a)
        elif fa * fb < 0:
            lo, hi, flo = a, b, fa
            while (hi - lo).total_seconds() > 1.0:
                mid = lo + (hi - lo) / 2
                fm = alt_fn(mid)
                if flo * fm <= 0:
                    hi = mid
                else:
                    lo, flo = mid, fm
            out.append(lo + (hi - lo) / 2)
    return out


# ---------------------------------------------------------------------------
# Dark windows
# ---------------------------------------------------------------------------

def dark_windows(site: Site, start_date: dt.date, nights: int, eph) -> list[DarkWindow]:
    """Per local night, the interval with Sun altitude < -18°, or nothing.

    Returns one DarkWindow per night where astronomical darkness exists;
    nights without darkness are simply absent from the list.
    """
    ts = _ts()
    sun_alt = _alt_deg_fn(eph, ts, eph["sun"], site)
    tz = ZoneInfo(site.tz_name)
    windows: list[DarkWindow] = []
    for i in range(nights):
        # Scan local noon to next local noon: brackets sunset/sunrise.
        noon = dt.datetime(start_date.year, start_date.month, start_date.day,
                           12, 0, tzinfo=tz).astimezone(dt.timezone.utc)
        end = noon + dt.timedelta(days=1)
        times = _samples(noon, end)
        dark = [t for t in times if sun_alt(t) < DARK_LIMIT_DEG]
        if dark:
            windows.append(DarkWindow(start_utc=dark[0], end_utc=dark[-1]))
        start_date += dt.timedelta(days=1)
    return windows


# ---------------------------------------------------------------------------
# Moon
# ---------------------------------------------------------------------------

PHASE_NAMES = [
    "New Moon",            # illum < 0.03
    "Waxing Crescent",     # 0.03–0.44, increasing
    "First Quarter",       # 0.44–0.56, increasing
    "Waxing Gibbous",      # 0.56–0.97, increasing
    "Full Moon",           # illum > 0.97
    "Waning Gibbous",      # 0.56–0.97, decreasing
    "Last Quarter",        # 0.44–0.56, decreasing
    "Waning Crescent",     # 0.03–0.44, decreasing
]


def phase_name(illumination: float, increasing: bool) -> str:
    """8-name phase mapping from illumination fraction and trend.

    Thresholds: <0.03 New, >0.97 Full, 0.44–0.56 quarter, otherwise
    crescent (<0.44) or gibbous (>0.56); waxing if increasing else waning.
    """
    if illumination < 0.03:
        return "New Moon"
    if illumination > 0.97:
        return "Full Moon"
    if illumination < 0.44:
        return "Waxing Crescent" if increasing else "Waning Crescent"
    if illumination <= 0.56:
        return "First Quarter" if increasing else "Last Quarter"
    return "Waxing Gibbous" if increasing else "Waning Gibbous"


def _moon_illumination(eph, ts: Timescale, when: dt.datetime) -> float:
    from skyfield import almanac

    t = ts.from_datetime(when)
    return float(almanac.fraction_illuminated(eph, "moon", t))


def moon_info(site: Site, window: DarkWindow, eph) -> MoonInfo:
    """Moon state over the window: illumination at midpoint, phase name from
    illumination + increasing/decreasing (compared 6 h apart around midpoint),
    rise/set = horizon crossings inside the window (None if none),
    up_fraction and max_alt over 5-min samples."""
    ts = _ts()
    moon_alt = _alt_deg_fn(eph, ts, eph["moon"], site)
    mid = window.start_utc + (window.end_utc - window.start_utc) / 2
    illum = _moon_illumination(eph, ts, mid)
    later = _moon_illumination(eph, ts, min(mid + dt.timedelta(hours=6),
                                            window.end_utc))
    times = _samples(window.start_utc, window.end_utc)
    crossings = _crossings(moon_alt, times)
    rise = crossings[0] if crossings else None
    set_ = crossings[1] if len(crossings) > 1 else None
    # If the Moon is already up at window start, the first crossing is a set.
    if crossings and moon_alt(window.start_utc) > 0.0:
        rise, set_ = (None, crossings[0]) if len(crossings) > 0 else (None, None)
    return MoonInfo(
        phase_name=phase_name(illum, later >= illum),
        illumination_frac=round(illum, 4),
        rise_utc=rise,
        set_utc=set_,
        up_fraction=round(_up_fraction(moon_alt, times), 4),
        max_alt_deg=round(_max_alt_deg(moon_alt, times), 2),
    )


# ---------------------------------------------------------------------------
# Radiants
# ---------------------------------------------------------------------------

def radiant_up_hours(site: Site, window: DarkWindow,
                     ra_deg: float, dec_deg: float, eph) -> float:
    """Hours of the window with the radiant above the horizon (5-min samples)."""
    ts = _ts()
    star = Star(ra_hours=ra_deg / 15.0, dec_degrees=dec_deg)
    alt = _alt_deg_fn(eph, ts, star, site)
    times = _samples(window.start_utc, window.end_utc)
    return round(_up_hours(alt, times), 3)
