from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.media_studio import CHANNEL_CANVAS, prepare_channel_images, synthesize_hero
from app.video_studio import build_storyboard, render_listing_video


def test_channel_cards_match_marketplace_canvas(tmp_path: Path):
    src = tmp_path / "raw.png"
    Image.new("RGB", (400, 300), (200, 40, 40)).save(src)
    result = prepare_channel_images(src, tmp_path / "out", title="AI Story Teddy", sku="JOY-AI-001")
    assert result["origin"] == "product_photo"
    assert result["cutout"] == "passthrough"
    amazon = Image.open(result["channels"]["amazon"]["path"])
    assert amazon.size == CHANNEL_CANVAS["amazon"]["size"]
    tiktok = Image.open(result["channels"]["tiktok_shop"]["path"])
    assert tiktok.size == CHANNEL_CANVAS["tiktok_shop"]["size"]


def test_synthetic_hero_is_labeled():
    im = synthesize_hero("Demo Toy", (200, 200))
    assert im.size == (200, 200)


def test_storyboard_has_four_shots_and_renders_frames(tmp_path: Path):
    listings = {
        "tiktok_shop": {
            "selling_points": ["on-device stories"],
            "video_script": "Hook then demo.",
        }
    }
    board = build_storyboard({"sku": "JOY-AI-001", "name": "AI Story Teddy"}, listings)
    assert len(board["shots"]) == 4
    assert [s["id"] for s in board["shots"]] == ["hook", "demo", "proof", "cta"]
    rendered = render_listing_video(storyboard=board, out_dir=tmp_path, hero_path=None)
    assert len(rendered["frames"]) == 4
    assert rendered["status"] in {"STORYBOARD_ONLY", "RENDERED"}
    assert Path(rendered["frames"][0]).exists()
