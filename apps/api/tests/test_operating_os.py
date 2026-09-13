from app.crossborder_ai_toy import classify_crossborder_advantage, mix_policy_for_channel, sku_ops_plan, toy_archetype
from app.operating_os import MixItem, analyze_portfolio, classify_advantage, diagnose_sku
from app.product_unit import companion_passport
from app.schemas import MixPolicy, SelectionInput, SelectionPolicy
from app.selection_engine import ProductZoneEngine


def test_fake_advantage_is_called_out():
    payload = SelectionInput(
        product_name="Pretty Story Homogeneous Toy",
        exclusive_rights=False,
        uniqueness=80,
        brand_advantage=78,
        channel_control=30,
        cost_advantage=40,
        supply_advantage=40,
        content_advantage=55,
        market_demand=70,
        competition_intensity=88,
        expected_margin_pct=18,
    )
    quality, _sources, reasons = classify_advantage(payload)
    assert quality == "FAKE"
    assert any("伪优势" in r for r in reasons)


def test_self_intoxicated_advantage():
    payload = SelectionInput(
        product_name="Team Favorite",
        exclusive_rights=False,
        uniqueness=40,
        content_advantage=90,
        brand_advantage=80,
        market_demand=35,
        competition_intensity=40,
        expected_margin_pct=30,
    )
    quality, _, _ = classify_advantage(payload)
    assert quality == "SELF_INTOXICATED"


def test_homogeneous_mix_triggers_portfolio_contradiction():
    items = [
        MixItem(name="A", zone="EXCLUSIVE", expected_margin_pct=45, exclusive_rights=True, uniqueness=80, channel_control=80),
        MixItem(name="B", zone="ADVANTAGE", expected_margin_pct=32, cost_advantage=80, supply_advantage=80),
        MixItem(name="C", zone="HOMOGENEOUS", expected_margin_pct=12, competition_intensity=90, uniqueness=20),
        MixItem(name="D", zone="HOMOGENEOUS", expected_margin_pct=10, competition_intensity=90, uniqueness=18),
        MixItem(name="E", zone="HOMOGENEOUS", expected_margin_pct=11, competition_intensity=88, uniqueness=22),
        MixItem(name="F", zone="HOMOGENEOUS", expected_margin_pct=9, competition_intensity=92, uniqueness=15),
        MixItem(name="G", zone="HOMOGENEOUS", expected_margin_pct=8, competition_intensity=90, uniqueness=16),
    ]
    result = analyze_portfolio(items, MixPolicy())
    assert result["mix"]["sku_share"]["HOMOGENEOUS"] >= 65
    assert result["main_contradiction_code"] == "MIX_DRAG"
    assert result["mix"]["current_blended_margin_pct"] < result["mix"]["target_blended_margin_pct"]
    assert any("同质区" in a for a in result["recommended_actions"])


def test_target_mix_improves_profit_story():
    before = [
        MixItem(name="ex", zone="EXCLUSIVE", expected_margin_pct=40, exclusive_rights=True),
        MixItem(name="ad", zone="ADVANTAGE", expected_margin_pct=28),
        *[MixItem(name=f"h{i}", zone="HOMOGENEOUS", expected_margin_pct=10) for i in range(8)],
    ]
    after = [
        MixItem(name="ex1", zone="EXCLUSIVE", expected_margin_pct=40, exclusive_rights=True),
        MixItem(name="ex2", zone="EXCLUSIVE", expected_margin_pct=38, exclusive_rights=True),
        MixItem(name="ad1", zone="ADVANTAGE", expected_margin_pct=28),
        MixItem(name="ad2", zone="ADVANTAGE", expected_margin_pct=30),
        MixItem(name="ad3", zone="ADVANTAGE", expected_margin_pct=29),
        *[MixItem(name=f"h{i}", zone="HOMOGENEOUS", expected_margin_pct=10) for i in range(5)],
    ]
    r0 = analyze_portfolio(before)
    r1 = analyze_portfolio(after)
    assert r0["mix"]["sku_share"]["HOMOGENEOUS"] == 80
    assert r1["mix"]["sku_share"]["EXCLUSIVE"] == 20
    assert r1["mix"]["sku_share"]["ADVANTAGE"] == 30
    assert r1["mix"]["sku_share"]["HOMOGENEOUS"] == 50
    assert r1["mix"]["current_blended_margin_pct"] > r0["mix"]["current_blended_margin_pct"]


def test_selection_engine_attaches_philosophy():
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
    assert result.philosophy.advantage_quality == "CREATED"
    assert result.philosophy.reliability_score > 60


def test_diagnose_price_war():
    ph = diagnose_sku(
        SelectionInput(
            product_name="Generic",
            uniqueness=20,
            competition_intensity=90,
            expected_margin_pct=18,
            market_demand=70,
        ),
        zone="HOMOGENEOUS",
        decision="HOLD",
        risk_score=40,
    )
    assert ph.main_contradiction_code == "PRICE_WAR"
    assert ph.gaming_move == "CHANGE_BOARD"


def test_management_process_has_value_and_goals():
    items = [
        MixItem(name="ex", zone="EXCLUSIVE", expected_margin_pct=40, exclusive_rights=True, uniqueness=80, channel_control=80),
        MixItem(name="ad", zone="ADVANTAGE", expected_margin_pct=30, cost_advantage=80, supply_advantage=80),
        MixItem(name="h", zone="HOMOGENEOUS", expected_margin_pct=12, uniqueness=20),
    ]
    result = analyze_portfolio(items)
    mg = result["management"]
    assert mg["active_step"]
    assert len(mg["process_loop"]) == 11
    assert {x["letter"] for x in mg["talent_value"]} == {"V", "A", "L", "U", "E"}
    assert any(g["name"] == "组合毛利" for g in mg["goals"])
    assert mg["ceo_agenda"]


def test_approve_gate_blocks_homogeneous_scale_when_mix_dragged():
    from app.operating_os import approve_management_gate, publish_management_error

    gate = approve_management_gate(
        zone="HOMOGENEOUS",
        decision="SCALE",
        quality="WEAK",
        homogeneous_share=70,
        homogeneous_alert=65,
    )
    assert gate["blocked"] is True
    assert publish_management_error(zone="HOMOGENEOUS", decision="TEST", homogeneous_share=70, homogeneous_alert=65)


def test_fake_scale_is_downgraded_to_test():
    from app.operating_os import approve_management_gate

    gate = approve_management_gate(
        zone="ADVANTAGE",
        decision="SCALE",
        quality="FAKE",
        homogeneous_share=30,
        homogeneous_alert=65,
    )
    assert gate["blocked"] is False
    assert gate["force_decision"] == "TEST"


def test_fake_ai_label_without_soul_or_rights():
    quality, _, reasons = classify_advantage(
        SelectionInput(
            product_name="AI Companion Bunny",
            exclusive_rights=False,
            uniqueness=40,
            has_persona=False,
            memory_enabled=False,
        )
    )
    assert quality == "FAKE"
    assert any("AI" in r or "魂" in r for r in reasons)
    assert classify_crossborder_advantage(SelectionInput(product_name="AI Companion Bunny")) == "FAKE_AI_LABEL"


def test_amazon_mix_is_stricter_than_tiktok():
    amazon = mix_policy_for_channel("Amazon")
    tiktok = mix_policy_for_channel("TikTok Shop")
    assert amazon.homogeneous_target_pct < tiktok.homogeneous_target_pct
    assert amazon.homogeneous_alert_pct < tiktok.homogeneous_alert_pct


def test_crossborder_plan_orders_tiktok_before_amazon():
    plan = sku_ops_plan(
        SelectionInput(product_name="AI Story Teddy", exclusive_rights=True, market="US", has_persona=True, memory_enabled=True),
        zone="EXCLUSIVE",
        decision="TEST",
        channel="TikTok Shop",
    )
    assert plan["archetype"] == "COMPANION"
    assert "CPC" in plan["certs_required"]
    assert plan["entry_sequence"][0].startswith("TikTok")
    assert "Amazon" in plan["entry_sequence"][-1]
    assert toy_archetype(SelectionInput(product_name="Generic Voice Robot")) == "GENERIC_VOICE"


def test_portfolio_includes_crossborder_playbook():
    items = [
        MixItem(name="A", zone="EXCLUSIVE", expected_margin_pct=40, exclusive_rights=True, channel="Amazon", market="US"),
        MixItem(name="B", zone="ADVANTAGE", expected_margin_pct=30, channel="TikTok Shop"),
        MixItem(name="C", zone="HOMOGENEOUS", expected_margin_pct=12, channel="Amazon"),
    ]
    result = analyze_portfolio(items)
    assert "TikTok Shop TEST" in result["crossborder"]["entry_sequence"][0]
    channels = {row["channel"] for row in result["crossborder"]["channel_mix_snapshot"]}
    assert "Amazon" in channels
