"""TOML config load/merge/validate (ARCHITECTURE.md §4).

Explicit path -> that file only. No path -> config.local.toml merged over
config.example.toml in cwd (missing both -> ConfigError). Validation errors
always name the offending field.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class LLMCfg:
    base_url: str
    model: str
    api_key: str | None = None
    timeout_s: int = 30


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
    sensor_cfg = SensorCfg(kind, sensor.get("path"), sensor.get("url"),
                           sensor.get("field_map"), timeout)

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
    llm_cfg = LLMCfg(str(llm["base_url"]), str(llm["model"]), api_key, ltimeout)

    for name, v in (("cache_dir", cache_dir), ("out_dir", out_dir)):
        if v is not None and not isinstance(v, (str, Path)):
            raise _err(name, "must be a path string")

    return Config(cfg_site, sensor_cfg, llm_cfg, nights,
                  Path(cache_dir or "cache"), Path(out_dir or "out"))


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_config(path: str | None = None) -> Config:
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
    return _validate(_section(data, "site"), _section(data, "sensor"),
                     _section(data, "llm"), data.get("nights", 7),
                     data.get("cache_dir", "cache"), data.get("out_dir", "out"))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
