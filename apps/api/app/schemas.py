from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SelectionInput(BaseModel):
    product_name: str = "Unnamed Product"
    exclusive_rights: bool = False
    uniqueness: float = Field(50, ge=0, le=100)
    channel_control: float = Field(50, ge=0, le=100)
    cost_advantage: float = Field(50, ge=0, le=100)
    supply_advantage: float = Field(50, ge=0, le=100)
    content_advantage: float = Field(50, ge=0, le=100)
    brand_advantage: float = Field(50, ge=0, le=100)
    market_demand: float = Field(50, ge=0, le=100)
    competition_intensity: float = Field(50, ge=0, le=100)
    expected_margin_pct: float = Field(30, ge=-100, le=100)
    compliance_risk: float = Field(30, ge=0, le=100)
    return_risk: float = Field(30, ge=0, le=100)
    cash_cycle_days: int = Field(30, ge=0, le=365)
    market: str = "US"
    recommended_channel: str = "TikTok Shop"
    soul_recipe_id: str = ""
    has_persona: bool = False
    memory_enabled: bool = False
    skills: list[str] = Field(default_factory=list)
    hw_gen: int = Field(1, ge=1, le=4)
    module_tier: str = "Mini"
    shell: str = ""
    claimed_features: list[str] = Field(default_factory=list)
    certs_held: list[str] = Field(default_factory=list)


class StrategyCircle(BaseModel):
    code: str
    label: str
    score: float
    status: Literal["HEALTHY", "WATCH", "ALERT"]
    note: str


class SkuPhilosophy(BaseModel):
    advantage_quality: Literal["FAKE", "SELF_INTOXICATED", "CREATED", "WEAK"]
    advantage_quality_label: str
    advantage_sources: list[str] = Field(default_factory=list)
    advantage_source_labels: list[str] = Field(default_factory=list)
    main_contradiction_code: str
    main_contradiction: str
    reliability_score: float
    strategy: str
    implementation: str
    gaming_move: str
    gaming_move_label: str
    notes: list[str] = Field(default_factory=list)


class MixPolicy(BaseModel):
    exclusive_target_pct: float = Field(20, ge=0, le=100)
    advantage_target_pct: float = Field(30, ge=0, le=100)
    homogeneous_target_pct: float = Field(50, ge=0, le=100)
    homogeneous_alert_pct: float = Field(65, ge=0, le=100)


class SelectionResult(BaseModel):
    product_name: str
    zone: Literal["EXCLUSIVE", "ADVANTAGE", "HOMOGENEOUS"]
    zone_label: str
    opportunity_score: float
    decision: Literal["SCALE", "TEST", "HOLD", "REJECT"]
    exclusive_score: float
    advantage_score: float
    risk_score: float
    reasons: list[str]
    recommended_actions: list[str]
    philosophy: SkuPhilosophy | None = None
    has_companion_soul: bool = False
    needs_hardware_gate: bool = False
    cert_gap: list[str] = Field(default_factory=list)
    crossborder: dict | None = None


class SelectionPolicy(BaseModel):
    exclusive_zone_threshold: float = Field(68, ge=0, le=100)
    advantage_zone_threshold: float = Field(66, ge=0, le=100)
    scale_score_exclusive: float = Field(66, ge=0, le=100)
    scale_score_advantage: float = Field(72, ge=0, le=100)
    scale_score_homogeneous: float = Field(82, ge=0, le=100)
    min_margin_exclusive: float = Field(25, ge=-100, le=100)
    min_margin_advantage: float = Field(30, ge=-100, le=100)
    min_margin_homogeneous: float = Field(38, ge=-100, le=100)
    homogeneous_min_strong_advantages: int = Field(2, ge=1, le=5)
    max_risk_for_scale: float = Field(55, ge=0, le=100)

class MarketSignalCreate(BaseModel):
    source: str = "manual"
    market: str = "US"
    channel: str = "MULTI"
    keyword: str
    demand_score: float = Field(50, ge=0, le=100)
    growth_score: float = Field(50, ge=0, le=100)
    social_velocity: float = Field(50, ge=0, le=100)
    competition_score: float = Field(50, ge=0, le=100)
    median_price: float = Field(0, ge=0)
    confidence: float = Field(50, ge=0, le=100)


class CandidateCreate(BaseModel):
    product_name: str
    source: str = "Supplier Pool"
    supplier_name: str = ""
    supplier_sku: str = ""
    market: str = "US"
    recommended_channel: str = "TikTok Shop"
    supplier_price: float = Field(0, ge=0)
    estimated_landed_cost: float = Field(0, ge=0)
    target_retail_price: float = Field(0, ge=0)
    exclusive_rights: bool = False
    uniqueness: float = Field(50, ge=0, le=100)
    channel_control: float = Field(50, ge=0, le=100)
    cost_advantage: float = Field(50, ge=0, le=100)
    supply_advantage: float = Field(50, ge=0, le=100)
    content_advantage: float = Field(50, ge=0, le=100)
    brand_advantage: float = Field(50, ge=0, le=100)
    market_demand: float = Field(50, ge=0, le=100)
    competition_intensity: float = Field(50, ge=0, le=100)
    compliance_risk: float = Field(30, ge=0, le=100)
    return_risk: float = Field(30, ge=0, le=100)
    cash_cycle_days: int = Field(30, ge=0, le=365)
    soul_recipe_id: str = ""
    has_persona: bool = False
    memory_enabled: bool = False
    skills: list[str] = Field(default_factory=list)
    hw_gen: int = Field(1, ge=1, le=4)
    module_tier: str = "Mini"
    shell: str = ""
    claimed_features: list[str] = Field(default_factory=list)
    certs_held: list[str] = Field(default_factory=list)


class CandidateDecision(BaseModel):
    action: Literal["APPROVE", "REJECT", "REEVALUATE"]
    note: str = ""


class GoogleTrendsPull(BaseModel):
    market: str = "US"
    keywords: list[str] = Field(default_factory=list, min_length=1, max_length=20)


class PublicPageCrawl(BaseModel):
    market: str = "US"
    urls: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    keywords: list[str] = Field(default_factory=list, min_length=1, max_length=20)


class MarketSignalBatch(BaseModel):
    signals: list[MarketSignalCreate] = Field(default_factory=list, min_length=1, max_length=500)


class ChannelAccountCreate(BaseModel):
    channel: Literal["Shopify", "Amazon", "TikTok Shop", "Mock"]
    market: str = "US"
    account_name: str
    credential_env_prefix: str = ""
    store_domain: str = ""
    seller_id: str = ""
    marketplace_id: str = ""
    shop_cipher: str = ""
    config: dict = Field(default_factory=dict)


class ShopifyConnectRequest(BaseModel):
    shop_url: str
    access_token: str
    api_version: str = "2026-07"


class ChannelPublishRequest(BaseModel):
    master_product_id: int
    channel_account_id: int
    publish_as_draft: bool = True
    channel_payload: dict = Field(default_factory=dict)


class ChannelOrderSyncRequest(BaseModel):
    since_hours: int = Field(72, ge=1, le=24 * 90)


class CostEntryCreate(BaseModel):
    channel_account_id: int | None = None
    channel: str
    market: str = "US"
    cost_type: Literal["PLATFORM_FEE", "AD_SPEND", "SHIPPING", "REFUND", "OTHER"]
    amount: float = Field(ge=0)
    currency: str = "USD"
    external_order_id: str = ""
    order_no: str = ""
    sku: str = ""
    source: str = "MANUAL"
    source_ref: str = ""
