"""T20: the verified brief wired into both plan pipelines (offline suite).

Online path: urlopen is always mocked (forecast/TLE canned; the example
config's LAN LLM endpoint raises unless a test says otherwise) and the LLM
call itself is stubbed at `clearnight.verify.generate_brief` with canned
replies — a clean computed-only brief and an always-bad brief — so the real
verifier, retry loop, and template fallback run end-to-end. Offline path:
urlopen raises if EVER called, proving the offline plan never attempts the
LLM. Empty-nights path: high-latitude synthetic config, zero dark nights.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from clearnight.__main__ import TEMPLATE_BRIEF_LABEL, run_plan
from clearnight.brief import BriefResult, _mean
from clearnight.fixtures import FIXTURES_DIR
from clearnight.verify import generate_brief

REPO = Path(__file__).resolve().parent.parent
BSP = REPO / "cache" / "de421.bsp"
FORECAST_HOST = "api.open-meteo.com"
TLE_HOST = "celestrak.org"
LLM_HOST = "localhost"


class _Resp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _raising_urlopen(calls: list[str]):
    """Mock that records forecast/TLE URLs and raises if the LLM (or any
    other) URL is ever requested."""

    def urlopen(url, timeout=None):
        u = str(getattr(url, "full_url", url))
        calls.append(u)
        if FORECAST_HOST in u:
            return _Resp((FIXTURES_DIR / "forecast.json").read_bytes())
        if TLE_HOST in u:
            return _Resp((FIXTURES_DIR / "tle.txt").read_bytes())
        raise AssertionError(f"network attempted in offline test: {u!r}")

    return urlopen


class _PlanBase(unittest.TestCase):
    """tmp cwd mirroring the repo layout; stdout captured per run."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="clearnight-t20-"))
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

    def run_plan_capture(self, *argv: str):
        out = io.StringIO()
        with mock.patch("urllib.request.urlopen",
                        _raising_urlopen(self.calls)):
            with contextlib.redirect_stdout(out):
                rc = run_plan(list(argv))
        return rc, out.getvalue()


def _clean_reply(nights, site_name, llm, tz=None, messages=None,
                 offline=False):
    """Canned LLM reply citing ONLY computed values of the nights it is
    handed (the T19 clean-brief pattern, rebuilt from the live pipeline's
    own data so the real verifier passes it)."""
    tz = tz or ZoneInfo("America/Chicago")
    n0 = nights[0]
    local = n0.dark.start_utc.astimezone(tz)
    h12 = local.hour % 12 or 12
    when = f"{h12}:{local.minute:02d} {local.strftime('%p').lower()}"
    cloud = round(_mean([w.cloud_total_pct for w in n0.weather]))
    wind = round(_mean([w.wind_kmh for w in n0.weather]), 1)
    illum = round(n0.moon.illumination_frac * 100)
    shower = n0.showers[0]
    text = (
        f"Tonight at {site_name} go out at {when} under a "
        f"{n0.moon.phase_name} moon {illum} percent lit. Clouds near "
        f"{cloud} percent and wind around {wind} km/h. Watch for the "
        f"{shower.name} with a ZHR of {round(shower.zhr)}."
    )
    return BriefResult(text=text, source="llm", attempts=1, violations=[])


def _bad_reply(nights, site_name, llm, tz=None, messages=None, offline=False):
    """Canned reply with an invented time, a wrong percent, a wrong name
    and a promised count — always bad, every call."""
    return BriefResult(
        text="Go out at 3:27 am under a Full moon 84 percent lit; the "
             "Perseids promise a ZHR of 200 over the southern horizon.",
        source="llm", attempts=1, violations=[])


@unittest.skipUnless(BSP.is_file(), "de421.bsp not in local cache")
class TestOnlineBriefWiring(_PlanBase):
    def setUp(self) -> None:
        super().setUp()
        shutil.copy(BSP, self.tmp / "cache" / "de421.bsp")
        # Plain site name: the claim extractor cannot carry a parenthetical,
        # so the canned reply cites the bare park name (T19 fixture style).
        cfg = (self.tmp / "config.example.toml").read_text(encoding="utf-8")
        (self.tmp / "config.example.toml").write_text(
            cfg.replace('name = "Black Mesa State Park (demo)"',
                        'name = "Black Mesa State Park"'), encoding="utf-8")

    def test_clean_llm_brief_rendered_verified(self) -> None:
        with mock.patch("clearnight.verify.generate_brief", _clean_reply):
            rc, out = self.run_plan_capture("plan", "--nights", "1")
        self.assertEqual(rc, 0)
        self.assertIn("TONIGHT'S BRIEF", out)
        self.assertNotIn(TEMPLATE_BRIEF_LABEL, out)
        self.assertIn("brief: local model, verified - ", out)
        self.assertIn("brief: llm-verified (", out)
        html = (self.tmp / "out" / "plan.html").read_text(encoding="utf-8")
        self.assertIn("TONIGHT'S BRIEF", html)
        self.assertIn("brief: llm-verified (", html)
        # The LLM stub never touched urlopen: no LLM_HOST URL was recorded.
        self.assertFalse([c for c in self.calls if LLM_HOST in c])

    def test_bad_llm_brief_falls_back_to_labeled_template(self) -> None:
        with mock.patch("clearnight.verify.generate_brief", _bad_reply):
            rc, out = self.run_plan_capture("plan", "--nights", "1")
        self.assertEqual(rc, 0)
        # Label wording intact, wrapped across <=80-col text lines.
        self.assertIn("Template brief (LLM output unavailable", out)
        self.assertIn("computed, not generated).", out)
        self.assertIn("brief: template (verification failed:", out)
        html = (self.tmp / "out" / "plan.html").read_text(encoding="utf-8")
        self.assertIn(TEMPLATE_BRIEF_LABEL, html)

    def test_empty_llm_reply_degrades_to_template(self) -> None:
        # Live smoke finding: the model can return blank content (reasoning
        # burned the token budget). An empty "verified" brief must never be
        # rendered; it degrades to the labeled template, honestly labeled.
        def empty_reply(nights, site_name, llm, tz=None, messages=None,
                        offline=False):
            return BriefResult(text="", source="llm", attempts=1,
                               violations=[])

        with mock.patch("clearnight.verify.generate_brief", empty_reply):
            rc, out = self.run_plan_capture("plan", "--nights", "1")
        self.assertEqual(rc, 0)
        self.assertIn("Template brief (LLM output unavailable", out)
        self.assertIn("brief: template (LLM returned an empty reply)", out)
        self.assertNotIn("brief: llm-verified", out)


class TestOfflinePlanNeverCallsLLM(_PlanBase):
    def test_offline_template_no_llm_url(self) -> None:
        rc, out = self.run_plan_capture("plan", "--offline")
        self.assertEqual(rc, 0)
        self.assertIn("Template brief (LLM output unavailable", out)
        self.assertIn("TONIGHT'S BRIEF", out)
        self.assertIn("brief: template (offline; LLM not attempted)", out)
        # urlopen raises on ANY non-forecast/TLE URL, so reaching here with
        # no AssertionError proves the offline plan never attempted the LLM.
        self.assertFalse([c for c in self.calls if LLM_HOST in c])


@unittest.skipUnless(BSP.is_file(), "de421.bsp not in local cache")
class TestEmptyNightsHighLatitude(_PlanBase):
    def test_zero_dark_nights_renders_honest_message(self) -> None:
        cfg = (REPO / "config.example.toml").read_text(encoding="utf-8")
        cfg = cfg.replace('lat = 36.85', 'lat = 78.2')
        cfg = cfg.replace('lon = -102.88', 'lon = 15.6')
        cfg = cfg.replace('tz = "America/Chicago"',
                          'tz = "Arctic/Longyearbyen"')
        cfg = cfg.replace('path = "clearnight/fixtures/sensor.csv"',
                          f'path = "{(FIXTURES_DIR / "sensor.csv").as_posix()}"')
        (self.tmp / "config.example.toml").write_text(cfg, encoding="utf-8")
        # Synthetic zero-dark-nights window (polar summer): the ephemeris
        # path yields no astronomical darkness for any planned night.
        with mock.patch("clearnight.__main__.dark_windows",
                        lambda *a, **k: []):
            rc, out = self.run_plan_capture("plan", "--nights", "3")
        self.assertEqual(rc, 0)
        self.assertIn("dark windows: 0 of 3", out)
        self.assertIn("No nights with astronomical darkness", out)
        self.assertIn("brief: template (no nights with astronomical "
                      "darkness)", out)


if __name__ == "__main__":
    unittest.main()
