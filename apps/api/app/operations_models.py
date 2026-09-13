from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InventoryLocation(Base):
    __tablename__ = "inventory_locations"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_inventory_location_company_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    location_type: Mapped[str] = mapped_column(String(40), default="OWN_STOCK")
    country: Mapped[str] = mapped_column(String(8), default="US")
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"
    __table_args__ = (
        UniqueConstraint("company_id", "location_id", "master_product_id", name="uq_inventory_balance_company_location_product"),
        Index("ix_inventory_balance_company_product", "company_id", "master_product_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("inventory_locations.id"), index=True)
    master_product_id: Mapped[int] = mapped_column(ForeignKey("master_products.id"), index=True)
    on_hand: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    safety_stock: Mapped[int] = mapped_column(Integer, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        UniqueConstraint("company_id", "idempotency_key", name="uq_inventory_movement_idem"),
        Index("ix_inventory_movement_ref", "reference_type", "reference_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    balance_id: Mapped[int] = mapped_column(ForeignKey("inventory_balances.id"), index=True)
    movement_type: Mapped[str] = mapped_column(String(48), index=True)
    on_hand_delta: Mapped[int] = mapped_column(Integer, default=0)
    reserved_delta: Mapped[int] = mapped_column(Integer, default=0)
    reference_type: Mapped[str] = mapped_column(String(48), default="")
    reference_id: Mapped[str] = mapped_column(String(180), default="")
    idempotency_key: Mapped[str] = mapped_column(String(220))
    note: Mapped[str] = mapped_column(Text, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"
    __table_args__ = (UniqueConstraint("company_id", "commerce_order_item_id", name="uq_inventory_reservation_order_item"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    commerce_order_id: Mapped[int] = mapped_column(ForeignKey("commerce_orders.id"), index=True)
    commerce_order_item_id: Mapped[int] = mapped_column(ForeignKey("commerce_order_items.id"), index=True)
    balance_id: Mapped[int] = mapped_column(ForeignKey("inventory_balances.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FulfillmentOrder(Base):
    __tablename__ = "fulfillment_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "commerce_order_id", name="uq_fulfillment_company_order"),
        Index("ix_fulfillment_company_status", "company_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    commerce_order_id: Mapped[int] = mapped_column(ForeignKey("commerce_orders.id"), index=True)
    channel_account_id: Mapped[int | None] = mapped_column(ForeignKey("channel_accounts.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="NEW", index=True)
    mode_summary: Mapped[str] = mapped_column(String(120), default="")
    exception_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FulfillmentItem(Base):
    __tablename__ = "fulfillment_items"
    __table_args__ = (UniqueConstraint("fulfillment_order_id", "commerce_order_item_id", name="uq_fulfillment_item_order_item"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    fulfillment_order_id: Mapped[int] = mapped_column(ForeignKey("fulfillment_orders.id"), index=True)
    commerce_order_item_id: Mapped[int] = mapped_column(ForeignKey("commerce_order_items.id"), index=True)
    master_product_id: Mapped[int | None] = mapped_column(ForeignKey("master_products.id"), nullable=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    fulfillment_mode: Mapped[str] = mapped_column(String(48), default="UNALLOCATED")
    inventory_balance_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_balances.id"), nullable=True)
    supplier_product_id: Mapped[int | None] = mapped_column(ForeignKey("supplier_products.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ALLOCATED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupplierFulfillmentRequest(Base):
    __tablename__ = "supplier_fulfillment_requests"
    __table_args__ = (UniqueConstraint("fulfillment_order_id", "supplier_id", name="uq_supplier_request_fulfillment_supplier"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    fulfillment_order_id: Mapped[int] = mapped_column(ForeignKey("fulfillment_orders.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="REQUESTED", index=True)
    line_items_json: Mapped[str] = mapped_column(Text, default="[]")
    estimated_purchase_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    external_request_id: Mapped[str] = mapped_column(String(180), default="")
    supplier_note: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (UniqueConstraint("company_id", "idempotency_key", name="uq_shipment_idem"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    fulfillment_order_id: Mapped[int] = mapped_column(ForeignKey("fulfillment_orders.id"), index=True)
    supplier_request_id: Mapped[int | None] = mapped_column(ForeignKey("supplier_fulfillment_requests.id"), nullable=True)
    carrier: Mapped[str] = mapped_column(String(100), default="")
    tracking_number: Mapped[str] = mapped_column(String(180), default="")
    tracking_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(32), default="SHIPPED", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(220))
    shipped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
