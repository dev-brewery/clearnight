"""ISS TLE cache + visible-pass prediction (ARCHITECTURE §4 iss.py).

TLE source: CelesTrak GP query for NORAD 25544, cached under "celestrak_iss.txt"
with a 24 h max age. Online fetch failures fall back to stale cache, then to the
committed fixture (clearnight/fixtures/tle.txt). Offline mode uses the cache
(fresh or stale, flagged) and finally the fixture.

Pass prediction: for each dark window, sample the ISS altitude every 30 s; a
pass is a contiguous run of samples above 10° elevation, kept only if the ISS
is SUNLIT at the pass maximum. Passes spanning a window boundary are clamped
to the window; duplicates from adjacent windows are deduplicated.

Sunlight test — cylindrical Earth shadow (approximation):
the satellite is in shadow when it is on the night side of the Earth
(r · ŝ < 0, with r the geocentric satellite position and ŝ the unit
Earth→Sun direction) AND its perpendicular distance from the Sun-Earth
axis is below the Earth radius (6371 km mean). This ignores the penumbra
and Earth's oblateness; it is accurate to a few seconds for ISS
visibility filtering, which is fine here. Full-accuracy checks happen
in T22; skyfield's is_sunlit() is the cross-check there.
"""

from __future__ import annotations

import datetime as dt
import urllib.request
from dataclasses import dataclass

from .cache import Cache
from .fixtures import FIXTURES_DIR
from .models import DarkWindow, ISSPass, Site

TLE_KEY = "celestrak_iss.txt"
TLE_MAX_AGE_S = 24 * 3600
TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"
USER_AGENT = "clearnight/0.1 (github.com/dev-brewery/clearnight)"
TIMEOUT_S = 15

SAMPLE_STEP = dt.timedelta(seconds=30)
ALT_LIMIT_DEG = 10.0
EARTH_RADIUS_KM = 6371.0

COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


@dataclass(frozen=True)
class TLEData:
    """Parsed TLE groups plus provenance.

    groups: list of 3-line strings (name line + TLE line 1 + line 2).
    source: "cache" (fresh), "cache-stale" (offline, > 24 h), or
            "fixture" (committed demo TLE).
    """

    groups: list[str]
    source: str


def _split_groups(text: str) -> list[str]:
    """Split raw TLE text into complete 3-line groups (name + 2 TLE lines)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    groups: list[str] = []
    i = 0
    while i + 2 < len(lines) + 1 and i < len(lines):
        if i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            groups.append("\n".join([lines[i], lines[i + 1], lines[i + 2]]))
            i += 3
        else:
            i += 1  # skip malformed fragment (e.g. dangling name line)
    return groups


def _fixture_text() -> str:
    return (FIXTURES_DIR / "tle.txt").read_text(encoding="utf-8")


def load_tle(cache: Cache, offline: bool) -> TLEData:
    """Load ISS TLE, fresh cache -> stale cache -> fixture as last resort."""
    raw = cache.path(TLE_KEY).read_bytes() if cache.path(TLE_KEY).is_file() else None
    if offline:
        if raw is not None:
            fresh = cache.fresh(TLE_KEY, TLE_MAX_AGE_S)
            return TLEData(_split_groups(raw.decode("utf-8")), "cache" if fresh else "cache-stale")
        return TLEData(_split_groups(_fixture_text()), "fixture")
    if raw is not None and cache.fresh(TLE_KEY, TLE_MAX_AGE_S):
        return TLEData(_split_groups(raw.decode("utf-8")), "cache")
    try:
        req = urllib.request.Request(TLE_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            text = resp.read().decode("utf-8")
        groups = _split_groups(text)
        if not groups:
            raise ValueError("CelesTrak reply contained no TLE group")
        cache.put(TLE_KEY, text.encode("utf-8"))
        return TLEData(groups, "cache")
    except Exception:
        if raw is not None:  # stale cache beats the fixture
            return TLEData(_split_groups(raw.decode("utf-8")), "cache-stale")
        return TLEData(_split_groups(_fixture_text()), "fixture")


def _compass(az_deg: float) -> str:
    idx = int(((az_deg % 360.0) + 22.5) // 45.0) % 8
    return COMPASS[idx]


def _sunlit(t, sat, eph) -> bool:
    """Cylindrical Earth-shadow test (see module docstring)."""
    r = sat.at(t).position.km
    s = eph["earth"].at(t).observe(eph["sun"]).apparent().position.km
    s_hat = s / (s ** 2).sum() ** 0.5
    along = float(r @ s_hat)
    perp2 = float(r @ r) - along * along
    return not (along < 0.0 and perp2 < EARTH_RADIUS_KM ** 2)


def visible_passes(
    site: Site,
    windows: list[DarkWindow],
    tle_groups: list[str],
) -> list[ISSPass]:
    """Visible ISS passes across the given astronomical-darkness windows.

    First TLE group wins (the fixture has exactly one). Sampling every 30 s;
    a pass is a contiguous run above 10° elevation, clamped to the window,
    kept only if the ISS is sunlit at the maximum.
    """
    if not tle_groups:
        return []
    from skyfield.api import EarthSatellite, load, wgs84

    ts = load.timescale(builtin=True)
    eph_cache: dict[str, object] = {}

    lines = tle_groups[0].splitlines()
    sat = EarthSatellite(lines[1], lines[2], lines[0].strip(), ts)
    topo = sat - wgs84.latlon(site.lat, site.lon, elevation_m=site.elevation_m)

    def sample(when: dt.datetime):
        t = ts.from_datetime(when)
        el, az, _ = topo.at(t).altaz()
        return el.degrees, az.degrees, t

    passes: list[ISSPass] = []
    for win in windows:
        n = int((win.end_utc - win.start_utc) / SAMPLE_STEP) + 1
        times = [win.start_utc + i * SAMPLE_STEP for i in range(n)]
        times[-1] = min(times[-1], win.end_utc)
        samples = [sample(w) for w in times]
        above = [s for s in samples if s[0] > ALT_LIMIT_DEG]
        if not above:
            continue
        start, maxs, end = above[0], max(above, key=lambda s: s[0]), above[-1]
        if maxs[0] <= ALT_LIMIT_DEG:
            continue
        if "eph" not in eph_cache:
            # Required for the shadow test; caller guarantees the bsp is in
            # the cache for live use (tests skip when absent).
            from pathlib import Path

            from .cache import Cache as _C
            from .sky import load_ephemeris

            eph_cache["eph"] = load_ephemeris(_C(Path("cache")), offline=True)
        if not _sunlit(maxs[2], sat, eph_cache["eph"]):
            continue
        passes.append(
            ISSPass(
                start_utc=start[2].utc_datetime(),
                max_utc=maxs[2].utc_datetime(),
                end_utc=end[2].utc_datetime(),
                max_alt_deg=round(maxs[0], 2),
                start_dir=_compass(start[1]),
                max_dir=_compass(maxs[1]),
                end_dir=_compass(end[1]),
            )
        )

    # Deduplicate passes shared by adjacent windows (same start within 60 s).
    seen: list[ISSPass] = []
    for p in passes:
        if any(abs((p.start_utc - q.start_utc).total_seconds()) < 60 for q in seen):
            continue
        seen.append(p)
    return seen
