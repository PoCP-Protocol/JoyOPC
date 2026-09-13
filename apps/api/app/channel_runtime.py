from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .adapters.channels.amazon import AmazonAdapter
from .adapters.channels.mock import MockChannelAdapter
from .adapters.channels.shopify import ShopifyAdapter
from .adapters.channels.tiktok_shop import TikTokShopAdapter
from .content_factory import content_factory
from .models import (
    ChannelAccount,
    ChannelCostEntry,
    ChannelListing,
    ChannelObjectRef,
    ChannelOrderLink,
    ChannelSyncRun,
    CommerceOrder,
    CommerceOrderItem,
    MasterProduct,
)


def shopify_channel_account(db: Session) -> ChannelAccount | None:
    return db.scalar(select(ChannelAccount).where(ChannelAccount.channel == "Shopify").order_by(ChannelAccount.id))


def first_publishable_master_product(db: Session) -> MasterProduct | None:
    return db.scalar(
        select(MasterProduct)
        .where(MasterProduct.active.is_(True), MasterProduct.decision.notin_(("HOLD", "REJECT")))
        .order_by(MasterProduct.opportunity_score.desc(), MasterProduct.id)
    )


def adapter_for(account: ChannelAccount):
    cfg = _json(account.config_json)
    if account.channel == "Shopify":
        return ShopifyAdapter(
            store_domain=account.store_domain,
            env_prefix=account.credential_env_prefix or "SHOPIFY",
            api_version=str(cfg.get("api_version") or "2026-07"),
        )
    if account.channel == "Amazon":
        return AmazonAdapter(
            seller_id=account.seller_id,
            marketplace_id=account.marketplace_id,
            env_prefix=account.credential_env_prefix or "AMAZON_SP",
            region=str(cfg.get("region") or "NA"),
        )
    if account.channel == "TikTok Shop":
        return TikTokShopAdapter(
            shop_cipher=account.shop_cipher,
            env_prefix=account.credential_env_prefix or "TIKTOK_SHOP",
        )
    if account.channel == "Mock":
        return MockChannelAdapter()
    raise ValueError(f"Unsupported channel: {account.channel}")


def account_dict(account: ChannelAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "channel": account.channel,
        "market": account.market,
        "account_name": account.account_name,
        "status": account.status,
        "credential_env_prefix": account.credential_env_prefix,
        "store_domain": account.store_domain,
        "seller_id": account.seller_id,
        "marketplace_id": account.marketplace_id,
        "shop_cipher_set": bool(account.shop_cipher),
        "config": _json(account.config_json),
        "last_error": account.last_error,
        "last_checked_at": account.last_checked_at.isoformat() if account.last_checked_at else None,
        "last_order_sync_at": account.last_order_sync_at.isoformat() if account.last_order_sync_at else None,
    }


async def check_account(db: Session, account: ChannelAccount) -> dict[str, Any]:
    run = ChannelSyncRun(channel_account_id=account.id, operation="CONNECTION_CHECK")
    db.add(run)
    db.flush()
    try:
        result = await adapter_for(account).check_connection()
        account.status = result.get("status", "CONNECTED")
        account.last_error = ""
        account.last_checked_at = datetime.utcnow()
        run.status = "DONE"
        run.records_received = 1
        run.records_written = 1
        run.response_json = json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:
        account.status = "ERROR"
        account.last_error = str(exc)
        account.last_checked_at = datetime.utcnow()
        run.status = "FAILED"
        run.error_message = str(exc)
        result = {"status": "ERROR", "error": str(exc)}
    run.completed_at = datetime.utcnow()
    db.commit()
    return result


async def publish_master_product(
    db: Session,
    *,
    account: ChannelAccount,
    product: MasterProduct,
    publish_as_draft: bool,
    channel_payload: dict[str, Any],
) -> dict[str, Any]:
    run = ChannelSyncRun(channel_account_id=account.id, operation="PUBLISH_PRODUCT")
    db.add(run)
    db.flush()
    listing = db.scalar(
        select(ChannelListing).where(
            ChannelListing.master_product_id == product.id,
            ChannelListing.channel == account.channel,
            ChannelListing.market == account.market,
        )
    )
    if listing is None:
        listing = ChannelListing(
            master_product_id=product.id,
            channel=account.channel,
            market=account.market,
            status="DRAFT",
            selling_price=product.retail_price,
        )
        db.add(listing)
        db.flush()

    request_product = {
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "selling_price": listing.selling_price or product.retail_price,
        "publish_as_draft": publish_as_draft,
        "vendor": "JoyOPC",
    }
    if account.channel == "Shopify":
        copy = content_factory.generate(
            {
                "sku": product.sku,
                "name": product.name,
                "category": product.category,
                "features": [product.selection_reason] if product.selection_reason else [],
            },
            "shopify",
        )
        shopify_copy = (copy.get("listings") or {}).get("shopify") or {}
        request_product["description_html"] = shopify_copy.get("description_html") or ""
        request_product["tags"] = shopify_copy.get("tags") or ["ai-toy", "kids", "joyopc"]
    request_product.update(channel_payload)
    run.request_json = json.dumps(request_product, ensure_ascii=False, default=str)
    try:
        result = await adapter_for(account).publish_product(request_product)
        status = result.get("status", "UNKNOWN")
        run.response_json = json.dumps(result, ensure_ascii=False, default=str)
        run.records_received = 1
        if status in {"PUBLISHED", "SUBMITTED"}:
            listing.external_listing_id = str(result.get("external_listing_id") or "")
            listing.status = "ACTIVE" if status == "PUBLISHED" and not publish_as_draft else "SUBMITTED"
            result["listing_status"] = listing.status
            result["master_sku"] = product.sku
            result["admin_url"] = result.get("admin_url") or ""
            ref = db.scalar(select(ChannelObjectRef).where(ChannelObjectRef.channel_listing_id == listing.id))
            if ref is None:
                ref = ChannelObjectRef(channel_account_id=account.id, channel_listing_id=listing.id)
                db.add(ref)
            ref.external_product_id = str(result.get("external_product_id") or "")
            ref.external_variant_id = str(result.get("external_variant_id") or "")
            ref.external_sku = str(result.get("external_sku") or product.sku)
            ref.payload_json = json.dumps(result.get("raw") or {}, ensure_ascii=False, default=str)
            ref.last_synced_at = datetime.utcnow()
            run.records_written = 1
            run.status = "DONE"
        else:
            listing.status = status
            run.status = "BLOCKED"
            result["listing_status"] = listing.status
            result["master_sku"] = product.sku
    except Exception as except_exc:
        listing.status = "ERROR"
        run.status = "FAILED"
        run.error_message = str(except_exc)
        result = {"status": "ERROR", "error": str(except_exc), "master_sku": product.sku, "listing_status": "ERROR"}
    run.completed_at = datetime.utcnow()
    db.commit()
    return result


async def sync_orders(db: Session, *, account: ChannelAccount, since_iso: str | None) -> dict[str, Any]:
    run = ChannelSyncRun(
        channel_account_id=account.id,
        operation="ORDER_SYNC",
        request_json=json.dumps({"since": since_iso}, ensure_ascii=False),
    )
    db.add(run)
    db.flush()
    try:
        rows = await adapter_for(account).pull_orders(since_iso=since_iso)
        run.records_received = len(rows)
        written = 0
        for raw in rows:
            if not raw.get("external_order_id"):
                continue
            _upsert_order(db, account, raw)
            written += 1
        account.last_order_sync_at = datetime.utcnow()
        account.last_error = ""
        run.records_written = written
        run.status = "DONE"
        run.response_json = json.dumps({"received": len(rows), "written": written}, ensure_ascii=False)
        result = {"status": "DONE", "received": len(rows), "written": written}
    except Exception as exc:
        account.last_error = str(exc)
        run.status = "FAILED"
        run.error_message = str(exc)
        result = {"status": "ERROR", "error": str(exc)}
    run.completed_at = datetime.utcnow()
    db.commit()
    if result.get("status") == "DONE":
        reconcile_profit(db)
    return result


def _upsert_order(db: Session, account: ChannelAccount, raw: dict[str, Any]) -> CommerceOrder:
    external_id = str(raw["external_order_id"])
    link = db.scalar(
        select(ChannelOrderLink).where(
            ChannelOrderLink.channel_account_id == account.id,
            ChannelOrderLink.external_order_id == external_id,
        )
    )
    if link:
        order = db.get(CommerceOrder, link.commerce_order_id)
        if order is None:
            raise RuntimeError("Broken order link")
        db.query(CommerceOrderItem).filter(CommerceOrderItem.commerce_order_id == order.id).delete()
    else:
        display = raw.get("external_order_name") or external_id
        order_no = f"{account.channel}:{display}"
        suffix = 1
        candidate_no = order_no
        while db.scalar(select(CommerceOrder.id).where(CommerceOrder.order_no == candidate_no)) is not None:
            suffix += 1
            candidate_no = f"{order_no}:{suffix}"
        order = CommerceOrder(order_no=candidate_no, channel=account.channel, market=account.market)
        db.add(order)
        db.flush()
        link = ChannelOrderLink(
            commerce_order_id=order.id,
            channel_account_id=account.id,
            external_order_id=external_id,
        )
        db.add(link)

    order.channel = account.channel
    order.market = account.market
    order.gross_sales = float(raw.get("gross_sales") or 0)
    link.external_order_name = str(raw.get("external_order_name") or "")
    link.currency = str(raw.get("currency") or "USD")
    link.status = str(raw.get("status") or "UNKNOWN")
    link.source_created_at = _parse_dt(raw.get("source_created_at"))
    link.source_updated_at = _parse_dt(raw.get("source_updated_at"))
    link.raw_json = json.dumps(raw.get("raw") or {}, ensure_ascii=False, default=str)
    link.imported_at = datetime.utcnow()

    for item in raw.get("items") or []:
        sku = str(item.get("sku") or "")
        product = db.scalar(select(MasterProduct).where(MasterProduct.sku == sku)) if sku else None
        qty = int(item.get("quantity") or 1)
        product_cost = round((product.landed_cost if product else 0) * qty, 2)
        row = CommerceOrderItem(
            commerce_order_id=order.id,
            master_product_id=product.id if product else None,
            external_line_item_id=str(item.get("external_line_item_id") or ""),
            sku=sku,
            title=str(item.get("title") or ""),
            quantity=qty,
            gross_sales=float(item.get("gross_sales") or 0),
            discount_amount=float(item.get("discount_amount") or 0),
            net_sales=float(item.get("net_sales") or 0),
            product_cost=product_cost,
            currency=link.currency,
        )
        db.add(row)
    db.flush()
    return order


def reconcile_profit(db: Session) -> dict[str, Any]:
    orders = db.scalars(select(CommerceOrder)).all()
    entries = db.scalars(select(ChannelCostEntry)).all()
    links = {x.commerce_order_id: x for x in db.scalars(select(ChannelOrderLink)).all()}
    updated = 0
    for order in orders:
        items = db.scalars(select(CommerceOrderItem).where(CommerceOrderItem.commerce_order_id == order.id)).all()
        if not items:
            continue
        for item in items:
            item.shipping_cost = item.platform_fee = item.ad_cost = item.refund_cost = 0.0
            product = db.get(MasterProduct, item.master_product_id) if item.master_product_id else None
            item.product_cost = round((product.landed_cost if product else 0) * item.quantity, 2)
        link = links.get(order.id)
        matching = [
            e
            for e in entries
            if e.channel == order.channel
            and (
                (e.order_no and e.order_no == order.order_no)
                or (link and e.external_order_id and e.external_order_id == link.external_order_id)
                or (e.sku and any(i.sku == e.sku for i in items))
            )
        ]
        for entry in matching:
            targets = [i for i in items if entry.sku and i.sku == entry.sku] or items
            weights = [max(i.net_sales, 0.01) for i in targets]
            total_weight = sum(weights) or len(targets)
            for item, weight in zip(targets, weights):
                amount = round(entry.amount * weight / total_weight, 2)
                if entry.cost_type == "PLATFORM_FEE":
                    item.platform_fee += amount
                elif entry.cost_type == "AD_SPEND":
                    item.ad_cost += amount
                elif entry.cost_type == "SHIPPING":
                    item.shipping_cost += amount
                elif entry.cost_type == "REFUND":
                    item.refund_cost += amount
                else:
                    item.platform_fee += amount
        order.gross_sales = round(sum(i.net_sales for i in items), 2)
        order.product_cost = round(sum(i.product_cost for i in items), 2)
        order.shipping_cost = round(sum(i.shipping_cost for i in items), 2)
        order.platform_fee = round(sum(i.platform_fee for i in items), 2)
        order.ad_cost = round(sum(i.ad_cost for i in items), 2)
        order.refund_cost = round(sum(i.refund_cost for i in items), 2)
        updated += 1
    db.commit()
    return {"status": "DONE", "orders_reconciled": updated}


def sku_profit(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(CommerceOrderItem)).all()
    grouped: dict[str, dict[str, Any]] = {}
    for item in rows:
        sku = item.sku or "UNMAPPED"
        g = grouped.setdefault(
            sku,
            {
                "sku": sku,
                "title": item.title,
                "units": 0,
                "net_sales": 0.0,
                "product_cost": 0.0,
                "shipping_cost": 0.0,
                "platform_fee": 0.0,
                "ad_cost": 0.0,
                "refund_cost": 0.0,
                "contribution_profit": 0.0,
                "orders": set(),
            },
        )
        g["units"] += item.quantity
        g["net_sales"] += item.net_sales
        g["product_cost"] += item.product_cost
        g["shipping_cost"] += item.shipping_cost
        g["platform_fee"] += item.platform_fee
        g["ad_cost"] += item.ad_cost
        g["refund_cost"] += item.refund_cost
        g["contribution_profit"] += item.contribution_profit
        g["orders"].add(item.commerce_order_id)
    result = []
    for g in grouped.values():
        g["order_count"] = len(g.pop("orders"))
        for key in ["net_sales", "product_cost", "shipping_cost", "platform_fee", "ad_cost", "refund_cost", "contribution_profit"]:
            g[key] = round(g[key], 2)
        g["contribution_margin_pct"] = round(g["contribution_profit"] / g["net_sales"] * 100, 1) if g["net_sales"] else 0
        cost_presence = sum(g[k] > 0 for k in ["shipping_cost", "platform_fee", "ad_cost", "refund_cost"])
        g["profit_quality"] = "RECONCILED" if cost_presence >= 2 else "PROVISIONAL"
        result.append(g)
    return sorted(result, key=lambda x: x["contribution_profit"], reverse=True)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


def _json(value: str) -> dict:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
