from __future__ import annotations

from .config import ScannerConfig
from .models import Candidate, ScoreBreakdown, SymbolSnapshot

HARD_NO_TRADE_REASONS = {
    "status=TRADING_DISABLED",
    "low_quote_volume_24h",
    "large_cap_proxy_quote_volume",
    "spread_too_wide",
    "critically_thin_order_book",
}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _passes_universe(snapshot: SymbolSnapshot, config: ScannerConfig) -> list[str]:
    reasons: list[str] = []
    if snapshot.status != "TRADING":
        reasons.append(f"status={snapshot.status}")
    if snapshot.quote_volume_24h < config.universe.min_quote_volume_24h:
        reasons.append("low_quote_volume_24h")
    if (
        config.universe.max_quote_volume_24h > 0
        and snapshot.quote_volume_24h > config.universe.max_quote_volume_24h
        and "event-backed" not in snapshot.tags
        and "recent-listing" not in snapshot.tags
        and "binance-alpha" not in snapshot.tags
    ):
        reasons.append("large_cap_proxy_quote_volume")
    if snapshot.spread_pct > config.universe.max_spread_pct:
        reasons.append("spread_too_wide")
    min_depth = min(snapshot.depth_usd_1pct_bid, snapshot.depth_usd_1pct_ask)
    if min_depth < config.universe.critical_depth_usd_1pct_per_side:
        reasons.append("critically_thin_order_book")
    elif min_depth < config.universe.min_depth_usd_1pct_per_side:
        reasons.append("thin_order_book")
    if snapshot.trade_count_5m < config.universe.min_trade_count_5m:
        reasons.append("not_enough_recent_trades")
    return reasons


def _has_hard_block(blocked_reasons: list[str]) -> bool:
    return any(reason in HARD_NO_TRADE_REASONS or reason.startswith("status=") for reason in blocked_reasons)


def _score_catalyst(snapshot: SymbolSnapshot, config: ScannerConfig) -> float:
    if snapshot.catalyst_score_override is None:
        return 0.0
    return _clamp(snapshot.catalyst_score_override, 0.0, config.weights.catalyst_max)


def _score_social(snapshot: SymbolSnapshot, config: ScannerConfig) -> float:
    if snapshot.social_score_override is None:
        return 0.0
    return _clamp(snapshot.social_score_override, 0.0, config.weights.social_max)


def _score_momentum(snapshot: SymbolSnapshot, config: ScannerConfig) -> float:
    score = 0.0
    if snapshot.ret_15m > config.thresholds.min_ret_15m:
        score += min(8.0, (snapshot.ret_15m - config.thresholds.min_ret_15m) * 1.5)
    if snapshot.ret_1h > config.thresholds.min_ret_1h:
        score += min(8.0, (snapshot.ret_1h - config.thresholds.min_ret_1h) * 0.8)
    if snapshot.distance_from_24h_high_pct <= config.thresholds.max_distance_from_24h_high_pct:
        score += 4.0
    if snapshot.ret_5m > 0:
        score += min(2.0, snapshot.ret_5m * 0.5)
    if snapshot.ret_1h > config.thresholds.no_chase_ret_1h_pct:
        score -= min(6.0, (snapshot.ret_1h - config.thresholds.no_chase_ret_1h_pct) * 0.4)
    return _clamp(score, 0.0, config.weights.momentum_max)


def _score_volume(snapshot: SymbolSnapshot, config: ScannerConfig) -> float:
    score = 0.0
    if snapshot.volume_multiple_5m >= config.thresholds.min_volume_multiple_5m:
        score += min(8.0, (snapshot.volume_multiple_5m - config.thresholds.min_volume_multiple_5m + 1.0) * 2.0)
    if snapshot.volume_multiple_15m >= config.thresholds.min_volume_multiple_15m:
        score += min(6.0, (snapshot.volume_multiple_15m - config.thresholds.min_volume_multiple_15m + 1.0) * 1.5)
    if snapshot.trade_count_multiple_5m >= config.thresholds.min_trade_count_multiple_5m:
        score += min(4.0, (snapshot.trade_count_multiple_5m - config.thresholds.min_trade_count_multiple_5m + 1.0) * 1.5)
    if snapshot.quote_volume_1h > 0 and snapshot.quote_volume_24h > 0:
        hourly_share = snapshot.quote_volume_1h / snapshot.quote_volume_24h
        score += min(2.0, hourly_share * 24.0)
    return _clamp(score, 0.0, config.weights.volume_max)


def _score_liquidity(snapshot: SymbolSnapshot, config: ScannerConfig) -> float:
    score = 0.0
    if snapshot.spread_pct <= 0.10:
        score += 7.0
    elif snapshot.spread_pct <= 0.25:
        score += 4.0
    elif snapshot.spread_pct <= config.universe.max_spread_pct:
        score += 1.0

    min_depth = min(snapshot.depth_usd_1pct_bid, snapshot.depth_usd_1pct_ask)
    if min_depth >= 500_000:
        score += 8.0
    elif min_depth >= 200_000:
        score += 6.0
    elif min_depth >= config.universe.min_depth_usd_1pct_per_side:
        score += 3.0
    return _clamp(score, 0.0, config.weights.liquidity_max)


def _score_structure(snapshot: SymbolSnapshot, config: ScannerConfig) -> float:
    score = 0.0
    if snapshot.breakout_active:
        score += 6.0
    if snapshot.held_breakout_retest:
        score += 4.0
    if snapshot.higher_low_confirmed:
        score += 3.0
    if snapshot.vwap_reclaim:
        score += 2.0
    if snapshot.extended_move_flag:
        score -= 5.0
    if snapshot.distance_from_30m_high_pct <= 0.5:
        score += 2.0
    return _clamp(score, 0.0, config.weights.structure_max)


def _score_supply_penalty(snapshot: SymbolSnapshot, config: ScannerConfig) -> float:
    penalty = 0.0
    if snapshot.circulating_ratio is not None and snapshot.circulating_ratio < 0.20:
        penalty -= 5.0
    if snapshot.fdv_to_market_cap is not None and snapshot.fdv_to_market_cap > 4.0:
        penalty -= 3.0
    if snapshot.unlock_within_30d:
        penalty -= 5.0
    return _clamp(penalty, config.weights.supply_penalty_min, 0.0)


def _score_market_penalty(snapshot: SymbolSnapshot, config: ScannerConfig) -> float:
    penalty = 0.0
    if snapshot.extended_move_flag:
        penalty -= 6.0
    penalty -= min(10.0, float(len(snapshot.market_flags)) * 2.0)
    return _clamp(penalty, config.weights.market_penalty_min, 0.0)


def classify_tier(score: float, config: ScannerConfig) -> str:
    if score >= 75.0:
        return "A"
    if score >= 60.0:
        return "B"
    if score >= 50.0:
        return "C"
    return "D"


def _state_reasons(snapshot: SymbolSnapshot, breakdown: ScoreBreakdown, blocked_reasons: list[str], config: ScannerConfig) -> tuple[str, list[str]]:
    reasons: list[str] = []
    min_depth = min(snapshot.depth_usd_1pct_bid, snapshot.depth_usd_1pct_ask)
    event_ready = breakdown.catalyst >= config.thresholds.min_catalyst_score_ready
    event_review = breakdown.catalyst >= config.thresholds.min_catalyst_score_review
    event_watch = breakdown.catalyst >= config.thresholds.min_catalyst_score_watch
    event_momentum = breakdown.catalyst >= config.thresholds.min_catalyst_score_momentum_ready
    structure_ready = snapshot.breakout_active or snapshot.held_breakout_retest or snapshot.higher_low_confirmed
    momentum_ready = snapshot.volume_multiple_5m >= config.thresholds.min_volume_multiple_ready
    liquidity_ready = (
        snapshot.spread_pct <= config.thresholds.max_spread_pct_ready
        and min_depth >= config.thresholds.min_depth_usd_ready
    )
    momentum_continuation = (
        snapshot.ret_15m >= config.thresholds.min_ret_15m
        and snapshot.ret_1h >= config.thresholds.min_ret_1h
        and snapshot.volume_multiple_5m >= config.thresholds.min_volume_multiple_momentum_ready
        and snapshot.spread_pct <= config.thresholds.max_spread_pct_momentum_ready
        and min_depth >= config.thresholds.min_depth_usd_momentum_ready
        and snapshot.distance_from_30m_high_pct <= config.thresholds.max_distance_from_30m_high_momentum_pct
        and snapshot.trade_count_5m >= config.universe.min_trade_count_5m
        and not snapshot.extended_move_flag
    )
    ready_fast_path = (
        breakdown.total >= max(config.thresholds.tradable_score - 6.0, config.thresholds.min_review_score)
        and event_ready
        and momentum_ready
        and liquidity_ready
        and structure_ready
        and breakdown.volume >= 9.0
        and breakdown.liquidity >= 4.0
    )
    momentum_fast_path = (
        event_momentum
        and momentum_continuation
        and breakdown.total >= config.thresholds.min_review_score
        and breakdown.volume >= 8.0
        and breakdown.liquidity >= 4.0
    )

    if _has_hard_block(blocked_reasons):
        reasons.append("hard_market_block")
        return "no-trade", reasons

    if (
        (breakdown.total >= config.thresholds.tradable_score or ready_fast_path)
        and event_ready
        and momentum_ready
        and liquidity_ready
        and structure_ready
        and not blocked_reasons
    ):
        reasons.extend(["event_confirmed", "market_confirmed", "structure_ready"])
        return "ready", reasons

    if (
        (breakdown.total >= config.thresholds.min_momentum_ready_score or momentum_fast_path)
        and event_momentum
        and momentum_continuation
        and "not_enough_recent_trades" not in blocked_reasons
    ):
        reasons.extend(["momentum_continuation", "event_backing"])
        if "thin_order_book" in blocked_reasons:
            reasons.append("thin_but_allowed_for_momentum")
        if "too_extended_without_reset" in blocked_reasons:
            reasons.append("extension_allowed_for_momentum")
        if not structure_ready:
            reasons.append("continuation_without_reset")
        return "momentum-ready", reasons

    if "too_extended_without_reset" in blocked_reasons:
        reasons.append("too_extended")
        return "no-trade", reasons

    if event_review and breakdown.total >= config.thresholds.min_review_score:
        reasons.append("event_strong_enough_for_review")
        if "thin_order_book" in blocked_reasons:
            reasons.append("thin_but_reviewable")
        if "not_enough_recent_trades" in blocked_reasons:
            reasons.append("recent_trades_light")
        if not structure_ready:
            reasons.append("waiting_for_structure")
        if not momentum_ready:
            reasons.append("waiting_for_volume")
        return "review", reasons

    if event_watch:
        reasons.append("event_present")
    elif breakdown.social > 0:
        reasons.append("narrative_present")

    if breakdown.total >= config.thresholds.watchlist_score:
        reasons.append("score_above_watchlist")
    if not structure_ready:
        reasons.append("waiting_for_structure")
    if not momentum_ready:
        reasons.append("waiting_for_volume")
    if not liquidity_ready:
        reasons.append("liquidity_not_ready")

    if event_watch or (breakdown.total >= config.thresholds.watchlist_score and not _has_hard_block(blocked_reasons)):
        return "watch", reasons

    reasons.append("no_event_edge")
    return "no-trade", reasons


def score_symbol(snapshot: SymbolSnapshot, config: ScannerConfig) -> Candidate:
    blocked_reasons = _passes_universe(snapshot, config)
    breakdown = ScoreBreakdown(
        catalyst=_score_catalyst(snapshot, config),
        momentum=_score_momentum(snapshot, config),
        volume=_score_volume(snapshot, config),
        liquidity=_score_liquidity(snapshot, config),
        structure=_score_structure(snapshot, config),
        social=_score_social(snapshot, config),
        supply_penalty=_score_supply_penalty(snapshot, config),
        market_penalty=_score_market_penalty(snapshot, config),
    )

    if snapshot.ret_1h > config.thresholds.no_chase_ret_1h_pct and not snapshot.held_breakout_retest:
        blocked_reasons.append("too_extended_without_reset")

    state, state_reasons = _state_reasons(snapshot, breakdown, blocked_reasons, config)
    eligible = state in {"ready", "momentum-ready"}
    return Candidate(
        snapshot=snapshot,
        breakdown=breakdown,
        tier=classify_tier(breakdown.total, config),
        raw_state=state,
        state=state,
        eligible=eligible,
        blocked_reasons=blocked_reasons,
        raw_state_reasons=list(state_reasons),
        state_reasons=state_reasons,
    )
