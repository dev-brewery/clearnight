"""T15: render module — red-on-black HTML + <=80-col text (A1, A3, A7)."""

from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

from clearnight.config import Site
from clearnight.models import (
    Conditions,
    DarkWindow,
    HourWeather,
    MoonInfo,
    Night,
    NightScore,
    ShowerEvent,
)
from clearnight.render import (
    TEMPLATE_BRIEF_LABEL,
    Plan,
    render_html,
    render_text,
)

# ---------------------------------------------------------------------------
# Minimal deterministic plan fixture (pure, no network, no fixture files).


def _night(date_iso: str, total: int, verdict: str, *,
           reasons: list[str] | None = None) -> Night:
    d = dt.date.fromisoformat(date_iso)
    window = DarkWindow(
        dt.datetime(d.year, d.month, d.day, 2, 0, tzinfo=dt.timezone.utc),
        dt.datetime(d.year, d.month, d.day + 1, 11, 0, tzinfo=dt.timezone.utc),
    )
    weather = [
        HourWeather(dt.datetime(d.year, d.month, d.day, 3, 0,
                                tzinfo=dt.timezone.utc), cloud_total_pct=12.0),
        HourWeather(dt.datetime(d.year, d.month, d.day, 4, 0,
                                tzinfo=dt.timezone.utc), cloud_total_pct=24.0),
    ]
    moon = MoonInfo(phase_name="New Moon", illumination_frac=0.01,
                    rise_utc=None, set_utc=None, up_fraction=0.0,
                    max_alt_deg=0.0)
    peak = ShowerEvent(
        name="Draconids <Peak&Show>", peak_utc=window.start_utc,
        active_start=window.start_utc, active_end=window.end_utc,
        zhr=10.0, radiant_ra_deg=262.0, radiant_dec_deg=54.0,
        parent_body="21P", radiant_up_hours=9.5, is_peak_night=True,
    )
    score = NightScore(
        total=total, verdict=verdict, cloud_term=1.0,
        moon_term=1.0, transparency_term=0.9, dew_term=1.0, wind_term=1.0,
        base=70.0, meteor_bonus=6, iss_bonus=0, event_bonus=6,
        reasons=reasons or [],
    )
    return Night(d, window, moon, weather,
                 Conditions(dew_spread_c=12.0, dew_risk="low",
                            pressure_trend="flat", trend_hpa_3h=0.0,
                            forecast_vs_actual=None),
                 [peak], [], score)


def _plan() -> Plan:
    site = Site(name="Test <Site&Co>", lat=36.0, lon=-102.0,
                elevation_m=1300.0, tz_name="America/Chicago")
    ranked = [
        _night("2026-10-08", 100, "PRIME"),
        _night("2026-10-12", 15, "STAY IN BED", reasons=["overcast"]),
    ]
    return Plan(site=site, mode="OFFLINE fixture epoch",
                reference_label="2026-10-07", ranked=ranked)


# --------------------------------------------------------------------- html


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_data(self, data):
        self.text.append(data)


class TestRenderHtml(unittest.TestCase):
    def setUp(self) -> None:
        self.out = render_html(_plan())
        self.parser = _Collector()
        self.parser.feed(self.out)

    def test_parses_as_html(self) -> None:
        self.assertIn("html", self.parser.tags)
        self.assertIn("style", self.parser.tags)

    def test_contains_every_night_date_and_verdict(self) -> None:
        for date in ("2026-10-08", "2026-10-12"):
            self.assertIn(date, self.out)
        for verdict in ("PRIME", "STAY IN BED"):
            self.assertIn(verdict, self.out)
        # Every score shown with its verdict band beside it.
        self.assertIn("TOTAL 100", self.out)
        self.assertIn("TOTAL 15", self.out)

    def test_inline_style_no_external_requests(self) -> None:
        self.assertIn("<style>", self.out)
        self.assertNotIn("http://", self.out)
        self.assertNotIn("https://", self.out)
        self.assertNotIn("src=", self.out)
        self.assertNotIn("href=", self.out)

    def test_red_on_black_and_print_css(self) -> None:
        self.assertIn("background: #000", self.out)
        self.assertIn("#ff3b30", self.out)
        self.assertIn("@media print", self.out)

    def test_required_fields_present(self) -> None:
        for marker in ("dark window (local)", "moon", "clouds", "dew risk",
                       "shower:", "PEAK", "iss:", "notes", "overcast",
                       "Template brief"):
            self.assertIn(marker, self.out)

    def test_provenance_footer(self) -> None:
        self.assertIn("<footer>", self.out)
        self.assertIn("Open-Meteo", self.out)
        self.assertIn("CelesTrak", self.out)

    def test_escapes_data_driven_strings(self) -> None:
        self.assertNotIn("<Site&Co>", self.out)
        self.assertIn("&lt;Site&amp;Co&gt;", self.out)
        self.assertIn("Draconids &lt;Peak&amp;Show&gt;", self.out)

    def test_template_label_wording_intact(self) -> None:
        self.assertIn(TEMPLATE_BRIEF_LABEL, self.out)


# --------------------------------------------------------------------- text


class TestRenderText(unittest.TestCase):
    def setUp(self) -> None:
        self.out = render_text(_plan())
        self.lines = self.out.splitlines()

    def test_no_line_exceeds_80_columns(self) -> None:
        for line in self.lines:
            self.assertLessEqual(len(line), 80, repr(line))

    def test_label_wording_intact_exactly_once_across_wrap(self) -> None:
        lines = self.lines
        i = next(n for n, ln in enumerate(lines)
                 if ln.startswith("Template brief ("))
        # The label is wrapped across two lines; wording intact when joined.
        joined = lines[i].strip() + " " + lines[i + 1].strip()
        self.assertEqual(joined, TEMPLATE_BRIEF_LABEL)
        self.assertEqual(self.out.count("Template brief ("), 1)

    def test_every_night_present_with_verdict(self) -> None:
        self.assertIn("night 2026-10-08", self.out)
        self.assertIn("night 2026-10-12", self.out)
        self.assertIn("total 100 PRIME", self.out)
        self.assertIn("total 15 STAY IN BED", self.out)

    def test_required_fields_present(self) -> None:
        for marker in ("dark window (local)", "moon:", "clouds:", "dew risk:",
                       "shower:", "PEAK", "iss:", "notes:"):
            self.assertIn(marker, self.out)


# ---------------------------------------------------------------------- CLI


class TestCliWritesNewHtml(unittest.TestCase):
    def test_plan_offline_writes_red_on_black_html(self) -> None:
        import contextlib
        import io
        import os
        import shutil
        import socket
        from unittest import mock

        from clearnight.__main__ import run_plan

        repo = Path(__file__).resolve().parent.parent
        tmp = Path(tempfile.mkdtemp(prefix="clearnight-render-"))
        shutil.copy(repo / "config.example.toml", tmp / "config.example.toml")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        cwd = Path.cwd()
        os.chdir(tmp)
        self.addCleanup(os.chdir, cwd)

        class _NoConnect(socket.socket):
            def connect(self, address):
                raise AssertionError(f"network connect: {address!r}")

        with mock.patch("socket.socket", _NoConnect), \
                contextlib.redirect_stdout(io.StringIO()):
            rc = run_plan(["plan", "--offline"])
        self.assertEqual(rc, 0)
        out = (tmp / "out" / "plan.html").read_text(encoding="utf-8")
        self.assertIn("background: #000", out)
        self.assertIn("#ff3b30", out)
        self.assertIn("<style>", out)


if __name__ == "__main__":
    unittest.main()
