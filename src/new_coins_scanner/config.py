from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass(slots=True)
class UniverseConfig:
    min_quote_volume_24h: float = 5_000_000.0
    max_quote_volume_24h: float = 250_000_000.0
    max_spread_pct: float = 0.35
    critical_depth_usd_1pct_per_side: float = 3_000.0
    min_depth_usd_1pct_per_side: float = 30_000.0
    min_trade_count_5m: int = 120
    quote_asset_suffixes: tuple[str, ...] = ("USDT",)
    excluded_base_assets: tuple[str, ...] = (
        "BTC",
        "ETH",
        "XRP",
        "BNB",
        "SOL",
        "ADA",
        "AVAX",
        "BCH",
        "DOT",
        "LINK",
        "LTC",
        "NEAR",
        "POL",
        "SHIB",
        "SUI",
        "TON",
        "TRX",
        "DOGE",
        "FIGR_HELOC",
    )


@dataclass(slots=True)
class WeightConfig:
    catalyst_max: float = 20.0
    momentum_max: float = 20.0
    volume_max: float = 20.0
    liquidity_max: float = 15.0
    structure_max: float = 15.0
    social_max: float = 10.0
    supply_penalty_min: float = -10.0
    market_penalty_min: float = -20.0


@dataclass(slots=True)
class ThresholdConfig:
    min_ret_15m: float = 1.0
    min_ret_1h: float = 3.0
    max_distance_from_24h_high_pct: float = 2.5
    min_volume_multiple_5m: float = 2.0
    min_volume_multiple_15m: float = 1.8
    min_trade_count_multiple_5m: float = 1.5
    no_chase_ret_1h_pct: float = 24.0
    min_catalyst_score_watch: float = 8.0
    min_catalyst_score_review: float = 10.0
    min_catalyst_score_ready: float = 10.0
    min_catalyst_score_momentum_ready: float = 10.0
    min_review_score: float = 34.0
    min_momentum_ready_score: float = 42.0
    min_volume_multiple_ready: float = 2.2
    min_volume_multiple_momentum_ready: float = 1.8
    max_spread_pct_ready: float = 0.30
    max_spread_pct_momentum_ready: float = 0.25
    min_depth_usd_ready: float = 60_000.0
    min_depth_usd_momentum_ready: float = 15_000.0
    max_distance_from_30m_high_momentum_pct: float = 1.5
    watchlist_score: float = 52.0
    tradable_score: float = 60.0


@dataclass(slots=True)
class RuntimeConfig:
    shortlist_limit: int = 25
    rolling_window_batch_size: int = 100
    depth_limit: int = 100
    live_top_n_by_quote_volume: int = 50
    live_top_n_by_24h_gainers: int = 20


@dataclass(slots=True)
class DashboardConfig:
    state_path: str = "data/runtime/state.json"
    host: str = "127.0.0.1"
    port: int = 8787


@dataclass(slots=True)
class ScannerConfig:
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    weights: WeightConfig = field(default_factory=WeightConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)


def _merge_section(target: object, values: dict[str, object]) -> None:
    for key, value in values.items():
        if hasattr(target, key):
            setattr(target, key, value)


def load_config(path: str | Path | None = None) -> ScannerConfig:
    config = ScannerConfig()
    if path is None:
        return config
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    for section_name in ("universe", "weights", "thresholds", "runtime", "dashboard"):
        section_values = data.get(section_name)
        if isinstance(section_values, dict):
            _merge_section(getattr(config, section_name), section_values)
    return config
