from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .config import ScannerConfig
from .event_models import AnnouncementItem, EventCandidate, EventSignal
from .event_providers import (
    BinanceAlphaProvider,
    KuCoinAnnouncementsProvider,
    LocalEventFeedProvider,
    OKXAnnouncementsProvider,
)
from .models import SymbolSnapshot


DEFAULT_LOCAL_EVENT_FEED = Path("data/local_event_feed.json")


def _announcement_sort_key(value: str) -> tuple[int, float]:
    if not value:
        return (1, 0.0)
    for fmt in ("%b %d, %Y", "%m/%d/%Y, %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            return (0, parsed.timestamp())
        except ValueError:
            continue
    return (1, 0.0)


def load_event_signals(local_feed_path: str | Path | None = None) -> list[EventSignal]:
    signals: list[EventSignal] = []
    for provider in (
        BinanceAlphaProvider(),
        OKXAnnouncementsProvider(),
        KuCoinAnnouncementsProvider(),
    ):
        try:
            signals.extend(provider.fetch())
        except Exception:
            continue
    feed_path = Path(local_feed_path) if local_feed_path else DEFAULT_LOCAL_EVENT_FEED
    signals.extend(LocalEventFeedProvider(feed_path).fetch())
    return signals


def load_official_announcements() -> list[AnnouncementItem]:
    items: list[AnnouncementItem] = []
    for provider in (OKXAnnouncementsProvider(), KuCoinAnnouncementsProvider()):
        try:
            items.extend(provider.fetch_announcements())
        except Exception:
            continue
    items.sort(key=lambda item: _announcement_sort_key(item.published_at), reverse=True)
    return items


def rank_event_signals(signals: list[EventSignal]) -> list[EventCandidate]:
    merged: dict[str, EventSignal] = {}
    for signal in signals:
        existing = merged.get(signal.symbol)
        if existing is None:
            merged[signal.symbol] = EventSignal(
                symbol=signal.symbol,
                source=signal.source,
                signal_type=signal.signal_type,
                event_score=signal.event_score,
                narrative_score=signal.narrative_score,
                liquidity_score=signal.liquidity_score,
                volume_score=signal.volume_score,
                tradable_on_binance=signal.tradable_on_binance,
                tags=list(signal.tags),
                summary=signal.summary,
                raw={"signals": [signal.raw]},
            )
            continue

        existing.event_score = max(existing.event_score, signal.event_score)
        existing.narrative_score = max(existing.narrative_score, signal.narrative_score)
        existing.liquidity_score = max(existing.liquidity_score, signal.liquidity_score)
        existing.volume_score = max(existing.volume_score, signal.volume_score)
        existing.tradable_on_binance = existing.tradable_on_binance or signal.tradable_on_binance
        existing.tags.extend(tag for tag in signal.tags if tag not in existing.tags)
        existing.source = ",".join(sorted(set(existing.source.split(",") + [signal.source])))
        if signal.summary and signal.summary not in existing.summary:
            existing.summary = " | ".join(part for part in [existing.summary, signal.summary] if part)
        existing.raw.setdefault("signals", []).append(signal.raw)

    ranked = [EventCandidate(signal=signal) for signal in merged.values()]
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked


def merge_event_signals_into_snapshots(
    snapshots: list[SymbolSnapshot],
    signals: list[EventSignal],
    config: ScannerConfig,
) -> list[SymbolSnapshot]:
    by_symbol: dict[str, list[EventSignal]] = defaultdict(list)
    for signal in signals:
        by_symbol[signal.symbol].append(signal)

    for snapshot in snapshots:
        matched: list[EventSignal] = []
        for suffix in config.universe.quote_asset_suffixes:
            if snapshot.symbol.endswith(suffix):
                base_asset = snapshot.symbol[: -len(suffix)]
                matched.extend(by_symbol.get(base_asset, []))
                break
        matched.extend(by_symbol.get(snapshot.symbol, []))
        if not matched:
            continue

        best_event = max(matched, key=lambda signal: signal.event_score)
        best_narrative = max(matched, key=lambda signal: signal.narrative_score)
        snapshot.catalyst_score_override = max(snapshot.catalyst_score_override or 0.0, best_event.event_score)
        snapshot.social_score_override = max(snapshot.social_score_override or 0.0, best_narrative.narrative_score)
        snapshot.tags.extend(tag for signal in matched for tag in signal.tags if tag not in snapshot.tags)
        snapshot.notes.extend(
            f"{signal.source}:{signal.signal_type}:{signal.summary}" for signal in matched if signal.summary
        )

        alpha_like = next((signal for signal in matched if signal.source == "binance-alpha"), None)
        if alpha_like:
            raw = alpha_like.raw
            total_supply = float(raw.get("totalSupply") or 0.0)
            circulating_supply = float(raw.get("circulatingSupply") or 0.0)
            market_cap = float(raw.get("marketCap") or 0.0)
            fdv = float(raw.get("fdv") or 0.0)
            if total_supply > 0:
                snapshot.circulating_ratio = circulating_supply / total_supply
            if market_cap > 0:
                snapshot.fdv_to_market_cap = fdv / market_cap if fdv > 0 else None
    return snapshots
