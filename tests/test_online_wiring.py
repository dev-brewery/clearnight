"""T16: online path wiring, mocked urlopen (offline test suite).

The bsp-dependent live-sky tests run only when the local ephemeris cache has
de421.bsp (copying the committed-on-this-machine cache file into the tmp cwd,
never downloading). urlopen is always mocked here; the suite stays offline.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from clearnight.__main__ import run_plan
from clearnight.fixtures import FIXTURES_DIR

REPO = Path(__file__).resolve().parent.parent
BSP = REPO / "cache" / "de421.bsp"
FORECAST_HOST = "api.open-meteo.com"
TLE_HOST = "celestrak.org"
LLM_HOST = "localhost"  # example config's llama.cpp endpoint
SENSOR_HOST = "ha-mock.test"  # T27: mocked HA sensor endpoint

# Owner's HA mock presets (T27): dummy values, never real site data.
_DRY_BODY = (b'{"temperature_c": 21.4, "humidity_pct": 48, '
             b'"pressure_hpa": 1013.2, "dew_point_c": 10.1, '
             b'"last_updated": "2025-10-09T01:00:00+00:00"}')
_BROKEN_BODY = b'{"temperature_c": 12.0}'  # humidity missing


class _Resp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(calls: list[str], forecast_payload: bytes, tle_payload: bytes,
                  sensor_payload: bytes | Exception | None = None):
    def urlopen(url, timeout=None):
        u = str(getattr(url, "full_url", url))
        if SENSOR_HOST in u:  # T27: mocked HA sensor endpoint
            if isinstance(sensor_payload, Exception):
                raise sensor_payload
            return _Resp(sensor_payload)  # type: ignore[arg-type]
        if LLM_HOST in u:  # not counted: LLM attempts are not data sources
            raise OSError("llm endpoint unreachable (mock)")
        calls.append(u)
        if FORECAST_HOST in calls[-1]:
            return _Resp(forecast_payload)
        if TLE_HOST in calls[-1]:
            return _Resp(tle_payload)
        raise AssertionError(f"unexpected URL: {url!r}")

    return urlopen


class OnlineBase(unittest.TestCase):
    """tmp cwd mirroring the repo layout; stdout captured per run."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="clearnight-online-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        shutil.copy(REPO / "config.example.toml",
                    self.tmp / "config.example.toml")
        (self.tmp / "cache").mkdir()
        (self.tmp / "clearnight" / "fixtures").mkdir(parents=True)
        shutil.copy(FIXTURES_DIR / "sensor.csv",
                    self.tmp / "clearnight" / "fixtures" / "sensor.csv")
        self.cwd = Path.cwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self.cwd)
        self.calls: list[str] = []

    def run_online(self, *argv: str, sensor_payload: bytes | Exception | None = None) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch("urllib.request.urlopen",
                        _fake_urlopen(self.calls,
                                      (FIXTURES_DIR / "forecast.json")
                                      .read_bytes(),
                                      (FIXTURES_DIR / "tle.txt").read_bytes(),
                                      sensor_payload=sensor_payload)):
            with contextlib.redirect_stdout(out):
                rc = run_plan(["plan", "--nights", "1", *argv])
        return rc, out.getvalue()


@unittest.skipUnless(BSP.is_file(), "de421.bsp not in local cache")
class TestSensorProvenanceHttpJson(OnlineBase):
    """T27: the footer states the sensor read outcome, never overstates."""

    def setUp(self) -> None:
        super().setUp()
        cfg = (REPO / "config.example.toml").read_text(encoding="utf-8")
        cfg = cfg.replace(
            '[sensor]\nkind = "csv"\npath = "clearnight/fixtures/sensor.csv"',
            '[sensor]\nkind = "http_json"\n'
            f'url = "http://{SENSOR_HOST}/api/states/sensor.mock"\n'
            'field_map = { timestamp = "last_updated", '
            'temperature = "temperature_c", humidity = "humidity_pct", '
            'pressure = "pressure_hpa", dew_point = "dew_point_c" }')
        (self.tmp / "config.example.toml").write_text(cfg, encoding="utf-8")

    def test_dry_preset_footer_live_and_low_risk(self) -> None:
        rc, out = self.run_online(sensor_payload=_DRY_BODY)
        self.assertEqual(rc, 0)
        self.assertIn("sensor: http_json (live, 1 reading @ "
                      "2025-10-09T01:00:00+00:00)", out)
        self.assertIn("spread 11.3C", out)
        self.assertIn("dew risk: low", out)
        html = (self.tmp / "out" / "plan.html").read_text(encoding="utf-8")
        self.assertIn("sensor: http_json (live, 1 reading @ "
                      "2025-10-09T01:00:00+00:00)", html)

    def test_401_footer_degraded_exit_zero_no_traceback(self) -> None:
        err = urllib.error.HTTPError(
            f"http://{SENSOR_HOST}/api/states/sensor.mock", 401,
            "Unauthorized", None, None)
        rc, out = self.run_online(sensor_payload=err)
        self.assertEqual(rc, 0)
        self.assertIn("sensor: http_json (degraded: HTTPError"
                      " - dew input falls back to forecast)", out)
        self.assertNotIn("Traceback", out)
        html = (self.tmp / "out" / "plan.html").read_text(encoding="utf-8")
        self.assertIn("degraded: HTTPError", html)

    def test_missing_humidity_still_live_and_renders(self) -> None:
        rc, out = self.run_online(sensor_payload=_BROKEN_BODY)
        self.assertEqual(rc, 0)
        self.assertIn("sensor: http_json (live, 1 reading @ ", out)
        self.assertNotIn("degraded", out)


@unittest.skipUnless(BSP.is_file(), "de421.bsp not in local cache")
class TestOnlineCacheThrough(OnlineBase):
    def setUp(self) -> None:
        super().setUp()
        shutil.copy(BSP, self.tmp / "cache" / "de421.bsp")

    def test_first_run_hits_network_once_second_run_cache_only(self) -> None:
        rc1, out1 = self.run_online()
        self.assertEqual(rc1, 0)
        self.assertIn("ONLINE", out1)
        forecast_hits = [c for c in self.calls if FORECAST_HOST in c]
        tle_hits = [c for c in self.calls if TLE_HOST in c]
        self.assertEqual(len(forecast_hits), 1, self.calls)
        self.assertEqual(len(tle_hits), 1, self.calls)
        self.assertIn("forecast: network", out1)

        before = len(self.calls)
        rc2, out2 = self.run_online()
        self.assertEqual(rc2, 0)
        self.assertEqual(len(self.calls), before, "network hit on second run")
        self.assertIn("forecast: cache", out2)
        self.assertIn("TLE: CelesTrak via cache", out2)
        self.assertIn("ephemeris: de421.bsp (cache)", out2)
        html = (self.tmp / "out" / "plan.html").read_text(encoding="utf-8")
        self.assertIn("ONLINE", html)

    def test_forecast_network_failure_still_renders(self) -> None:
        def urlopen(url, timeout=None):
            self.calls.append(str(getattr(url, "full_url", url)))
            if FORECAST_HOST in self.calls[-1]:
                raise OSError("network down")
            return _Resp((FIXTURES_DIR / "tle.txt").read_bytes())

        with mock.patch("urllib.request.urlopen", urlopen):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = run_plan(["plan", "--nights", "1"])
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("forecast: network unavailable; committed fixture "
                      "fallback", text)
        self.assertTrue((self.tmp / "out" / "plan.html").is_file())


class TestTLEStaleCacheNote(OnlineBase):
    def test_stale_tle_footer_note_without_bsp(self) -> None:
        # Seed a stale TLE cache entry; no bsp, network dead -> degraded run
        # that must still exit 0 with the staleness footer note.
        stale = self.tmp / "cache" / "celestrak_iss.txt"
        stale.write_bytes((FIXTURES_DIR / "tle.txt").read_bytes())
        old = time.time() - 3 * 24 * 3600
        os.utime(stale, (old, old))

        def urlopen(url, timeout=None):
            self.calls.append(str(getattr(url, "full_url", url)))
            raise OSError("network down")

        # skyfield's loader binds urlopen at import time; block it too so the
        # missing-bsp path cannot touch the network.
        from skyfield import iokit as _iokit

        with mock.patch("urllib.request.urlopen", urlopen), \
                mock.patch.object(_iokit, "urlopen", urlopen):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = run_plan(["plan", "--nights", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("TLE: cache-stale (passes may be off)", out.getvalue())
        self.assertTrue((self.tmp / "out" / "plan.html").is_file())


if __name__ == "__main__":
    unittest.main()
