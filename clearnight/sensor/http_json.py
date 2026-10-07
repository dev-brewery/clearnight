"""HTTP-JSON sensor adapter: one GET, fields mapped via dotted paths."""

from __future__ import annotations

import datetime as dt
import json
import warnings
import urllib.request

from clearnight.models import Reading


def _dig(obj: object, dotted: str) -> object:
    cur: object = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


class HttpJsonAdapter:
    def __init__(self, url: str, field_map: dict[str, str], timeout_s: int = 10,
                 headers: dict[str, str] | None = None) -> None:
        self.url = url
        self.field_map = field_map
        self.timeout_s = timeout_s
        self.headers = headers or {}

    def read_recent(self, hours: int = 6, now_utc: dt.datetime | None = None) -> list[Reading]:
        now = now_utc or dt.datetime.now(dt.timezone.utc)
        try:
            hdrs = {"User-Agent": "clearnight/0.1", **self.headers}
            req = urllib.request.Request(self.url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            raw_ts = _dig(body, self.field_map["timestamp"]) if "timestamp" in self.field_map else None
            ts = (dt.datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                  if raw_ts else now)

            def opt(key: str) -> float | None:
                v = _dig(body, self.field_map[key]) if key in self.field_map else None
                return float(v) if v is not None else None

            reading = Reading(ts, opt("temperature"), opt("humidity"),
                              opt("pressure"), opt("dew_point"))
            return [reading]
        except Exception as exc:  # transport or parse error: degrade, never crash
            warnings.warn(f"sensor http_json failed: {type(exc).__name__}")
            return []
