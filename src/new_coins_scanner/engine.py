from __future__ import annotations

import json
from pathlib import Path

from .binance import BinanceSpotPublicClient, STABLE_ASSETS, _ticker_ret_24h, build_live_snapshots
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


def run_fast_live_scan(config: ScannerConfig, api_base: str | None = None) -> list[Candidate]:
    client = BinanceSpotPublicClient(api_base=api_base or "https://api.binance.com")
    all_tickers = client.ticker_24hr()
    universe: list[tuple[dict, float, float]] = []
    for item in all_tickers:
        symbol = str(item.get("symbol", ""))
        suffix = next((value for value in config.universe.quote_asset_suffixes if symbol.endswith(value)), "")
        if not suffix or not symbol.isascii():
            continue
        base_asset = symbol[: -len(suffix)]
        if base_asset in config.universe.excluded_base_assets or base_asset in STABLE_ASSETS:
            continue
        try:
            quote_volume = float(item.get("quoteVolume", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if quote_volume < config.universe.min_quote_volume_24h:
            continue
        if config.universe.max_quote_volume_24h > 0 and quote_volume > config.universe.max_quote_volume_24h:
            continue
        universe.append((item, quote_volume, _ticker_ret_24h(item)))

    by_quote_volume = sorted(universe, key=lambda item: item[1], reverse=True)
    by_24h_return = sorted(universe, key=lambda item: item[2], reverse=True)
    selected_symbols = list(
        dict.fromkeys(
            [item[0]["symbol"] for item in by_quote_volume[: config.runtime.live_top_n_by_quote_volume]]
            + [item[0]["symbol"] for item in by_24h_return[: config.runtime.live_top_n_by_24h_gainers]]
        )
    )
    if not selected_symbols:
        return []

    selected_tickers = {str(item["symbol"]): item for item, _, _ in universe if item["symbol"] in selected_symbols}
    book_rows = {item["symbol"]: item for item in client.book_ticker(selected_symbols)}
    snapshots: list[SymbolSnapshot] = []
    for symbol in selected_symbols:
        item = selected_tickers.get(symbol)
        book = book_rows.get(symbol, {})
        if item is None:
            continue
        last_price = float(item.get("lastPrice", 0.0) or 0.0)
        bid_price = float(book.get("bidPrice", 0.0) or 0.0)
        ask_price = float(book.get("askPrice", 0.0) or 0.0)
        bid_qty = float(book.get("bidQty", 0.0) or 0.0)
        ask_qty = float(book.get("askQty", 0.0) or 0.0)
        midpoint = (bid_price + ask_price) / 2.0 if bid_price and ask_price else last_price
        spread_pct = 0.0 if midpoint <= 0 else ((ask_price - bid_price) / midpoint) * 100.0
        top_book_depth = min(bid_price * bid_qty, ask_price * ask_qty) if bid_price and ask_price else 0.0
        quote_volume_24h = float(item.get("quoteVolume", 0.0) or 0.0)
        snapshots.append(
            SymbolSnapshot(
                symbol=symbol,
                status="TRADING",
                last_price=last_price,
                bid_price=bid_price,
                ask_price=ask_price,
                quote_volume_24h=quote_volume_24h,
                ret_24h=_ticker_ret_24h(item),
                trade_count_24h=int(item.get("count", 0) or 0),
                spread_pct=spread_pct,
                depth_usd_1pct_bid=top_book_depth,
                depth_usd_1pct_ask=top_book_depth,
                distance_from_24h_high_pct=0.0
                if float(item.get("highPrice", 0.0) or 0.0) <= 0
                else ((float(item["highPrice"]) - last_price) / float(item["highPrice"])) * 100.0,
                tags=["fast-live", "small-cap-proxy"],
                raw={"ticker_24h": item, "book_ticker": book},
            )
        )

    signals = load_event_signals()
    snapshots = merge_event_signals_into_snapshots(snapshots, signals, config)
    return rank_snapshots(snapshots, config)


def run_event_scan(local_feed_path: str | Path | None = None) -> list[EventCandidate]:
    return rank_event_signals(load_event_signals(local_feed_path))


def run_announcement_scan() -> list[AnnouncementItem]:
    return load_official_announcements()
