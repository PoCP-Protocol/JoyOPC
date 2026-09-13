from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request

from app.adapters.saleor import saleor_adapter

router = APIRouter(prefix="/api/integrations/saleor", tags=["saleor-kernel"])


@router.get("/health")
async def saleor_health() -> dict[str, Any]:
    return await saleor_adapter.health()


@router.post("/webhooks")
async def saleor_webhooks(
    request: Request,
    saleor_event: str | None = Header(default=None, alias="Saleor-Event"),
    saleor_api_url: str | None = Header(default=None, alias="Saleor-Api-Url"),
) -> dict[str, Any]:
    payload = await request.json()
    event = saleor_event or payload.get("event") or "UNKNOWN"
    result = saleor_adapter.ingest_webhook(event, payload if isinstance(payload, dict) else {})
    result["saleor_api_url"] = saleor_api_url
    return result
