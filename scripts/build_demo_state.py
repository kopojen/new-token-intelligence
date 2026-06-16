from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from new_coins_scanner.config import load_config
from new_coins_scanner.engine import run_sample_scan
from new_coins_scanner.event_engine import DEFAULT_LOCAL_EVENT_FEED
from new_coins_scanner.event_providers import LocalEventFeedProvider
from new_coins_scanner.runtime_state import write_runtime_state
from new_coins_scanner.state_views import build_signal_rows, build_top_gainer_rows, selection_counts


def main() -> int:
    config = load_config("data/scanner_config.toml")
    candidates = run_sample_scan(config, "data/sample_market_snapshot.json")
    counts = selection_counts(candidates)
    now = datetime.now(timezone.utc).isoformat()
    local_events = LocalEventFeedProvider(DEFAULT_LOCAL_EVENT_FEED).fetch()

    state = {
        "updated_at": now,
        "cycle": {
            "started_at": now,
            "finished_at": now,
            "candidate_count": len(candidates),
            "tracked_universe_count": counts["tracked_universe_count"],
            "top_volume_universe_count": counts["top_volume_universe_count"],
            "top_gainer_universe_count": counts["top_gainer_universe_count"],
        },
        "signals": build_signal_rows(candidates),
        "top_gainers": build_top_gainer_rows(candidates),
        "announcements": [
            {
                "source": signal.source,
                "event_type": signal.signal_type,
                "symbol_candidates": [signal.symbol],
                "title": signal.summary,
            }
            for signal in local_events
        ],
        "errors": [],
    }

    output_path = write_runtime_state(state, Path(config.dashboard.state_path))
    print(f"wrote demo dashboard state to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
