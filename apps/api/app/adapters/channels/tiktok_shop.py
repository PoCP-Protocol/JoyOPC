from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from .base import ChannelAdapter


class TikTokShopAdapter(ChannelAdapter):
    def __init__(self, *, shop_cipher: str, env_prefix: str = "TIKTOK_SHOP"):
        self.shop_cipher = shop_cipher
        self.env_prefix = env_prefix or "TIKTOK_SHOP"
        self.base_url = os.getenv(f"{self.env_prefix}_BASE_URL", "https://open-api.tiktokglobalshop.com").rstrip("/")
        self.app_key = os.getenv(f"{self.env_prefix}_APP_KEY", "")
        self.app_secret = os.getenv(f"{self.env_prefix}_APP_SECRET", "")
        self.access_token = os.getenv(f"{self.env_prefix}_ACCESS_TOKEN", "")
        self.create_product_path = os.getenv(f"{self.env_prefix}_CREATE_PRODUCT_PATH", "/product/202309/products")
        self.search_orders_path = os.getenv(f"{self.env_prefix}_SEARCH_ORDERS_PATH", "/order/202309/orders/search")

    @property
    def connected(self) -> bool:
        return all([self.shop_cipher, self.app_key, self.app_secret, self.access_token])

    def _signature(self, path: str, params: dict[str, Any], body: dict | None) -> str:
        # TikTok Shop v202309+: HMAC-SHA256 over app_secret + path + sorted params + body + app_secret.
        # sign itself and access_token are excluded from the signed query string.
        pairs = "".join(f"{k}{params[k]}" for k in sorted(params) if k not in {"sign", "access_token"})
        body_text = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if body else ""
        base = f"{self.app_secret}{path}{pairs}{body_text}{self.app_secret}"
        return hmac.new(self.app_secret.encode(), base.encode(), hashlib.sha256).hexdigest()

    async def _request(self, method: str, path: str, *, params: dict | None = None, body: dict | None = None) -> dict:
        if not self.connected:
            raise RuntimeError("TikTok Shop app credentials/access token/shop_cipher are incomplete")
        query = dict(params or {})
        query.setdefault("app_key", self.app_key)
        query.setdefault("timestamp", int(time.time()))
        query.setdefault("shop_cipher", self.shop_cipher)
        query["sign"] = self._signature(path, query, body)
        headers = {"Content-Type": "application/json", "x-tts-access-token": self.access_token}
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(method, f"{self.base_url}{path}", params=query, json=body, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") not in (None, 0):
            raise RuntimeError(f"TikTok Shop error {payload.get('code')}: {payload.get('message')}")
        return payload

    async def check_connection(self) -> dict[str, Any]:
        if not self.connected:
            return {"status": "NOT_CONNECTED", "reason": "missing app/access/shop configuration"}
        # Authorized shops is a safe read-only connectivity probe.
        data = await self._request("GET", "/authorization/202309/shops", params={})
        return {"status": "CONNECTED", "raw": data.get("data", data)}

    async def publish_product(self, product: dict[str, Any]) -> dict[str, Any]:
        payload = product.get("tiktok_payload") or {}
        if not payload:
            return {
                "status": "REQUIRES_CHANNEL_ATTRIBUTES",
                "reason": "TikTok Shop requires a leaf category, category rules, attributes, images and SKU payload",
                "required": ["tiktok_payload"],
            }
        payload = dict(payload)
        payload.setdefault("idempotency_key", product.get("idempotency_key"))
        data = await self._request("POST", self.create_product_path, body=payload)
        body = data.get("data") or {}
        product_id = str(body.get("product_id") or body.get("id") or "")
        return {
            "status": "SUBMITTED",
            "external_product_id": product_id,
            "external_variant_id": "",
            "external_listing_id": product_id,
            "external_sku": product["sku"],
            "raw": data,
        }

    async def update_price(self, external_listing_id: str, price: float, *, external_variant_id: str = "") -> dict[str, Any]:
        return {"status": "REQUIRES_SKU_MAPPING", "listing": external_listing_id, "price": price}

    async def update_inventory(self, external_listing_id: str, quantity: int, *, external_variant_id: str = "") -> dict[str, Any]:
        return {"status": "REQUIRES_SKU_MAPPING", "listing": external_listing_id, "quantity": quantity}

    async def pull_orders(self, *, since_iso: str | None = None) -> list[dict[str, Any]]:
        # Search Orders schemas vary by market and app permissions. Keep the path configurable and normalize common fields.
        body: dict[str, Any] = {"page_size": 50}
        if since_iso:
            # Caller may override the request body in a future market-specific adapter. The generic adapter does not
            # guess whether this shop expects create_time_ge or update_time_ge.
            pass
        data = await self._request("POST", self.search_orders_path, body=body)
        payload = data.get("data") or {}
        orders = payload.get("orders") or payload.get("order_list") or []
        normalized: list[dict[str, Any]] = []
        for order in orders:
            items = []
            raw_items = order.get("line_items") or order.get("items") or []
            for item in raw_items:
                qty = int(item.get("quantity") or 1)
                sale = _money(item.get("sale_price") or item.get("sku_sale_price") or item.get("original_price")) * qty
                items.append(
                    {
                        "external_line_item_id": str(item.get("id") or item.get("line_item_id") or ""),
                        "sku": item.get("seller_sku") or item.get("sku") or "",
                        "title": item.get("product_name") or item.get("display_name") or "",
                        "quantity": qty,
                        "gross_sales": sale,
                        "discount_amount": 0.0,
                        "net_sales": sale,
                    }
                )
            normalized.append(
                {
                    "external_order_id": str(order.get("id") or order.get("order_id") or ""),
                    "external_order_name": str(order.get("id") or order.get("order_id") or ""),
                    "status": order.get("status") or "UNKNOWN",
                    "currency": order.get("currency") or "USD",
                    "source_created_at": order.get("create_time") or order.get("created_at"),
                    "source_updated_at": order.get("update_time") or order.get("updated_at"),
                    "gross_sales": round(sum(i["net_sales"] for i in items), 2),
                    "items": items,
                    "raw": order,
                }
            )
        return normalized


def _money(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("amount") or value.get("value") or 0
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
