"""CLI entry point: plan | log | fetch (ARCHITECTURE.md §4).

T06: `fetch --record-fixtures` records the demo fixture set from the live APIs
(one-time run, network available); bare `fetch` prints fixture status offline.
T14: `plan --offline` assembles the full night plan from committed fixtures
(no network, no LLM; template brief). Online wiring lands in T16;
`log` lands in T17.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import sys
import textwrap
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from clearnight import fixtures
from clearnight.cache import Cache
from clearnight.config import Config, ConfigError, load_config
from clearnight.conditions import assess
from clearnight.forecast import fetch_hourly, slice_to_window
from clearnight.meteors import events_for_night, load_showers
from clearnight.models import DarkWindow, HourWeather, MoonInfo, Night, NightScore
from clearnight.models import ISSPass as ISSPassModel
from clearnight.sensor import make_adapter
from clearnight.score import rank, score_night

LOG_MSG = "log: not implemented until T17"
FETCH_MSG = "fetch: not implemented until T06"
ONLINE_MSG = (
    "plan: online mode wiring lands in T16 "
    "(offline mode against fixtures is implemented)"
)
TEMPLATE_BRIEF_LABEL = (
    "Template brief (LLM output unavailable or failed verification; "
    "all values are computed, not generated)."
)
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


def _fmt_hms(when: dt.datetime) -> str:
    return when.strftime("%H:%M")


def _to_local(when: dt.datetime | None, tz: ZoneInfo) -> dt.datetime | None:
    if when is None:
        return None
    return when.astimezone(tz)


def _cloud_mean(weather: list[HourWeather]) -> float | None:
    vals = [w.cloud_total_pct for w in weather if w.cloud_total_pct is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _breakdown_lines(score: NightScore) -> list[str]:
    return [
        f"total {score.total} {score.verdict} | base {score.base:.1f}",
        f"cloud {score.cloud_term:.2f} moon {score.moon_term:.2f} "
        f"trans {score.transparency_term:.2f} dew {score.dew_term:.2f} "
        f"wind {score.wind_term:.2f}",
        f"meteor_bonus {score.meteor_bonus} iss_bonus {score.iss_bonus}",
    ]


def _shower_lines(night: Night, tz: ZoneInfo) -> list[str]:
    if not night.showers:
        return ["showers: none active"]
    lines = []
    for s in night.showers:
        mark = " PEAK" if s.is_peak_night else ""
        lines.append(
            f"shower: {s.name} ZHR {s.zhr:g} radiant up {s.radiant_up_hours:.1f}h{mark}"
        )
    return lines


def _iss_lines(night: Night, tz: ZoneInfo) -> list[str]:
    if not night.iss_passes:
        return ["iss: no visible passes"]
    lines = []
    for p in night.iss_passes:
        s = _to_local(p.start_utc, tz)
        m = _to_local(p.max_utc, tz)
        e = _to_local(p.end_utc, tz)
        lines.append(
            f"iss: {_fmt_hms(s)}-{_fmt_hms(e)} max {_fmt_hms(m)} "
            f"{p.max_alt_deg:.0f}deg {p.start_dir}>{p.max_dir}>{p.end_dir}"
        )
    return lines


def _moon_line(night: Night, tz: ZoneInfo) -> str:
    moon = night.moon
    rise = _to_local(moon.rise_utc, tz)
    set_ = _to_local(moon.set_utc, tz)
    rs = (
        f"rise {_fmt_hms(rise) if rise else '-'} "
        f"set {_fmt_hms(set_) if set_ else '-'}"
    )
    return (
        f"moon: {moon.phase_name} illum {moon.illumination_frac * 100:.0f}% {rs}"
    )


def _night_block(night: Night, tz: ZoneInfo) -> list[str]:
    ws = _to_local(night.dark.start_utc, tz)
    we = _to_local(night.dark.end_utc, tz)
    cloud = _cloud_mean(night.weather)
    lines = [
        f"night {night.date_local.isoformat()}",
    ]
    lines.extend("  " + l for l in _breakdown_lines(night.score))
    lines.extend([
        f"  dark window (local): {_fmt_hms(ws)}-{_fmt_hms(we)}",
        "  " + _moon_line(night, tz),
        f"  clouds: mean {cloud if cloud is not None else 'n/a'}%"
        f" | dew risk: {night.conditions.dew_risk}"
        f" (spread {night.conditions.dew_spread_c:.1f}C)",
    ])
    if night.score.reasons:
        lines.append("  notes: " + ", ".join(night.score.reasons))
    lines.extend("  " + l for l in _shower_lines(night, tz))
    lines.extend("  " + l for l in _iss_lines(night, tz))
    return lines


def _wrap78(text: str) -> list[str]:
    return textwrap.wrap(text, width=78, subsequent_indent="  ",
                         break_long_words=False, break_on_hyphens=False)


def _template_brief(ranked: list[Night], tz: ZoneInfo) -> list[str]:
    """Template brief from computed data only (LLM lands T18/T20)."""
    lines = [TEMPLATE_BRIEF_LABEL]
    for night in ranked[:3]:
        ws = _to_local(night.dark.start_utc, tz)
        we = _to_local(night.dark.end_utc, tz)
        when = f"go {_fmt_hms(ws)}-{_fmt_hms(we)} local"
        peaks = [s.name for s in night.showers if s.is_peak_night]
        active = [s.name for s in night.showers if not s.is_peak_night]
        look: list[str] = []
        if peaks:
            look.append(f"{', '.join(peaks)} PEAK")
        if active:
            look.append(f"{', '.join(active)} active")
        if night.iss_passes:
            look.append(f"{len(night.iss_passes)} ISS pass(es)")
        if night.moon.illumination_frac * night.moon.up_fraction < 0.1:
            look.append("dark moon")
        line = (
            f"- {night.date_local.isoformat()} (score {night.score.total} "
            f"{night.score.verdict}): {when}; look for "
            + ("; ".join(look) if look else "deep-sky under dark skies")
            + "."
        )
        lines.extend(_wrap78(line))
    return lines


def _text_summary(ranked: list[Night], cfg: Config) -> str:
    tz = ZoneInfo(cfg.site.tz_name)
    lines: list[str] = []
    lines.append(f"stargazing plan - {cfg.site.name} (OFFLINE fixture epoch)")
    lines.append(
        f"site {cfg.site.lat:.2f}, {cfg.site.lon:.2f} | "
        f"{len(ranked)} nights, ranked"
    )
    lines.append("")
    for night in ranked:
        lines.extend(_night_block(night, tz))
        lines.append("")
    lines.extend(_template_brief(ranked, tz))
    lines.append("")
    for row in _wrap78(
        "data: committed fixtures (Open-Meteo, CelesTrak, NASA JPL de421); "
        "generated for reference date 2026-10-07 (OFFLINE)"
    ):
        lines.append(row)
    return "\n".join(lines) + "\n"


def _html_plan(ranked: list[Night], cfg: Config) -> str:
    tz = ZoneInfo(cfg.site.tz_name)
    esc = html.escape
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        "<title>clearnight plan (offline)</title></head><body>",
        f"<h1>Stargazing plan - {esc(cfg.site.name)} (OFFLINE fixture epoch)</h1>",
    ]
    for night in ranked:
        parts.append(f"<h2>Night {esc(night.date_local.isoformat())}</h2>")
        parts.append("<ul>")
        for line in _night_block(night, tz):
            parts.append(f"<li>{esc(line.strip())}</li>")
        parts.append("</ul>")
    parts.append("<h2>Brief</h2><ul>")
    for line in _template_brief(ranked, tz):
        parts.append(f"<li>{esc(line)}</li>")
    parts.append("</ul>")
    parts.append(
        "<footer>Fixture provenance: committed demo fixtures (Open-Meteo "
        "forecast, CelesTrak TLE, NASA JPL de421.bsp). Generated for pinned "
        "reference date 2026-10-07. Mode: OFFLINE.</footer>"
    )
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


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
        print(ONLINE_MSG)
        return 0

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
    text = _text_summary(ranked, cfg)
    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.html").write_text(_html_plan(ranked, cfg), encoding="utf-8")
    print(text, end="")
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
