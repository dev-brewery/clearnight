"""Sensor adapters: SensorAdapter protocol + make_adapter factory.

Adapters return Reading lists for the last `hours` (cutoff (now-hours, now]).
`now_utc` pins 'now' for deterministic offline behavior; defaults to real now.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Protocol, runtime_checkable

from clearnight.config import SensorCfg
from clearnight.models import Reading
from clearnight.sensor.csv_adapter import CSVAdapter
from clearnight.sensor.http_json import HttpJsonAdapter

__all__ = ["Reading", "SensorAdapter", "make_adapter", "CSVAdapter", "HttpJsonAdapter"]


@runtime_checkable
class SensorAdapter(Protocol):
    def read_recent(self, hours: int = 6,
                    now_utc: dt.datetime | None = None) -> list[Reading]: ...


def make_adapter(cfg: SensorCfg) -> SensorAdapter:
    if cfg.kind == "csv":
        from clearnight.sensor.csv_adapter import CSVAdapter
        return CSVAdapter(Path(cfg.path))  # type: ignore[arg-type]
    if cfg.kind == "http_json":
        from clearnight.sensor.http_json import HttpJsonAdapter
        return HttpJsonAdapter(cfg.url, cfg.field_map, cfg.timeout_s)  # type: ignore[arg-type]
    raise ValueError(f"unknown sensor kind: {cfg.kind!r}")
