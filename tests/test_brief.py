"""T18: brief generation — prompt snapshot, request shape, retry/fallback.

All urlopen calls are mocked with canned replies; the suite never touches a
network. Test nights are constructed deterministically from the demo-site
shape (America/Chicago) using only computed-style values — no real
coordinates, no fixtures fetched at test time.
"""

from __future__ import annotations

import datetime as dt
import json
import unittest
import urllib.error
from unittest import mock
from zoneinfo import ZoneInfo

from clearnight.brief import (
    SYSTEM_PROMPT,
    BriefResult,
    build_prompt,
    generate_brief,
)
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

TZ = ZoneInfo("America/Chicago")


def _utc(y: int, mo: int, d: int, h: int, mi: int) -> dt.datetime:
    return dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone.utc)


def _night(date_local: dt.date) -> Night:
    """One deterministic demo night (fixture-shaped, computed values only)."""
    start = dt.datetime(2026, 10, 7, 1, 14, tzinfo=dt.timezone.utc)  # 8:14 pm CDT
    end = dt.datetime(2026, 10, 7, 11, 2, tzinfo=dt.timezone.utc)    # 6:02 am CDT
    weather = [
        HourWeather(_utc(2026, 10, 7, 2, 0), cloud_total_pct=10.0, rh_pct=40.0,
                    wind_kmh=8.0, visibility_m=15000.0),
        HourWeather(_utc(2026, 10, 7, 3, 0), cloud_total_pct=14.0, rh_pct=44.0,
                    wind_kmh=8.4, visibility_m=15600.0),
    ]
    return Night(
        date_local=date_local,
        dark=DarkWindow(start, end),
        moon=MoonInfo("Waxing Crescent", 0.03, None,
                      _utc(2026, 10, 7, 1, 30), 0.10, 12.0),
        weather=weather,
        conditions=Conditions(4.0, "low", "flat", 0.0),
        showers=[ShowerEvent("Draconids", _utc(2026, 10, 8, 22, 0),
                             _utc(2026, 10, 6, 0, 0), _utc(2026, 10, 10, 0, 0),
                             10.0, 262.0, 54.0, "21P", 5.1, True)],
        iss_passes=[ISSPass(start, _utc(2026, 10, 7, 1, 18), _utc(2026, 10, 7, 1, 22),
                            34.0, "NW", "N", "NE")],
        score=NightScore(100, "PRIME", -3.0, -1.0, 4.0, 5.0, 5.0, 90.0,
                         10, 5, 0, ["dark, moonless"]),
    )


def _nights() -> list[Night]:
    base = dt.date(2026, 10, 6)
    return [_night(base + dt.timedelta(days=i)) for i in range(3)]


CFG_KEY = LLMCfg("http://llm-box.local/v1", "demo-model",
                 api_key="sekrit", timeout_s=17, max_tokens=777)
CFG_NOKEY = LLMCfg("http://llm-box.local/v1", "demo-model", timeout_s=17)


class _Resp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _llm_reply(text: str) -> _Resp:
    return _Resp(json.dumps(
        {"choices": [{"message": {"content": text}}]}).encode("utf-8"))


class PromptSnapshot(unittest.TestCase):
    """User payload contains only computed, pre-rounded night values."""

    def setUp(self):
        self.msgs = build_prompt(_nights(), "Black Mesa State Park")

    def test_system_message_constraints(self):
        sys_text = self.msgs[0]["content"]
        self.assertIn("ONLY facts", sys_text)
        self.assertIn("pre-rounded as given", sys_text)
        self.assertIn("Never invent or estimate", sys_text)
        self.assertIn("120 words", sys_text)
        self.assertIn("when to go out, which way to face, what to look for",
                      sys_text)

    def test_user_payload_exact_values(self):
        lines = self.msgs[1]["content"].splitlines()
        data = json.loads(lines[0])
        self.assertEqual(set(data), {"site", "nights"})
        self.assertEqual(data["site"], "Black Mesa State Park")
        self.assertEqual(len(data["nights"]), 3)
        n0 = data["nights"][0]
        self.assertEqual(n0["date"], "2026-10-06")
        self.assertEqual(n0["weekday"], "Tuesday")
        self.assertEqual(n0["dark_window"], {"start": "8:14 pm",
                                             "end": "6:02 am"})
        self.assertEqual(n0["moon"]["phase"], "Waxing Crescent")
        self.assertEqual(n0["moon"]["illum_pct"], 3)
        self.assertIsNone(n0["moon"]["rise"])
        self.assertEqual(n0["weather"]["cloud_pct"], 12)
        self.assertEqual(n0["weather"]["humidity_pct"], 42)
        self.assertEqual(n0["weather"]["wind_kmh"], 8.2)
        self.assertEqual(n0["weather"]["visibility_km"], 15.3)
        self.assertEqual(n0["dew_risk"], "low")
        self.assertEqual(n0["score"]["total"], 100)
        self.assertEqual(n0["score"]["verdict"], "PRIME")
        self.assertEqual(n0["showers"][0]["name"], "Draconids")
        self.assertEqual(n0["showers"][0]["zhr"], 10)
        self.assertTrue(n0["showers"][0]["peak"])
        self.assertEqual(n0["showers"][0]["radiant_up_hours"], 5.1)
        self.assertEqual(n0["iss_passes"][0]["start"], "8:14 pm")
        self.assertEqual(n0["iss_passes"][0]["max_alt_deg"], 34)
        self.assertEqual(n0["iss_passes"][0]["directions"], "NW>N>NE")

    def test_dates_are_local_and_distinct(self):
        lines = self.msgs[1]["content"].splitlines()
        data = json.loads(lines[0])
        self.assertEqual([n["date"] for n in data["nights"]],
                         ["2026-10-06", "2026-10-07", "2026-10-08"])
        self.assertEqual([n["weekday"] for n in data["nights"]],
                         ["Tuesday", "Wednesday", "Thursday"])

    def test_system_prompt_constant_shared(self):
        self.assertEqual(self.msgs[0]["content"], SYSTEM_PROMPT)

    def test_system_message_verbatim_times_rule(self):
        # T20c: live loop showed the model rewriting window times; the
        # system prompt must demand verbatim echo.
        sys_text = self.msgs[0]["content"]
        self.assertIn(
            "State times exactly as given in the data - same clock format, "
            "no reformatting, no recomputation, no conversion", sys_text)

    def test_allowed_times_lines_per_night(self):
        # T20c: compact ALLOWED TIMES whitelist appended after the JSON.
        allowed = self.msgs[1]["content"].splitlines()[1:]
        self.assertEqual(allowed, [
            "2026-10-06 allowed times: 8:14 PM, 6:02 AM",
            "2026-10-07 allowed times: 8:14 PM, 6:02 AM",
            "2026-10-08 allowed times: 8:14 PM, 6:02 AM",
        ])


class RequestShape(unittest.TestCase):
    """URL join, body constants, timeout, Authorization header discipline."""

    def _capture(self, cfg: LLMCfg):
        seen = {}

        def urlopen(req, timeout=None):
            seen["url"] = getattr(req, "full_url", req)
            seen["timeout"] = timeout
            seen["headers"] = {k.lower(): v for k, v in req.header_items()}
            seen["body"] = json.loads(req.data.decode("utf-8"))
            return _llm_reply("ok")

        with mock.patch("urllib.request.urlopen", urlopen):
            result = generate_brief(_nights(), "Black Mesa State Park", cfg)
        return seen, result

    def test_success_shape(self):
        seen, result = self._capture(CFG_KEY)
        self.assertEqual(result.source, "llm")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.text, "ok")
        self.assertEqual(result.violations, [])
        self.assertEqual(seen["url"],
                         "http://llm-box.local/v1/chat/completions")
        self.assertNotIn("//chat", seen["url"])
        self.assertEqual(seen["timeout"], 17)
        self.assertEqual(seen["body"]["temperature"], 0.2)
        self.assertEqual(seen["body"]["max_tokens"], 777)
        self.assertEqual(seen["body"]["model"], "demo-model")
        self.assertEqual(len(seen["body"]["messages"]), 2)

    def test_authorization_present_with_key(self):
        seen, _ = self._capture(CFG_KEY)
        self.assertEqual(seen["headers"]["authorization"],
                         "Bearer sekrit")

    def test_authorization_absent_without_key(self):
        seen, _ = self._capture(CFG_NOKEY)
        self.assertNotIn("authorization", seen["headers"])


class RetryAndFallback(unittest.TestCase):
    """One transport retry, then labeled template; offline never calls."""

    def test_retry_then_template(self):
        calls = []

        def urlopen(req, timeout=None):
            calls.append(1)
            raise urllib.error.URLError("connection refused")

        with mock.patch("urllib.request.urlopen", urlopen), \
                self.assertLogs("clearnight.brief", level="WARNING") as logs:
            result = generate_brief(_nights(), "Black Mesa State Park",
                                    CFG_KEY)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.source, "template")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.violations, [])
        self.assertIn("Template brief (LLM output unavailable",
                      result.text)
        # warning hygiene: exception class only — no URL, no api key
        joined = "\n".join(logs.output)
        self.assertIn("URLError", joined)
        self.assertNotIn("llm-box.local", joined)
        self.assertNotIn("sekrit", joined)
        self.assertNotIn("http", joined)

    def test_offline_never_calls_urlopen(self):
        def urlopen(*a, **k):
            raise AssertionError("offline mode must not call urlopen")

        with mock.patch("urllib.request.urlopen", urlopen):
            result = generate_brief(_nights(), "Black Mesa State Park",
                                    CFG_NOKEY, offline=True)
        self.assertEqual(result.source, "template")
        self.assertEqual(result.attempts, 0)
        self.assertIn("Template brief (LLM output unavailable", result.text)
        # computed-only template content, one line per top night
        self.assertIn("2026-10-06", result.text)
        self.assertIn("Draconids", result.text)

    def test_empty_nights_offline_template(self):
        """Zero dark nights (e.g. high-latitude summer): no crash, honest
        template line, same labeled header, no tz-dependent lines."""
        result = generate_brief([], "Black Mesa State Park", CFG_NOKEY,
                                offline=True)
        self.assertIsInstance(result, BriefResult)
        self.assertEqual(result.source, "template")
        self.assertEqual(result.attempts, 0)
        self.assertIn("Template brief (LLM output unavailable",
                      result.text)
        self.assertIn(
            "No nights with astronomical darkness in the plan window.",
            result.text)
        self.assertNotIn("2026-", result.text)  # no date/zone lines
        self.assertNotIn("am", result.text.split(chr(10))[-1])

    def test_empty_nights_online_never_calls_urlopen(self):
        """A brief for zero nights is pointless: template immediately,
        no LLM round-trip, attempts 0 even on the online path."""
        def urlopen(*a, **k):
            raise AssertionError("empty input must not call urlopen")

        with mock.patch("urllib.request.urlopen", urlopen):
            result = generate_brief([], "Black Mesa State Park", CFG_KEY)
        self.assertEqual(result.source, "template")
        self.assertEqual(result.attempts, 0)
        self.assertIn(
            "No nights with astronomical darkness in the plan window.",
            result.text)

    def test_success_result_is_briefresult(self):
        with mock.patch("urllib.request.urlopen",
                        lambda req, timeout=None: _llm_reply("go at 8:14 pm")):
            result = generate_brief(_nights(), "Black Mesa State Park",
                                    CFG_NOKEY)
        self.assertIsInstance(result, BriefResult)
        self.assertEqual(result.text, "go at 8:14 pm")


class EmptyReplyRetry(unittest.TestCase):
    """T20a: empty/whitespace content is a failed attempt within the retry
    budget; the request never carries the old hardcoded 400."""

    def test_empty_then_good_retry_source_llm(self):
        replies = [_llm_reply(""), _llm_reply("go at 8:14 pm")]

        def urlopen(req, timeout=None):
            return replies.pop(0)

        with mock.patch("urllib.request.urlopen", urlopen), \
                self.assertLogs("clearnight.brief", level="WARNING"):
            result = generate_brief(_nights(), "Black Mesa State Park",
                                    CFG_KEY)
        self.assertEqual(result.source, "llm")
        self.assertEqual(result.text, "go at 8:14 pm")

    def test_whitespace_content_counts_as_empty(self):
        replies = [_llm_reply("   "), _llm_reply("answer")]

        def urlopen(req, timeout=None):
            return replies.pop(0)

        with mock.patch("urllib.request.urlopen", urlopen), \
                self.assertLogs("clearnight.brief", level="WARNING"):
            result = generate_brief(_nights(), "Black Mesa State Park",
                                    CFG_KEY)
        self.assertEqual(result.source, "llm")
        self.assertEqual(result.text, "answer")

    def test_empty_on_all_attempts_falls_back_to_template(self):
        def urlopen(req, timeout=None):
            return _llm_reply("")

        with mock.patch("urllib.request.urlopen", urlopen), \
                self.assertLogs("clearnight.brief", level="WARNING") as logs:
            result = generate_brief(_nights(), "Black Mesa State Park",
                                    CFG_KEY)
        self.assertEqual(result.source, "template")
        self.assertEqual(result.attempts, 2)
        self.assertIn("Template brief (LLM output unavailable",
                      result.text)
        joined = "\n".join(logs.output)
        self.assertNotIn("llm-box.local", joined)
        self.assertNotIn("sekrit", joined)

    def test_body_never_carries_hardcoded_400(self):
        seen = {}

        def urlopen(req, timeout=None):
            seen["body"] = json.loads(req.data.decode("utf-8"))
            return _llm_reply("ok")

        with mock.patch("urllib.request.urlopen", urlopen):
            generate_brief(_nights(), "Black Mesa State Park", CFG_KEY)
        self.assertNotEqual(seen["body"]["max_tokens"], 400)
        self.assertEqual(seen["body"]["max_tokens"], 777)


if __name__ == "__main__":
    unittest.main()
