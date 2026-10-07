"""Tests for clearnight.sensor — fully offline; urlopen is mocked.

CSV fixture: clearnight/fixtures/sensor.csv, ends 2026-10-07T18:00Z.
Pinned now = 2026-10-07T23:00Z, so read_recent(6) covers 17:00Z..23:00Z.
"""

import datetime as dt
import io
import json
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from clearnight.config import SensorCfg
from clearnight.fixtures import FIXTURES_DIR
from clearnight.models import Reading
from clearnight.sensor import CSVAdapter, HttpJsonAdapter, make_adapter

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 7, 23, 0, 0, tzinfo=UTC)
FIXTURE = FIXTURES_DIR / "sensor.csv"

CSV_CFG = SensorCfg(kind="csv", path=str(FIXTURE))
HTTP_CFG = SensorCfg(kind="http_json", url="http://example.invalid/api",
                     field_map={"timestamp": "attributes.timestamp_utc",
                                "temperature": "attributes.temperature_c",
                                "humidity": "attributes.humidity_pct",
                                "pressure": "attributes.pressure_hpa",
                                "dew_point": "attributes.dew_point_c"})


class TestCSVAdapter(unittest.TestCase):
    def test_reads_recent_from_fixture(self):
        readings = CSVAdapter(Path(FIXTURE)).read_recent(hours=6, now_utc=NOW)
        self.assertGreater(len(readings), 0)
        for r in readings:
            self.assertLess(r.timestamp_utc, NOW + dt.timedelta(seconds=1))
            self.assertGreater(r.timestamp_utc, NOW - dt.timedelta(hours=6))
        # newest-last ordering
        ts = [r.timestamp_utc for r in readings]
        self.assertEqual(ts, sorted(ts))
        # 18:00Z row is the only one within (17:00, 23:00]
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].timestamp_utc, dt.datetime(2026, 10, 7, 18, 0, tzinfo=UTC))

    def test_excludes_older_than_hours(self):
        readings = CSVAdapter(Path(FIXTURE)).read_recent(hours=6, now_utc=NOW)
        self.assertTrue(all(r.timestamp_utc > NOW - dt.timedelta(hours=6) for r in readings))

    def test_empty_values_become_none(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sensor.csv"
            path.write_text(
                "timestamp_utc,temperature_c,humidity_pct,pressure_hpa,dew_point_c\n"
                "2026-10-07T22:00:00Z,21.5,,1012.0,\n", encoding="utf-8")
            readings = CSVAdapter(path).read_recent(hours=6, now_utc=NOW)
            self.assertEqual(len(readings), 1)
            self.assertEqual(readings[0].temperature_c, 21.5)
            self.assertIsNone(readings[0].humidity_pct)
            self.assertEqual(readings[0].pressure_hpa, 1012.0)
            self.assertIsNone(readings[0].dew_point_c)

    def test_malformed_rows_skipped_with_warning(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sensor.csv"
            path.write_text(
                "timestamp_utc,temperature_c,humidity_pct,pressure_hpa,dew_point_c\n"
                "not-a-timestamp,20,50,1012,9\n"          # line 2: bad timestamp
                "2026-10-07T21:00:00Z,abc,50,1012,9\n"    # line 3: non-numeric
                "2026-10-07T22:00:00Z,20.1,50,1012.4,9.3\n",  # line 4: good
                encoding="utf-8")
            with self.assertWarns(UserWarning) as ctx:
                readings = CSVAdapter(path).read_recent(hours=6, now_utc=NOW)
            self.assertIn("line 2", str(ctx.warning))
            self.assertEqual(len(readings), 1)
            self.assertEqual(readings[0].timestamp_utc, dt.datetime(2026, 10, 7, 22, 0, tzinfo=UTC))

    def test_missing_file_returns_empty_list(self):
        with self.assertWarns(UserWarning):
            readings = CSVAdapter(Path("no/such/file.csv")).read_recent(hours=6, now_utc=NOW)
        self.assertEqual(readings, [])


class TestHttpJsonAdapter(unittest.TestCase):
    BODY = json.dumps({
        "attributes": {
            "timestamp_utc": "2026-10-07T22:30:00Z",
            "temperature_c": 18.2,
            "humidity_pct": 47,
            "pressure_hpa": 1011.9,
            "dew_point_c": 7.1,
        }
    }).encode("utf-8")

    def _mock_urlopen(self, body: bytes):
        return mock.patch.object(urllib.request, "urlopen",
                                 mock.mock_open(read_data=body))

    def test_dotted_path_mapping(self):
        with self._mock_urlopen(self.BODY):
            readings = HttpJsonAdapter("http://x", HTTP_CFG.field_map).read_recent(
                hours=6, now_utc=NOW)
        self.assertEqual(len(readings), 1)
        r = readings[0]
        self.assertEqual(r.timestamp_utc, dt.datetime(2026, 10, 7, 22, 30, tzinfo=UTC))
        self.assertEqual(r.temperature_c, 18.2)
        self.assertEqual(r.humidity_pct, 47.0)
        self.assertEqual(r.pressure_hpa, 1011.9)
        self.assertEqual(r.dew_point_c, 7.1)

    def test_absent_timestamp_uses_pinned_now(self):
        body = json.dumps({"temperature_c": 20.0}).encode("utf-8")
        fmap = {"temperature": "temperature_c"}
        with self._mock_urlopen(body):
            readings = HttpJsonAdapter("http://x", fmap).read_recent(hours=6, now_utc=NOW)
        self.assertEqual(readings[0].timestamp_utc, NOW)

    def test_transport_error_returns_empty_with_warning(self):
        def boom(req, timeout):
            raise urllib.error.URLError("connection refused")
        with mock.patch.object(urllib.request, "urlopen", boom):
            with self.assertWarns(UserWarning) as ctx:
                readings = HttpJsonAdapter("http://x", HTTP_CFG.field_map).read_recent(
                    hours=6, now_utc=NOW)
        self.assertIn("URLError", str(ctx.warning))
        self.assertNotIn("http://x", str(ctx.warning))  # URL never echoed into logs
        self.assertEqual(readings, [])

    def test_parse_error_returns_empty_list(self):
        with self._mock_urlopen(b"not json {"):
            readings = HttpJsonAdapter("http://x", HTTP_CFG.field_map).read_recent(
                hours=6, now_utc=NOW)
        self.assertEqual(readings, [])

    def test_user_agent_header(self):
        seen = {}
        def fake_urlopen(req, timeout):
            seen["ua"] = req.headers.get("User-agent")
            raise urllib.error.URLError("stop")
        with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
            HttpJsonAdapter("http://x", HTTP_CFG.field_map).read_recent(6, NOW)
        self.assertEqual(seen["ua"], "clearnight/0.1")


class TestFactory(unittest.TestCase):
    def test_both_kinds_constructed_from_cfg(self):
        a = make_adapter(CSV_CFG)
        b = make_adapter(HTTP_CFG)
        self.assertIsInstance(a, CSVAdapter)
        self.assertIsInstance(b, HttpJsonAdapter)
        # A8: switching adapters is config-only — same call signature
        import inspect
        self.assertEqual(inspect.signature(a.read_recent),
                         inspect.signature(b.read_recent))

    def test_unknown_kind_raises_valueerror(self):
        with self.assertRaises(ValueError):
            make_adapter(SensorCfg(kind="zigbee"))


if __name__ == "__main__":
    unittest.main()
