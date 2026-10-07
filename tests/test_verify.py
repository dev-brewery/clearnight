"""T19: verifier — claim extraction, checking, retry loop, fallback.

All canned: no network. Nights are deterministic demo-site-shaped objects
(America/Chicago); the retry loop uses a stubbed generate function.
"""

from __future__ import annotations

import datetime as dt
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from clearnight.brief import BriefResult
from clearnight.config import LLMCfg
from clearnight.models import (
    Conditions,
    DarkWindow,
    HourWeather,
    ISSPass,
    MoonInfo,
    Night,
    NightScore,
    ShowerEvent,
)
from clearnight.verify import (
    Claims,
    check_claims,
    extract_claims,
    verified_brief,
)

TZ = ZoneInfo("America/Chicago")
CFG = LLMCfg("http://llm-box.local/v1", "demo-model", timeout_s=17)


def _utc(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone.utc)


def _night(date_local: dt.date, *, dirs=("NW", "N", "NE"), max_alt=34.0) -> Night:
    start = _utc(2026, 10, 7, 1, 14)  # 8:14 pm CDT
    weather = [
        HourWeather(_utc(2026, 10, 7, 2, 0), cloud_total_pct=10.0, rh_pct=40.0,
                    wind_kmh=8.0, visibility_m=15000.0),
        HourWeather(_utc(2026, 10, 7, 3, 0), cloud_total_pct=14.0, rh_pct=44.0,
                    wind_kmh=8.4, visibility_m=15600.0),
    ]
    return Night(
        date_local=date_local,
        dark=DarkWindow(start, _utc(2026, 10, 7, 11, 2)),  # 6:02 am CDT
        moon=MoonInfo("Waxing Crescent", 0.03, None,
                      _utc(2026, 10, 7, 1, 30), 0.10, 12.0),  # set 8:30 pm
        weather=weather,
        conditions=Conditions(4.0, "low", "flat", 0.0),
        showers=[ShowerEvent("Draconids", _utc(2026, 10, 8, 22, 0),
                             _utc(2026, 10, 6, 0, 0), _utc(2026, 10, 10, 0, 0),
                             10.0, 262.0, 54.0, "21P", 5.1, True)],
        iss_passes=[ISSPass(start, _utc(2026, 10, 7, 1, 18),
                            _utc(2026, 10, 7, 1, 22), max_alt,
                            dirs[0], dirs[1], dirs[2])],
        score=NightScore(100, "PRIME", -3.0, -1.0, 4.0, 5.0, 5.0, 90.0,
                         10, 5, 0, ["dark, moonless"]),
    )


def _nights(n=3, **kw) -> list[Night]:
    base = dt.date(2026, 10, 6)  # a Tuesday
    return [_night(base + dt.timedelta(days=i), **kw) for i in range(n)]


SITE = "Black Mesa State Park"

GOOD_BRIEF = (
    "Tonight at Black Mesa State Park the dark window opens at 8:14 pm and "
    "the night scores 100 - PRIME. The Waxing Crescent moon sets by 8:30 pm. "
    "Watch the Draconids (ZHR of 10) and catch the ISS pass climbing toward "
    "the northeast. Clouds near 12 percent."
)

BAD_BRIEF = (
    "Go out at 9:47 pm; humidity is 62% and the seeing is great tonight."
)


class TestExtract(unittest.TestCase):
    def test_times_normalized(self):
        claims = extract_claims("opens 8:14 pm, closes 20:30, ends at 6:02 am")
        minutes = sorted(m for m, _ in claims.times)
        self.assertEqual(minutes, [6 * 60 + 2, 20 * 60 + 14, 20 * 60 + 30])
        self.assertTrue(any("pm" in raw for _, raw in claims.times))

    def test_numbers_classified(self):
        claims = extract_claims("62%, 34 degrees, 8 km/h, 5 celsius, 10")
        kinds = sorted(n.unit for n in claims.numbers)
        self.assertEqual(kinds, ["", "celsius", "degrees", "kmh", "percent"])
        raws = [n.raw for n in claims.numbers]
        self.assertIn("10", raws)

    def test_times_not_recounted_as_numbers(self):
        claims = extract_claims("at 8:14 pm about 12 percent cloud")
        self.assertEqual(len(claims.numbers), 1)
        self.assertEqual(claims.numbers[0].unit, "percent")

    def test_directions_and_daywords(self):
        claims = extract_claims("look northwest tonight, clear tomorrow, "
                                "NNE after midnight; face south")
        self.assertIn("NW", claims.directions)
        self.assertIn("NNE", claims.directions)
        self.assertIn("S", claims.directions)
        self.assertEqual(claims.day_words, ("tonight", "tomorrow"))

    def test_claims_frozen(self):
        claims = extract_claims("8:14 pm")
        with self.assertRaises(Exception):
            claims.times = ()

    def test_iso_date_not_number_claims(self):
        # T20d live regression: "2026" in a date was classified as a count.
        claims = extract_claims("Best night: 2026-10-08, peak after midnight")
        self.assertEqual(claims.numbers, ())

    def test_bare_year_not_count_claim(self):
        claims = extract_claims("Since 2021 the club has met; 15 meteors")
        bare = [n for n in claims.numbers if n.unit == ""]
        self.assertEqual([n.value for n in bare], [15.0])

    def test_compass_am_pm_and_no_not_names(self):
        # T20d live regressions: SE/PM captured as names, sentence-initial No.
        claims = extract_claims(
            "The shower moves SE. No visible ISS passes tonight; "
            "best around 10:00 PM.")
        for bad in ("SE", "No", "PM"):
            self.assertNotIn(bad, claims.names)


class TestCheck(unittest.TestCase):
    def check(self, text, nights=None, **kw):
        return check_claims(extract_claims(text), nights or _nights(),
                            SITE, TZ)

    def test_clean_brief_zero_violations(self):
        self.assertEqual(self.check(GOOD_BRIEF), [])

    def test_bad_time_and_percent_flagged_with_allowed_values(self):
        v = self.check(BAD_BRIEF)
        self.assertEqual(len(v), 2)
        joined = " | ".join(v)
        self.assertIn("9:47", joined)
        self.assertIn("20:14", joined)          # allowed value present
        self.assertIn("62%", joined)
        self.assertIn("42", joined)             # computed humidity allowed

    def test_wrong_shower_name_flagged(self):
        v = self.check("Watch the Perseids tonight.")
        self.assertEqual(len(v), 1)
        self.assertIn("Perseids", v[0])
        self.assertIn("Draconids", v[0])

    def test_wrong_compass_flagged(self):
        nights = _nights(dirs=("S", "SE", "E"))
        self.assertEqual(check_claims(extract_claims("look southeast"),
                                      nights, SITE, TZ), [])
        v = check_claims(extract_claims("look north"), nights, SITE, TZ)
        self.assertEqual(len(v), 1)
        self.assertIn("north", v[0].lower())

    def test_overhead_requires_60_deg(self):
        v = self.check("The ISS passes nearly overhead.")
        self.assertEqual(len(v), 1)
        self.assertIn("34", v[0])  # highest computed pass
        ok = self.check("The ISS passes nearly overhead.",
                        _nights(max_alt=72.0))
        self.assertEqual(ok, [])

    def test_tomorrow_mismatch_and_weekday_match(self):
        one = _nights(1)  # first night 2026-10-06, only night
        v = check_claims(extract_claims("better tomorrow"), one, SITE, TZ)
        self.assertEqual(len(v), 1)
        self.assertIn("2026-10-07", v[0])
        self.assertEqual(check_claims(extract_claims("clear on Tuesday"),
                                      one, SITE, TZ), [])
        v = check_claims(extract_claims("clear on Wednesday"), one, SITE, TZ)
        self.assertEqual(len(v), 1)

    def test_zhr_citation_ok_count_promise_flagged(self):
        self.assertEqual(self.check("the Draconids list a ZHR of 10"), [])
        v = self.check("you might count 15 meteors")
        self.assertEqual(len(v), 1)
        self.assertIn("promise", v[0])
        self.assertIn("10", v[0])  # the only citable ZHR

    def test_date_in_brief_not_count_violation(self):
        # T20d live regression: dated briefs must not trip the promise rule.
        self.assertEqual(self.check("Plan for 2026-10-08: dark at 8:14 pm."),
                         [])

    def test_site_name_containment_matches(self):
        # T20d live regression: model wrote "Black Mesa State Park", the
        # allowed set has "Black Mesa State Park (demo)".
        v = check_claims(extract_claims("Tonight at Black Mesa State Park."),
                         _nights(), "Black Mesa State Park (demo)", TZ)
        self.assertEqual([x for x in v if "allowed names" in x], [])

    def test_overhead_strictness_preserved(self):
        # "look overhead" with only a 20 deg pass REMAINS a violation.
        v = check_claims(extract_claims("look overhead tonight"),
                         _nights(max_alt=20.0), SITE, TZ)
        self.assertEqual(len(v), 1)
        self.assertIn("60 deg", v[0])

    def test_bare_number_percent_context(self):
        self.assertEqual(self.check("humidity near 42 and it holds"), [])


class TestVerifiedBrief(unittest.TestCase):
    def _run(self, texts, offline=False, **kw):
        calls = []

        def stub(plan_nights, site_name, llm, offline=False, tz=None,
                 messages=None):
            calls.append(list(messages or []))
            text = texts[min(len(calls) - 1, len(texts) - 1)]
            return BriefResult(text=text, source="llm", attempts=1,
                               violations=[])

        with mock.patch("clearnight.verify.generate_brief", side_effect=stub):
            result = verified_brief(_nights(), SITE, CFG, TZ,
                                    offline=offline, **kw)
        return result, calls

    def test_success_after_two_failures(self):
        result, calls = self._run([BAD_BRIEF, BAD_BRIEF, GOOD_BRIEF])
        self.assertEqual((result.source, result.attempts, result.violations),
                         ("llm", 3, []))
        self.assertEqual(result.text, GOOD_BRIEF)
        # retry messages grow: original 2 + one follow-up per violation round
        self.assertEqual(len(calls[0]), 2)
        self.assertEqual(len(calls[2]), 4)
        self.assertIn("not in the data", calls[1][-1]["content"])
        self.assertIn("20:14", calls[1][-1]["content"])  # exact allowed values

    def test_success_on_fifth_call_within_default_budget(self):
        # T20c: default budget is now 4 retries (5 calls); a reasoning
        # model converging on the 5th call still lands an LLM brief.
        result, calls = self._run([BAD_BRIEF] * 4 + [GOOD_BRIEF])
        self.assertEqual((result.source, result.attempts, result.violations),
                         ("llm", 5, []))
        self.assertEqual(len(calls), 5)

    def test_four_failures_fall_back_to_template(self):
        # T20c: default budget exhausted after 5 calls (4 retries).
        result, calls = self._run([BAD_BRIEF])
        self.assertEqual(result.source, "template")
        self.assertEqual(result.attempts, 5)
        self.assertEqual(len(calls), 5)
        self.assertTrue(result.violations)
        self.assertIn("Template brief", result.text)

    def test_template_result_short_circuits(self):
        calls = []

        def stub(plan_nights, site_name, llm, offline=False, tz=None,
                 messages=None):
            calls.append(1)
            return BriefResult(text="t", source="template", attempts=2,
                               violations=[])

        with mock.patch("clearnight.verify.generate_brief", side_effect=stub):
            result = verified_brief(_nights(), SITE, CFG, TZ)
        self.assertEqual(result.source, "template")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(calls), 1)

    def test_offline_never_calls_generate(self):
        def stub(*a, **kw):
            raise AssertionError("generate must not be called offline")

        with mock.patch("clearnight.verify.generate_brief", side_effect=stub):
            result = verified_brief(_nights(), SITE, CFG, TZ, offline=True)
        self.assertEqual(result.source, "template")
        self.assertEqual(result.attempts, 0)
        self.assertEqual(result.violations, [])

    def test_no_llm(self):
        result, _ = self._run([], offline=True)
        self.assertEqual(result.source, "template")


if __name__ == "__main__":
    unittest.main()
