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
        self.assertIn("OFFLINE (fixture epoch)", r.stdout)
        self.assertIn("placeholder plan - real pipeline lands in T14", r.stdout)

    def test_plan_nights_override(self) -> None:
        r = run_cli("plan", "--offline", "--nights", "3", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nights: 3", r.stdout)

    def test_plan_explicit_config(self) -> None:
        r = run_cli("plan", "--config", str(self.tmp / "config.example.toml"),
                    cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Black Mesa State Park (demo)", r.stdout)

    def test_log_stub_exits_0(self) -> None:
        r = run_cli("log", "--date", "2026-10-10", "--went-out",
                    "--clearness", "4", "--meteors", "2", "--iss-seen",
                    "--notes", "test", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("log: not implemented until T17", r.stdout)

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
