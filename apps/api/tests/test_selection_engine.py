from app.schemas import SelectionInput, SelectionPolicy
from app.selection_engine import ProductZoneEngine


def test_exclusive_zone():
    result = ProductZoneEngine(SelectionPolicy()).evaluate(
        SelectionInput(
            product_name="Exclusive AI Toy",
            exclusive_rights=True,
            uniqueness=90,
            channel_control=90,
            market_demand=85,
            competition_intensity=45,
            cost_advantage=75,
            supply_advantage=80,
            content_advantage=85,
            expected_margin_pct=48,
            compliance_risk=25,
            return_risk=20,
            cash_cycle_days=20,
        )
    )
    assert result.zone == "EXCLUSIVE"
    assert result.decision in {"SCALE", "TEST"}


def test_homogeneous_is_strict():
    result = ProductZoneEngine(SelectionPolicy()).evaluate(
        SelectionInput(
            product_name="Commodity Robot",
            exclusive_rights=False,
            uniqueness=20,
            channel_control=20,
            cost_advantage=45,
            supply_advantage=55,
            content_advantage=35,
            brand_advantage=20,
            market_demand=70,
            competition_intensity=90,
            expected_margin_pct=22,
            compliance_risk=30,
            return_risk=45,
            cash_cycle_days=40,
        )
    )
    assert result.zone == "HOMOGENEOUS"
    assert result.decision != "SCALE"
