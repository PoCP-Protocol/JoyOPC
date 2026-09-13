from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class RawMarketSignal:
    source: str
    market: str
    channel: str
    keyword: str
    demand_score: float
    growth_score: float
    social_velocity: float
    competition_score: float
    median_price: float
    confidence: float


class MarketSignalAdapter(Protocol):
    """Boundary for future real Amazon/TikTok/Google/market-data connectors."""

    def collect(self, *, market: str, keyword: str) -> list[RawMarketSignal]: ...
