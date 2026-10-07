"""Tests for clearnight.iss — offline; bsp-dependent checks follow the T07
pattern (skipUnless the cached de421.bsp exists). Network is never touched:
urlopen is mocked or asserted not to be called."""

import datetime as dt
import json
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from clearnight.cache import Cache
from clearnight.fixtures import FIXTURES_DIR, load_manifest
from clearnight.iss import (
    TLE_KEY,
    TLE_URL,
    _split_groups,
    load_tle,
    visible_passes,
)
from clearnight.models import DarkWindow, ISSPass, Site

DEMO = Site(name="demo", lat=36.85, lon=-102.88, elevation_m=1300.0,
            tz_name="America/Chicago")
UTC = dt.timezone.utc
FIXTURE_TLE = (FIXTURES_DIR / "tle.txt").read_text(encoding="utf-8")
BSP_AVAILABLE = Path("cache/de421.bsp").is_file()


def _win(date: str, start: str, end: str) -> DarkWindow:
    return DarkWindow(
        dt.datetime.fromisoformat(f"{date}T{start}+00:00"),
        dt.datetime.fromisoformat(f"{date}T{end}+00:00"),
    )


class TestSplitGroups(unittest.TestCase):
    def test_fixture_is_one_complete_group(self):
        groups = _split_groups(FIXTURE_TLE)
        self.assertEqual(len(groups), 1)
        lines = groups[0].splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("ISS (ZARYA)"))
        self.assertTrue(lines[1].startswith("1 "))
        self.assertTrue(lines[2].startswith("2 "))

    def test_malformed_fragments_skipped(self):
        text = "NAME ONLY\n1 25544U x\n2 25544 y\nGARBAGE\n"
        self.assertEqual(len(_split_groups(text)), 1)

    def test_empty_text_no_groups(self):
        self.assertEqual(_split_groups(""), [])


class TestLoadTLE(unittest.TestCase):
    def test_fixture_parses(self):
        data = load_tle(Cache(Path("cache")), offline=True)
        self.assertIn("ISS (ZARYA)", data.groups[0])

    def test_fresh_cache_skips_network(self):
        with TemporaryDirectory() as d:
            cache = Cache(Path(d))
            cache.put(TLE_KEY, FIXTURE_TLE.encode())
            p = cache.path(TLE_KEY)
            past = (dt.datetime.now().timestamp()) - 60  # 1 min old, fresh
            import os
            os.utime(p, (past, past))
            with mock.patch("clearnight.iss.urllib.request.urlopen") as u:
                u.side_effect = AssertionError("network called with fresh cache")
                data = load_tle(cache, offline=False)
            self.assertEqual(data.source, "cache")
            self.assertEqual(len(data.groups), 1)

    def test_stale_cache_offline_flags_staleness(self):
        with TemporaryDirectory() as d:
            cache = Cache(Path(d))
            cache.put(TLE_KEY, FIXTURE_TLE.encode())
            import os
            old = dt.datetime.now().timestamp() - 25 * 3600  # > 24 h
            os.utime(cache.path(TLE_KEY), (old, old))
            data = load_tle(cache, offline=True)
            self.assertEqual(data.source, "cache-stale")
            self.assertEqual(len(data.groups), 1)

    def test_no_cache_offline_falls_back_to_fixture(self):
        with TemporaryDirectory() as d:
            data = load_tle(Cache(Path(d)), offline=True)
            self.assertEqual(data.source, "fixture")
            self.assertIn("ISS (ZARYA)", data.groups[0])

    def test_online_failure_falls_back_to_stale_then_fixture(self):
        with TemporaryDirectory() as d:
            cache = Cache(Path(d))
            with mock.patch("clearnight.iss.urllib.request.urlopen",
                            side_effect=OSError("down")):
                self.assertEqual(load_tle(cache, offline=False).source, "fixture")
            cache.put(TLE_KEY, FIXTURE_TLE.encode())
            import os
            old = dt.datetime.now().timestamp() - 25 * 3600
            os.utime(cache.path(TLE_KEY), (old, old))
            with mock.patch("clearnight.iss.urllib.request.urlopen",
                            side_effect=OSError("down")):
                self.assertEqual(load_tle(cache, offline=False).source, "cache-stale")


class TestStructural(unittest.TestCase):
    def test_isspass_fields(self):
        t = dt.datetime(2026, 10, 14, 11, 21, tzinfo=UTC)
        p = ISSPass(t, t, t, 20.0, "S", "SE", "E")
        for f in ("start_utc", "max_utc", "end_utc", "max_alt_deg",
                  "start_dir", "max_dir", "end_dir"):
            self.assertTrue(hasattr(p, f))

    def test_empty_tle_empty_list(self):
        self.assertEqual(visible_passes(DEMO, [], []), [])
        w = _win("2026-10-08", "01:55:00", "02:00:00")
        self.assertEqual(visible_passes(DEMO, [w], []), [])


@unittest.skipUnless(BSP_AVAILABLE, "cache/de421.bsp not present")
class TestPassesAgainstRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sky = json.loads((FIXTURES_DIR / "sky.json").read_text(encoding="utf-8"))
        cls.windows = [
            (n["date_local"],
             DarkWindow(dt.datetime.fromisoformat(n["dark_start_utc"]),
                        dt.datetime.fromisoformat(n["dark_end_utc"])))
            for n in sky["nights"]
        ]
        cls.recorded = sky["iss_passes"]
        cls.computed = {
            date: visible_passes(DEMO, [w], _split_groups(FIXTURE_TLE))
            for date, w in cls.windows
        }

    def test_same_count_as_recorded_per_night(self):
        for date, passes in self.computed.items():
            self.assertEqual(len(passes), len(self.recorded[date]),
                             f"{date}: computed {len(passes)} vs recorded {len(self.recorded[date])}")

    def test_times_within_60s_and_alt_within_1deg(self):
        for date, passes in self.computed.items():
            for p, r in zip(passes, self.recorded[date]):
                for attr, key in (("start_utc", "start_utc"), ("max_utc", "max_utc"),
                                  ("end_utc", "end_utc")):
                    got = getattr(p, attr)
                    want = dt.datetime.fromisoformat(r[key])
                    self.assertLess(abs((got - want).total_seconds()), 60, f"{date} {key}")
                self.assertLess(abs(p.max_alt_deg - r["max_alt_deg"]), 1.0, date)

    def test_directions_in_8_point_set(self):
        pts = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}
        for passes in self.computed.values():
            for p in passes:
                for d in (p.start_dir, p.max_dir, p.end_dir):
                    self.assertIn(d, pts)

    def test_all_max_alt_above_limit(self):
        for passes in self.computed.values():
            for p in passes:
                self.assertGreater(p.max_alt_deg, 10.0)


if __name__ == "__main__":
    unittest.main()
