from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.channels import gateway
from app.adapters.channels.shopify import ShopifyAdapter, shopify_adapter_from_db
from app.content_factory import content_factory
from app.database import get_db
from app.models import ChannelAccount, ChannelListing, MasterProduct

router = APIRouter(prefix="/api/channels", tags=["channel-gateway"])


class ProductPayload(BaseModel):
    sku: str | None = None
    name: str | None = None
    category: str | None = None
    retail_price: float | None = None
    price: float | None = None
    quantity: int = 0


class ShipPayload(BaseModel):
    tracking_no: str


class CampaignPayload(BaseModel):
    name: str = "test-campaign"
    budget: float | None = None
    extras: dict = Field(default_factory=dict)


class ShopifyConnectPayload(BaseModel):
    shop_url: str
    access_token: str
    api_version: str = "2024-10"


def _adapter(channel: str, db: Session | None = None):
    try:
        resolved = gateway.resolve(channel)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if resolved.channel == "shopify":
        return shopify_adapter_from_db(db)
    return resolved


@router.get("")
def list_channels(db: Session = Depends(get_db)) -> dict:
    channels = gateway.list_channels()
    shopify = shopify_adapter_from_db(db)
    for item in channels:
        if item["channel"] == "shopify":
            item["configured"] = shopify.configured()
            item["shop"] = shopify.shop_url or None
            item["publish_mode"] = "draft"
    return {"channels": channels}


@router.get("/health")
async def channels_health(db: Session = Depends(get_db)) -> dict:
    results = []
    for item in gateway.list_channels():
        adapter = _adapter(item["channel"], db)
        results.append(await adapter.health())
    return {"channels": [r.model_dump() for r in results]}


@router.post("/shopify/connect")
async def connect_shopify(payload: ShopifyConnectPayload, db: Session = Depends(get_db)) -> dict:
    adapter = ShopifyAdapter(payload.shop_url, payload.access_token, payload.api_version)
    health = await adapter.health()
    if health.status != "OK":
        raise HTTPException(400, health.message or "Shopify Admin API connection failed")
    account = db.scalar(select(ChannelAccount).where(ChannelAccount.channel == "shopify"))
    if account is None:
        account = ChannelAccount(channel="shopify")
        db.add(account)
    account.shop_domain = adapter.shop_url
    account.access_token = payload.access_token.strip()
    account.api_version = adapter.api_version
    account.connected_shop_name = str(health.data.get("shop") or adapter.shop_url)
    account.active = True
    db.commit()
    return {
        "connected": True,
        "shop": account.connected_shop_name,
        "domain": account.shop_domain,
        "publish_mode": "draft",
    }


@router.post("/shopify/publish-first-master")
async def publish_first_shopify_master(db: Session = Depends(get_db)) -> dict:
    product = db.scalar(select(MasterProduct).where(MasterProduct.active.is_(True)).order_by(MasterProduct.opportunity_score.desc()))
    if product is None:
        raise HTTPException(404, "no master product to publish")
    return await publish_master_product("shopify", product.id, db)


@router.post("/{channel}/publish_product")
async def publish_product(channel: str, product: ProductPayload, db: Session = Depends(get_db)) -> dict:
    adapter = _adapter(channel, db)
    result = await adapter.publish_product(product.model_dump())
    return result.model_dump()


@router.post("/{channel}/update_price")
async def update_price(channel: str, listing_id: str, price: float, db: Session = Depends(get_db)) -> dict:
    result = await _adapter(channel, db).update_price(listing_id, price)
    return result.model_dump()


@router.post("/{channel}/update_inventory")
async def update_inventory(channel: str, listing_id: str, quantity: int, db: Session = Depends(get_db)) -> dict:
    result = await _adapter(channel, db).update_inventory(listing_id, quantity)
    return result.model_dump()


@router.post("/{channel}/pull_orders")
async def pull_orders(channel: str, db: Session = Depends(get_db)) -> dict:
    result = await _adapter(channel, db).pull_orders()
    return result.model_dump()


@router.post("/{channel}/acknowledge_order")
async def acknowledge_order(channel: str, order_id: str, db: Session = Depends(get_db)) -> dict:
    result = await _adapter(channel, db).acknowledge_order(order_id)
    return result.model_dump()


@router.post("/{channel}/ship_order")
async def ship_order(channel: str, order_id: str, payload: ShipPayload, db: Session = Depends(get_db)) -> dict:
    result = await _adapter(channel, db).ship_order(order_id, payload.tracking_no)
    return result.model_dump()


@router.post("/{channel}/cancel_order")
async def cancel_order(channel: str, order_id: str, reason: str = "", db: Session = Depends(get_db)) -> dict:
    result = await _adapter(channel, db).cancel_order(order_id, reason)
    return result.model_dump()


@router.post("/{channel}/pull_reviews")
async def pull_reviews(channel: str, db: Session = Depends(get_db)) -> dict:
    result = await _adapter(channel, db).pull_reviews()
    return result.model_dump()


@router.post("/{channel}/pull_metrics")
async def pull_metrics(channel: str, db: Session = Depends(get_db)) -> dict:
    result = await _adapter(channel, db).pull_metrics()
    return result.model_dump()


@router.post("/{channel}/create_campaign")
async def create_campaign(channel: str, campaign: CampaignPayload, db: Session = Depends(get_db)) -> dict:
    result = await _adapter(channel, db).create_campaign(campaign.model_dump())
    return result.model_dump()


@router.post("/{channel}/pull_ad_metrics")
async def pull_ad_metrics(channel: str, db: Session = Depends(get_db)) -> dict:
    result = await _adapter(channel, db).pull_ad_metrics()
    return result.model_dump()


@router.post("/{channel}/publish_master/{product_id}")
async def publish_master_product(channel: str, product_id: int, db: Session = Depends(get_db)) -> dict:
    adapter = _adapter(channel, db)
    product = db.get(MasterProduct, product_id)
    if product is None:
        raise HTTPException(404, "master product not found")
    payload = {
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "retail_price": product.retail_price,
        "quantity": 0,
        "features": [product.selection_reason] if product.selection_reason else [],
    }
    if adapter.channel == "shopify":
        listing_copy = content_factory.generate(payload, "shopify")
        payload["listing"] = listing_copy.get("listings", {}).get("shopify") or {}
    result = await adapter.publish_product(payload)
    wanted = {channel.lower().replace(" ", "_"), adapter.channel, adapter.display_name.lower().replace(" ", "_")}
    listing = next((row for row in product.listings if row.channel.lower().replace(" ", "_") in wanted), None)
    if listing is None:
        listing = ChannelListing(
            master_product_id=product.id,
            channel=adapter.display_name,
            market=product.target_market,
            selling_price=product.retail_price,
        )
        db.add(listing)
    if result.status == "OK":
        listing.status = "DRAFT"
        listing.external_listing_id = str(result.data.get("id") or listing.external_listing_id)
        listing.selling_price = product.retail_price
    elif result.status == "DRY_RUN":
        listing.status = "SUBMITTED"
        if not listing.external_listing_id:
            listing.external_listing_id = f"DRY-{product.sku}-{adapter.channel}"
    else:
        listing.status = "ERROR"
    db.commit()
    data = result.model_dump()
    data["listing_id"] = listing.id
    data["listing_status"] = listing.status
    data["master_sku"] = product.sku
    data["master_name"] = product.name
    return data
