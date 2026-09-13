from app.discovery_engine import CandidateIntelligenceEngine
from app.models import MarketSignal, ProductCandidate
from app.schemas import SelectionPolicy


def test_market_signal_can_upgrade_demand_but_not_bypass_zone_rules():
    candidate = ProductCandidate(
        candidate_code="T-1",
        product_name="Commodity Voice Robot",
        target_retail_price=40,
        estimated_landed_cost=24,
        exclusive_rights=False,
        uniqueness=25,
        channel_control=20,
        cost_advantage=45,
        supply_advantage=50,
        content_advantage=40,
        brand_advantage=20,
        market_demand=50,
        competition_intensity=85,
        compliance_risk=25,
        return_risk=40,
        cash_cycle_days=35,
    )
    signals = [
        MarketSignal(
            source="demo",
            market="US",
            channel="Amazon",
            keyword="voice robot toy",
            demand_score=95,
            growth_score=90,
            social_velocity=80,
            competition_score=95,
            confidence=90,
        )
    ]
    result = CandidateIntelligenceEngine(SelectionPolicy()).evaluate(candidate, signals)
    assert result["market_demand"] > 80
    assert result["selection"].zone == "HOMOGENEOUS"
    assert result["selection"].decision != "SCALE"


def test_exclusive_candidate_can_be_scale_candidate():
    candidate = ProductCandidate(
        candidate_code="T-2",
        product_name="Exclusive Companion Pet",
        target_retail_price=69,
        estimated_landed_cost=24,
        exclusive_rights=True,
        uniqueness=90,
        channel_control=85,
        cost_advantage=78,
        supply_advantage=80,
        content_advantage=92,
        brand_advantage=60,
        market_demand=85,
        competition_intensity=55,
        compliance_risk=25,
        return_risk=25,
        cash_cycle_days=20,
    )
    result = CandidateIntelligenceEngine(SelectionPolicy()).evaluate(candidate, [])
    assert result["selection"].zone == "EXCLUSIVE"
    assert result["selection"].decision == "SCALE"
