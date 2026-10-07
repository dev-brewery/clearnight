"""Field log: append/read JSONL entries, match to nights (T17, ARCH §4).

Storage: `out/fieldlog.jsonl`, one JSON object per line, keys matching the
FieldLogEntry fields; dates ISO (date_local "YYYY-MM-DD", recorded_utc ISO
8601 with offset). Corrupt lines are skipped with a warning on stderr — a
bad night never breaks the plan. Matching is on date_local; when several
entries share a date the LATEST recorded_utc wins (evening + morning
addendum logging is expected).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from clearnight.models import FieldLogEntry, Night

LOG_FILENAME = "fieldlog.jsonl"


def _entry_to_dict(entry: FieldLogEntry) -> dict:
    return {
        "date_local": entry.date_local.isoformat(),
        "went_out": entry.went_out,
        "clearness": entry.clearness,
        "meteors_counted": entry.meteors_counted,
        "iss_seen": entry.iss_seen,
        "notes": entry.notes,
        "recorded_utc": entry.recorded_utc.isoformat(),
    }


def _entry_from_dict(obj: dict) -> FieldLogEntry:
    return FieldLogEntry(
        date_local=dt.date.fromisoformat(obj["date_local"]),
        went_out=bool(obj["went_out"]),
        clearness=int(obj["clearness"]),
        meteors_counted=int(obj["meteors_counted"]),
        iss_seen=bool(obj["iss_seen"]),
        notes=str(obj.get("notes", "")),
        recorded_utc=dt.datetime.fromisoformat(obj["recorded_utc"]),
    )


def log_path(out_dir: Path) -> Path:
    return Path(out_dir) / LOG_FILENAME


def append_entry(out_dir: Path, entry: FieldLogEntry) -> None:
    """Append one entry as a JSONL line, creating the file if needed."""
    p = log_path(out_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_entry_to_dict(entry), ensure_ascii=False) + "\n")


def read_entries(out_dir: Path) -> list[FieldLogEntry]:
    """Parse all entries; corrupt lines are skipped with a stderr warning."""
    p = log_path(out_dir)
    if not p.is_file():
        return []
    entries: list[FieldLogEntry] = []
    with p.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(_entry_from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                print(f"warning: {p}:{lineno}: skipping corrupt field-log "
                      f"line ({type(e).__name__})", file=sys.stderr)
    return entries


def match_to_nights(
    nights: list[Night], entries: list[FieldLogEntry]
) -> list[tuple[Night, FieldLogEntry | None]]:
    """Pair each night with its log entry (latest recorded_utc wins), or None."""
    latest: dict[dt.date, FieldLogEntry] = {}
    for e in entries:
        cur = latest.get(e.date_local)
        if cur is None or e.recorded_utc > cur.recorded_utc:
            latest[e.date_local] = e
    return [(n, latest.get(n.date_local)) for n in nights]
