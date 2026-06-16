from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EventSignal:
    symbol: str
    source: str
    signal_type: str
    event_score: float
    narrative_score: float = 0.0
    liquidity_score: float = 0.0
    volume_score: float = 0.0
    tradable_on_binance: bool = False
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EventCandidate:
    signal: EventSignal

    @property
    def score(self) -> float:
        return self.signal.event_score + self.signal.narrative_score + self.signal.liquidity_score + self.signal.volume_score


@dataclass(slots=True)
class AnnouncementItem:
    source: str
    title: str
    url: str
    published_at: str = ""
    event_type: str = "other"
    symbol_candidates: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
