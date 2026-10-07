"""Committed demo fixtures + epoch pinning (ARCHITECTURE §4 fixtures.py contract).

load_manifest() reads clearnight/fixtures/manifest.json. resolve_today() pins the
epoch: offline => the manifest reference_date; online => today in the given tz.
"""

from __future__ import annotations

import json
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_manifest() -> dict:
    path = FIXTURES_DIR / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_today(offline: bool, tz: ZoneInfo) -> dt.date:
    if offline:
        ref = load_manifest()["reference_date"]
        return dt.date.fromisoformat(ref)
    return dt.datetime.now(tz).date()
