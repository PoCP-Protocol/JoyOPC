from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any
from urllib.parse import quote

import httpx

from .base import ChannelAdapter


REGION_ENDPOINTS = {
    "NA": "https://sellingpartnerapi-na.amazon.com",
    "EU": "https://sellingpartnerapi-eu.amazon.com",
    "FE": "https://sellingpartnerapi-fe.amazon.com",
}


class AmazonAdapter(ChannelAdapter):
    def __init__(self, *, seller_id: str, marketplace_id: str, env_prefix: str = "AMAZON_SP", region: str = "NA"):
        self.seller_id = seller_id
        self.marketplace_id = marketplace_id
        self.env_prefix = env_prefix or "AMAZON_SP"
        self.region = region.upper()
        self.base_url = os.getenv(f"{self.env_prefix}_BASE_URL", REGION_ENDPOINTS.get(self.region, REGION_ENDPOINTS["NA"]))
        self.client_id = os.getenv(f"{self.env_prefix}_LWA_CLIENT_ID", "")
        self.client_secret = os.getenv(f"{self.env_prefix}_LWA_CLIENT_SECRET", "")
        self.refresh_token = os.getenv(f"{self.env_prefix}_LWA_REFRESH_TOKEN", "")
        self.default_product_type = os.getenv(f"{self.env_prefix}_DEFAULT_PRODUCT_TYPE", "")

    @property
    def connected(self) -> bool:
        return all([self.seller_id, self.marketplace_id, self.client_id, self.client_secret, self.refresh_token])

    async def _access_token(self) -> str:
        if not self.connected:
            raise RuntimeError("Amazon SP-API credentials or seller/marketplace id are incomplete")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.amazon.com/auth/o2/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            )
        response.raise_for_status()
        return response.json()["access_token"]

    async def _request(self, method: str, path: str, *, params: dict | None = None, json_body: dict | None = None) -> dict:
        token = await self._access_token()
        headers = {
            "x-amz-access-token": token,
            "x-amz-date": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "user-agent": "JoyOPC/0.4 (Language=Python)",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(method, f"{self.base_url}{path}", params=params, json=json_body, headers=headers)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    async def check_connection(self) -> dict[str, Any]:
        if not self.connected:
            return {"status": "NOT_CONNECTED", "reason": "missing LWA/seller/marketplace configuration"}
        data = await self._request(
            "GET",
            f"/listings/2021-08-01/items/{quote(self.seller_id, safe='')}",
            params={"marketplaceIds": self.marketplace_id, "pageSize": 1},
        )
        return {"status": "CONNECTED", "seller_id": self.seller_id, "marketplace_id": self.marketplace_id, "raw": data}

    async def publish_product(self, product: dict[str, Any]) -> dict[str, Any]:
        product_type = product.get("amazon_product_type") or self.default_product_type
        attributes = product.get("amazon_attributes") or {}
        if not product_type or not attributes:
            return {
                "status": "REQUIRES_CHANNEL_ATTRIBUTES",
                "reason": "Amazon listing requires Product Type Definition-backed attributes",
                "required": ["amazon_product_type", "amazon_attributes"],
            }
        sku = product["sku"]
        payload = {
            "productType": product_type,
            "requirements": "LISTING",
            "attributes": attributes,
        }
        data = await self._request(
            "PUT",
            f"/listings/2021-08-01/items/{quote(self.seller_id, safe='')}/{quote(sku, safe='')}",
            params={"marketplaceIds": self.marketplace_id},
            json_body=payload,
        )
        return {
            "status": "SUBMITTED",
            "external_product_id": sku,
            "external_variant_id": "",
            "external_listing_id": sku,
            "external_sku": sku,
            "raw": data,
        }

    async def update_price(self, external_listing_id: str, price: float, *, external_variant_id: str = "") -> dict[str, Any]:
        # Exact attribute names vary by Product Type Definition. Do not guess and corrupt a live listing.
        return {"status": "REQUIRES_PRODUCT_TYPE_PATCH_SCHEMA", "listing": external_listing_id, "price": price}

    async def update_inventory(self, external_listing_id: str, quantity: int, *, external_variant_id: str = "") -> dict[str, Any]:
        payload = {
            "productType": "PRODUCT",
            "patches": [
                {
                    "op": "replace",
                    "path": "/attributes/fulfillment_availability",
                    "value": [{"fulfillment_channel_code": "DEFAULT", "quantity": int(quantity)}],
                }
            ],
        }
        data = await self._request(
            "PATCH",
            f"/listings/2021-08-01/items/{quote(self.seller_id, safe='')}/{quote(external_listing_id, safe='')}",
            params={"marketplaceIds": self.marketplace_id},
            json_body=payload,
        )
        return {"status": "SUBMITTED", "listing": external_listing_id, "quantity": quantity, "raw": data}

    async def pull_orders(self, *, since_iso: str | None = None) -> list[dict[str, Any]]:
        # Orders API v2026-01-01. includedData gives proceeds/expense in the same sync call when the role permits it.
        params: dict[str, Any] = {
            "marketplaceIds": self.marketplace_id,
            "includedData": "PROCEEDS,EXPENSE,PROMOTION",
            "maxResultsPerPage": 50,
        }
        if since_iso:
            params["lastUpdatedAfter"] = since_iso
        data = await self._request("GET", "/orders/2026-01-01/orders", params=params)
        payload = data.get("payload", data)
        orders = payload.get("orders") or payload.get("Orders") or []
        normalized: list[dict[str, Any]] = []
        for order in orders:
            items = []
            for item in order.get("orderItems", []) or []:
                sku = item.get("sellerSku") or item.get("sku") or ""
                qty = int(item.get("quantityOrdered") or item.get("quantity") or 1)
                net = _amazon_item_net_sales(item)
                items.append(
                    {
                        "external_line_item_id": item.get("orderItemId") or item.get("id") or "",
                        "sku": sku,
                        "title": item.get("title") or "",
                        "quantity": qty,
                        "gross_sales": net,
                        "discount_amount": 0.0,
                        "net_sales": net,
                    }
                )
            normalized.append(
                {
                    "external_order_id": order.get("orderId") or order.get("AmazonOrderId") or "",
                    "external_order_name": order.get("orderId") or "",
                    "status": order.get("fulfillmentStatus") or order.get("orderStatus") or "UNKNOWN",
                    "currency": _amazon_currency(order) or "USD",
                    "source_created_at": order.get("createdTime") or order.get("PurchaseDate"),
                    "source_updated_at": order.get("lastUpdatedTime") or order.get("LastUpdateDate"),
                    "gross_sales": round(sum(i["net_sales"] for i in items), 2),
                    "items": items,
                    "raw": order,
                }
            )
        return normalized


def _amazon_item_net_sales(item: dict) -> float:
    total = 0.0
    for breakdown in ((item.get("proceeds") or {}).get("breakdowns") or []):
        if str(breakdown.get("type", "")).upper() in {"ITEM", "SHIPPING"}:
            subtotal = breakdown.get("subtotal")
            if isinstance(subtotal, dict):
                total += float(subtotal.get("amount") or subtotal.get("value") or 0)
            else:
                total += float(subtotal or 0)
    if total:
        return round(total, 2)
    price = (((item.get("product") or {}).get("price") or {}).get("unitPrice") or {})
    amount = price.get("amount") if isinstance(price, dict) else price
    return round(float(amount or 0) * int(item.get("quantityOrdered") or item.get("quantity") or 1), 2)


def _amazon_currency(order: dict) -> str:
    for item in order.get("orderItems", []) or []:
        for breakdown in ((item.get("proceeds") or {}).get("breakdowns") or []):
            subtotal = breakdown.get("subtotal")
            if isinstance(subtotal, dict) and subtotal.get("currencyCode"):
                return subtotal["currencyCode"]
    return ""
