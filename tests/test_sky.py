"""Tests for clearnight.sky — fully offline (no bsp download, no network).

Computed-vs-recorded full-fidelity checks happen at T22; here we test the
pure date/window math, sampling logic with mocked altitude functions, the
phase-name mapping, and structural invariants of the recorded sky.json.
"""

import datetime as dt
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from clearnight.cache import Cache
from clearnight.fixtures import FIXTURES_DIR, load_manifest
from clearnight.models import DarkWindow, Site
from clearnight.sky import (
    BSP_NAME,
    SAMPLE_STEP,
    SkyUnavailable,
    _crossings,
    _samples,
    _up_fraction,
    _up_hours,
    _max_alt_deg,
    load_ephemeris,
    phase_name,
)

DEMO = Site(name="demo", lat=36.85, lon=-102.88, elevation_m=1300.0,
            tz_name="America/Chicago")
UTC = dt.timezone.utc


def const_fn(v):
    return lambda t: v


class TestLoadEphemeris(unittest.TestCase):
    def test_offline_empty_cache_raises(self):
        with TemporaryDirectory() as d:
            cache = Cache(Path(d))
            with self.assertRaises(SkyUnavailable) as cm:
                load_ephemeris(cache, offline=True)
            self.assertIn(BSP_NAME, str(cm.exception))
            self.assertIn(str(Path(d).resolve()), str(cm.exception))


class TestSamplingHelpers(unittest.TestCase):
    def setUp(self):
        self.start = dt.datetime(2026, 10, 7, 3, 0, tzinfo=UTC)
        self.times = _samples(self.start, self.start + dt.timedelta(hours=1))
        self.assertEqual((self.times[-1] - self.times[0]).total_seconds(), 3600)

    def test_sample_grid_spacing(self):
        gaps = {(b - a).total_seconds() for a, b in
                zip(self.times, self.times[1:])}
        self.assertTrue(gaps.issubset({SAMPLE_STEP.total_seconds()}))

    def test_up_fraction_and_max(self):
        def alt(t):
            return 10.0 if t.minute % 20 < 10 else -10.0
        self.assertGreater(_up_fraction(alt, self.times), 0.0)
        self.assertLess(_up_fraction(alt, self.times), 1.0)
        self.assertEqual(_max_alt_deg(alt, self.times), 10.0)
        self.assertEqual(_max_alt_deg(const_fn(-30), self.times), -30.0)

    def test_crossings_linear(self):
        def alt(t):
            return (t - self.times[0]).total_seconds() / 1800.0 - 1.0
        cross = _crossings(alt, self.times)
        self.assertEqual(len(cross), 1)
        self.assertLess(abs((cross[0] - self.times[0]).total_seconds()
                            - 1800.0), 2.0)

    def test_up_hours_pole_radiant(self):
        # Radiant at Dec +89 from lat 36.85 is circumpolar: up the whole window.
        # Mocked geometry: altitude always positive (dec + lat > 90 - lat rule:
        # dec=89 > 90 - 36.85 = 53.15).
        hours = _up_hours(const_fn(30.0), self.times)
        self.assertAlmostEqual(hours, 1.0, delta=0.01)


class TestPhaseNames(unittest.TestCase):
    def test_mapping(self):
        cases = [
            (0.0, True, "New Moon"), (0.02, False, "New Moon"),
            (0.10, True, "Waxing Crescent"), (0.40, False, "Waning Crescent"),
            (0.50, True, "First Quarter"), (0.50, False, "Last Quarter"),
            (0.70, True, "Waxing Gibbous"), (0.80, False, "Waning Gibbous"),
            (0.98, True, "Full Moon"), (1.0, False, "Full Moon"),
        ]
        for illum, inc, expected in cases:
            self.assertEqual(phase_name(illum, inc), expected)


class TestSkyFixture(unittest.TestCase):
    """Structural invariants of the recorded fixture (offline)."""

    @classmethod
    def setUpClass(cls):
        cls.sky = json.loads((FIXTURES_DIR / "sky.json").read_text("utf-8"))

    def test_site_matches_manifest(self):
        m = load_manifest()["site"]
        self.assertEqual(self.sky["site"]["lat"], m["lat"])
        self.assertEqual(self.sky["site"]["lon"], m["lon"])
        self.assertEqual(self.sky["site"]["tz"], m["tz"])

    def test_seven_nights_monotonic(self):
        nights = self.sky["nights"]
        self.assertEqual(len(nights), 7)
        dates = [dt.date.fromisoformat(n["date_local"]) for n in nights]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(len(set(dates)), 7)
        self.assertEqual(dates[0],
                         dt.date.fromisoformat(self.sky["reference_date"]))

    def test_window_invariants(self):
        for n in self.sky["nights"]:
            s = dt.datetime.fromisoformat(n["dark_start_utc"])
            e = dt.datetime.fromisoformat(n["dark_end_utc"])
            self.assertEqual(s.tzinfo, UTC)
            self.assertLess(s, e)
            # Darkness lasts at most a full night (≤ 14 h at this latitude).
            self.assertLess((e - s).total_seconds(), 14 * 3600)
            m = n["moon"]
            self.assertGreaterEqual(m["illumination_frac"], 0.0)
            self.assertLessEqual(m["illumination_frac"], 1.0)
            self.assertGreaterEqual(m["up_fraction"], 0.0)
            self.assertLessEqual(m["up_fraction"], 1.0)
            self.assertGreaterEqual(m["max_alt_deg"], -90.0)
            self.assertLessEqual(m["max_alt_deg"], 90.0)
            if m["rise_utc"] and m["set_utc"]:
                r = dt.datetime.fromisoformat(m["rise_utc"])
                st = dt.datetime.fromisoformat(m["set_utc"])
                if r < st:
                    self.assertGreater(r, s - dt.timedelta(minutes=5))
                    self.assertLess(st, e + dt.timedelta(minutes=5))

    def test_oct9_new_moon_draconid_precondition(self):
        oct9 = [n for n in self.sky["nights"]
                if n["date_local"] == "2026-10-09"]
        self.assertEqual(len(oct9), 1)
        self.assertLess(oct9[0]["moon"]["illumination_frac"], 0.02)


class TestDarkWindowsSkippable(unittest.TestCase):
    """Ephemeris-backed cases: skipped when de421.bsp is not cached."""

    def setUp(self):
        from clearnight import sky as sky_mod
        try:
            self.eph = sky_mod.load_ephemeris(
                Cache(Path("cache")), offline=True)
        except SkyUnavailable:
            self.skipTest("de421.bsp not in cache; ephemeris cases skipped")

    def test_tromso_midsummer_no_darkness(self):
        from clearnight.sky import dark_windows
        tromso = Site(name="tromso", lat=69.6, lon=18.9, elevation_m=10.0,
                      tz_name="Europe/Oslo")
        windows = dark_windows(tromso, dt.date(2026, 6, 21), 3, self.eph)
        self.assertEqual(windows, [])

    def test_demo_site_window_count(self):
        from clearnight.sky import dark_windows
        windows = dark_windows(DEMO, dt.date(2026, 10, 7), 7, self.eph)
        self.assertEqual(len(windows), 7)
        for w in windows:
            self.assertIsInstance(w, DarkWindow)
            self.assertLess((w.end_utc - w.start_utc).total_seconds(),
                            14 * 3600)


if __name__ == "__main__":
    unittest.main()
