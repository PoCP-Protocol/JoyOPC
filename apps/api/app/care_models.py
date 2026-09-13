from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .foundation_models import utcnow


class ReturnCase(Base):
    __tablename__ = "return_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    commerce_order_id: Mapped[int | None] = mapped_column(ForeignKey("commerce_orders.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(String(80), default="CUSTOMER_REQUEST")
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    advice: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CareTicket(Base):
    __tablename__ = "care_tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    channel: Mapped[str] = mapped_column(String(64), default="TikTok Shop")
    kind: Mapped[str] = mapped_column(String(40), default="CHAT")  # CHAT / REVIEW / A_TO_Z
    external_id: Mapped[str] = mapped_column(String(180), default="")
    subject: Mapped[str] = mapped_column(String(240), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupplierPayable(Base):
    __tablename__ = "supplier_payables"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("opc_companies.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    amount: Mapped[str] = mapped_column(String(24), default="0")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    reference: Mapped[str] = mapped_column(String(180), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
