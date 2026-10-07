"""CLI entry point: plan | log | fetch (ARCHITECTURE.md §4).

T06: `fetch --record-fixtures` records the demo fixture set from the live APIs
(one-time run, network available); bare `fetch` prints fixture status offline.
`plan` still prints a placeholder (real pipeline T14); `log` lands in T17.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import urllib.request

from clearnight import fixtures
from clearnight.config import ConfigError, load_config

LOG_MSG = "log: not implemented until T17"
FETCH_MSG = "fetch: not implemented until T06"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clearnight", description="Stargazing planner."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="generate a stargazing plan")
    p_plan.add_argument("--offline", action="store_true",
                        help="run offline against committed fixtures (fixture epoch)")
    p_plan.add_argument("--config", default=None, metavar="PATH",
                        help="explicit config file (else config.local.toml over config.example.toml)")
    p_plan.add_argument("--nights", type=int, default=None, metavar="N",
                        help="number of nights, 1-14 (overrides config)")

    p_log = sub.add_parser("log", help="append a field-log entry")
    p_log.add_argument("--date", required=True, metavar="YYYY-MM-DD")
    p_log.add_argument("--went-out", action="store_true")
    p_log.add_argument("--clearness", type=int, choices=range(0, 6), default=None, metavar="0-5")
    p_log.add_argument("--meteors", type=int, default=None, metavar="N")
    p_log.add_argument("--iss-seen", action="store_true")
    p_log.add_argument("--notes", default=None, metavar="TEXT")

    p_fetch = sub.add_parser("fetch", help="fetch/cache external data")
    p_fetch.add_argument("--record-fixtures", action="store_true",
                         help="record demo fixtures from the live APIs (needs network)")

    return parser


def _cmd_plan(args: argparse.Namespace) -> int:
    if args.nights is not None and not 1 <= args.nights <= 14:
        print(f"--nights must be in [1, 14], got {args.nights}", file=sys.stderr)
        return 2
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 1
    nights = args.nights if args.nights is not None else cfg.nights
    mode = "OFFLINE (fixture epoch)" if args.offline else "ONLINE"
    site = cfg.site
    print(f"site: {site.name}")
    print(f"location: {site.lat:.4f}, {site.lon:.4f}")
    print(f"nights: {nights}")
    print(f"mode: {mode}")
    print("placeholder plan - real pipeline lands in T14")
    return 0


def _cmd_log(_args: argparse.Namespace) -> int:
    print(LOG_MSG)
    return 0


FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude=36.85&longitude=-102.88"
    "&hourly=temperature_2m,relative_humidity_2m,dew_point_2m,cloud_cover"
    ",cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility"
    ",wind_speed_10m,pressure_msl&past_days=1&forecast_days=8&timezone=UTC"
)
TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"
UA = "clearnight/0.1 (github.com/dev-brewery/clearnight)"
SENSOR_HEADER = [
    "timestamp_utc", "temperature_c", "humidity_pct", "pressure_hpa",
    "dew_point_c",
]


def _get(url: str, timeout: float = 15.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _build_sensor_rows(forecast: dict) -> list[list[str]]:
    """Past-day analysis hours of the forecast reply -> sensor.csv rows."""
    hourly = forecast["hourly"]
    times: list[str] = hourly["time"]
    # Analysis (past) hours have minute == "00" and fall on/before today's date.
    now_date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    rows = []
    for i, ts in enumerate(times):
        if ts > now_date + "T23:59":
            continue
        if dt.datetime.fromisoformat(ts) > dt.datetime.now(dt.timezone.utc).replace(tzinfo=None):
            continue
        rows.append([
            ts + ":00Z" if len(ts) == 16 else ts,
            str(hourly["temperature_2m"][i]),
            str(hourly["relative_humidity_2m"][i]),
            str(hourly["pressure_msl"][i]),
            str(hourly["dew_point_2m"][i]),
        ])
    return rows


def _record_fixtures() -> int:
    fdir = fixtures.FIXTURES_DIR
    fdir.mkdir(parents=True, exist_ok=True)
    try:
        forecast_raw = _get(FORECAST_URL)
        forecast = json.loads(forecast_raw)
        tle_raw = _get(TLE_URL)
    except Exception as e:  # noqa: BLE001 - report any network failure cleanly
        print(f"fetch: recording failed: {e}", file=sys.stderr)
        return 1
    sensor_rows = _build_sensor_rows(forecast)
    manifest = {
        "reference_date": "2026-10-07",
        "site": {
            "name": "Black Mesa State Park (demo)",
            "lat": 36.85,
            "lon": -102.88,
            "tz": "America/Chicago",
        },
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "sky_json": "recorded in T07",
        "provenance": {
            "forecast": "Open-Meteo forecast API (keyless)",
            "tle": "CelesTrak GP NORAD 25544",
            "sensor": (
                "Open-Meteo past-day analysis hours for the demo site"),
        },
    }
    # All data in hand: write atomically enough (nothing partial on error above).
    (fdir / "forecast.json").write_bytes(forecast_raw)
    (fdir / "tle.txt").write_bytes(tle_raw)
    with open(fdir / "sensor.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SENSOR_HEADER)
        w.writerows(sensor_rows)
    (fdir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"fixtures recorded in {fdir}")
    return 0


def _fetch_status() -> int:
    try:
        m = fixtures.load_manifest()
    except FileNotFoundError:
        print("fetch: no fixtures recorded yet (manifest.json missing)")
        return 0
    fdir = fixtures.FIXTURES_DIR
    for name in ("forecast.json", "tle.txt", "sensor.csv"):
        p = fdir / name
        state = f"{p.stat().st_size} bytes" if p.is_file() else "MISSING"
        print(f"{name}: {state}")
    print(f"sky.json: {m.get('sky_json', 'missing')}")
    print(f"reference_date: {m['reference_date']} (offline epoch)")
    print("generated_utc: " + m.get("generated_utc", "?"))
    return 0


def _cmd_fetch(args: argparse.Namespace) -> int:
    if args.record_fixtures:
        return _record_fixtures()
    print(FETCH_MSG)
    return _fetch_status()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "plan":
        return _cmd_plan(args)
    if args.command == "log":
        return _cmd_log(args)
    return _cmd_fetch(args)


if __name__ == "__main__":
    sys.exit(main())
