from __future__ import annotations

from dataclasses import dataclass

from .models import MarketSignal, ProductCandidate
from .schemas import SelectionInput, SelectionPolicy
from .selection_engine import ProductZoneEngine


@dataclass(slots=True)
class CandidateIntelligenceEngine:
    """Turns market/supplier facts into JoyOPC's three-zone decision model.

    V0.2 deliberately keeps external market collection behind adapters. This engine
    is deterministic and auditable: it can run on manually entered signals today
    and on Amazon/TikTok/Google/Shopify connectors later without changing the rule core.
    """

    policy: SelectionPolicy

    @staticmethod
    def expected_margin_pct(retail: float, landed: float) -> float:
        if retail <= 0:
            return 0.0
        return round((retail - landed) / retail * 100.0, 1)

    @staticmethod
    def blended_market_demand(signals: list[MarketSignal], fallback: float) -> float:
        if not signals:
            return fallback
        weights = [max(s.confidence, 10) for s in signals]
        total = sum(weights)
        score = sum(
            (s.demand_score * 0.45 + s.growth_score * 0.30 + s.social_velocity * 0.25) * w
            for s, w in zip(signals, weights)
        ) / total
        return round(max(0, min(100, score)), 1)

    @staticmethod
    def blended_competition(signals: list[MarketSignal], fallback: float) -> float:
        if not signals:
            return fallback
        weights = [max(s.confidence, 10) for s in signals]
        total = sum(weights)
        return round(sum(s.competition_score * w for s, w in zip(signals, weights)) / total, 1)

    def evaluate(self, candidate: ProductCandidate, signals: list[MarketSignal]) -> dict:
        margin = self.expected_margin_pct(candidate.target_retail_price, candidate.estimated_landed_cost)
        market_demand = self.blended_market_demand(signals, candidate.market_demand)
        competition = self.blended_competition(signals, candidate.competition_intensity)
        payload = SelectionInput(
            product_name=candidate.product_name,
            exclusive_rights=candidate.exclusive_rights,
            uniqueness=candidate.uniqueness,
            channel_control=candidate.channel_control,
            cost_advantage=candidate.cost_advantage,
            supply_advantage=candidate.supply_advantage,
            content_advantage=candidate.content_advantage,
            brand_advantage=candidate.brand_advantage,
            market_demand=market_demand,
            competition_intensity=competition,
            expected_margin_pct=margin,
            compliance_risk=candidate.compliance_risk,
            return_risk=candidate.return_risk,
            cash_cycle_days=candidate.cash_cycle_days,
        )
        result = ProductZoneEngine(self.policy).evaluate(payload)
        return {
            "selection": result,
            "expected_margin_pct": margin,
            "market_demand": market_demand,
            "competition_intensity": competition,
            "signal_count": len(signals),
        }
