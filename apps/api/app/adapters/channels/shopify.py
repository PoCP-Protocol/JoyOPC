from __future__ import annotations

import os
from typing import Any

import httpx

from .base import ChannelAdapter


class ShopifyAdapter(ChannelAdapter):
    def __init__(self, *, store_domain: str, env_prefix: str = "SHOPIFY", api_version: str = "2026-07"):
        self.store_domain = store_domain.replace("https://", "").rstrip("/")
        self.env_prefix = env_prefix or "SHOPIFY"
        self.api_version = api_version
        self.access_token = os.getenv(f"{self.env_prefix}_ACCESS_TOKEN", "")

    @property
    def connected(self) -> bool:
        return bool(self.store_domain and self.access_token)

    async def _graphql(self, query: str, variables: dict | None = None) -> dict[str, Any]:
        if not self.connected:
            raise RuntimeError(f"Missing {self.env_prefix}_ACCESS_TOKEN or store_domain")
        url = f"https://{self.store_domain}/admin/api/{self.api_version}/graphql.json"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "X-Shopify-Access-Token": self.access_token,
                },
                json={"query": query, "variables": variables or {}},
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(str(payload["errors"]))
        return payload.get("data", {})

    async def check_connection(self) -> dict[str, Any]:
        if not self.connected:
            return {"status": "NOT_CONNECTED", "reason": "missing store domain/access token"}
        data = await self._graphql("query { shop { name currencyCode myshopifyDomain } }")
        shop = data.get("shop") or {}
        return {"status": "CONNECTED", "shop": shop}

    async def publish_product(self, product: dict[str, Any]) -> dict[str, Any]:
        # Shopify's current productCreate creates the product + initial variant.
        # We then update that default variant with the JoyOPC price.
        mutation = """
        mutation CreateJoyOPCProduct($product: ProductCreateInput!) {
          productCreate(product: $product) {
            product { id title variants(first: 1) { nodes { id } } }
            userErrors { field message }
          }
        }
        """
        input_product = {
            "title": product["name"],
            "descriptionHtml": product.get("description_html", ""),
            "vendor": product.get("vendor", "JoyOPC"),
            "productType": product.get("category", "AI Toy"),
            "status": "DRAFT" if product.get("publish_as_draft", True) else "ACTIVE",
            "metafields": [
                {
                    "namespace": "joyopc",
                    "key": "master_sku",
                    "type": "single_line_text_field",
                    "value": product["sku"],
                }
            ],
        }
        data = await self._graphql(mutation, {"product": input_product})
        result = data.get("productCreate") or {}
        if result.get("userErrors"):
            raise RuntimeError(str(result["userErrors"]))
        shop_product = result.get("product") or {}
        nodes = ((shop_product.get("variants") or {}).get("nodes") or [])
        variant_id = nodes[0].get("id") if nodes else ""
        if variant_id and product.get("selling_price") is not None:
            await self.update_price(shop_product.get("id", ""), float(product["selling_price"]), external_variant_id=variant_id)
        return {
            "status": "PUBLISHED",
            "external_product_id": shop_product.get("id", ""),
            "external_variant_id": variant_id,
            "external_listing_id": shop_product.get("id", ""),
            "external_sku": product["sku"],
            "raw": shop_product,
        }

    async def update_price(self, external_listing_id: str, price: float, *, external_variant_id: str = "") -> dict[str, Any]:
        if not external_variant_id:
            raise RuntimeError("Shopify price update requires external_variant_id")
        mutation = """
        mutation UpdateJoyOPCVariant($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
          productVariantsBulkUpdate(productId: $productId, variants: $variants) {
            productVariants { id price }
            userErrors { field message }
          }
        }
        """
        data = await self._graphql(
            mutation,
            {"productId": external_listing_id, "variants": [{"id": external_variant_id, "price": str(round(price, 2))}]},
        )
        result = data.get("productVariantsBulkUpdate") or {}
        if result.get("userErrors"):
            raise RuntimeError(str(result["userErrors"]))
        return {"status": "UPDATED", "listing": external_listing_id, "price": price, "raw": result}

    async def update_inventory(self, external_listing_id: str, quantity: int, *, external_variant_id: str = "") -> dict[str, Any]:
        # Inventory updates require a location/inventory item relationship. V0.4 keeps the action explicit
        # instead of guessing a location and mutating inventory incorrectly.
        return {
            "status": "REQUIRES_LOCATION_MAPPING",
            "listing": external_listing_id,
            "variant": external_variant_id,
            "quantity": quantity,
        }

    async def pull_orders(self, *, since_iso: str | None = None) -> list[dict[str, Any]]:
        query_text = ""
        if since_iso:
            query_text = f"updated_at:>={since_iso}"
        query = """
        query JoyOPCOrders($first: Int!, $query: String) {
          orders(first: $first, reverse: true, query: $query) {
            nodes {
              id name createdAt updatedAt displayFinancialStatus displayFulfillmentStatus currencyCode
              currentTotalPriceSet { shopMoney { amount currencyCode } }
              currentTotalDiscountsSet { shopMoney { amount currencyCode } }
              lineItems(first: 100) {
                nodes {
                  id sku title quantity
                  originalTotalSet { shopMoney { amount currencyCode } }
                  discountedTotalSet { shopMoney { amount currencyCode } }
                }
              }
            }
          }
        }
        """
        data = await self._graphql(query, {"first": 50, "query": query_text or None})
        rows: list[dict[str, Any]] = []
        for order in ((data.get("orders") or {}).get("nodes") or []):
            items = []
            for item in ((order.get("lineItems") or {}).get("nodes") or []):
                gross = float((((item.get("originalTotalSet") or {}).get("shopMoney") or {}).get("amount") or 0))
                net = float((((item.get("discountedTotalSet") or {}).get("shopMoney") or {}).get("amount") or gross))
                items.append(
                    {
                        "external_line_item_id": item.get("id", ""),
                        "sku": item.get("sku") or "",
                        "title": item.get("title") or "",
                        "quantity": int(item.get("quantity") or 0),
                        "gross_sales": gross,
                        "discount_amount": max(gross - net, 0),
                        "net_sales": net,
                    }
                )
            total_money = ((order.get("currentTotalPriceSet") or {}).get("shopMoney") or {})
            rows.append(
                {
                    "external_order_id": order.get("id", ""),
                    "external_order_name": order.get("name", ""),
                    "status": f"{order.get('displayFinancialStatus') or 'UNKNOWN'} / {order.get('displayFulfillmentStatus') or 'UNKNOWN'}",
                    "currency": order.get("currencyCode") or total_money.get("currencyCode") or "USD",
                    "source_created_at": order.get("createdAt"),
                    "source_updated_at": order.get("updatedAt"),
                    "gross_sales": float(total_money.get("amount") or 0),
                    "items": items,
                    "raw": order,
                }
            )
        return rows
