"""CLI entry point: plan | log | fetch (ARCHITECTURE.md §4).

T05 skeleton: `plan` loads config and prints a placeholder plan (no network,
no LLM); `log` and `fetch` are stubs printing their intent. The real pipeline
lands in T14 (plan), T17 (log), T06+ (fetch).
"""

from __future__ import annotations

import argparse
import sys

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

    sub.add_parser("fetch", help="fetch/cache external data")

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


def _cmd_fetch(_args: argparse.Namespace) -> int:
    print(FETCH_MSG)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "plan":
        return _cmd_plan(args)
    if args.command == "log":
        return _cmd_log(args)
    return _cmd_fetch(args)


if __name__ == "__main__":
    sys.exit(main())
