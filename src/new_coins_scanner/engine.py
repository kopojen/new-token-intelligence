from __future__ import annotations

import json
from pathlib import Path

from .binance import BinanceSpotPublicClient, build_live_snapshots
from .config import ScannerConfig
from .event_engine import (
    load_event_signals,
    load_official_announcements,
    merge_event_signals_into_snapshots,
    rank_event_signals,
)
from .event_models import AnnouncementItem, EventCandidate
from .models import Candidate, SymbolSnapshot
from .scoring import score_symbol


def load_sample_snapshots(path: str | Path) -> list[SymbolSnapshot]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    snapshots: list[SymbolSnapshot] = []
    for item in payload["symbols"]:
        snapshots.append(SymbolSnapshot(**item))
    return snapshots


def rank_snapshots(snapshots: list[SymbolSnapshot], config: ScannerConfig) -> list[Candidate]:
    candidates = [score_symbol(snapshot, config) for snapshot in snapshots]
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


def run_sample_scan(config: ScannerConfig, sample_path: str | Path) -> list[Candidate]:
    return rank_snapshots(load_sample_snapshots(sample_path), config)


def run_live_scan(config: ScannerConfig, api_base: str | None = None) -> list[Candidate]:
    client = BinanceSpotPublicClient(api_base=api_base or "https://api.binance.com")
    snapshots = build_live_snapshots(client, config)
    signals = load_event_signals()
    snapshots = merge_event_signals_into_snapshots(snapshots, signals, config)
    return rank_snapshots(snapshots, config)


def run_event_scan(local_feed_path: str | Path | None = None) -> list[EventCandidate]:
    return rank_event_signals(load_event_signals(local_feed_path))


def run_announcement_scan() -> list[AnnouncementItem]:
    return load_official_announcements()
