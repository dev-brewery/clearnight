"""T17: field log — append/read JSONL, latest-wins matching, `log` CLI,
and FIELD LOG blocks in both rendered plans. Fully offline, tmp dirs."""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clearnight import fieldlog
from clearnight.__main__ import main, run_plan
from clearnight.models import FieldLogEntry, Night

REPO = Path(__file__).resolve().parent.parent


class _NoConnectSocket(socket.socket):
    def connect(self, address):
        raise AssertionError(f"network connect attempted: {address!r}")


def _entry(date: str, recorded: str, *, notes: str = "n",
           clearness: int = 3) -> FieldLogEntry:
    return FieldLogEntry(
        date_local=dt.date.fromisoformat(date),
        went_out=True,
        clearness=clearness,
        meteors_counted=7,
        iss_seen=False,
        notes=notes,
        recorded_utc=dt.datetime.fromisoformat(recorded),
    )


class TestAppendRead(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="clearnight-log-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_roundtrip(self) -> None:
        e = _entry("2026-10-09", "2026-10-10T03:00:00+00:00",
                   notes="great, saw 7", clearness=4)
        fieldlog.append_entry(self.tmp, e)
        lines = (self.tmp / "fieldlog.jsonl").read_text(
            encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        obj = json.loads(lines[0])
        self.assertEqual(obj["date_local"], "2026-10-09")
        self.assertEqual(obj["clearness"], 4)
        self.assertEqual(obj["meteors_counted"], 7)
        self.assertEqual(obj["notes"], "great, saw 7")
        self.assertEqual(obj["recorded_utc"], "2026-10-10T03:00:00+00:00")
        got = fieldlog.read_entries(self.tmp)
        self.assertEqual(got, [e])

    def test_corrupt_line_skipped_with_warning(self) -> None:
        fieldlog.append_entry(self.tmp, _entry(
            "2026-10-09", "2026-10-10T03:00:00+00:00"))
        p = self.tmp / "fieldlog.jsonl"
        p.write_text("{not json\n" + p.read_text(encoding="utf-8"),
                     encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            got = fieldlog.read_entries(self.tmp)
        self.assertEqual(len(got), 1)
        self.assertIn("warning", err.getvalue())

    def test_read_missing_file(self) -> None:
        self.assertEqual(fieldlog.read_entries(self.tmp), [])


class TestMatch(unittest.TestCase):
    def test_latest_wins_and_none(self) -> None:
        night = mock.Mock(spec=Night)
        night.date_local = dt.date(2026, 10, 9)
        other = mock.Mock(spec=Night)
        other.date_local = dt.date(2026, 10, 10)
        early = _entry("2026-10-09", "2026-10-10T03:00:00+00:00",
                       notes="evening")
        late = _entry("2026-10-09", "2026-10-10T14:00:00+00:00",
                      notes="morning addendum")
        matched = fieldlog.match_to_nights([night, other], [early, late])
        by_date = {n.date_local: e for n, e in matched}
        self.assertEqual(by_date[dt.date(2026, 10, 9)].notes,
                         "morning addendum")
        self.assertIsNone(by_date[dt.date(2026, 10, 10)])


class TestLogCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="clearnight-logcli-"))
        shutil.copy(REPO / "config.example.toml",
                    self.tmp / "config.example.toml")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cwd = Path.cwd()

        import os
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self.cwd)

    def test_log_appends_one_line(self) -> None:
        rc = main(["log", "--date", "2026-10-09", "--went-out",
                   "--clearness", "4", "--meteors", "7", "--iss-seen",
                   "--notes", "test"])
        self.assertEqual(rc, 0)
        lines = (self.tmp / "out" / "fieldlog.jsonl").read_text(
            encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        obj = json.loads(lines[0])
        self.assertEqual(obj["date_local"], "2026-10-09")
        self.assertTrue(obj["went_out"])
        self.assertEqual(obj["clearness"], 4)
        self.assertEqual(obj["meteors_counted"], 7)
        self.assertTrue(obj["iss_seen"])
        self.assertEqual(obj["notes"], "test")
        self.assertIn("recorded_utc", obj)

    def test_log_without_date_exits_2(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main(["log"])
        self.assertEqual(cm.exception.code, 2)

    def test_two_appends_two_lines(self) -> None:
        main(["log", "--date", "2026-10-09", "--went-out"])
        main(["log", "--date", "2026-10-09"])
        lines = (self.tmp / "out" / "fieldlog.jsonl").read_text(
            encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)


class TestPlanIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="clearnight-planlog-"))
        shutil.copy(REPO / "config.example.toml",
                    self.tmp / "config.example.toml")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cwd = Path.cwd()

        import os
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self.cwd)
        self._socket_patch = mock.patch("socket.socket", _NoConnectSocket)
        self._socket_patch.start()
        self.addCleanup(self._socket_patch.stop)

    def _run_plan(self) -> tuple[int, str, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = run_plan(["plan", "--offline"])
        html = (self.tmp / "out" / "plan.html").read_text(encoding="utf-8")
        return rc, out.getvalue(), html

    def test_logged_night_gets_block(self) -> None:
        main(["log", "--date", "2026-10-09", "--went-out",
              "--clearness", "4", "--meteors", "7", "--iss-seen",
              "--notes", "dew on the eyepiece"])
        rc, text, html = self._run_plan()
        self.assertEqual(rc, 0)
        start = text.index("night 2026-10-09")
        end = text.index("night 2026-10-", start + 1)
        block = text[start:end]
        self.assertIn("FIELD LOG:", block)
        self.assertIn("went out: yes", block)
        self.assertIn("clearness 4/5", block)
        self.assertIn("meteors counted: 7", block)
        self.assertIn("ISS seen: yes", block)
        self.assertIn("notes: dew on the eyepiece", block)
        self.assertIn("recorded-at:", block)
        # HTML carries the same block with the note text.
        self.assertIn("FIELD LOG:", html)
        self.assertIn("dew on the eyepiece", html)

    def test_unlogged_nights_show_no_block(self) -> None:
        main(["log", "--date", "2026-10-09", "--went-out"])
        _, text, html = self._run_plan()
        # Exactly one FIELD LOG block in text, anchored to Oct 9's section.
        self.assertEqual(text.count("FIELD LOG:"), 1)
        idx = text.index("night 2026-10-09")
        nxt = text.index("night 2026-10-", idx + 1)
        self.assertLess(text.index("FIELD LOG:"), nxt)
        self.assertGreater(text.index("FIELD LOG:"), idx)
        self.assertEqual(html.count("FIELD LOG:"), 1)


if __name__ == "__main__":
    unittest.main()
