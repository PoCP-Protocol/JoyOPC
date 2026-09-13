from app.schemas import SelectionInput, SelectionPolicy
from app.selection_engine import ProductZoneEngine
from app.product_unit import companion_passport


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
            **companion_passport(soul_recipe_id="js-exclusive-toy-v1", shell="plush").to_selection_fields(),
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


def test_exclusive_without_soul_is_homogeneous():
    result = ProductZoneEngine(SelectionPolicy()).evaluate(
        SelectionInput(
            product_name="Talking Shell No Memory",
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
    assert result.zone == "HOMOGENEOUS"
    assert result.has_companion_soul is False


def test_gen1_camera_cannot_be_exclusive():
    result = ProductZoneEngine(SelectionPolicy()).evaluate(
        SelectionInput(
            product_name="Gen1 Camera Buddy",
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
            **companion_passport(
                soul_recipe_id="js-vision-too-early-v1",
                shell="plush",
                claimed_features=["mic", "speaker", "network", "camera"],
            ).to_selection_fields(),
        )
    )
    assert result.zone == "ADVANTAGE"
    assert result.needs_hardware_gate is True


def test_cert_gap_blocks_scale():
    unit = companion_passport(soul_recipe_id="js-uncertified-v1", shell="plush", certs_held=[])
    result = ProductZoneEngine(SelectionPolicy()).evaluate(
        SelectionInput(
            product_name="Soul Ready Uncertified",
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
            **unit.to_selection_fields(),
        )
    )
    assert result.zone == "EXCLUSIVE"
    assert result.decision == "TEST"
    assert "CPC" in result.cert_gap
