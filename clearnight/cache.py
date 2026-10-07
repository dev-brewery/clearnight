"""Disk cache with per-key max-age (ARCHITECTURE §4 cache.py contract)."""

from __future__ import annotations

import time
from pathlib import Path


class Cache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        if not key:
            raise ValueError("cache key must not be empty")
        if key in (".", "..") or "/" in key or "\\" in key:
            raise ValueError(f"invalid cache key: {key!r}")
        p = self.root / key
        # Defense in depth: resolved path must stay inside root.
        if p.resolve().parent != self.root.resolve():
            raise ValueError(f"invalid cache key: {key!r}")
        return p

    def get(self, key: str, max_age_s: int | None) -> bytes | None:
        try:
            p = self.path(key)
        except ValueError:
            raise
        if not p.is_file():
            return None
        if max_age_s is not None:
            if time.time() - p.stat().st_mtime > max_age_s:
                return None
        return p.read_bytes()

    def put(self, key: str, data: bytes) -> None:
        p = self.path(key)
        p.write_bytes(data)

    def fresh(self, key: str, max_age_s: int) -> bool:
        return self.get(key, max_age_s) is not None

    def age(self, key: str) -> float | None:
        p = self.path(key)
        if not p.is_file():
            return None
        return time.time() - p.stat().st_mtime
