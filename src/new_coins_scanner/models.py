from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SymbolSnapshot:
    symbol: str
    name: str = ""
    source: str = "spot"
    status: str = "TRADING"
    last_price: float = 0.0
    bid_price: float = 0.0
    ask_price: float = 0.0
    quote_volume_24h: float = 0.0
    ret_24h: float = 0.0
    trade_count_24h: int = 0
    ret_5m: float = 0.0
    ret_15m: float = 0.0
    ret_1h: float = 0.0
    quote_volume_5m: float = 0.0
    quote_volume_15m: float = 0.0
    quote_volume_1h: float = 0.0
    volume_multiple_5m: float = 0.0
    volume_multiple_15m: float = 0.0
    trade_count_5m: int = 0
    trade_count_15m: int = 0
    trade_count_1h: int = 0
    trade_count_multiple_5m: float = 0.0
    spread_pct: float = 0.0
    depth_usd_1pct_bid: float = 0.0
    depth_usd_1pct_ask: float = 0.0
    depth_usd_2pct_bid: float = 0.0
    depth_usd_2pct_ask: float = 0.0
    distance_from_24h_high_pct: float = 100.0
    distance_from_30m_high_pct: float = 100.0
    breakout_active: bool = False
    held_breakout_retest: bool = False
    higher_low_confirmed: bool = False
    vwap_reclaim: bool = False
    extended_move_flag: bool = False
    catalyst_score_override: float | None = None
    social_score_override: float | None = None
    circulating_ratio: float | None = None
    fdv_to_market_cap: float | None = None
    unlock_within_30d: bool = False
    market_flags: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScoreBreakdown:
    catalyst: float = 0.0
    momentum: float = 0.0
    volume: float = 0.0
    liquidity: float = 0.0
    structure: float = 0.0
    social: float = 0.0
    supply_penalty: float = 0.0
    market_penalty: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.catalyst
            + self.momentum
            + self.volume
            + self.liquidity
            + self.structure
            + self.social
            + self.supply_penalty
            + self.market_penalty
        )


@dataclass(slots=True)
class Candidate:
    snapshot: SymbolSnapshot
    breakdown: ScoreBreakdown
    tier: str
    raw_state: str
    state: str
    eligible: bool
    blocked_reasons: list[str] = field(default_factory=list)
    raw_state_reasons: list[str] = field(default_factory=list)
    state_reasons: list[str] = field(default_factory=list)
    review_confidence: float = 0.0
    review_summary: str = ""
    review_source: str = ""

    @property
    def score(self) -> float:
        return self.breakdown.total
