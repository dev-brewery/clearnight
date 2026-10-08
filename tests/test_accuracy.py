"""T22 A4: accuracy of dark_windows / moon_info against timeanddate.com.

Method (recorded per A4): reference values were captured 2026-10-08 from
timeanddate.com for the demo site (Black Mesa State Park, OK; 36.85 N,
-102.88 W) for Oct 7-10 2026, and stored with sources in
tests/fixtures/accuracy_reference.json. Oct 9/10 night bounds are derived
from the Oct 7 tabulated pair plus the site's daily drift; that derivation
and all URLs are recorded in the fixture's _source field.

Checks, tolerance +-5 min on window bounds:
  - dark-window bounds Oct 7/8/9/10 within +-5 min of reference;
  - Oct 9 (New Moon): moon down the entire window (rise/set None,
    up_fraction 0.0);
  - Oct 8 morning moonrise (ref 5:47 am CDT): a crossing is found inside
    the Oct 7-night window within +-6 min (see fixture tolerances note:
    timeanddate quotes upper-limb + refraction, sky.py reports the
    center-of-disk alt=0 crossing, ~2 min later by convention);
  - illumination trajectory: each of the Oct 8/9/10 night midpoints within
    +-2.0 points of linear interpolation of the lunar-noon references
    (Oct 8 4.3%, Oct 9 1.0%, Oct 10 0.1%). The Oct 7 night is excluded:
    its midpoint precedes the earliest reference point.

BSP-gated: skipped unless cache/de421.bsp is present. Offline-safe.
"""

from __future__ import annotations

import datetime as dt
import json
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from clearnight.cache import Cache
from clearnight.models import Site
from clearnight.sky import SkyUnavailable, dark_windows, load_ephemeris, moon_info

REPO = Path(__file__).resolve().parent.parent
SITE = Site(name="accuracy", lat=36.85, lon=-102.88, elevation_m=1400.0,
            tz_name="America/Chicago")
TZ = ZoneInfo("America/Chicago")


def _ref() -> dict:
    return json.loads(
        (REPO / "tests" / "fixtures" / "accuracy_reference.json")
        .read_text(encoding="utf-8"))


@unittest.skipUnless((REPO / "cache" / "de421.bsp").is_file(),
                     "de421.bsp not in cache; accuracy cases skipped")
class TestAccuracy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eph = load_ephemeris(Cache(REPO / "cache"), offline=True)
        cls.windows = {w.start_utc.astimezone(TZ).date().isoformat(): w
                       for w in dark_windows(SITE, dt.date(2026, 10, 7), 4,
                                             cls.eph)}
        cls.ref = _ref()

    def test_dark_window_bounds_within_5_min(self):
        for date_s, ref_night in self.ref["nights"].items():
            self.assertIn(date_s, self.windows, f"no window for {date_s}")
            w = self.windows[date_s]
            start_local = w.start_utc.astimezone(TZ)
            end_local = w.end_utc.astimezone(TZ)
            rs = dt.datetime.combine(start_local.date(),
                                     dt.time.fromisoformat(
                                         ref_night["dark_start_local"]),
                                     tzinfo=TZ)
            re_ = dt.datetime.combine(end_local.date(),
                                      dt.time.fromisoformat(
                                          ref_night["dark_end_local"]),
                                      tzinfo=TZ)
            self.assertLessEqual(
                abs((start_local - rs).total_seconds()) / 60.0, 5.0,
                f"{date_s} dark start {start_local:%H:%M} vs ref "
                f"{rs:%H:%M}")
            self.assertLessEqual(
                abs((end_local - re_).total_seconds()) / 60.0, 5.0,
                f"{date_s} dark end {end_local:%H:%M} vs ref {re_:%H:%M}")

    def test_oct9_new_moon_down_entire_window(self):
        w = self.windows["2026-10-09"]
        mi = moon_info(SITE, w, self.eph)
        self.assertIsNone(mi.rise_utc)
        self.assertIsNone(mi.set_utc)
        self.assertEqual(mi.up_fraction, 0.0)

    def test_oct8_morning_moonrise_crossing_found(self):
        # The moonrise at ~5:47 am local Oct 8 falls inside the window that
        # begins the evening of Oct 7; a horizon crossing must be found.
        ref_min = self.ref["moon"]["2026-10-08_morning_moonrise_local"]
        w = self.windows["2026-10-07"]
        mi = moon_info(SITE, w, self.eph)
        self.assertIsNotNone(mi.rise_utc,
                             "no moonrise crossing found in Oct 7 window")
        rise_local = mi.rise_utc.astimezone(TZ)
        rs = dt.datetime.combine(rise_local.date(),
                                 dt.time.fromisoformat(ref_min), tzinfo=TZ)
        diff = abs((rise_local - rs).total_seconds()) / 60.0
        tol = self.ref["tolerances"]["moonrise_minutes"]
        self.assertLessEqual(diff, tol,
                             f"moonrise {rise_local:%H:%M} vs ref {rs:%H:%M} "
                             f"= {diff:.1f} min > {tol} min")

    def test_illumination_trajectory(self):
        refs = self.ref["moon"]["illumination_lunar_noon"]
        points = sorted(
            (dt.datetime.fromisoformat(f"{d}T12:00").replace(tzinfo=TZ), v)
            for d, v in refs.items())

        def interp(when_local: dt.datetime) -> float:
            if when_local <= points[0][0]:
                return points[0][1]
            if when_local >= points[-1][0]:
                return points[-1][1]
            for (t0, v0), (t1, v1) in zip(points, points[1:]):
                if t0 <= when_local <= t1:
                    frac = ((when_local - t0).total_seconds()
                            / (t1 - t0).total_seconds())
                    return v0 + frac * (v1 - v0)
            raise AssertionError("unreachable")

        tol = self.ref["tolerances"]["illumination_abs"]
        for date_s in ("2026-10-08", "2026-10-09", "2026-10-10"):
            w = self.windows[date_s]
            mi = moon_info(SITE, w, self.eph)
            mid_local = (w.start_utc + (w.end_utc - w.start_utc) / 2
                         ).astimezone(TZ)
            expected = interp(mid_local)
            self.assertLessEqual(
                abs(mi.illumination_frac - expected), tol,
                f"{date_s} midpoint illumination {mi.illumination_frac} vs "
                f"interpolated {expected:.4f}")


if __name__ == "__main__":
    unittest.main()
