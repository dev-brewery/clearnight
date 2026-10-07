"""Tests for clearnight.conditions (T12)."""

import datetime as dt
import unittest

from clearnight.conditions import assess, dew_risk_label
from clearnight.models import HourWeather, Reading

T0 = dt.datetime(2026, 10, 8, 21, 0, tzinfo=dt.timezone.utc)


def reading_at(minutes: float, **kw) -> Reading:
    return Reading(timestamp_utc=T0 + dt.timedelta(minutes=minutes), **kw)


def reading(hours_ago: float, **kw) -> Reading:
    return Reading(timestamp_utc=T0 - dt.timedelta(hours=hours_ago), **kw)


def weather(hour: int, temperature_c=None, dew_point_c=None) -> HourWeather:
    return HourWeather(
        time_utc=T0.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=hour),
        temperature_c=temperature_c,
        dew_point_c=dew_point_c,
    )


class TestDewRiskLabel(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(dew_risk_label(8.0), "low")
        self.assertEqual(dew_risk_label(7.9), "moderate")
        self.assertEqual(dew_risk_label(3.0), "moderate")
        self.assertEqual(dew_risk_label(2.9), "high")


class TestDewSpread(unittest.TestCase):
    def test_sensor_projected_wins(self):
        readings = [
            reading(3, temperature_c=20.0, dew_point_c=15.0),
            reading(0, temperature_c=21.0, dew_point_c=10.0),
        ]
        c = assess(readings, [weather(0, temperature_c=30.0, dew_point_c=29.0)])
        self.assertEqual(c.dew_spread_c, 11.0)
        self.assertEqual(c.dew_risk, "low")

    def test_forecast_fallback_when_no_readings(self):
        rows = [weather(0, temperature_c=22.0, dew_point_c=20.0),
                weather(1, temperature_c=24.0, dew_point_c=18.0)]
        c = assess([], rows)
        self.assertEqual(c.dew_spread_c, 4.0)  # mean 23.0 - mean 19.0
        self.assertEqual(c.dew_risk, "moderate")

    def test_neither_source_is_high(self):
        c = assess([reading(0, temperature_c=20.0)], [weather(0, temperature_c=22.0)])
        self.assertEqual(c.dew_spread_c, 0.0)
        self.assertEqual(c.dew_risk, "high")  # documented rule: 0.0-when-unknowable -> high


class TestPressureTrend(unittest.TestCase):
    def test_rising(self):
        c = assess([reading(3, pressure_hpa=1013.0), reading(0, pressure_hpa=1016.0)], [])
        self.assertEqual(c.pressure_trend, "rising")
        self.assertEqual(c.trend_hpa_3h, 3.0)

    def test_falling(self):
        c = assess([reading(3, pressure_hpa=1015.0), reading(0, pressure_hpa=1013.0)], [])
        self.assertEqual(c.pressure_trend, "falling")
        self.assertEqual(c.trend_hpa_3h, -2.0)

    def test_flat(self):
        c = assess([reading(3, pressure_hpa=1013.0), reading(0, pressure_hpa=1013.5)], [])
        self.assertEqual(c.pressure_trend, "flat")
        self.assertEqual(c.trend_hpa_3h, 0.5)

    def test_single_reading_unknown(self):
        c = assess([reading(0, pressure_hpa=1013.0)], [])
        self.assertEqual(c.pressure_trend, "unknown")
        self.assertEqual(c.trend_hpa_3h, 0.0)

    def test_old_readings_outside_window_ignored(self):
        c = assess([reading(10, pressure_hpa=1000.0), reading(9, pressure_hpa=1010.0),
                    reading(0, pressure_hpa=1013.0)], [])
        self.assertEqual(c.pressure_trend, "unknown")


class TestForecastVsActual(unittest.TestCase):
    def test_matching_hour(self):
        readings = [reading_at(30, temperature_c=23.9)]  # 21:30 -> floor hour 21:00
        c = assess(readings, [weather(0, temperature_c=22.1), weather(1, temperature_c=23.0)])
        self.assertEqual(c.forecast_vs_actual, "sensor 23.9C vs forecast 22.1C (+1.8)")

    def test_nearest_earlier_hour(self):
        readings = [reading_at(90, temperature_c=20.0)]  # 22:30, only 21:00 available
        c = assess(readings, [weather(0, temperature_c=19.0)])
        self.assertEqual(c.forecast_vs_actual, "sensor 20.0C vs forecast 19.0C (+1.0)")

    def test_no_weather_match(self):
        c = assess([reading_at(30, temperature_c=23.9)], [weather(2, temperature_c=22.0)])
        self.assertIsNone(c.forecast_vs_actual)

    def test_no_reading_temperature(self):
        c = assess([reading_at(0)], [weather(0, temperature_c=22.0)])
        self.assertIsNone(c.forecast_vs_actual)


class TestEmpty(unittest.TestCase):
    def test_all_unknown_no_crash(self):
        c = assess([], [])
        self.assertEqual(c.dew_spread_c, 0.0)
        self.assertEqual(c.dew_risk, "high")
        self.assertEqual(c.pressure_trend, "unknown")
        self.assertEqual(c.trend_hpa_3h, 0.0)
        self.assertIsNone(c.forecast_vs_actual)


if __name__ == "__main__":
    unittest.main()
