"""Tests for clearnight.meteors (offline; committed table is source of truth)."""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from clearnight.meteors import MeteorDataError, events_for_night, load_showers

TABLE = Path(__file__).resolve().parent.parent / "data" / "meteor_showers_2026.json"


def _by_name(events):
    return {e.name: e for e in events}


def _write_table(doc: dict) -> Path:
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(doc, tmp)
    tmp.close()
    return Path(tmp.name)


class TestTable(unittest.TestCase):
    def test_load_default_table(self):
        showers = load_showers()
        names = {s.name for s in showers}
        for expected in (
            "Quadrantids", "Lyrids", "eta-Aquariids", "Southern delta-Aquariids",
            "Perseids", "Draconids", "Orionids", "Southern Taurids",
            "Northern Taurids", "Leonids", "Geminids", "Ursids",
        ):
            self.assertIn(expected, names)
        for s in showers:
            self.assertFalse(s.is_peak_night)

    def test_draconids_critical_values(self):
        dra = _by_name(load_showers())["Draconids"]
        self.assertEqual(dra.peak_utc, dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc))
        self.assertEqual(dra.zhr, 10)
        self.assertEqual(dra.radiant_ra_deg, 262)
        self.assertEqual(dra.radiant_dec_deg, 54)
        self.assertEqual(dra.parent_body, "21P/Giacobini-Zinner")
        self.assertEqual(dra.active_start.date(), dt.date(2026, 10, 6))
        self.assertEqual(dra.active_end.date(), dt.date(2026, 10, 10))

    def test_source_recorded(self):
        doc = json.loads(TABLE.read_text(encoding="utf-8"))
        self.assertEqual(doc["_source"], "https://www.imo.net/resources/calendar/")


class TestEventsForNight(unittest.TestCase):
    def setUp(self):
        self.showers = load_showers()

    def test_draconid_peak_night(self):
        events = events_for_night(self.showers, dt.date(2026, 10, 9))
        dra = _by_name(events)["Draconids"]
        self.assertTrue(dra.is_peak_night)

    def test_peak_boundary(self):
        # |peak Oct 9 - night| <= 1 day; Draconids active Oct 6-10 only
        for d, expected in (
            (dt.date(2026, 10, 8), True),
            (dt.date(2026, 10, 10), True),
            (dt.date(2026, 10, 7), False),
        ):
            dra = _by_name(events_for_night(self.showers, d))["Draconids"]
            self.assertEqual(dra.is_peak_night, expected, f"{d}")
        # Oct 11: outside the active window entirely
        self.assertNotIn("Draconids", _by_name(events_for_night(self.showers, dt.date(2026, 10, 11))))

    def test_out_of_season(self):
        # Apr 1: no major shower active (Lyrids start Apr 16)
        events = events_for_night(self.showers, dt.date(2026, 4, 1))
        self.assertEqual([e.name for e in events], [])
        # Apr 20: Lyrids active and flagged peak on Apr 21-23 window only
        ly = _by_name(events_for_night(self.showers, dt.date(2026, 4, 20)))["Lyrids"]
        self.assertFalse(ly.is_peak_night)
        ly = _by_name(events_for_night(self.showers, dt.date(2026, 4, 22)))["Lyrids"]
        self.assertTrue(ly.is_peak_night)

    def test_year_wrap_quadrantids(self):
        # Quadrantids active 12-28..01-12 around the New Year
        events = events_for_night(self.showers, dt.date(2026, 1, 3))
        q = _by_name(events)["Quadrantids"]
        self.assertTrue(q.is_peak_night)
        events = events_for_night(self.showers, dt.date(2026, 1, 12))
        self.assertIn("Quadrantids", _by_name(events))
        # Outside the Jan 2026 season entirely
        events = events_for_night(self.showers, dt.date(2026, 6, 1))
        self.assertNotIn("Quadrantids", _by_name(events))
        # (Next season's Dec 2026 side is next year's table; wrap covered synthetically below.)

    def test_synthetic_wrap(self):
        # Synthetic shower active Dec 30..Jan 03, peak Jan 1
        wrap = _write_table({"year": 2027, "showers": [{
            "name": "Wrapids",
            "peak_utc": "2027-01-01T00:00:00Z",
            "active_start": "12-30",
            "active_end": "01-03",
            "zhr": 5,
            "radiant_ra_deg": 0,
            "radiant_dec_deg": 0,
            "parent": "X/1",
        }]})
        try:
            showers = load_showers(wrap)
            for d, expected in (
                (dt.date(2026, 12, 30), False),
                (dt.date(2026, 12, 31), True),
                (dt.date(2027, 1, 1), True),
                (dt.date(2027, 1, 2), True),
                (dt.date(2027, 1, 3), False),   # still active, but 2 days past peak
                (dt.date(2027, 1, 4), None),    # not active → absent
            ):
                events = events_for_night(showers, d)
                if expected is None:
                    self.assertEqual([e.name for e in events], [])
                else:
                    self.assertIn("Wrapids", _by_name(events), f"{d}")
                    w = _by_name(events)["Wrapids"]
                    self.assertEqual(w.is_peak_night, expected, f"{d}")
        finally:
            wrap.unlink()

    def test_radiant_up_fn_wiring(self):
        fn = lambda ra, dec: 7.5  # noqa: E731
        events = events_for_night(self.showers, dt.date(2026, 10, 9), radiant_up_hours_fn=fn)
        for e in events:
            self.assertEqual(e.radiant_up_hours, 7.5)
        # without fn: field untouched
        events = events_for_night(self.showers, dt.date(2026, 10, 9))
        dra = _by_name(events)["Draconids"]
        self.assertEqual(dra.radiant_up_hours, 0.0)


class TestMalformed(unittest.TestCase):
    def test_bad_json_raises(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        tmp.write("{not json")
        tmp.close()
        try:
            with self.assertRaises(MeteorDataError):
                load_showers(Path(tmp.name))
        finally:
            Path(tmp.name).unlink()

    def test_missing_keys_raises(self):
        p = _write_table({"showers": [{"name": "NoKeys"}]})
        try:
            with self.assertRaises(MeteorDataError) as cm:
                load_showers(p)
            self.assertIn("missing keys", str(cm.exception))
        finally:
            p.unlink()

    def test_missing_file_raises(self):
        with self.assertRaises(MeteorDataError):
            load_showers("/nonexistent/showers.json")


if __name__ == "__main__":
    unittest.main()
