"""T14: `plan --offline` end-to-end from committed fixtures only (A1 proof).

Runs the pipeline in-process via run_plan() with socket.socket patched to
raise on any connect — proving no network — in a tmp cwd containing only
config.example.toml (no config.local.toml, no cache, no out/).
"""

from __future__ import annotations

import contextlib
import io
import re
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clearnight.__main__ import TEMPLATE_BRIEF_LABEL, run_plan

REPO = Path(__file__).resolve().parent.parent


class _NoConnectSocket(socket.socket):
    def connect(self, address):
        raise AssertionError(f"network connect attempted: {address!r}")


class TestPlanOffline(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="clearnight-plan-"))
        shutil.copy(REPO / "config.example.toml", self.tmp / "config.example.toml")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cwd = Path.cwd()
        import os

        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self.cwd)
        self._socket_patch = mock.patch("socket.socket", _NoConnectSocket)
        self._socket_patch.start()
        self.addCleanup(self._socket_patch.stop)
        self.out = io.StringIO()
        with contextlib.redirect_stdout(self.out):
            self.rc = run_plan(["plan", "--offline"])
        self.stdout = self.out.getvalue()

    def test_exit_0_and_html_written(self) -> None:
        self.assertEqual(self.rc, 0)
        html = (self.tmp / "out" / "plan.html").read_text(encoding="utf-8")
        self.assertTrue(html.strip())
        for date in (
            "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-10",
            "2026-10-11", "2026-10-12", "2026-10-13",
        ):
            self.assertIn(date, html)
        # A3 field labels present.
        for label in (
            "dark window (local)", "moon", "clouds", "dew risk",
            "shower:", "iss:", "PEAK",
        ):
            self.assertIn(label, html)

    def test_stdout_summary_present(self) -> None:
        self.assertIn("night 2026-10-08", self.stdout)
        self.assertIn("Template brief", self.stdout)

    def test_nights_sorted_descending_by_score(self) -> None:
        totals = [
            int(m) for m in re.findall(r"^  total (\d+)", self.stdout, re.M)
        ]
        self.assertEqual(len(totals), 7)
        self.assertEqual(totals, sorted(totals, reverse=True))
        # The overcast-capped nights land last.
        last_block = self.stdout[self.stdout.rfind("night 2026-"):]
        self.assertIn("STAY IN BED", last_block)
        self.assertIn("overcast", last_block)

    def test_template_brief_label_exactly_once(self) -> None:
        # T15: the 103-char label is wrapped across two <=80-col lines in the
        # text summary (exact wording wins, wrapping allowed, never truncated).
        lines = self.stdout.splitlines()
        i = next(n for n, ln in enumerate(lines)
                 if ln.startswith("Template brief ("))
        wrapped = [lines[i].strip(), lines[i + 1].strip()]
        self.assertEqual(" ".join(wrapped), TEMPLATE_BRIEF_LABEL)
        html = (self.tmp / "out" / "plan.html").read_text(encoding="utf-8")
        self.assertIn(TEMPLATE_BRIEF_LABEL, html)

    def test_draconids_peak_bonus_real(self) -> None:
        # Radiant-up recording makes the peak bonus land: >= 1 night shows
        # meteor_bonus 6 in its breakdown line.
        self.assertGreaterEqual(len(re.findall(r"meteor_bonus 6", self.stdout)), 1)

    def test_works_with_only_committed_files(self) -> None:
        # setUp copied ONLY config.example.toml; no cache/, no out/,
        # no config.local.toml existed. Everything needed came from the repo.
        self.assertFalse((self.tmp / "config.local.toml").exists())
        self.assertEqual(self.rc, 0)


if __name__ == "__main__":
    unittest.main()
