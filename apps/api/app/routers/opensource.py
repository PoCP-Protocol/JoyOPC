from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.ai_provider import ai_provider
from app.adapters.channels import gateway
from app.adapters.saleor import saleor_adapter
from app.adapters.saleor_mcp import saleor_mcp
from app.content_factory import content_factory
from app.database import get_db
from app.models import MasterProduct
from app.multimodal import MultimodalGateway

router = APIRouter(tags=["opensource-foundation"])


class ListingRequest(BaseModel):
    sku: str | None = None
    name: str = "AI Toy"
    features: list[str] = Field(default_factory=list)
    channel: str = "all"


@router.get("/api/foundation")
async def foundation(db: Session = Depends(get_db)) -> dict:
    saleor = await saleor_adapter.health()
    mcp = await saleor_mcp.health()
    from app.adapters.channels.shopify import shopify_adapter_from_db

    channels = []
    for item in gateway.list_channels():
        adapter = shopify_adapter_from_db(db) if item["channel"] == "shopify" else gateway.resolve(item["channel"])
        channels.append((await adapter.health()).model_dump())
    return {
        "kernel": saleor,
        "saleor_mcp": mcp,
        "ai_provider": ai_provider.status(),
        "multimodal": MultimodalGateway().status(),
        "content_factory": {"inspired_by": content_factory.source, "status": "ready"},
        "channels": channels,
        "vendor": {
            "saleor_platform": saleor_mcp.vendor_path.parent.joinpath("saleor-platform").exists(),
            "saleor_mcp": saleor_mcp.vendor_path.exists(),
            "open_listing_studio": saleor_mcp.vendor_path.parent.joinpath("open-listing-studio").exists(),
            "openlinker": saleor_mcp.vendor_path.parent.joinpath("openlinker").exists(),
        },
        "rule": "JoyOPC composes official OSS. It does not fork Saleor or turn Shopify into the platform kernel.",
    }


@router.get("/api/integrations/saleor-mcp/health")
async def mcp_health() -> dict:
    return await saleor_mcp.health()


@router.post("/api/content/listings")
def generate_listings(payload: ListingRequest) -> dict:
    return content_factory.generate(payload.model_dump(), payload.channel)


@router.post("/api/content/listings/master/{product_id}")
def generate_master_listings(product_id: int, channel: str = "all", db: Session = Depends(get_db)) -> dict:
    product = db.get(MasterProduct, product_id)
    if product is None:
        raise HTTPException(404, "master product not found")
    return content_factory.generate(
        {"sku": product.sku, "name": product.name, "features": [product.selection_reason] if product.selection_reason else []},
        channel,
    )
