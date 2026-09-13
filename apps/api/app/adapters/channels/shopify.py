from __future__ import annotations

import os
import re
from typing import Any

import httpx

from .base import ChannelAdapter

PLACEHOLDER_DOMAINS = {"your-store.myshopify.com", "example.myshopify.com"}
_TOKEN_RE = re.compile(r"^(shpat_|shpca_|shpua_)[A-Za-z0-9]+$")


def normalize_shop_domain(raw: str) -> str:
    value = (raw or "").strip().lower()
    value = value.replace("https://", "").replace("http://", "")
    value = value.split("/")[0].split("?")[0]
    if not value:
        return ""
    if not value.endswith(".myshopify.com"):
        value = f"{value}.myshopify.com"
    return value


def looks_like_admin_token(token: str) -> bool:
    return bool(_TOKEN_RE.match((token or "").strip()))


def admin_product_url(store_domain: str, product_gid: str) -> str:
    numeric = (product_gid or "").rsplit("/", 1)[-1]
    if not numeric:
        return ""
    return f"https://{store_domain}/admin/products/{numeric}"


def build_shopify_draft_payload(product: dict[str, Any], copy: dict[str, Any] | None = None) -> dict[str, Any]:
    copy = copy or {}
    price = product.get("selling_price", product.get("retail_price", product.get("price", 0))) or 0
    draft = bool(product.get("publish_as_draft", True))
    return {
        "title": product.get("name") or "Untitled",
        "descriptionHtml": copy.get("description_html") or product.get("description_html") or "",
        "vendor": product.get("vendor") or "JoyOPC",
        "productType": product.get("category") or "AI Toy",
        "status": "draft" if draft else "active",
        "tags": copy.get("tags") or ["ai-toy", "kids", "joyopc"],
        "metafields": [
            {"namespace": "joyopc", "key": "master_sku", "type": "single_line_text_field", "value": product.get("sku") or ""}
        ],
        "variants": [{"sku": product.get("sku") or "", "price": f"{float(price):.2f}"}],
    }


class ShopifyAdapter(ChannelAdapter):
    def __init__(self, *, store_domain: str = "", env_prefix: str = "SHOPIFY", api_version: str = "2026-07"):
        self.env_prefix = env_prefix or "SHOPIFY"
        self.api_version = api_version or "2026-07"
        self.access_token = os.getenv(f"{self.env_prefix}_ACCESS_TOKEN", "").strip()
        domain = store_domain or os.getenv(f"{self.env_prefix}_SHOP_URL", "") or os.getenv("SHOPIFY_SHOP_URL", "")
        self.store_domain = normalize_shop_domain(domain)
        if self.store_domain in PLACEHOLDER_DOMAINS:
            fallback = normalize_shop_domain(os.getenv(f"{self.env_prefix}_SHOP_URL", "") or os.getenv("SHOPIFY_SHOP_URL", ""))
            if fallback:
                self.store_domain = fallback

    @property
    def connected(self) -> bool:
        return bool(
            self.store_domain
            and self.store_domain not in PLACEHOLDER_DOMAINS
            and self.access_token
        )

    def _product_input(self, product: dict[str, Any]) -> dict[str, Any]:
        preview = build_shopify_draft_payload(product, {"description_html": product.get("description_html", ""), "tags": product.get("tags") or []})
        return {
            "title": preview["title"],
            "descriptionHtml": preview["descriptionHtml"],
            "vendor": preview["vendor"],
            "productType": preview["productType"],
            "status": "DRAFT" if product.get("publish_as_draft", True) else "ACTIVE",
            "tags": preview["tags"],
            "metafields": preview["metafields"],
        }

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
        if response.status_code in {401, 403, 404}:
            raise RuntimeError("Shopify rejected the shop domain or Admin API token")
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(str(payload["errors"]))
        return payload.get("data", {})

    async def check_connection(self) -> dict[str, Any]:
        if not self.connected:
            return {"status": "NOT_CONNECTED", "reason": "missing store domain/access token"}
        try:
            data = await self._graphql("query { shop { name currencyCode myshopifyDomain } }")
        except Exception as exc:
            return {"status": "ERROR", "reason": str(exc)}
        shop = data.get("shop") or {}
        return {"status": "CONNECTED", "shop": shop, "store_domain": self.store_domain}

    async def _find_variant_by_sku(self, sku: str) -> dict[str, Any] | None:
        data = await self._graphql(
            """
            query FindJoyOPCVariant($query: String!) {
              productVariants(first: 1, query: $query) {
                nodes { id sku product { id title status } }
              }
            }
            """,
            {"query": f"sku:{sku}"},
        )
        nodes = ((data.get("productVariants") or {}).get("nodes") or [])
        return nodes[0] if nodes else None

    async def _set_variant_sku_price(self, product_id: str, variant_id: str, sku: str, price: float | None) -> dict[str, Any]:
        variant: dict[str, Any] = {"id": variant_id}
        if sku:
            variant["sku"] = sku
        if price is not None:
            variant["price"] = str(round(float(price), 2))
        data = await self._graphql(
            """
            mutation UpdateJoyOPCVariant($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
              productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                productVariants { id sku price }
                userErrors { field message }
              }
            }
            """,
            {"productId": product_id, "variants": [variant]},
        )
        result = data.get("productVariantsBulkUpdate") or {}
        if result.get("userErrors"):
            raise RuntimeError(str(result["userErrors"]))
        return result

    def _envelope(self, *, product: dict[str, Any], shop_product: dict[str, Any], variant_id: str, status: str) -> dict[str, Any]:
        product_id = shop_product.get("id", "")
        admin_url = admin_product_url(self.store_domain, product_id)
        return {
            "status": status,
            "external_product_id": product_id,
            "external_variant_id": variant_id,
            "external_listing_id": product_id,
            "external_sku": product["sku"],
            "admin_url": admin_url,
            "store_domain": self.store_domain,
            "raw": {**shop_product, "admin_url": admin_url},
        }

    async def publish_product(self, product: dict[str, Any]) -> dict[str, Any]:
        preview = build_shopify_draft_payload(product)
        draft = bool(product.get("publish_as_draft", True))
        listing_status = "SUBMITTED" if draft else "PUBLISHED"
        if not self.connected:
            return {
                "status": "DRY_RUN",
                "reason": "SHOPIFY_ACCESS_TOKEN / store domain not configured; GraphQL payload accepted locally",
                "data": {"product": preview, "admin_url": None},
                "external_listing_id": "",
                "external_sku": product.get("sku") or "",
            }

        sku = str(product["sku"])
        existing = await self._find_variant_by_sku(sku)
        if existing:
            product_id = (existing.get("product") or {}).get("id") or ""
            variant_id = existing.get("id") or ""
            update = await self._graphql(
                """
                mutation UpdateJoyOPCProduct($product: ProductUpdateInput!) {
                  productUpdate(product: $product) {
                    product { id title status variants(first: 1) { nodes { id } } }
                    userErrors { field message }
                  }
                }
                """,
                {
                    "product": {
                        "id": product_id,
                        "title": product["name"],
                        "descriptionHtml": product.get("description_html", ""),
                        "status": "DRAFT" if draft else "ACTIVE",
                    }
                },
            )
            result = update.get("productUpdate") or {}
            if result.get("userErrors"):
                raise RuntimeError(str(result["userErrors"]))
            shop_product = result.get("product") or existing.get("product") or {}
            if variant_id and product.get("selling_price") is not None:
                await self._set_variant_sku_price(product_id, variant_id, sku, float(product["selling_price"]))
            return self._envelope(product=product, shop_product=shop_product, variant_id=variant_id, status=listing_status)

        data = await self._graphql(
            """
            mutation CreateJoyOPCProduct($product: ProductCreateInput!) {
              productCreate(product: $product) {
                product { id title status variants(first: 1) { nodes { id } } }
                userErrors { field message }
              }
            }
            """,
            {"product": self._product_input(product)},
        )
        result = data.get("productCreate") or {}
        if result.get("userErrors"):
            raise RuntimeError(str(result["userErrors"]))
        shop_product = result.get("product") or {}
        nodes = ((shop_product.get("variants") or {}).get("nodes") or [])
        variant_id = nodes[0].get("id") if nodes else ""
        if variant_id:
            await self._set_variant_sku_price(
                shop_product.get("id", ""),
                variant_id,
                sku,
                float(product["selling_price"]) if product.get("selling_price") is not None else None,
            )
        return self._envelope(product=product, shop_product=shop_product, variant_id=variant_id, status=listing_status)

    async def update_price(self, external_listing_id: str, price: float, *, external_variant_id: str = "") -> dict[str, Any]:
        if not external_variant_id:
            raise RuntimeError("Shopify price update requires external_variant_id")
        raw = await self._set_variant_sku_price(external_listing_id, external_variant_id, "", price)
        return {"status": "UPDATED", "listing": external_listing_id, "price": price, "raw": raw}

    async def update_inventory(self, external_listing_id: str, quantity: int, *, external_variant_id: str = "") -> dict[str, Any]:
        return {
            "status": "REQUIRES_LOCATION_MAPPING",
            "listing": external_listing_id,
            "variant": external_variant_id,
            "quantity": quantity,
        }

    async def pull_orders(self, *, since_iso: str | None = None) -> list[dict[str, Any]]:
        query_text = f"updated_at:>={since_iso}" if since_iso else None
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
        data = await self._graphql(query, {"first": 50, "query": query_text})
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
