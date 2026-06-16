from __future__ import annotations

import argparse
import csv
from pathlib import Path

from new_coins_scanner.engine import run_announcement_scan
from new_coins_scanner.event_engine import DEFAULT_LOCAL_EVENT_FEED
from new_coins_scanner.event_providers import LocalEventFeedProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export official exchange announcement rows for demand-evidence analysis."
    )
    parser.add_argument(
        "--out",
        type=str,
        default="data/demand_evidence/announcement_evidence.csv",
        help="CSV output path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum announcements to write.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = run_announcement_scan()[: args.limit]
    fallback_signals = []
    if not rows:
        fallback_signals = LocalEventFeedProvider(DEFAULT_LOCAL_EVENT_FEED).fetch()[: args.limit]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source",
                "published_at",
                "event_type",
                "symbol_candidates",
                "title",
                "url",
            ],
        )
        writer.writeheader()
        for item in rows:
            writer.writerow(
                {
                    "source": item.source,
                    "published_at": item.published_at,
                    "event_type": item.event_type,
                    "symbol_candidates": "|".join(item.symbol_candidates),
                    "title": item.title,
                    "url": item.url,
                }
            )
        for signal in fallback_signals:
            writer.writerow(
                {
                    "source": signal.source,
                    "published_at": "",
                    "event_type": signal.signal_type,
                    "symbol_candidates": signal.symbol,
                    "title": signal.summary,
                    "url": "data/local_event_feed.json",
                }
            )

    total = len(rows) + len(fallback_signals)
    if rows:
        print(f"wrote {total} announcement rows to {out_path}")
    else:
        print(f"wrote {total} fallback local-event rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
