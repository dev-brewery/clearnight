"""CLI entry point: plan | log | fetch (ARCHITECTURE.md §4).

T06: `fetch --record-fixtures` records the demo fixture set from the live APIs
(one-time run, network available); bare `fetch` prints fixture status offline.
T14: `plan --offline` assembles the full night plan from committed fixtures
(no network, no LLM; template brief). T15: rendering moved to clearnight.render
(red-on-black HTML + <=80-col text); this module builds the Plan structure and
delegates. T16: `plan` (no --offline) runs the ONLINE path: live sky from the
cached ephemeris, live Open-Meteo forecast through the cache, real sensor
adapter, fresh TLE + computed ISS passes — every source with its fallback
chain, provenance collected into the footer. `log` lands in T17.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from clearnight import fixtures, render
from clearnight.cache import Cache
from clearnight.config import Config, ConfigError, load_config
from clearnight.conditions import assess
from clearnight.forecast import cache_key, fetch_hourly, slice_to_window
from clearnight.iss import TLE_MAX_AGE_S, load_tle, visible_passes
from clearnight.meteors import events_for_night, load_showers
from clearnight.models import DarkWindow, MoonInfo, Night
from clearnight.models import ISSPass as ISSPassModel
from clearnight.render import TEMPLATE_BRIEF_LABEL, Plan
from clearnight.sensor import make_adapter
from clearnight.score import rank, score_night
from clearnight.sky import (
    BSP_NAME,
    SkyUnavailable,
    dark_windows,
    load_ephemeris,
    moon_info,
    radiant_up_hours,
)

LOG_MSG = "log: not implemented until T17"
FETCH_MSG = "fetch: not implemented until T06"
FIXTURES_SKY = Path(__file__).parent / "fixtures" / "sky.json"


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


def _load_sky_doc() -> dict:
    return json.loads(FIXTURES_SKY.read_text(encoding="utf-8"))



def run_plan(argv: list[str]) -> int:
    """Run the plan pipeline; main() delegates here (in-process testability)."""
    args = _build_parser().parse_args(argv)
    if args.command != "plan":
        raise ValueError("run_plan handles 'plan' only")
    if args.nights is not None and not 1 <= args.nights <= 14:
        print(f"--nights must be in [1, 14], got {args.nights}", file=sys.stderr)
        return 2
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 1
    if not args.offline:
        return _run_plan_online(cfg, args)

    n = args.nights if args.nights is not None else cfg.nights
    tz = ZoneInfo(cfg.site.tz_name)
    today = fixtures.resolve_today(offline=True, tz=tz)
    sky_doc = _load_sky_doc()
    nights_raw = sky_doc["nights"][:n]
    cache = Cache(cfg.cache_dir)
    showers = load_showers()
    radiant: dict[str, dict[str, float]] = sky_doc.get("radiant_up", {})
    ra_to_name = {
        (round(s.radiant_ra_deg, 3), round(s.radiant_dec_deg, 3)): s.name
        for s in showers
    }

    adapter = make_adapter(cfg.sensor)
    now_utc = dt.datetime(today.year, today.month, today.day, 23, 0,
                          tzinfo=dt.timezone.utc)
    readings = adapter.read_recent(6, now_utc=now_utc)

    nights: list[Night] = []
    for rec in nights_raw:
        date = dt.date.fromisoformat(rec["date_local"])
        window = DarkWindow(
            dt.datetime.fromisoformat(rec["dark_start_utc"]),
            dt.datetime.fromisoformat(rec["dark_end_utc"]),
        )
        weather = slice_to_window(
            fetch_hourly(cfg.site, window.start_utc,
                         int((window.end_utc - window.start_utc).total_seconds()
                             // 3600) + 1, cache, offline=True),
            window,
        )
        conditions = assess(readings, weather)

        def radiant_up_fn(ra_deg: float, dec_deg: float,
                          _date: dt.date = date) -> float:
            name = ra_to_name[(round(ra_deg, 3), round(dec_deg, 3))]
            return float(radiant.get(_date.isoformat(), {}).get(name, 0.0))

        night_showers = events_for_night(showers, date,
                                         radiant_up_hours_fn=radiant_up_fn)
        passes = [
            ISSPassModel(
                start_utc=dt.datetime.fromisoformat(p["start_utc"]),
                max_utc=dt.datetime.fromisoformat(p["max_utc"]),
                end_utc=dt.datetime.fromisoformat(p["end_utc"]),
                max_alt_deg=p["max_alt_deg"],
                start_dir=p["start_dir"],
                max_dir=p["max_dir"],
                end_dir=p["end_dir"],
            )
            for p in sky_doc.get("iss_passes", {}).get(date.isoformat(), [])
        ]
        m = rec["moon"]
        moon = MoonInfo(
            phase_name=m["phase_name"],
            illumination_frac=m["illumination_frac"],
            rise_utc=(dt.datetime.fromisoformat(m["rise_utc"])
                      if m.get("rise_utc") else None),
            set_utc=(dt.datetime.fromisoformat(m["set_utc"])
                     if m.get("set_utc") else None),
            up_fraction=m["up_fraction"],
            max_alt_deg=m["max_alt_deg"],
        )
        score = score_night(window, moon, weather, conditions.dew_spread_c,
                            night_showers, passes)
        nights.append(Night(date, window, moon, weather, conditions,
                            night_showers, passes, score))

    ranked = rank(nights)
    plan = Plan(site=cfg.site, mode="OFFLINE fixture epoch",
                reference_label=today.isoformat(), ranked=ranked,
                notes=("sources: committed fixtures (Open-Meteo, CelesTrak, "
                       "NASA JPL de421.bsp; pinned reference date)"))
    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.html").write_text(render.render_html(plan),
                                       encoding="utf-8")
    print(render.render_text(plan), end="")
    return 0


# -------------------------------------------------------------- online ----


def _readings_online(cfg: Config, notes: list[str]):
    """Real sensor adapter at real now; failure -> no readings, noted."""
    kind = cfg.sensor.kind
    try:
        readings = make_adapter(cfg.sensor).read_recent(6)
        notes.append(f"sensor: {kind} adapter (live read)")
        return readings
    except Exception as e:  # noqa: BLE001 - degraded source, keep planning
        notes.append(f"sensor: {kind} adapter failed ({type(e).__name__}); "
                     "no ground truth")
        return []


def _run_plan_online(cfg: Config, args: argparse.Namespace) -> int:
    """T16 online path: live sources, cache-through, per-source fallbacks.

    Exit 0 even with degraded sources (each falls back per its module chain
    and is named in the footer); non-zero only on total failure.
    """
    n = args.nights if args.nights is not None else cfg.nights
    tz = ZoneInfo(cfg.site.tz_name)
    today = fixtures.resolve_today(offline=False, tz=tz)
    cache = Cache(cfg.cache_dir)
    notes: list[str] = [f"reference date {today.isoformat()} (site tz)"]
    showers = load_showers()

    # Sky: live ephemeris, else committed fixture sky.json.
    bsp = cache.path(BSP_NAME)
    eph_ok = bsp.is_file()
    try:
        eph = load_ephemeris(cache, offline=False)
    except Exception as e:  # noqa: BLE001 - download failed -> fixture sky
        eph = None
        notes.append("ephemeris: unavailable ("
                     f"{type(e).__name__}); fixture sky.json")
    else:
        notes.append("ephemeris: de421.bsp ("
                     + ("cache" if eph_ok else "downloaded") + ")")

    def slice_forecast(window: DarkWindow):
        key = cache_key(cfg.site, window.start_utc)
        fresh_before = cache.fresh(key, 3600)
        hours = int((window.end_utc - window.start_utc).total_seconds()
                    // 3600) + 1
        weather = fetch_hourly(cfg.site, window.start_utc, hours, cache,
                               offline=False)
        if cache.get(key, None) is not None:
            notes.append("forecast: "
                         + ("cache" if fresh_before else "network")
                         + " (Open-Meteo, cache max-age 1 h)")
        else:
            notes.append("forecast: network unavailable; committed "
                         "fixture fallback (dates may not overlap)")
        if not weather:
            notes.append("forecast: no hours overlap the dark window")
        return weather

    windows: list[DarkWindow]
    if eph is not None:
        windows = dark_windows(cfg.site, today, n, eph)
    else:
        windows = []
        notes.append("sky: live dark windows unavailable; fixture windows")
    notes.append(f"dark windows: {len(windows)} of {n} nights with "
                 "astronomical darkness")

    # ISS: fresh TLE within 24 h, else stale cache / fixture (flagged).
    try:
        tle = load_tle(cache, offline=False)
    except Exception as e:  # noqa: BLE001
        tle = None
        notes.append(f"TLE: load failed ({type(e).__name__}); no passes")
    else:
        if tle.source != "cache":
            notes.append(f"TLE: {tle.source} (passes may be off)")
        else:
            notes.append(f"TLE: CelesTrak via cache (max-age "
                         f"{TLE_MAX_AGE_S // 3600} h)")
    try:
        passes_all = (visible_passes(cfg.site, windows, tle.groups)
                      if tle is not None and windows else [])
    except Exception as e:  # noqa: BLE001 - bsp/sat computation failure
        passes_all = []
        notes.append(f"ISS: pass computation failed ({type(e).__name__})")

    readings = _readings_online(cfg, notes)

    nights: list[Night] = []
    if eph is not None:
        night_sources = ((win.start_utc.astimezone(tz).date(), win)
                         for win in windows)
    else:
        sky_doc = _load_sky_doc()
        radiant: dict[str, dict[str, float]] = sky_doc.get("radiant_up", {})
        moon_by_date = {
            rec["date_local"]: rec["moon"] for rec in sky_doc["nights"]
        }
        ra_to_name = {
            (round(s.radiant_ra_deg, 3), round(s.radiant_dec_deg, 3)): s.name
            for s in showers
        }
        night_sources = [
            (dt.date.fromisoformat(rec["date_local"]),
             DarkWindow(dt.datetime.fromisoformat(rec["dark_start_utc"]),
                        dt.datetime.fromisoformat(rec["dark_end_utc"])))
            for rec in sky_doc["nights"][:n]
        ]
    for date, window in night_sources:
        weather = slice_forecast(window)
        conditions = assess(readings, weather)

        if eph is not None:
            moon = moon_info(cfg.site, window, eph)

            def radiant_up_fn(ra_deg: float, dec_deg: float,
                              _win: DarkWindow = window) -> float:
                return radiant_up_hours(cfg.site, _win, ra_deg, dec_deg, eph)
        else:
            m = moon_by_date[date.isoformat()]
            moon = MoonInfo(
                phase_name=m["phase_name"],
                illumination_frac=m["illumination_frac"],
                rise_utc=(dt.datetime.fromisoformat(m["rise_utc"])
                          if m.get("rise_utc") else None),
                set_utc=(dt.datetime.fromisoformat(m["set_utc"])
                         if m.get("set_utc") else None),
                up_fraction=m["up_fraction"],
                max_alt_deg=m["max_alt_deg"],
            )

            def radiant_up_fn(ra_deg: float, dec_deg: float,
                              _date: dt.date = date) -> float:
                name = ra_to_name[(round(ra_deg, 3), round(dec_deg, 3))]
                return float(radiant.get(_date.isoformat(), {}).get(name, 0.0))

        night_showers = events_for_night(showers, date,
                                         radiant_up_hours_fn=radiant_up_fn)
        passes = [p for p in passes_all
                  if window.start_utc <= p.start_utc <= window.end_utc]
        score = score_night(window, moon, weather, conditions.dew_spread_c,
                            night_showers, passes)
        nights.append(Night(date, window, moon, weather, conditions,
                            night_showers, passes, score))

    ranked = rank(nights)
    plan = Plan(site=cfg.site, mode="ONLINE live",
                reference_label=today.isoformat(), ranked=ranked,
                notes=tuple(notes))
    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.html").write_text(render.render_html(plan),
                                       encoding="utf-8")
    print(render.render_text(plan), end="")
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
        return run_plan(argv)
    if args.command == "log":
        return _cmd_log(args)
    return _cmd_fetch(args)


if __name__ == "__main__":
    sys.exit(main())
