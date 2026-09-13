from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .discovery_engine import CandidateIntelligenceEngine
from .models import (
    AgentTask,
    ChannelAccount,
    ChannelCostEntry,
    ChannelListing,
    ChannelObjectRef,
    ChannelOrderLink,
    ChannelSyncRun,
    CommerceOrderItem,
    CommerceOrder,
    IngestionBatch,
    ImportedProductRecord,
    MarketConnectorRun,
    MarketSignal,
    MasterProduct,
    MultimodalAnalysis,
    OPCCompany,
    ProductAsset,
    ProductCandidate,
    Supplier,
    SupplierProduct,
)
from .schemas import SelectionInput, SelectionPolicy
from .selection_engine import ProductZoneEngine


def seed_demo(db: Session, *, reset: bool = False) -> None:
    if reset:
        for model in [
            ChannelCostEntry,
            CommerceOrderItem,
            ChannelOrderLink,
            ChannelObjectRef,
            ChannelSyncRun,
            ChannelAccount,
            MultimodalAnalysis,
            ProductAsset,
            ImportedProductRecord,
            MarketConnectorRun,
            IngestionBatch,
            AgentTask,
    ChannelAccount,
    ChannelCostEntry,
            ChannelListing,
    ChannelObjectRef,
    ChannelOrderLink,
    ChannelSyncRun,
    CommerceOrderItem,
            CommerceOrder,
            ProductCandidate,
            MarketSignal,
            SupplierProduct,
            MasterProduct,
            Supplier,
            OPCCompany,
        ]:
            db.execute(delete(model))
        db.commit()

    if db.scalar(select(OPCCompany.id).limit(1)) is not None:
        return

    db.add(OPCCompany(name="JoyOPC AI Toy Trading", base_currency="USD"))
    db.add_all([
        ChannelAccount(channel="Mock", market="US", account_name="JoyOPC Safe Sandbox", status="CONNECTED", credential_env_prefix="MOCK"),
        ChannelAccount(channel="Shopify", market="US", account_name="JoyOPC Shopify", status="NOT_CONNECTED", credential_env_prefix="SHOPIFY", store_domain="your-store.myshopify.com", config_json='{"api_version":"2026-07"}'),
        ChannelAccount(channel="Amazon", market="US", account_name="JoyOPC Amazon US", status="NOT_CONNECTED", credential_env_prefix="AMAZON_SP", marketplace_id="ATVPDKIKX0DER", config_json='{"region":"NA"}'),
        ChannelAccount(channel="TikTok Shop", market="US", account_name="JoyOPC TikTok Shop US", status="NOT_CONNECTED", credential_env_prefix="TIKTOK_SHOP"),
    ])
    supplier = Supplier(name="Shenzhen SmartToy Supply Co.", supports_dropship=True)
    db.add(supplier)
    db.flush()

    engine = ProductZoneEngine(SelectionPolicy())
    demo_products = [
        (
            "JOY-AI-001",
            "AI Story Teddy",
            69.0,
            25.0,
            SelectionInput(
                product_name="AI Story Teddy",
                exclusive_rights=True,
                uniqueness=82,
                channel_control=78,
                cost_advantage=72,
                supply_advantage=80,
                content_advantage=88,
                brand_advantage=60,
                market_demand=86,
                competition_intensity=52,
                expected_margin_pct=46,
                compliance_risk=38,
                return_risk=28,
                cash_cycle_days=22,
            ),
        ),
        (
            "JOY-AI-002",
            "AI Pocket Translator Toy",
            49.0,
            19.5,
            SelectionInput(
                product_name="AI Pocket Translator Toy",
                exclusive_rights=False,
                uniqueness=60,
                channel_control=48,
                cost_advantage=82,
                supply_advantage=84,
                content_advantage=78,
                brand_advantage=50,
                market_demand=78,
                competition_intensity=60,
                expected_margin_pct=40,
                compliance_risk=30,
                return_risk=26,
                cash_cycle_days=18,
            ),
        ),
        (
            "JOY-AI-003",
            "Generic Voice Robot",
            39.0,
            22.5,
            SelectionInput(
                product_name="Generic Voice Robot",
                exclusive_rights=False,
                uniqueness=28,
                channel_control=25,
                cost_advantage=55,
                supply_advantage=65,
                content_advantage=45,
                brand_advantage=30,
                market_demand=64,
                competition_intensity=88,
                expected_margin_pct=24,
                compliance_risk=34,
                return_risk=52,
                cash_cycle_days=35,
            ),
        ),
    ]

    for idx, (sku, name, retail, landed, input_data) in enumerate(demo_products, start=1):
        result = engine.evaluate(input_data)
        p = MasterProduct(
            sku=sku,
            name=name,
            retail_price=retail,
            landed_cost=landed,
            expected_margin_pct=input_data.expected_margin_pct,
            zone=result.zone,
            opportunity_score=result.opportunity_score,
            decision=result.decision,
            selection_reason="；".join(result.reasons),
        )
        db.add(p)
        db.flush()
        db.add(
            SupplierProduct(
                supplier_id=supplier.id,
                master_product_id=p.id,
                supplier_sku=f"SZ-{idx:03d}",
                supplier_price=landed * 0.78,
                moq=1 if idx < 3 else 50,
                lead_time_days=5 + idx,
                exclusive_rights=input_data.exclusive_rights,
                authorization_scope="US online channels" if input_data.exclusive_rights else "non-exclusive",
            )
        )
        db.add(
            ChannelListing(
                master_product_id=p.id,
                channel=["TikTok Shop", "Amazon", "Shopify"][idx - 1],
                market="US",
                external_listing_id=f"DEMO-{idx}",
                status="ACTIVE" if idx < 3 else "DRAFT",
                selling_price=retail,
            )
        )

    db.add_all(
        [
            MarketSignal(source="TikTok", market="US", channel="TikTok Shop", keyword="AI companion toy", demand_score=90, growth_score=92, social_velocity=94, competition_score=68, median_price=64, confidence=86),
            MarketSignal(source="Amazon", market="US", channel="Amazon", keyword="AI companion toy", demand_score=84, growth_score=76, social_velocity=58, competition_score=72, median_price=69, confidence=92),
            MarketSignal(source="TikTok", market="US", channel="TikTok Shop", keyword="AI learning pet", demand_score=82, growth_score=88, social_velocity=91, competition_score=55, median_price=59, confidence=80),
            MarketSignal(source="Amazon", market="US", channel="Amazon", keyword="voice robot toy", demand_score=66, growth_score=44, social_velocity=42, competition_score=90, median_price=39, confidence=88),
        ]
    )
    db.flush()

    candidates = [
        ProductCandidate(
            candidate_code="CAND-001",
            product_name="AI Emotion Companion Pet",
            source="Shenzhen Supplier Pool",
            supplier_name="FuturePet Tech",
            supplier_sku="FP-AI-08",
            market="US",
            recommended_channel="TikTok Shop",
            supplier_price=17.8,
            estimated_landed_cost=24.0,
            target_retail_price=69.0,
            exclusive_rights=True,
            uniqueness=88,
            channel_control=82,
            cost_advantage=76,
            supply_advantage=78,
            content_advantage=92,
            brand_advantage=58,
            market_demand=84,
            competition_intensity=58,
            compliance_risk=36,
            return_risk=28,
            cash_cycle_days=21,
        ),
        ProductCandidate(
            candidate_code="CAND-002",
            product_name="AI Learning Pet",
            source="Shenzhen Supplier Pool",
            supplier_name="LearnBot Electronics",
            supplier_sku="LB-PET-21",
            market="US",
            recommended_channel="Amazon",
            supplier_price=15.5,
            estimated_landed_cost=21.5,
            target_retail_price=54.0,
            exclusive_rights=False,
            uniqueness=64,
            channel_control=52,
            cost_advantage=84,
            supply_advantage=86,
            content_advantage=81,
            brand_advantage=48,
            market_demand=78,
            competition_intensity=60,
            compliance_risk=30,
            return_risk=25,
            cash_cycle_days=18,
        ),
        ProductCandidate(
            candidate_code="CAND-003",
            product_name="Generic AI Voice Robot",
            source="Open Supplier Pool",
            supplier_name="Commodity Robot Factory",
            supplier_sku="GR-100",
            market="US",
            recommended_channel="Amazon",
            supplier_price=17.0,
            estimated_landed_cost=26.0,
            target_retail_price=39.0,
            exclusive_rights=False,
            uniqueness=24,
            channel_control=20,
            cost_advantage=48,
            supply_advantage=58,
            content_advantage=42,
            brand_advantage=25,
            market_demand=65,
            competition_intensity=90,
            compliance_risk=35,
            return_risk=50,
            cash_cycle_days=36,
        ),
    ]
    db.add_all(candidates)
    db.flush()

    intelligence = CandidateIntelligenceEngine(SelectionPolicy())
    all_signals = db.scalars(select(MarketSignal)).all()
    for candidate in candidates:
        result = intelligence.evaluate(candidate, all_signals)
        selection = result["selection"]
        candidate.expected_margin_pct = result["expected_margin_pct"]
        candidate.market_demand = result["market_demand"]
        candidate.competition_intensity = result["competition_intensity"]
        candidate.zone = selection.zone
        candidate.opportunity_score = selection.opportunity_score
        candidate.decision = selection.decision
        candidate.risk_score = selection.risk_score
        candidate.status = "EVALUATED"
        candidate.rationale = "；".join(selection.reasons)
        candidate.next_actions = "；".join(selection.recommended_actions)

    demo_orders = [
        CommerceOrder(order_no="JOY-10001", channel="TikTok Shop", gross_sales=690, product_cost=250, shipping_cost=82, platform_fee=62, ad_cost=118, refund_cost=0),
        CommerceOrder(order_no="JOY-10002", channel="Amazon", gross_sales=490, product_cost=195, shipping_cost=64, platform_fee=73, ad_cost=81, refund_cost=14),
        CommerceOrder(order_no="JOY-10003", channel="Shopify", gross_sales=207, product_cost=75, shipping_cost=25, platform_fee=8, ad_cost=42, refund_cost=0),
    ]
    db.add_all(demo_orders)
    db.flush()
    products = db.scalars(select(MasterProduct).order_by(MasterProduct.id)).all()
    for idx, (order, product) in enumerate(zip(demo_orders, products), start=1):
        db.add(CommerceOrderItem(
            commerce_order_id=order.id, master_product_id=product.id, external_line_item_id=f"DEMO-LINE-{idx}",
            sku=product.sku, title=product.name, quantity=10 if idx < 3 else 3,
            gross_sales=order.gross_sales, net_sales=order.gross_sales, product_cost=order.product_cost, currency="USD",
        ))
        db.add_all([
            ChannelCostEntry(channel=order.channel, cost_type="SHIPPING", amount=order.shipping_cost, order_no=order.order_no, sku=product.sku, source="DEMO"),
            ChannelCostEntry(channel=order.channel, cost_type="PLATFORM_FEE", amount=order.platform_fee, order_no=order.order_no, sku=product.sku, source="DEMO"),
            ChannelCostEntry(channel=order.channel, cost_type="AD_SPEND", amount=order.ad_cost, order_no=order.order_no, sku=product.sku, source="DEMO"),
        ])
        if order.refund_cost:
            db.add(ChannelCostEntry(channel=order.channel, cost_type="REFUND", amount=order.refund_cost, order_no=order.order_no, sku=product.sku, source="DEMO"))

    db.add_all(
        [
            AgentTask(agent="Market AI", title="发现 6 个 AI 陪伴玩具新机会", priority="HIGH", recommendation="优先分析独占授权可能性与 TikTok 内容传播性"),
            AgentTask(agent="Buyer AI", title="AI Emotion Companion Pet 进入独占区候选", priority="HIGH", requires_ceo_approval=True, recommendation="建议批准进入 Master Product，并锁定美国线上渠道独家权"),
            AgentTask(agent="Pricing AI", title="Generic Voice Robot 利润安全垫不足", priority="HIGH", requires_ceo_approval=True, recommendation="同质区不建议价格战；若不能把落地成本再降 12%，暂停上架"),
            AgentTask(agent="Content AI", title="为优势区新品生成 12 套短视频测试素材", priority="MEDIUM", recommendation="按痛点/场景/对比/UGC 四类内容做 A/B 测试"),
            AgentTask(agent="Commerce CFO", title="按贡献利润而非 GMV 排名 SKU", priority="MEDIUM", recommendation="将广告费、平台费、物流、退款统一归入 SKU 贡献利润"),
        ]
    )
    db.commit()
