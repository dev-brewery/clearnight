"""TOML config load/merge/validate (ARCHITECTURE.md §4).

Explicit path -> that file only. No path -> config.local.toml merged over
config.example.toml in cwd (missing both -> ConfigError). Validation errors
always name the offending field.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from clearnight.models import Site


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class SensorCfg:
    kind: str
    path: str | None = None
    url: str | None = None
    field_map: dict[str, str] | None = None
    timeout_s: int = 10
    # Extra HTTP headers (e.g. Authorization). config.local.toml ONLY — never
    # commit tokens. TOML table [sensor.headers]. Keys and values must be str.
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class LLMCfg:
    base_url: str
    model: str
    api_key: str | None = None
    timeout_s: int = 30
    # Reasoning models spend tokens on thinking before the answer; a small
    # budget yields finish_reason "length" with empty content (T20a).
    max_tokens: int = 2000
    # Extra request-body fields merged into the chat/completions JSON
    # (extra_body keys win over defaults). e.g. GLM thinking level:
    # {"thinking": {"type": "enabled", "level": "low"}}.
    extra_body: dict | None = None


@dataclass(frozen=True)
class Config:
    site: Site
    sensor: SensorCfg
    llm: LLMCfg
    nights: int = 7
    cache_dir: Path = Path("cache")
    out_dir: Path = Path("out")


_SENSOR_REQUIRED = {"csv": ["path"], "http_json": ["url", "field_map"]}


def _err(field: str, msg: str) -> ConfigError:
    return ConfigError(f"config field '{field}': {msg}")


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    v = data.get(name)
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise _err(name, "must be a [table]")
    return v


def _validate(site: dict[str, Any], sensor: dict[str, Any], llm: dict[str, Any],
              nights: Any, cache_dir: Any, out_dir: Any) -> Config:
    for f in ("name", "lat", "lon", "elevation_m", "tz"):
        if f not in site:
            raise _err(f"site.{f}", "required")
    if not isinstance(site["lat"], (int, float)) or isinstance(site["lat"], bool):
        raise _err("site.lat", "must be a number")
    if not -90.0 <= site["lat"] <= 90.0:
        raise _err("site.lat", f"must be in [-90, 90], got {site['lat']}")
    if not isinstance(site["lon"], (int, float)) or isinstance(site["lon"], bool):
        raise _err("site.lon", "must be a number")
    if not -180.0 <= site["lon"] <= 180.0:
        raise _err("site.lon", f"must be in [-180, 180], got {site['lon']}")
    if not isinstance(site["elevation_m"], (int, float)) or isinstance(site["elevation_m"], bool):
        raise _err("site.elevation_m", "must be a number")
    if site["elevation_m"] < -430:
        raise _err("site.elevation_m", f"must be >= -430, got {site['elevation_m']}")
    try:
        ZoneInfo(str(site["tz"]))
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise _err("site.tz", f"unknown timezone {site['tz']!r} ({e})") from e
    cfg_site = Site(str(site["name"]), float(site["lat"]), float(site["lon"]),
                    float(site["elevation_m"]), str(site["tz"]))

    if not isinstance(nights, int) or isinstance(nights, bool):
        raise _err("nights", "must be an int")
    if not 1 <= nights <= 14:
        raise _err("nights", f"must be in [1, 14], got {nights}")

    if sensor.get("kind") not in _SENSOR_REQUIRED:
        raise _err("sensor.kind", f"must be one of {sorted(_SENSOR_REQUIRED)}, "
                                  f"got {sensor.get('kind')!r}")
    kind = sensor["kind"]
    for req in _SENSOR_REQUIRED[kind]:
        if sensor.get(req) is None:
            raise _err(f"sensor.{req}", f"required when sensor.kind = '{kind}'")
    if kind == "http_json" and not isinstance(sensor["field_map"], dict):
        raise _err("sensor.field_map", "must be a [table] of response-key -> Reading field")
    timeout = sensor.get("timeout_s", 10)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        raise _err("sensor.timeout_s", "must be a positive int")
    headers = sensor.get("headers")
    if headers is not None:
        if not isinstance(headers, dict):
            raise _err("sensor.headers", "must be a [table] of header-name -> value")
        for k, v in headers.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise _err("sensor.headers", "header names and values must be strings")
    sensor_cfg = SensorCfg(kind, sensor.get("path"), sensor.get("url"),
                           sensor.get("field_map"), timeout, headers)

    for f in ("base_url", "model"):
        if not llm.get(f):
            raise _err(f"llm.{f}", "required")
    if not isinstance(llm["base_url"], str) or not llm["base_url"].startswith(("http://", "https://")):
        raise _err("llm.base_url", f"must start with http:// or https://, got {llm['base_url']!r}")
    ltimeout = llm.get("timeout_s", 30)
    if not isinstance(ltimeout, int) or isinstance(ltimeout, bool) or ltimeout <= 0:
        raise _err("llm.timeout_s", "must be a positive int")
    api_key = llm.get("api_key")
    if api_key is not None and not isinstance(api_key, str):
        raise _err("llm.api_key", "must be a string")
    max_tokens = llm.get("max_tokens", 2000)
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
        raise _err("llm.max_tokens", "must be a positive int")
    extra_body = llm.get("extra_body")
    if extra_body is not None:
        if not isinstance(extra_body, dict):
            raise _err("llm.extra_body", "must be a [llm.extra_body] table")
        try:
            json.dumps(extra_body)
        except (TypeError, ValueError) as e:
            raise _err("llm.extra_body",
                       f"must be JSON-serializable ({e})") from e
    llm_cfg = LLMCfg(str(llm["base_url"]), str(llm["model"]), api_key,
                     ltimeout, max_tokens, extra_body)

    for name, v in (("cache_dir", cache_dir), ("out_dir", out_dir)):
        if v is not None and not isinstance(v, (str, Path)):
            raise _err(name, "must be a path string")

    return Config(cfg_site, sensor_cfg, llm_cfg, nights,
                  Path(cache_dir or "cache"), Path(out_dir or "out"))


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        # A malformed user config is a clean error naming the file and the
        # parse problem — never a traceback (T25).
        raise ConfigError(f"invalid TOML in {path}: {e}") from e


_ENV_KEYS = {
    "CLEARNIGHT_LLM_BASE_URL": ("llm", "base_url"),
    "CLEARNIGHT_LLM_MODEL": ("llm", "model"),
    "CLEARNIGHT_LLM_API_KEY": ("llm", "api_key"),
    "CLEARNIGHT_SENSOR_URL": ("sensor", "url"),
}


def load_dotenv(path: Path | None = None) -> None:
    """Parse a .env file (KEY=VALUE lines, # comments, optional quotes) and
    os.environ.setdefault each key: the real environment wins over .env, .env
    wins over nothing. Called by load_config; safe if no .env exists."""
    p = path if path is not None else Path(".env")
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def _apply_env_overrides(data: dict[str, Any]) -> None:
    """Env vars (CLEARNIGHT_*) override the corresponding TOML values when set."""
    for key, (section, field) in _ENV_KEYS.items():
        val = os.environ.get(key)
        if val is not None:
            data.setdefault(section, {})[field] = val


def load_config(path: str | None = None) -> Config:
    load_dotenv()
    if path is not None:
        p = Path(path)
        if not p.is_file():
            raise ConfigError(f"config file not found: {p}")
        data = _load_toml(p)
    else:
        example = Path("config.example.toml")
        local = Path("config.local.toml")
        if not example.is_file() and not local.is_file():
            raise ConfigError(
                f"no config found: searched {example} and {local} in "
                f"{Path.cwd()}; provide one or pass an explicit path"
            )
        data = _load_toml(example) if example.is_file() else {}
        if local.is_file():
            _deep_merge(data, _load_toml(local))
    _apply_env_overrides(data)
    return _validate(_section(data, "site"), _section(data, "sensor"),
                     _section(data, "llm"), data.get("nights", 7),
                     data.get("cache_dir", "cache"), data.get("out_dir", "out"))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
