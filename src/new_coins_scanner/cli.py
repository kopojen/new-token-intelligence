from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .config import ScannerConfig, load_config
from .dashboard import serve_dashboard
from .engine import run_announcement_scan, run_event_scan, run_live_scan, run_sample_scan
from .event_models import AnnouncementItem, EventCandidate
from .models import Candidate


DEFAULT_CONFIG_PATH = Path("data/scanner_config.toml")
DEFAULT_SAMPLE_PATH = Path("data/sample_market_snapshot.json")


def _format_pct(value: float) -> str:
    return f"{value:>7.2f}%"


def _format_usd(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:>6.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:>6.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:>6.2f}K"
    return f"{value:>7.0f}"


def _print_table(candidates: list[Candidate], limit: int) -> None:
    print("symbol   ret24h   ret1h  vol5m  spread  depth1%   24h volume")
    print("------  ------- ------- ------ ------- --------  ----------")
    for candidate in candidates[:limit]:
        snapshot = candidate.snapshot
        depth = min(snapshot.depth_usd_1pct_bid, snapshot.depth_usd_1pct_ask)
        print(
            f"{snapshot.symbol:<6} "
            f"{_format_pct(snapshot.ret_24h):>8} "
            f"{_format_pct(snapshot.ret_1h):>7} "
            f"{snapshot.volume_multiple_5m:>6.2f} "
            f"{_format_pct(snapshot.spread_pct):>7} "
            f"{_format_usd(depth):>8}  "
            f"{_format_usd(snapshot.quote_volume_24h):>10}"
        )


def _print_event_table(candidates: list[EventCandidate], limit: int) -> None:
    print("symbol  score source         listed tags")
    print("------  ----- ------------- ------ --------------------------------")
    for candidate in candidates[:limit]:
        tags = ",".join(candidate.signal.tags[:4]) or "-"
        print(
            f"{candidate.signal.symbol:<6} "
            f"{candidate.score:>5.1f} "
            f"{candidate.signal.source:<13} "
            f"{('yes' if candidate.signal.tradable_on_binance else 'no'):>6} "
            f"{tags}"
        )


def _print_announcement_table(items: list[AnnouncementItem], limit: int) -> None:
    print("source                published             type          symbols        title")
    print("--------------------  --------------------  ------------  ------------  ----------------------------------------")
    for item in items[:limit]:
        symbols = ",".join(item.symbol_candidates[:2]) or "-"
        print(
            f"{item.source:<20} "
            f"{item.published_at[:20]:<20} "
            f"{item.event_type:<12} "
            f"{symbols:<12} "
            f"{item.title[:40]}"
        )


def _resolve_config(path: str | None) -> ScannerConfig:
    chosen = Path(path) if path else DEFAULT_CONFIG_PATH
    if chosen.exists():
        return load_config(chosen)
    return load_config(None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Small-cap crypto market monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample_parser = subparsers.add_parser("sample", help="run using local sample data")
    sample_parser.add_argument("--config", type=str, default=None)
    sample_parser.add_argument("--sample", type=str, default=str(DEFAULT_SAMPLE_PATH))
    sample_parser.add_argument("--limit", type=int, default=10)

    live_parser = subparsers.add_parser("live", help="run using Binance public market data")
    live_parser.add_argument("--config", type=str, default=None)
    live_parser.add_argument("--limit", type=int, default=15)
    live_parser.add_argument("--api-base", type=str, default=None)

    events_parser = subparsers.add_parser("events", help="run event/narrative scan")
    events_parser.add_argument("--limit", type=int, default=15)

    announcements_parser = subparsers.add_parser("announcements", help="show recent exchange announcements")
    announcements_parser.add_argument("--limit", type=int, default=20)

    dashboard_parser = subparsers.add_parser("dashboard", help="serve a local monitoring dashboard")
    dashboard_parser.add_argument("--config", type=str, default=None)
    dashboard_parser.add_argument("--state", type=str, default=None)
    dashboard_parser.add_argument("--host", type=str, default=None)
    dashboard_parser.add_argument("--port", type=int, default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = _resolve_config(getattr(args, "config", None))

    try:
        if args.command == "sample":
            candidates = run_sample_scan(config, args.sample)
            _print_table(candidates, args.limit)
            return 0
        if args.command == "live":
            candidates = run_live_scan(config, api_base=args.api_base)
            _print_table(candidates, args.limit)
            return 0
        if args.command == "events":
            event_candidates = run_event_scan()
            _print_event_table(event_candidates, args.limit)
            return 0
        if args.command == "announcements":
            items = run_announcement_scan()
            _print_announcement_table(items, args.limit)
            return 0
        if args.command == "dashboard":
            state_path = args.state or config.dashboard.state_path
            host = args.host or config.dashboard.host
            port = args.port or config.dashboard.port
            print(f"serving dashboard on http://{host}:{port}")
            print(f"state path: {Path(state_path).resolve()}")
            serve_dashboard(state_path, host, port)
            return 0
    except Exception as exc:  # pragma: no cover - CLI fallback path
        print(f"scanner failed: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
