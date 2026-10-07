"""Tests for clearnight.models (T02)."""

import dataclasses
import datetime as dt
import unittest

from clearnight.models import (
    Conditions,
    DarkWindow,
    FieldLogEntry,
    HourWeather,
    ISSPass,
    MoonInfo,
    Night,
    NightScore,
    Reading,
    ShowerEvent,
    Site,
)

UTC = dt.timezone.utc


def utc(y, mo, d, h=0, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=UTC)


class ConstructValid(unittest.TestCase):
    """Every dataclass constructs with valid values."""

    def test_site(self):
        s = Site("Black Mesa State Park", 36.85, -102.88, 1450.0, "America/Chicago")
        self.assertEqual(s.name, "Black Mesa State Park")

    def test_hour_weather_full(self):
        w = HourWeather(
            utc(2026, 10, 7, 2), 5.0, 0.0, 2.0, 1.0, 45.0, 4.0, 10.0, 24000.0, 8.0
        )
        self.assertEqual(w.cloud_total_pct, 5.0)

    def test_hour_weather_optional_only(self):
        w = HourWeather(utc(2026, 10, 7, 3))
        self.assertIsNone(w.rh_pct)

    def test_dark_window(self):
        w = DarkWindow(utc(2026, 10, 7, 2), utc(2026, 10, 7, 12))
        self.assertEqual(w.start_utc, utc(2026, 10, 7, 2))

    def test_moon_info(self):
        m = MoonInfo("Waning Crescent", 0.21, None, utc(2026, 10, 7, 13), 0.5, 40.0)
        self.assertIsNone(m.rise_utc)

    def test_shower_event(self):
        e = ShowerEvent(
            "Draconids", utc(2026, 10, 8, 18), utc(2026, 10, 4), utc(2026, 10, 12),
            10.0, 262.0, 54.0, "21P/Giacobini-Zinner", 6.5, True,
        )
        self.assertTrue(e.is_peak_night)

    def test_iss_pass(self):
        p = ISSPass(
            utc(2026, 10, 7, 3, 12), utc(2026, 10, 7, 3, 15), utc(2026, 10, 7, 3, 18),
            55.0, "WNW", "NNE", "NE",
        )
        self.assertEqual(p.max_dir, "NNE")

    def test_conditions(self):
        c = Conditions(6.0, "moderate", "falling", -1.5, None)
        self.assertEqual(c.dew_risk, "moderate")

    def test_night_score(self):
        s = NightScore(
            83, "WORTH IT", 0.95, 0.32, 0.89, 0.5, 1.0, 83.38, 0, 0, 0,
            ["clear skies"],
        )
        self.assertEqual(s.verdict, "WORTH IT")

    def test_night(self):
        n = Night(
            dt.date(2026, 10, 7),
            DarkWindow(utc(2026, 10, 7, 2), utc(2026, 10, 7, 12)),
            MoonInfo("New Moon", 0.01, None, None, 0.5, 30.0),
            [HourWeather(utc(2026, 10, 7, 2), 5.0)],
            Conditions(6.0, "moderate", "flat", 0.0),
            [],
            [],
            None,
        )
        self.assertIsNone(n.score)

    def test_reading(self):
        r = Reading(utc(2026, 10, 7, 1), 10.0, 50.0, 1013.0, 1.0)
        self.assertEqual(r.pressure_hpa, 1013.0)

    def test_reading_all_optional_none(self):
        r = Reading(utc(2026, 10, 7, 1))
        self.assertIsNone(r.temperature_c)

    def test_field_log_entry(self):
        e = FieldLogEntry(dt.date(2026, 10, 7), True, 4, 12, True, "great night", utc(2026, 10, 8, 6))
        self.assertEqual(e.clearness, 4)


class Frozen(unittest.TestCase):
    """Mutation raises FrozenInstanceError."""

    def test_site_frozen(self):
        s = Site("x", 1.0, 2.0, 3.0, "UTC")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            s.lat = 99.0

    def test_night_frozen(self):
        n = Night(
            dt.date(2026, 10, 7),
            DarkWindow(utc(2026, 10, 7, 2), utc(2026, 10, 7, 12)),
            MoonInfo("New Moon", 0.0, None, None, 0.0, 0.0),
            [], Conditions(0.0, "low", "flat", 0.0), [], [],
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            n.score = None

    def test_reading_frozen(self):
        r = Reading(utc(2026, 10, 7, 1))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            r.temperature_c = 1.0


class TypeErrors(unittest.TestCase):
    """Wrong types on required fields raise TypeError naming the field."""

    def test_site_lat(self):
        with self.assertRaises(TypeError) as cm:
            Site("x", "36.85", 0.0, 0.0, "UTC")
        self.assertIn("Site.lat", str(cm.exception))

    def test_dark_window_start_utc(self):
        with self.assertRaises(TypeError) as cm:
            DarkWindow("2026-10-07T02:00Z", utc(2026, 10, 7, 12))
        self.assertIn("DarkWindow.start_utc", str(cm.exception))

    def test_reading_timestamp_utc(self):
        with self.assertRaises(TypeError) as cm:
            Reading(1760000000)
        self.assertIn("Reading.timestamp_utc", str(cm.exception))

    def test_naive_datetime_rejected(self):
        with self.assertRaises(TypeError) as cm:
            Reading(dt.datetime(2026, 10, 7, 1))
        self.assertIn("naive", str(cm.exception))
        with self.assertRaises(TypeError):
            DarkWindow(dt.datetime(2026, 10, 7, 2), utc(2026, 10, 7, 12))


class OptionalFields(unittest.TestCase):
    """Optional fields accept None."""

    def test_moon_rise_set_none(self):
        m = MoonInfo("New Moon", 0.0, None, None, 0.0, 0.0)
        self.assertIsNone(m.set_utc)

    def test_night_score_none(self):
        n = Night(
            dt.date(2026, 10, 7),
            DarkWindow(utc(2026, 10, 7, 2), utc(2026, 10, 7, 12)),
            MoonInfo("New Moon", 0.0, None, None, 0.0, 0.0),
            [], Conditions(0.0, "low", "flat", 0.0), [], [], None,
        )
        self.assertIsNone(n.score)

    def test_conditions_forecast_vs_actual_none(self):
        c = Conditions(0.0, "low", "unknown", 0.0, None)
        self.assertIsNone(c.forecast_vs_actual)


if __name__ == "__main__":
    unittest.main()
