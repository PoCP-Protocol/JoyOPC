from pathlib import Path

from PIL import Image

from app.multimodal import AssetContext, LocalStructuredProvider, MultimodalGateway


def test_local_multimodal_provider_is_explicit_about_image_semantics(tmp_path: Path):
    image_path = tmp_path / "toy.png"
    Image.new("RGB", (640, 480)).save(image_path)
    result = LocalStructuredProvider().analyze(
        "AI Toy",
        [AssetContext(path=image_path, filename="toy.png", mime_type="image/png", asset_type="IMAGE")],
        {"uniqueness": 60, "content_advantage": 70, "compliance_risk": 30, "return_risk": 25},
    )
    assert result["provider"] == "local-structured"
    assert result["image_metadata"][0]["width"] == 640
    assert "LOCAL_PROVIDER_NO_IMAGE_SEMANTIC_INFERENCE" in result["warnings"]


def test_gateway_falls_back_to_local_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gateway = MultimodalGateway()
    assert gateway.status()["real_vision_configured"] is False
    assert gateway.provider("auto").name == "local-structured"
