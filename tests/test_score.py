"""T13 tests — scoring per ARCHITECTURE.md §5 (ratified D5 v2).

Worked-example inputs are the §5 numbers verbatim.
"""

from __future__ import annotations

import datetime as dt
import unittest

from clearnight.models import (
    DarkWindow,
    HourWeather,
    ISSPass,
    MoonInfo,
    Night,
    NightScore,
    ShowerEvent,
)
from clearnight.score import rank, score_night, verdict_label

UTC = dt.timezone.utc
D = dt.datetime


def weather(cloud=5.0, rh=45.0, vis=24000.0, wind=8.0):
    return [
        HourWeather(D(2026, 10, 7, 3, tzinfo=UTC), cloud_total_pct=cloud, rh_pct=rh,
                    visibility_m=vis, wind_kmh=wind),
        HourWeather(D(2026, 10, 7, 4, tzinfo=UTC), cloud_total_pct=cloud, rh_pct=rh,
                    visibility_m=vis, wind_kmh=wind),
    ]


WINDOW = DarkWindow(D(2026, 10, 7, 3, tzinfo=UTC), D(2026, 10, 7, 5, tzinfo=UTC))


def moon(illum, up):
    return MoonInfo("Full Moon", illum, None, None, up, 40.0)


def peak_shower(up=3.0):
    return ShowerEvent("Draconids", D(2026, 10, 7, 12, tzinfo=UTC),
                       D(2026, 10, 5, tzinfo=UTC), D(2026, 10, 9, tzinfo=UTC),
                       150.0, 262.0, 54.0, "21P/Giacobini-Zinner",
                       radiant_up_hours=up, is_peak_night=True)


def iss_pass(alt=45.0):
    return ISSPass(D(2026, 10, 7, 3, tzinfo=UTC), D(2026, 10, 7, 3, 5, tzinfo=UTC),
                   D(2026, 10, 7, 3, 10, tzinfo=UTC), alt, "NW", "N", "NE")


def score(cloud=5.0, illum=0.01, up=0.5, spread=6.0, rh=45.0, vis=24000.0,
          wind=8.0, showers=None, iss=None):
    return score_night(WINDOW, moon(illum, up), weather(cloud=cloud, rh=rh, vis=vis, wind=wind),
                       spread, showers or [], iss or [])


class WorkedExamples(unittest.TestCase):
    """The four §5 worked examples, numbers verbatim."""

    def test_example_a_prime_100(self):
        s = score(showers=[peak_shower(3.0)], iss=[iss_pass(45.0)])
        self.assertEqual(s.total, 100)
        self.assertEqual(s.verdict, "PRIME")
        self.assertAlmostEqual(s.base, 93.52, places=2)

    def test_example_b_full_moon_83(self):
        s = score(illum=1.0, up=0.8)
        self.assertEqual(s.total, 83)
        self.assertEqual(s.verdict, "WORTH IT")
        self.assertAlmostEqual(s.base, 83.38, places=2)

    def test_example_c_full_moon_all_night_81(self):
        s = score(illum=1.0, up=1.0)
        self.assertEqual(s.total, 81)
        self.assertEqual(s.verdict, "WORTH IT")
        self.assertAlmostEqual(s.base, 80.83, places=2)

    def test_example_d_overcast_8(self):
        s = score(cloud=90.0, illum=1.0, up=1.0, spread=1.0, rh=70.0,
                  vis=10000.0, wind=25.0)
        self.assertEqual(s.total, 8)
        self.assertEqual(s.verdict, "STAY IN BED")
        self.assertIn("overcast", s.reasons)

    def test_ordering_a5(self):
        totals = [score(showers=[peak_shower(3.0)], iss=[iss_pass(45.0)]).total,
                  score(illum=1.0, up=0.8).total,
                  score(illum=1.0, up=1.0).total,
                  score(cloud=90.0, illum=1.0, up=1.0, spread=1.0, rh=70.0,
                        vis=10000.0, wind=25.0).total]
        self.assertEqual(totals, [100, 83, 81, 8])


class OvercastCap(unittest.TestCase):
    def test_cap_binds_at_86_cloud(self):
        # §5 cap-binding variant: Example B weather, cloud 86%, peak + ISS.
        s = score(cloud=86.0, illum=0.01, up=0.5, showers=[peak_shower(3.0)],
                  iss=[iss_pass(45.0)])
        self.assertAlmostEqual(s.base, 57.07, places=2)
        self.assertEqual(s.total, 15)
        self.assertIn("overcast", s.reasons)
        self.assertEqual(s.verdict, "STAY IN BED")

    def test_uncapped_at_84_cloud(self):
        s = score(cloud=84.0, illum=0.01, up=0.5, showers=[peak_shower(3.0)],
                  iss=[iss_pass(45.0)])
        self.assertEqual(s.total, 66)
        self.assertNotIn("overcast", s.reasons)

    def test_cap_cannot_fire_when_cloud_entirely_missing(self):
        w = [HourWeather(D(2026, 10, 7, 3, tzinfo=UTC), rh_pct=45.0,
                         visibility_m=24000.0, wind_kmh=8.0)]
        s = score_night(WINDOW, moon(0.01, 0.5), w, 6.0,
                        [peak_shower(3.0)], [iss_pass(45.0)])
        self.assertEqual(s.cloud_term, 0.0)
        self.assertIn("cloud data missing", s.reasons)
        self.assertNotIn("overcast", s.reasons)


class WindCliff(unittest.TestCase):
    def wind_term(self, kmh):
        return score(wind=kmh).wind_term

    def test_cliff(self):
        self.assertEqual(self.wind_term(15), 1.0)
        self.assertEqual(self.wind_term(20), 0.5)
        self.assertEqual(self.wind_term(25), 0.0)


class VerdictBands(unittest.TestCase):
    def test_boundaries(self):
        cases = [(85, "PRIME"), (84, "WORTH IT"), (70, "WORTH IT"),
                 (69, "Marginal"), (50, "Marginal"), (49, "Poor"),
                 (35, "Poor"), (34, "STAY IN BED")]
        for total, expected in cases:
            self.assertEqual(verdict_label(total), expected, f"total {total}")

    def test_score_night_sets_verdict(self):
        self.assertEqual(score().verdict, "PRIME")


class A5Orderings(unittest.TestCase):
    def test_dewier_spread_lowers_total(self):
        self.assertGreater(score(spread=6.0).total, score(spread=1.0).total)

    def test_peak_shower_raises_total(self):
        self.assertGreater(score(showers=[peak_shower(3.0)]).total, score().total)

    def test_meteor_bonus_rules(self):
        s = score(showers=[peak_shower(3.0)])
        self.assertEqual(s.meteor_bonus, 6)
        s = score(showers=[ShowerEvent("Orionids", D(2026, 10, 21, tzinfo=UTC),
                                       D(2026, 10, 2, tzinfo=UTC), D(2026, 11, 7, tzinfo=UTC),
                                       25.0, 95.0, 16.0, "1P/Halley", radiant_up_hours=2.0)])
        self.assertEqual(s.meteor_bonus, 2)
        self.assertEqual(score().meteor_bonus, 0)
        self.assertEqual(score(showers=[peak_shower(0.5)]).meteor_bonus, 0)

    def test_iss_bonus_cap(self):
        self.assertEqual(score(iss=[iss_pass(45.0)]).iss_bonus, 2)
        self.assertEqual(score(iss=[iss_pass(30.0)]).iss_bonus, 0)
        three = score(iss=[iss_pass(70.0)] * 3)
        self.assertEqual(three.iss_bonus, 4)  # min(4, 6)
        self.assertEqual(three.event_bonus, 4)


class EmptyRules(unittest.TestCase):
    def test_no_window(self):
        s = score_night(None, moon(0.01, 0.5), weather(), 6.0, [], [])
        self.assertEqual(s.total, 0)
        self.assertEqual(s.reasons, ["no astronomical darkness"])
        self.assertEqual(s.verdict, "STAY IN BED")

    def test_no_weather(self):
        s = score_night(WINDOW, moon(0.01, 0.5), [], 6.0, [], [])
        self.assertEqual(s.total, 0)
        self.assertEqual(s.reasons, ["no forecast data"])

    def test_all_none_terms(self):
        w = [HourWeather(D(2026, 10, 7, 3, tzinfo=UTC))]
        s = score_night(WINDOW, moon(0.01, 0.5), w, 6.0, [], [])
        for term in (s.cloud_term, s.transparency_term, s.wind_term):
            self.assertEqual(term, 0.0)
        for reason in ("cloud data missing", "humidity data missing",
                       "visibility data missing", "wind data missing"):
            self.assertIn(reason, s.reasons)


class RankTests(unittest.TestCase):
    def make(self, date, total):
        night = Night(
            date, WINDOW, moon(0.01, 0.5), weather(),
            __import__("clearnight.models", fromlist=["Conditions"]).Conditions(
                6.0, "low", "flat", 0.0),
            [], [],
        )
        if total is not None:
            night = Night(
                night.date_local, night.dark, night.moon, night.weather,
                night.conditions, night.showers, night.iss_passes,
                NightScore(total, "PRIME", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0),
            )
        return night

    def test_rank(self):
        d1, d2, d3 = dt.date(2026, 10, 7), dt.date(2026, 10, 8), dt.date(2026, 10, 9)
        nights = [self.make(d3, 50), self.make(d2, 83), self.make(d1, 50),
                  self.make(d2.replace(year=2027), None)]
        ranked = rank(nights)
        self.assertEqual([n.date_local for n in ranked], [d2, d1, d3, d2.replace(year=2027)])


if __name__ == "__main__":
    unittest.main()
