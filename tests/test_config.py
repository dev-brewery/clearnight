"""Tests for clearnight.config (T03). Runs offline; never touches a real
config.local.toml in the repo — all temp configs live in TemporaryDirectory."""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

from clearnight.config import Config, ConfigError, load_config

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "config.example.toml"


def write_and_load(toml_text: str) -> Config:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "config.toml"
        p.write_text(toml_text, encoding="utf-8")
        return load_config(str(p))


class TestExampleConfig(unittest.TestCase):
    def test_example_loads_and_validates(self):
        import os
        cwd = os.getcwd()
        os.chdir(REPO_ROOT)
        try:
            cfg = load_config()
        finally:
            os.chdir(cwd)
        self.assertEqual(cfg.site.name, "Black Mesa State Park (demo)")
        self.assertAlmostEqual(cfg.site.lat, 36.85)
        self.assertAlmostEqual(cfg.site.lon, -102.88)
        self.assertEqual(cfg.nights, 7)
        self.assertEqual(cfg.sensor.kind, "csv")
        self.assertEqual(cfg.sensor.path, "clearnight/fixtures/sensor.csv")
        self.assertIsNone(cfg.llm.api_key)
        self.assertEqual(cfg.llm.timeout_s, 300)
        self.assertEqual(cfg.llm.max_tokens, 2000)

    def test_explicit_example_path(self):
        cfg = load_config(str(EXAMPLE))
        self.assertEqual(cfg.llm.model,
                         "/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-Q6_K.gguf")
        self.assertEqual(cfg.cache_dir, Path("cache"))

    def test_missing_both_files_names_searched(self):
        with tempfile.TemporaryDirectory() as d:
            import os
            cwd = os.getcwd()
            os.chdir(d)
            try:
                with self.assertRaises(ConfigError) as cm:
                    load_config()
            finally:
                os.chdir(cwd)
            msg = str(cm.exception)
            self.assertIn("config.example.toml", msg)
            self.assertIn("config.local.toml", msg)

    def test_missing_explicit_path(self):
        with self.assertRaises(ConfigError):
            load_config("no/such/file.toml")


class TestMerge(unittest.TestCase):
    def test_local_overrides_site_lat_and_name(self):
        base = EXAMPLE.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config.example.toml").write_text(base, encoding="utf-8")
            (Path(d) / "config.local.toml").write_text(
                '[site]\nname = "My Backyard"\nlat = 40.5\n', encoding="utf-8")
            import os
            cwd = os.getcwd()
            os.chdir(d)
            try:
                cfg = load_config()
            finally:
                os.chdir(cwd)
        self.assertEqual(cfg.site.name, "My Backyard")
        self.assertAlmostEqual(cfg.site.lat, 40.5)
        self.assertAlmostEqual(cfg.site.lon, -102.88)  # untouched
        self.assertEqual(cfg.llm.model,
                         "/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-Q6_K.gguf")  # llm section intact (T20a served id)


class TestValidation(unittest.TestCase):
    BASE = """\
[site]
name = "T"
lat = 0.0
lon = 0.0
elevation_m = 0.0
tz = "UTC"

[sensor]
kind = "csv"
path = "x.csv"

[llm]
base_url = "http://localhost:8080/v1"
model = "m"
"""

    def load(self, extra: str) -> Config:
        # extra holds top-level keys; TOML requires them before any [table] header
        return write_and_load(self.BASE.replace("[site]", extra + "\n\n[site]"))

    def test_valid_local_overrides(self):
        cfg = self.load('nights = 3\nllm_api_key_override = "ignored"\n')
        self.assertEqual(cfg.nights, 3)
        self.assertIsNone(cfg.llm.api_key)

    def test_invalid_lat(self):
        with self.assertRaises(ConfigError) as cm:
            write_and_load(self.BASE.replace("lat = 0.0", "lat = 91.0"))
        self.assertIn("site.lat", str(cm.exception))

    def test_invalid_tz(self):
        with self.assertRaises(ConfigError) as cm:
            write_and_load(self.BASE.replace('tz = "UTC"', 'tz = "Mars/Olympus"'))
        self.assertIn("site.tz", str(cm.exception))

    def test_bad_sensor_kind(self):
        with self.assertRaises(ConfigError) as cm:
            write_and_load(self.BASE.replace('kind = "csv"', 'kind = "serial"'))
        self.assertIn("sensor.kind", str(cm.exception))

    def test_csv_missing_path(self):
        with self.assertRaises(ConfigError) as cm:
            write_and_load(self.BASE.replace('path = "x.csv"\n', ""))
        self.assertIn("sensor.path", str(cm.exception))

    def test_http_json_missing_url(self):
        toml = self.BASE.replace('kind = "csv"\npath = "x.csv"\n',
                                 'kind = "http_json"\n')
        with self.assertRaises(ConfigError) as cm:
            write_and_load(toml)
        self.assertIn("sensor.url", str(cm.exception))

    def test_bad_base_url(self):
        with self.assertRaises(ConfigError) as cm:
            write_and_load(self.BASE.replace("http://localhost", "ftp://localhost"))
        self.assertIn("llm.base_url", str(cm.exception))

    def test_nights_out_of_range(self):
        for bad in ("0", "15"):
            with self.assertRaises(ConfigError) as cm:
                self.load(f"nights = {bad}\n")
            self.assertIn("nights", str(cm.exception))

    def test_elevation_below_dead_sea(self):
        with self.assertRaises(ConfigError) as cm:
            write_and_load(self.BASE.replace("elevation_m = 0.0", "elevation_m = -500"))
        self.assertIn("site.elevation_m", str(cm.exception))

    def test_api_key_optional(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.toml"
            p.write_text(self.BASE.replace(
                '[llm]\n', '[llm]\napi_key = "sk-local-only"\n'), encoding="utf-8")
            self.assertEqual(load_config(str(p)).llm.api_key, "sk-local-only")

    def test_timeout_must_be_positive_int(self):
        toml = self.BASE.replace("[llm]", "timeout_s = -1\n\n[llm]")
        with self.assertRaises(ConfigError) as cm:
            write_and_load(toml)
        self.assertIn("sensor.timeout_s", str(cm.exception))

    def test_llm_max_tokens_must_be_positive_int(self):
        for bad in ("max_tokens = 0", "max_tokens = -5", 'max_tokens = "lots"'):
            toml = self.BASE.replace('model = "m"',
                                     f'model = "m"\n{bad}')
            with self.assertRaises(ConfigError) as cm:
                write_and_load(toml)
            self.assertIn("llm.max_tokens", str(cm.exception))

class TestNoPrivateIPsCommitted(unittest.TestCase):
    """T23 tripwire: no private-IP addresses in committed config files."""
    PATTERN = re.compile(r"192\.168\.|10\.0\.|172\.(1[6-9]|2\d|3[01])\.")

    def test_committed_config_files_have_no_private_ips(self):
        for name in ("config.example.toml", ".env.example"):
            text = (REPO_ROOT / name).read_text(encoding="utf-8")
            hits = self.PATTERN.findall(text)
            self.assertEqual(hits, [], f"{name} contains private IP(s): {hits}")


class TestDotenv(unittest.TestCase):
    """T23: .env parsing and CLEARNIGHT_* env overrides."""

    def _load_in_dir(self, d: Path, toml_text: str):
        import os
        cwd = os.getcwd()
        os.chdir(d)
        try:
            return load_config()
        finally:
            os.chdir(cwd)

    TOML = ('[site]\nname = "X"\nlat = 1\nlon = 2\nelevation_m = 100\n'
            'tz = "UTC"\n\n[sensor]\nkind = "csv"\npath = "s.csv"\n\n'
            '[llm]\nbase_url = "http://toml:1/v1"\nmodel = "toml-model"\n')

    def test_dotenv_parsed_and_setdefault_semantics(self):
        keys = ["CLEARNIGHT_LLM_BASE_URL", "CLEARNIGHT_LLM_MODEL",
                "CLEARNIGHT_SENSOR_URL", "CLEARNIGHT_LLM_API_KEY"]
        saved = {k: os.environ.pop(k, None) for k in keys}
        try:
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "config.example.toml").write_text(self.TOML, encoding="utf-8")
                (root / ".env").write_text(
                    '# comment\nCLEARNIGHT_LLM_BASE_URL=http://dotenv:2/v1\n'
                    'CLEARNIGHT_LLM_MODEL="quoted-model"\n'
                    "CLEARNIGHT_SENSOR_URL='single-quoted'\n"
                    'CLEARNIGHT_LLM_API_KEY=  \n', encoding="utf-8")
                cfg = self._load_in_dir(root, self.TOML)
            # .env wins over TOML; quoted values are unquoted
            self.assertEqual(cfg.llm.base_url, "http://dotenv:2/v1")
            self.assertEqual(cfg.llm.model, "quoted-model")
            self.assertEqual(cfg.sensor.url, "single-quoted")
            # empty .env value becomes "" - harmless (api_key optional str)
            self.assertEqual(cfg.llm.api_key, "")
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
                else:
                    os.environ.pop(k, None)

    def test_real_environment_wins_over_dotenv(self):
        keys = ["CLEARNIGHT_LLM_BASE_URL", "CLEARNIGHT_LLM_MODEL",
                "CLEARNIGHT_SENSOR_URL"]
        saved = {k: os.environ.pop(k, None) for k in keys}
        try:
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "config.example.toml").write_text(self.TOML, encoding="utf-8")
                (root / ".env").write_text(
                    "CLEARNIGHT_LLM_BASE_URL=http://dotenv:2/v1\n", encoding="utf-8")
                os.environ["CLEARNIGHT_LLM_BASE_URL"] = "http://env:3/v1"
                cfg = self._load_in_dir(root, self.TOML)
                # real environment wins over .env
                self.assertEqual(cfg.llm.base_url, "http://env:3/v1")
                # unset keys leave TOML values intact
                self.assertEqual(cfg.llm.model, "toml-model")
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
                else:
                    os.environ.pop(k, None)

    def test_env_override_applies_to_explicit_path_too(self):
        keys = ["CLEARNIGHT_LLM_BASE_URL"]
        saved = {k: os.environ.pop(k, None) for k in keys}
        try:
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "c.toml"
                p.write_text(self.TOML, encoding="utf-8")
                os.environ["CLEARNIGHT_LLM_BASE_URL"] = "http://env:4/v1"
                cfg = load_config(str(p))
            self.assertEqual(cfg.llm.base_url, "http://env:4/v1")
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
                else:
                    os.environ.pop(k, None)


if __name__ == "__main__":
    unittest.main()
