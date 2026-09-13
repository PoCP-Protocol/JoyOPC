from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.adapters.saleor import SaleorAdapter
from app.main import app


def test_saleor_health_without_url():
    health = asyncio.run(SaleorAdapter(graphql_url="", token="").health())
    assert health["connected"] is False
    assert health["kernel"] == "saleor"


def test_foundation_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/foundation")
    assert response.status_code == 200
    body = response.json()
    assert body["kernel"]["kernel"] == "saleor"
    channels = {item["channel"] for item in body["channels"]}
    assert "Shopify" in channels
    assert "Amazon" in channels
    assert "TikTok Shop" in channels
    oss_ids = {row["id"] for row in body["opensource"]["packages"]}
    assert "kuberiva-oms" in oss_ids
    assert "python-amazon-sp-api" in oss_ids
    assert "ai-ecommerce-media-studio" in oss_ids
    assert "product-card-processor" in oss_ids


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
