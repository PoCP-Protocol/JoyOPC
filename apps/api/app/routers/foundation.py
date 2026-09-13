from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.foundation_models import OutboxEvent, WebhookInbox
from app.foundation_runtime import enqueue_outbox, foundation_status, receive_inbox_event

router = APIRouter(prefix="/api/v05a", tags=["v0.5a-foundation"])


class InboxCreate(BaseModel):
    provider: str
    event_type: str
    external_event_id: str
    signature_status: str = "UNVERIFIED"
    company_id: int | None = None
    channel_account_id: int | None = None
    payload: dict = Field(default_factory=dict)


class OutboxCreate(BaseModel):
    aggregate_type: str
    aggregate_id: str = ""
    event_type: str
    company_id: int | None = None
    payload: dict = Field(default_factory=dict)


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    return foundation_status(db)


@router.post("/events/inbox")
def create_inbox_event(payload: InboxCreate, db: Session = Depends(get_db)) -> dict:
    row, duplicate = receive_inbox_event(db, **payload.model_dump())
    return {
        "id": row.id,
        "duplicate": duplicate,
        "provider": row.provider,
        "event_type": row.event_type,
        "signature_status": row.signature_status,
        "processing_status": row.processing_status,
    }


@router.get("/events/inbox")
def list_inbox(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(WebhookInbox).order_by(WebhookInbox.id.desc()).limit(100)).all()
    return [
        {
            "id": row.id,
            "company_id": row.company_id,
            "provider": row.provider,
            "event_type": row.event_type,
            "external_event_id": row.external_event_id,
            "signature_status": row.signature_status,
            "processing_status": row.processing_status,
            "retry_count": row.retry_count,
            "received_at": row.received_at.isoformat() if row.received_at else None,
        }
        for row in rows
    ]


@router.post("/events/outbox")
def create_outbox_event(payload: OutboxCreate, db: Session = Depends(get_db)) -> dict:
    row = enqueue_outbox(db, **payload.model_dump())
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": row.status, "event_type": row.event_type}


@router.get("/events/outbox")
def list_outbox(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(OutboxEvent).order_by(OutboxEvent.id.desc()).limit(100)).all()
    return [
        {
            "id": row.id,
            "company_id": row.company_id,
            "aggregate_type": row.aggregate_type,
            "aggregate_id": row.aggregate_id,
            "event_type": row.event_type,
            "status": row.status,
            "attempts": row.attempts,
            "payload": json.loads(row.payload_json or "{}"),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
