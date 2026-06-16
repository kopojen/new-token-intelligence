from __future__ import annotations

from .models import Candidate


def _depth_1pct_usd(candidate: Candidate) -> float:
    return min(candidate.snapshot.depth_usd_1pct_bid, candidate.snapshot.depth_usd_1pct_ask)


def build_signal_rows(candidates: list[Candidate], limit: int = 20) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for candidate in candidates[:limit]:
        rows.append(
            {
                "symbol": candidate.snapshot.symbol,
                "last_price": candidate.snapshot.last_price,
                "quote_volume_24h": candidate.snapshot.quote_volume_24h,
                "score": round(candidate.score, 2),
                "state": candidate.state,
                "raw_state": candidate.raw_state,
                "tier": candidate.tier,
                "eligible": candidate.eligible,
                "ret_24h": candidate.snapshot.ret_24h,
                "ret_15m": candidate.snapshot.ret_15m,
                "ret_1h": candidate.snapshot.ret_1h,
                "volume_multiple_5m": candidate.snapshot.volume_multiple_5m,
                "spread_pct": candidate.snapshot.spread_pct,
                "depth_1pct_usd": _depth_1pct_usd(candidate),
                "blocked_reasons": candidate.blocked_reasons[:3],
                "raw_state_reasons": candidate.raw_state_reasons[:4],
                "state_reasons": candidate.state_reasons[:4],
                "catalyst": round(candidate.breakdown.catalyst, 2),
                "momentum": round(candidate.breakdown.momentum, 2),
                "volume_score": round(candidate.breakdown.volume, 2),
                "liquidity_score": round(candidate.breakdown.liquidity, 2),
                "structure_score": round(candidate.breakdown.structure, 2),
                "social_score": round(candidate.breakdown.social, 2),
                "pending_state": "",
                "pending_count": 0,
                "tags": candidate.snapshot.tags[:8],
            }
        )
    return rows


def build_top_gainer_rows(candidates: list[Candidate], limit: int = 12) -> list[dict[str, object]]:
    top_gainers = sorted(
        candidates,
        key=lambda item: (item.snapshot.ret_24h, item.snapshot.volume_multiple_5m, item.score),
        reverse=True,
    )
    rows: list[dict[str, object]] = []
    for rank, candidate in enumerate(top_gainers[:limit], start=1):
        rows.append(
            {
                "rank": rank,
                "symbol": candidate.snapshot.symbol,
                "last_price": candidate.snapshot.last_price,
                "quote_volume_24h": candidate.snapshot.quote_volume_24h,
                "state": candidate.state,
                "score": round(candidate.score, 2),
                "ret_24h": candidate.snapshot.ret_24h,
                "ret_15m": candidate.snapshot.ret_15m,
                "ret_1h": candidate.snapshot.ret_1h,
                "volume_multiple_5m": candidate.snapshot.volume_multiple_5m,
                "depth_1pct_usd": _depth_1pct_usd(candidate),
                "blocked_reasons": candidate.blocked_reasons[:3],
                "state_reasons": candidate.state_reasons[:3],
                "tags": candidate.snapshot.tags[:8],
            }
        )
    return rows


def selection_counts(candidates: list[Candidate]) -> dict[str, int]:
    return {
        "tracked_universe_count": len(candidates),
        "top_volume_universe_count": sum(1 for candidate in candidates if "top-volume" in candidate.snapshot.tags),
        "top_gainer_universe_count": sum(1 for candidate in candidates if "top-gainer" in candidate.snapshot.tags),
    }
