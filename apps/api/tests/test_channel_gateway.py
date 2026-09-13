from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.channels import gateway
from app.adapters.saleor import SaleorAdapter
from app.main import app


def test_gateway_resolves_aliases():
    assert gateway.resolve("Amazon").channel == "amazon"
    assert gateway.resolve("tiktok").channel == "tiktok_shop"
    assert gateway.resolve("Shopify").channel == "shopify"


def test_unknown_channel():
    with pytest.raises(KeyError):
        gateway.resolve("lazada")


@pytest.mark.asyncio
async def test_dry_run_publish():
    result = await gateway.publish_product(
        "amazon", {"sku": "JOY-AI-001", "name": "AI Story Teddy", "retail_price": 69}
    )
    assert result.status == "DRY_RUN"
    assert result.data["listing"]["sku"] == "JOY-AI-001"


@pytest.mark.asyncio
async def test_saleor_health_without_url():
    health = await SaleorAdapter(graphql_url="", token="").health()
    assert health["connected"] is False
    assert health["kernel"] == "saleor"


def test_foundation_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/foundation")
    assert response.status_code == 200
    body = response.json()
    assert body["kernel"]["kernel"] == "saleor"
    channels = {item["channel"] for item in body["channels"]}
    assert channels == {"amazon", "tiktok_shop", "shopify"}


def test_saleor_webhook():
    with TestClient(app) as client:
        response = client.post(
            "/api/integrations/saleor/webhooks",
            json={"id": "T3JkZXI6MQ==", "number": "JOY-10001"},
            headers={"Saleor-Event": "ORDER_CREATED"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["event"] == "ORDER_CREATED"


def test_publish_master_dry_run():
    with TestClient(app) as client:
        products = client.get("/api/products").json()
        product_id = products[0]["id"]
        response = client.post(f"/api/channels/amazon/publish_master/{product_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DRY_RUN"
    assert body["listing_status"] == "SUBMITTED"
