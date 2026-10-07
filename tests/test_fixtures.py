"""Tests for committed fixtures + epoch pinning (T06). Offline, no network."""

from __future__ import annotations

import csv
import datetime as dt
import json
import unittest
from zoneinfo import ZoneInfo

from clearnight import fixtures

FDIR = fixtures.FIXTURES_DIR


class TestManifest(unittest.TestCase):
    def test_manifest_loads_and_reference_date_parses(self) -> None:
        m = fixtures.load_manifest()
        self.assertEqual(m["reference_date"], "2026-10-07")
        self.assertEqual(dt.date.fromisoformat(m["reference_date"]),
                         dt.date(2026, 10, 7))

    def test_resolve_today_offline_pins_epoch(self) -> None:
        tz = ZoneInfo("America/Chicago")
        self.assertEqual(fixtures.resolve_today(offline=True, tz=tz),
                         dt.date(2026, 10, 7))

    def test_resolve_today_online_uses_tz_today(self) -> None:
        tz = ZoneInfo("America/Chicago")
        self.assertEqual(fixtures.resolve_today(offline=False, tz=tz),
                         dt.datetime.now(tz).date())


class TestForecastFixture(unittest.TestCase):
    def test_forecast_json_valid_and_arrays_equal_length(self) -> None:
        data = json.loads((FDIR / "forecast.json").read_text(encoding="utf-8"))
        hourly = data["hourly"]
        lengths = {len(v) for k, v in hourly.items()
                   if k != "time" and isinstance(v, list)}
        self.assertGreaterEqual(len(hourly["time"]), 24)
        self.assertEqual(len(lengths), 1)  # all arrays equal length


class TestTLEFixture(unittest.TestCase):
    def test_tle_contains_iss_and_complete_groups(self) -> None:
        text = (FDIR / "tle.txt").read_text(encoding="utf-8")
        self.assertIn("ISS (ZARYA)", text)
        lines = [ln for ln in text.splitlines() if ln.strip()]
        self.assertTrue(lines)
        for i in range(0, len(lines), 3):
            group = lines[i:i + 3]
            self.assertEqual(len(group), 3)
            self.assertTrue(group[1].startswith("1 "))
            self.assertTrue(group[2].startswith("2 "))
            self.assertIn("ISS (ZARYA)", group[0])


class TestSensorFixture(unittest.TestCase):
    def test_sensor_csv_header_and_rows(self) -> None:
        with open(FDIR / "sensor.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["timestamp_utc", "temperature_c",
                                   "humidity_pct", "pressure_hpa",
                                   "dew_point_c"])
        self.assertGreaterEqual(len(rows), 7)  # header + >=6 data rows
        for row in rows[1:]:
            ts = row[0]
            self.assertTrue(ts.endswith("Z"), ts)
            dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    unittest.main()
