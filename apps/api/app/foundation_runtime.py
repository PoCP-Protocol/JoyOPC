from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .foundation_models import OutboxEvent, WebhookInbox
from .models import OPCCompany


def default_company_id(db: Session) -> int:
    company_id = db.scalar(select(OPCCompany.id).order_by(OPCCompany.id).limit(1))
    if company_id is None:
        company = OPCCompany(name="JoyOPC Default OPC", base_currency="USD")
        db.add(company)
        db.flush()
        company_id = company.id
    return int(company_id)


def receive_inbox_event(
    db: Session,
    *,
    provider: str,
    event_type: str,
    external_event_id: str,
    payload: dict[str, Any],
    signature_status: str = "UNVERIFIED",
    company_id: int | None = None,
    channel_account_id: int | None = None,
) -> tuple[WebhookInbox, bool]:
    existing = db.scalar(
        select(WebhookInbox).where(
            WebhookInbox.provider == provider,
            WebhookInbox.external_event_id == external_event_id,
        )
    )
    if existing is not None:
        return existing, True

    row = WebhookInbox(
        company_id=company_id or default_company_id(db),
        channel_account_id=channel_account_id,
        provider=provider,
        event_type=event_type,
        external_event_id=external_event_id,
        signature_status=signature_status,
        processing_status="RECEIVED" if signature_status == "VERIFIED" else "QUARANTINED",
        payload_json=json.dumps(payload, ensure_ascii=False, default=str),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(WebhookInbox).where(
                WebhookInbox.provider == provider,
                WebhookInbox.external_event_id == external_event_id,
            )
        )
        if existing is None:
            raise
        return existing, True
    db.refresh(row)
    return row, False


def enqueue_outbox(
    db: Session,
    *,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict[str, Any],
    company_id: int | None = None,
) -> OutboxEvent:
    row = OutboxEvent(
        company_id=company_id or default_company_id(db),
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload_json=json.dumps(payload, ensure_ascii=False, default=str),
    )
    db.add(row)
    db.flush()
    return row


def foundation_status(db: Session) -> dict[str, Any]:
    return {
        "version": "0.5A",
        "company_count": int(db.scalar(select(func.count()).select_from(OPCCompany)) or 0),
        "inbox_count": int(db.scalar(select(func.count()).select_from(WebhookInbox)) or 0),
        "outbox_pending": int(
            db.scalar(
                select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == "PENDING")
            )
            or 0
        ),
        "money_model": "Decimal/Numeric(18,4) for V0.5+ financial ledger",
        "event_model": "Inbox + Transactional Outbox",
    }
