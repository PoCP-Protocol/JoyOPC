from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class ProductUnitColumns:
    soul_recipe_id: Mapped[str] = mapped_column(String(80), default="")
    has_persona: Mapped[bool] = mapped_column(Boolean, default=False)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    skills_json: Mapped[str] = mapped_column(Text, default="[]")
    hw_gen: Mapped[int] = mapped_column(Integer, default=1)
    module_tier: Mapped[str] = mapped_column(String(24), default="Mini")
    shell: Mapped[str] = mapped_column(String(80), default="")
    claimed_features_json: Mapped[str] = mapped_column(Text, default="[]")
    certs_held_json: Mapped[str] = mapped_column(Text, default="[]")
    cert_gap_json: Mapped[str] = mapped_column(Text, default="[]")
    needs_hardware_gate: Mapped[bool] = mapped_column(Boolean, default=False)


class ProductZone(str, Enum):
    EXCLUSIVE = "EXCLUSIVE"
    ADVANTAGE = "ADVANTAGE"
    HOMOGENEOUS = "HOMOGENEOUS"


class ProductDecision(str, Enum):
    SCALE = "SCALE"
    TEST = "TEST"
    HOLD = "HOLD"
    REJECT = "REJECT"


class OPCCompany(Base):
    __tablename__ = "opc_companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    base_currency: Mapped[str] = mapped_column(String(8), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    country: Mapped[str] = mapped_column(String(80), default="CN")
    city: Mapped[str] = mapped_column(String(80), default="Shenzhen")
    supports_dropship: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MasterProduct(ProductUnitColumns, Base):
    __tablename__ = "master_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(120), default="AI Toy")
    target_market: Mapped[str] = mapped_column(String(120), default="US")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    retail_price: Mapped[float] = mapped_column(Float, default=0)
    landed_cost: Mapped[float] = mapped_column(Float, default=0)
    expected_margin_pct: Mapped[float] = mapped_column(Float, default=0)

    zone: Mapped[str] = mapped_column(String(24), default=ProductZone.HOMOGENEOUS.value)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0)
    decision: Mapped[str] = mapped_column(String(24), default=ProductDecision.HOLD.value)
    selection_reason: Mapped[str] = mapped_column(Text, default="")

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    supplier_products: Mapped[list["SupplierProduct"]] = relationship(back_populates="master_product")
    listings: Mapped[list["ChannelListing"]] = relationship(back_populates="master_product")


class SupplierProduct(Base):
    __tablename__ = "supplier_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    master_product_id: Mapped[int] = mapped_column(ForeignKey("master_products.id"))
    supplier_sku: Mapped[str] = mapped_column(String(80))
    supplier_price: Mapped[float] = mapped_column(Float, default=0)
    moq: Mapped[int] = mapped_column(Integer, default=1)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    exclusive_rights: Mapped[bool] = mapped_column(Boolean, default=False)
    authorization_scope: Mapped[str] = mapped_column(String(180), default="")

    master_product: Mapped[MasterProduct] = relationship(back_populates="supplier_products")


class ChannelListing(Base):
    __tablename__ = "channel_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_product_id: Mapped[int] = mapped_column(ForeignKey("master_products.id"))
    channel: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(64), default="US")
    external_listing_id: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    selling_price: Mapped[float] = mapped_column(Float, default=0)

    master_product: Mapped[MasterProduct] = relationship(back_populates="listings")


class CommerceOrder(Base):
    __tablename__ = "commerce_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(80), unique=True)
    channel: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(64), default="US")
    gross_sales: Mapped[float] = mapped_column(Float, default=0)
    product_cost: Mapped[float] = mapped_column(Float, default=0)
    shipping_cost: Mapped[float] = mapped_column(Float, default=0)
    platform_fee: Mapped[float] = mapped_column(Float, default=0)
    ad_cost: Mapped[float] = mapped_column(Float, default=0)
    refund_cost: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def contribution_profit(self) -> float:
        return round(
            self.gross_sales
            - self.product_cost
            - self.shipping_cost
            - self.platform_fee
            - self.ad_cost
            - self.refund_cost,
            2,
        )


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(220))
    priority: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    requires_ceo_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class MarketSignal(Base):
    __tablename__ = "market_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(80))
    market: Mapped[str] = mapped_column(String(40), default="US")
    channel: Mapped[str] = mapped_column(String(80), default="MULTI")
    keyword: Mapped[str] = mapped_column(String(180))
    demand_score: Mapped[float] = mapped_column(Float, default=50)
    growth_score: Mapped[float] = mapped_column(Float, default=50)
    social_velocity: Mapped[float] = mapped_column(Float, default=50)
    competition_score: Mapped[float] = mapped_column(Float, default=50)
    median_price: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=50)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductCandidate(ProductUnitColumns, Base):
    __tablename__ = "product_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    product_name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(100), default="Supplier Pool")
    supplier_name: Mapped[str] = mapped_column(String(180), default="")
    supplier_sku: Mapped[str] = mapped_column(String(100), default="")
    market: Mapped[str] = mapped_column(String(40), default="US")
    recommended_channel: Mapped[str] = mapped_column(String(80), default="TikTok Shop")
    supplier_price: Mapped[float] = mapped_column(Float, default=0)
    estimated_landed_cost: Mapped[float] = mapped_column(Float, default=0)
    target_retail_price: Mapped[float] = mapped_column(Float, default=0)
    expected_margin_pct: Mapped[float] = mapped_column(Float, default=0)

    exclusive_rights: Mapped[bool] = mapped_column(Boolean, default=False)
    uniqueness: Mapped[float] = mapped_column(Float, default=50)
    channel_control: Mapped[float] = mapped_column(Float, default=50)
    cost_advantage: Mapped[float] = mapped_column(Float, default=50)
    supply_advantage: Mapped[float] = mapped_column(Float, default=50)
    content_advantage: Mapped[float] = mapped_column(Float, default=50)
    brand_advantage: Mapped[float] = mapped_column(Float, default=50)
    market_demand: Mapped[float] = mapped_column(Float, default=50)
    competition_intensity: Mapped[float] = mapped_column(Float, default=50)
    compliance_risk: Mapped[float] = mapped_column(Float, default=30)
    return_risk: Mapped[float] = mapped_column(Float, default=30)
    cash_cycle_days: Mapped[int] = mapped_column(Integer, default=30)

    zone: Mapped[str] = mapped_column(String(24), default=ProductZone.HOMOGENEOUS.value)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0)
    decision: Mapped[str] = mapped_column(String(24), default=ProductDecision.HOLD.value)
    risk_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32), default="DISCOVERED")
    rationale: Mapped[str] = mapped_column(Text, default="")
    next_actions: Mapped[str] = mapped_column(Text, default="")
    promoted_master_product_id: Mapped[int | None] = mapped_column(ForeignKey("master_products.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_type: Mapped[str] = mapped_column(String(40))  # SUPPLIER_CATALOG / MARKET_SIGNAL
    filename: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(120), default="UPLOAD")
    status: Mapped[str] = mapped_column(String(32), default="PROCESSING")
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    accepted_records: Mapped[int] = mapped_column(Integer, default=0)
    rejected_records: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ImportedProductRecord(Base):
    __tablename__ = "imported_product_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingestion_batches.id"))
    row_number: Mapped[int] = mapped_column(Integer, default=0)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    normalized_json: Mapped[str] = mapped_column(Text, default="{}")
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("product_candidates.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACCEPTED")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductAsset(Base):
    __tablename__ = "product_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("product_candidates.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    asset_type: Mapped[str] = mapped_column(String(24), default="OTHER")
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MultimodalAnalysis(Base):
    __tablename__ = "multimodal_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("product_candidates.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80), default="local-structured")
    model: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(32), default="DONE")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    applied_to_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketConnectorRun(Base):
    __tablename__ = "market_connector_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    connector: Mapped[str] = mapped_column(String(80))
    market: Mapped[str] = mapped_column(String(40), default="US")
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    request_json: Mapped[str] = mapped_column(Text, default="{}")
    records_received: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChannelAccount(Base):
    __tablename__ = "channel_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str] = mapped_column(String(40), default="US")
    account_name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="NOT_CONNECTED")
    credential_env_prefix: Mapped[str] = mapped_column(String(80), default="")
    store_domain: Mapped[str] = mapped_column(String(255), default="")
    seller_id: Mapped[str] = mapped_column(String(160), default="")
    marketplace_id: Mapped[str] = mapped_column(String(160), default="")
    shop_cipher: Mapped[str] = mapped_column(String(255), default="")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_order_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChannelSyncRun(Base):
    __tablename__ = "channel_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_account_id: Mapped[int] = mapped_column(ForeignKey("channel_accounts.id"), index=True)
    operation: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    records_received: Mapped[int] = mapped_column(Integer, default=0)
    records_written: Mapped[int] = mapped_column(Integer, default=0)
    request_json: Mapped[str] = mapped_column(Text, default="{}")
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChannelObjectRef(Base):
    __tablename__ = "channel_object_refs"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_account_id: Mapped[int] = mapped_column(ForeignKey("channel_accounts.id"), index=True)
    channel_listing_id: Mapped[int] = mapped_column(ForeignKey("channel_listings.id"), index=True)
    external_product_id: Mapped[str] = mapped_column(String(180), default="")
    external_variant_id: Mapped[str] = mapped_column(String(180), default="")
    external_sku: Mapped[str] = mapped_column(String(120), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChannelOrderLink(Base):
    __tablename__ = "channel_order_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    commerce_order_id: Mapped[int] = mapped_column(ForeignKey("commerce_orders.id"), unique=True, index=True)
    channel_account_id: Mapped[int] = mapped_column(ForeignKey("channel_accounts.id"), index=True)
    external_order_id: Mapped[str] = mapped_column(String(180), index=True)
    external_order_name: Mapped[str] = mapped_column(String(180), default="")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    status: Mapped[str] = mapped_column(String(64), default="UNKNOWN")
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CommerceOrderItem(Base):
    __tablename__ = "commerce_order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    commerce_order_id: Mapped[int] = mapped_column(ForeignKey("commerce_orders.id"), index=True)
    master_product_id: Mapped[int | None] = mapped_column(ForeignKey("master_products.id"), nullable=True, index=True)
    external_line_item_id: Mapped[str] = mapped_column(String(180), default="")
    sku: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(240), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    gross_sales: Mapped[float] = mapped_column(Float, default=0)
    discount_amount: Mapped[float] = mapped_column(Float, default=0)
    net_sales: Mapped[float] = mapped_column(Float, default=0)
    product_cost: Mapped[float] = mapped_column(Float, default=0)
    shipping_cost: Mapped[float] = mapped_column(Float, default=0)
    platform_fee: Mapped[float] = mapped_column(Float, default=0)
    ad_cost: Mapped[float] = mapped_column(Float, default=0)
    refund_cost: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def contribution_profit(self) -> float:
        return round(
            self.net_sales
            - self.product_cost
            - self.shipping_cost
            - self.platform_fee
            - self.ad_cost
            - self.refund_cost,
            2,
        )


class ChannelCostEntry(Base):
    __tablename__ = "channel_cost_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_account_id: Mapped[int | None] = mapped_column(ForeignKey("channel_accounts.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str] = mapped_column(String(40), default="US")
    cost_type: Mapped[str] = mapped_column(String(40), index=True)  # PLATFORM_FEE / AD_SPEND / SHIPPING / REFUND / OTHER
    amount: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    external_order_id: Mapped[str] = mapped_column(String(180), default="", index=True)
    order_no: Mapped[str] = mapped_column(String(180), default="", index=True)
    sku: Mapped[str] = mapped_column(String(120), default="", index=True)
    source: Mapped[str] = mapped_column(String(100), default="MANUAL_IMPORT")
    source_ref: Mapped[str] = mapped_column(String(220), default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
