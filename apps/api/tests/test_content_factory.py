from __future__ import annotations

from app.content_factory import content_factory


def test_content_factory_maps_three_channels():
    result = content_factory.generate({"sku": "JOY-AI-001", "name": "AI Story Teddy", "features": ["on-device stories"]})
    assert "amazon" in result["listings"]
    assert len(result["listings"]["amazon"]["bullets"]) == 5
    assert "shopify" in result["listings"]
    assert "tiktok_shop" in result["listings"]
    assert "open-listing-studio" in result["inspired_by"]
