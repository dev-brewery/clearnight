"""Tests for clearnight.forecast — fully offline; urlopen is mocked or
asserted never to be called. Fixture: clearnight/fixtures/forecast.json,
fixed range 2026-10-06T00:00Z .. 2026-10-14T23:00Z (216 hours)."""

import datetime as dt
import json
import shutil
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from clearnight.cache import Cache
from clearnight.fixtures import FIXTURES_DIR
from clearnight.forecast import (
    HOURLY_VARS,
    TIMEOUT_S,
    build_url,
    cache_key,
    fetch_hourly,
    slice_to_window,
)
from clearnight.models import DarkWindow, Site

DEMO = Site(name="demo", lat=36.85, lon=-102.88, elevation_m=1300.0,
            tz_name="America/Chicago")
UTC = dt.timezone.utc
FIXTURE = FIXTURES_DIR / "forecast.json"
FIXTURE_BYTES = FIXTURE.read_bytes()


def _t(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


class TestParse(unittest.TestCase):
    def test_fixture_parses_full_count(self):
        from clearnight.forecast import _parse_hourly
        hours = _parse_hourly(FIXTURE_BYTES)
        self.assertEqual(len(hours), 216)
        first = hours[0]
        self.assertEqual(first.time_utc, _t("2026-10-06T00:00"))
        self.assertIsNotNone(first.cloud_total_pct)
        self.assertIsNotNone(first.temperature_c)
        self.assertIsInstance(first.visibility_m, float)

    def test_missing_variable_maps_to_none_no_crash(self):
        doc = json.loads(FIXTURE_BYTES.decode("utf-8"))
        del doc["hourly"]["visibility"]
        raw = json.dumps(doc).encode("utf-8")
        from clearnight.forecast import _parse_hourly
        hours = _parse_hourly(raw)
        self.assertEqual(len(hours), 216)
        self.assertTrue(all(h.visibility_m is None for h in hours))
        self.assertIsNotNone(hours[0].cloud_total_pct)

    def test_missing_value_maps_to_none(self):
        doc = json.loads(FIXTURE_BYTES.decode("utf-8"))
        doc["hourly"]["cloud_cover"][3] = None
        raw = json.dumps(doc).encode("utf-8")
        from clearnight.forecast import _parse_hourly
        hours = _parse_hourly(raw)
        self.assertIsNone(hours[3].cloud_total_pct)

    def test_length_mismatch_raises(self):
        doc = json.loads(FIXTURE_BYTES.decode("utf-8"))
        doc["hourly"]["cloud_cover"] = doc["hourly"]["cloud_cover"][:-1]
        raw = json.dumps(doc).encode("utf-8")
        from clearnight.forecast import _parse_hourly
        with self.assertRaises(ValueError):
            _parse_hourly(raw)


class TestURL(unittest.TestCase):
    def test_url_pinned_vars_dates_timezone(self):
        start = _t("2026-10-06T21:00")
        url = build_url(DEMO, start, 12)
        self.assertIn("latitude=36.85", url)
        self.assertIn("longitude=-102.88", url)
        self.assertIn(f"hourly={','.join(HOURLY_VARS)}", url)
        self.assertIn("start_date=2026-10-06", url)
        self.assertIn("end_date=2026-10-07", url)  # ceil to whole days
        self.assertIn("timezone=UTC", url)
        self.assertTrue(url.startswith("https://api.open-meteo.com/v1/forecast?"))

    def test_urlopen_receives_exact_url_and_timeout(self):
        with TemporaryDirectory() as tmp:
            cache = Cache(Path(tmp))
            start = _t("2026-10-06T21:00")
            with mock.patch.object(urllib.request, "urlopen") as m:
                m.return_value.__enter__.return_value.read.return_value = FIXTURE_BYTES
                fetch_hourly(DEMO, start, 12, cache, offline=False)
            args, kwargs = m.call_args
            self.assertEqual(args[0], build_url(DEMO, start, 12))
            self.assertEqual(kwargs.get("timeout"), TIMEOUT_S)


class TestCacheBehaviour(unittest.TestCase):
    START = _t("2026-10-08T21:00")

    def _fetch(self, tmp, offline, expect_network=True, stale=False):
        cache = Cache(Path(tmp))
        key = cache_key(DEMO, self.START)
        if stale:
            cache.put(key, FIXTURE_BYTES)
            old = (Path(tmp) / key)
            import os
            past = __import__("time").time() - 7200
            os.utime(old, (past, past))
        with mock.patch.object(urllib.request, "urlopen") as m:
            if expect_network:
                m.return_value.__enter__.return_value.read.return_value = FIXTURE_BYTES
            hours = fetch_hourly(DEMO, self.START, 10, cache, offline=offline)
            called = m.called
        return hours, called

    def test_fresh_cache_skips_network(self):
        with TemporaryDirectory() as tmp:
            cache = Cache(Path(tmp))
            cache.put(cache_key(DEMO, self.START), FIXTURE_BYTES)
            with mock.patch.object(urllib.request, "urlopen") as m:
                hours = fetch_hourly(DEMO, self.START, 10, cache, offline=False)
            self.assertFalse(m.called)
            self.assertEqual(len(hours), 10)

    def test_stale_cache_falls_back_without_network(self):
        with TemporaryDirectory() as tmp:
            hours, called = self._fetch(tmp, offline=False, expect_network=False,
                                        stale=True)
            self.assertFalse(called)
            self.assertEqual(len(hours), 10)

    def test_no_cache_network_error_uses_fixture(self):
        with TemporaryDirectory() as tmp:
            with TemporaryDirectory() as tmp2:
                cache = Cache(Path(tmp2))
                with mock.patch.object(
                    urllib.request, "urlopen",
                    side_effect=OSError("network down"),
                ):
                    hours = fetch_hourly(DEMO, self.START, 10, cache,
                                         offline=False)
            self.assertEqual(len(hours), 10)
            self.assertEqual(hours[0].time_utc, self.START)

    def test_offline_no_cache_uses_fixture(self):
        with TemporaryDirectory() as tmp:
            cache = Cache(Path(tmp))
            with mock.patch.object(urllib.request, "urlopen") as m:
                hours = fetch_hourly(DEMO, self.START, 10, cache, offline=True)
            self.assertFalse(m.called)
            self.assertEqual(len(hours), 10)

    def test_request_outside_fixture_range_returns_empty(self):
        with TemporaryDirectory() as tmp:
            cache = Cache(Path(tmp))
            start = _t("2026-11-01T00:00")
            with mock.patch.object(urllib.request, "urlopen",
                                   side_effect=OSError("down")):
                hours = fetch_hourly(DEMO, start, 6, cache, offline=False)
            self.assertEqual(hours, [])

    def test_request_partially_outside_is_clipped(self):
        with TemporaryDirectory() as tmp:
            cache = Cache(Path(tmp))
            start = _t("2026-10-13T20:00")
            with mock.patch.object(urllib.request, "urlopen",
                                   side_effect=OSError("down")):
                hours = fetch_hourly(DEMO, start, 8, cache, offline=False)
            # Request ends 2026-10-14T04:00, inside the fixture -> 8 hours.
            self.assertEqual(len(hours), 8)


class TestSliceToWindow(unittest.TestCase):
    def _hours(self, count, start="2026-10-08T00:00"):
        t0 = _t(start)
        from clearnight.models import HourWeather
        return [HourWeather(time_utc=t0 + dt.timedelta(hours=i),
                            cloud_total_pct=float(i)) for i in range(count)]

    def test_inclusive_both_bounds(self):
        weather = self._hours(30)
        win = DarkWindow(_t("2026-10-08T21:00"), _t("2026-10-09T02:00"))
        got = slice_to_window(weather, win)
        self.assertEqual([h.time_utc for h in got],
                         [_t(f"2026-10-08T{h:02d}") for h in (21, 22, 23)] +
                         [_t("2026-10-09T00"), _t("2026-10-09T01"),
                          _t("2026-10-09T02")])

    def test_outside_window_empty(self):
        weather = self._hours(24)
        win = DarkWindow(_t("2026-10-09T21:00"), _t("2026-10-09T23:00"))
        self.assertEqual(slice_to_window(weather, win), [])


if __name__ == "__main__":
    unittest.main()
