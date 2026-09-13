from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WebhookInbox(Base):
    __tablename__ = "webhook_inbox"
    __table_args__ = (
        UniqueConstraint("provider", "external_event_id", name="uq_webhook_provider_event"),
        Index("ix_webhook_inbox_status_received", "processing_status", "received_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    channel_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_accounts.id"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    external_event_id: Mapped[str] = mapped_column(String(220))
    signature_status: Mapped[str] = mapped_column(String(32), default="UNVERIFIED")
    processing_status: Mapped[str] = mapped_column(String(32), default="RECEIVED")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(160), default="")
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FinancialTransaction(Base):
    __tablename__ = "financial_transactions"
    __table_args__ = (
        UniqueConstraint("source", "external_transaction_id", name="uq_fin_source_transaction"),
        Index("ix_financial_transaction_order", "external_order_id", "occurred_at"),
        Index("ix_financial_transaction_sku", "sku", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    channel_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_accounts.id"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(80), index=True)
    transaction_type: Mapped[str] = mapped_column(String(64), index=True)
    external_transaction_id: Mapped[str] = mapped_column(String(220))
    external_order_id: Mapped[str] = mapped_column(String(180), default="", index=True)
    sku: Mapped[str] = mapped_column(String(120), default="", index=True)
    campaign_id: Mapped[str] = mapped_column(String(180), default="", index=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FinancialAllocation(Base):
    __tablename__ = "financial_allocations"
    __table_args__ = (
        Index("ix_financial_allocation_target", "target_type", "target_ref"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("financial_transactions.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(40))  # ORDER_ITEM / SKU / CAMPAIGN
    target_ref: Mapped[str] = mapped_column(String(180))
    allocation_method: Mapped[str] = mapped_column(String(64), default="DIRECT")
    allocation_ratio: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("1"))
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
