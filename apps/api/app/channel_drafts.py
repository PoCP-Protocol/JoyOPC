from __future__ import annotations

from typing import Any


def amazon_toy_draft(product: dict[str, Any], copy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Minimal TOYS_AND_GAMES draft attributes. Live PUT still needs seller-complete PTD fields."""
    copy = copy or {}
    amazon = copy.get("amazon") or copy
    marketplace = str(product.get("marketplace_id") or "ATVPDKIKX0DER")
    title = amazon.get("title") or product.get("name") or "AI Toy"
    bullets = amazon.get("bullets") or []
    description = amazon.get("description") or title
    sku = product.get("sku") or ""
    price = str(round(float(product.get("selling_price") or product.get("retail_price") or 0), 2))
    return {
        "amazon_product_type": "TOYS_AND_GAMES",
        "amazon_attributes": {
            "item_name": [{"value": title[:200], "marketplace_id": marketplace, "language_tag": "en_US"}],
            "product_description": [{"value": description[:2000], "marketplace_id": marketplace, "language_tag": "en_US"}],
            "bullet_point": [{"value": str(b)[:250], "marketplace_id": marketplace, "language_tag": "en_US"} for b in bullets[:5]],
            "supplier_declared_dg_hz_regulation": [{"value": "not_applicable", "marketplace_id": marketplace}],
            "fulfillment_availability": [{"fulfillment_channel_code": "DEFAULT", "quantity": int(product.get("quantity") or 0)}],
            "purchasable_offer": [
                {
                    "marketplace_id": marketplace,
                    "currency": product.get("currency") or "USD",
                    "our_price": [{"schedule": [{"value_with_tax": price}]}],
                }
            ],
        },
        "requirements": "LISTING_OFFER_ONLY" if product.get("publish_as_draft", True) else "LISTING",
        "sku": sku,
        "status_intent": "DRAFT",
    }


def tiktok_toy_draft(product: dict[str, Any], copy: dict[str, Any] | None = None) -> dict[str, Any]:
    copy = copy or {}
    tiktok = copy.get("tiktok_shop") or copy
    title = str(tiktok.get("short_title") or product.get("name") or "AI Toy")[:255]
    points = tiktok.get("selling_points") or []
    return {
        "title": title,
        "description": " ".join(str(p) for p in points) or title,
        "save_mode": "AS_DRAFT",
        "skus": [
            {
                "seller_sku": product.get("sku") or "",
                "price": {"amount": str(round(float(product.get("selling_price") or product.get("retail_price") or 0), 2)), "currency": product.get("currency") or "USD"},
                "inventory": [{"warehouse_id": "PRIMARY", "quantity": int(product.get("quantity") or 0)}],
            }
        ],
        "status_intent": "DRAFT",
        "note": "Leaf category / images still required by TikTok before SUBMITTED; this is a legal draft envelope.",
    }
