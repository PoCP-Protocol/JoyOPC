from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .base import ChannelAdapter


class MockChannelAdapter(ChannelAdapter):
    """Deterministic safe channel for end-to-end tests and demos."""

    def __init__(self, *, channel_name: str = "Mock"):
        self.channel_name = channel_name

    async def check_connection(self) -> dict[str, Any]:
        return {"status": "CONNECTED", "shop": {"name": "JoyOPC Mock Store", "currencyCode": "USD"}}

    async def publish_product(self, product: dict[str, Any]) -> dict[str, Any]:
        token = uuid4().hex[:12]
        return {
            "status": "PUBLISHED",
            "external_product_id": f"mock-prod-{token}",
            "external_variant_id": f"mock-var-{token}",
            "external_listing_id": f"mock-prod-{token}",
            "external_sku": product["sku"],
            "raw": {"title": product["name"]},
        }

    async def update_price(self, external_listing_id: str, price: float, *, external_variant_id: str = "") -> dict[str, Any]:
        return {"status": "UPDATED", "listing": external_listing_id, "price": price}

    async def update_inventory(self, external_listing_id: str, quantity: int, *, external_variant_id: str = "") -> dict[str, Any]:
        return {"status": "UPDATED", "listing": external_listing_id, "quantity": quantity}

    async def pull_orders(self, *, since_iso: str | None = None) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        return [
            {
                "external_order_id": "mock-order-1001",
                "external_order_name": "#1001",
                "status": "PAID / UNFULFILLED",
                "currency": "USD",
                "source_created_at": now,
                "source_updated_at": now,
                "gross_sales": 138.0,
                "items": [
                    {
                        "external_line_item_id": "mock-line-1",
                        "sku": "JOY-AI-001",
                        "title": "AI Story Teddy",
                        "quantity": 2,
                        "gross_sales": 138.0,
                        "discount_amount": 0.0,
                        "net_sales": 138.0,
                    }
                ],
                "raw": {"mock": True},
            }
        ]
