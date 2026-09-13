from __future__ import annotations

from fastapi.testclient import TestClient

from app.adapters.channels.shopify import build_shopify_draft_payload, normalize_shop_domain
from app.main import app


def test_normalize_shop_domain():
    assert normalize_shop_domain("https://Acme-Toys.myshopify.com/admin") == "acme-toys.myshopify.com"
    assert normalize_shop_domain("acme-toys") == "acme-toys.myshopify.com"


def test_draft_payload_is_unpublished():
    payload = build_shopify_draft_payload(
        {"sku": "JOY-AI-001", "name": "AI Story Teddy", "retail_price": 69, "category": "AI Toy"},
        {"seo_title": "AI Story Teddy", "description_html": "<p>Draft</p>", "tags": ["joyopc"]},
    )
    assert payload["status"] == "draft"
    assert payload["variants"][0]["sku"] == "JOY-AI-001"
    assert payload["variants"][0]["price"] == "69.00"


def test_shopify_publish_stays_draft_without_credentials(monkeypatch):
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SHOPIFY_SHOP_URL", raising=False)
    with TestClient(app) as client:
        response = client.post("/api/channels/shopify/publish_product", json={"sku": "JOY-AI-001", "name": "AI Story Teddy", "retail_price": 69})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DRY_RUN"
    assert body["data"]["product"]["status"] == "draft"


def test_connect_rejects_invalid_credentials():
    with TestClient(app) as client:
        response = client.post("/api/channels/shopify/connect", json={"shop_url": "demo-store", "access_token": "invalid"})
    assert response.status_code == 400


def test_publish_first_master_dry_run(monkeypatch):
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SHOPIFY_SHOP_URL", raising=False)
    with TestClient(app) as client:
        response = client.post("/api/channels/shopify/publish-first-master")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DRY_RUN"
    assert body["master_sku"]
    assert body["listing_status"] == "DRY_RUN"
