"""CSV sensor adapter: read_recent from an hourly sensor.csv file."""

from __future__ import annotations

import csv
import datetime as dt
import warnings
from pathlib import Path

from clearnight.models import Reading

_HEADER = ["timestamp_utc", "temperature_c", "humidity_pct", "pressure_hpa", "dew_point_c"]
_FIELDS = _HEADER[1:]


def _parse_ts(raw: str) -> dt.datetime:
    return dt.datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))


class CSVAdapter:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read_recent(self, hours: int = 6, now_utc: dt.datetime | None = None) -> list[Reading]:
        now = now_utc or dt.datetime.now(dt.timezone.utc)
        cutoff = now - dt.timedelta(hours=hours)
        if not self.path.is_file():
            warnings.warn(f"sensor csv not found: {self.path.name}")
            return []
        out: list[Reading] = []
        with self.path.open(newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            for lineno, row in enumerate(reader, start=1):
                if lineno == 1:
                    continue  # header
                if not row or all(c.strip() == "" for c in row):
                    continue
                try:
                    ts = _parse_ts(row[0])
                    vals: dict[str, float | None] = {}
                    for i, name in enumerate(_FIELDS, start=1):
                        cell = row[i].strip() if i < len(row) else ""
                        vals[name] = float(cell) if cell else None
                except (ValueError, IndexError):
                    warnings.warn(f"skipping malformed sensor row at line {lineno}")
                    continue
                if cutoff < ts <= now:
                    out.append(Reading(ts, vals["temperature_c"], vals["humidity_pct"],
                                       vals["pressure_hpa"], vals["dew_point_c"]))
        out.sort(key=lambda r: r.timestamp_utc)
        return out
