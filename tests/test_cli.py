"""CLI tests (T05). Subprocess-driven against `sys.executable -m clearnight`
from a temp cwd with config.example.toml copied in. Offline only — the plan
stub must not touch network or LLM."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "clearnight", *args],
        cwd=cwd, capture_output=True, text=True, timeout=60,
    )


class TestCLI(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="clearnight-cli-"))
        shutil.copy(REPO / "config.example.toml", self.tmp / "config.example.toml")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_plan_offline_exits_0_with_site_and_mode(self) -> None:
        r = run_cli("plan", "--offline", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Black Mesa State Park (demo)", r.stdout)
        self.assertIn("OFFLINE fixture epoch", r.stdout)
        self.assertTrue((self.tmp / "out" / "plan.html").is_file())

    def test_plan_nights_override(self) -> None:
        r = run_cli("plan", "--offline", "--nights", "3", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("3 nights, ranked", r.stdout)

    def test_plan_explicit_config(self) -> None:
        # T16: the online placeholder is gone; explicit-config wiring is
        # covered offline (--online network behavior lives in
        # test_online_wiring with mocked urlopen).
        r = run_cli("plan", "--offline", "--config",
                    str(self.tmp / "config.example.toml"), cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OFFLINE fixture epoch", r.stdout)

    def test_log_appends_entry_exits_0(self) -> None:
        # T17: the stub is gone; log appends to out/fieldlog.jsonl.
        r = run_cli("log", "--date", "2026-10-10", "--went-out",
                    "--clearness", "4", "--meteors", "2", "--iss-seen",
                    "--notes", "test", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("logged 2026-10-10", r.stdout)
        lines = (self.tmp / "out" / "fieldlog.jsonl").read_text(
            encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)

    def test_fetch_stub_exits_0(self) -> None:
        r = run_cli("fetch", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("fetch: not implemented until T06", r.stdout)

    def test_unknown_flag_exits_2(self) -> None:
        r = run_cli("plan", "--bogus", cwd=self.tmp)
        self.assertEqual(r.returncode, 2)

    def test_invalid_nights_exits_nonzero(self) -> None:
        r = run_cli("plan", "--nights", "99", cwd=self.tmp)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
