from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MEDIA_DIR
from app.content_factory import content_factory
from app.media_studio import prepare_channel_images
from app.models import MasterProduct, ProductAsset, ProductCandidate
from app.video_studio import build_storyboard, render_listing_video


def first_product_image(db: Session, product: MasterProduct) -> Path | None:
    candidate = db.scalar(
        select(ProductCandidate).where(ProductCandidate.promoted_master_product_id == product.id)
    )
    if candidate is None:
        return None
    assets = db.scalars(
        select(ProductAsset).where(ProductAsset.candidate_id == candidate.id, ProductAsset.asset_type == "IMAGE")
    ).all()
    for asset in assets:
        path = Path(asset.stored_path)
        if path.exists():
            return path
    return None


def build_listing_pack(db: Session, product: MasterProduct) -> dict[str, Any]:
    listings = content_factory.generate(
        {
            "sku": product.sku,
            "name": product.name,
            "category": product.category,
            "features": [product.selection_reason] if product.selection_reason else [],
        }
    )
    out_dir = MEDIA_DIR / product.sku
    source = first_product_image(db, product)
    images = prepare_channel_images(source, out_dir, title=product.name, sku=product.sku)
    amazon_hero = (images.get("channels") or {}).get("amazon") or {}
    storyboard = build_storyboard(
        {"sku": product.sku, "name": product.name},
        listings.get("listings") or {},
    )
    video = render_listing_video(storyboard=storyboard, out_dir=out_dir, hero_path=amazon_hero.get("path"))
    return {
        "master_sku": product.sku,
        "master_product_id": product.id,
        "listings": listings,
        "images": images,
        "video": video,
        "ready_for_channels": {
            "amazon": bool(amazon_hero),
            "shopify": True,
            "tiktok_shop": video.get("status") in {"RENDERED", "STORYBOARD_ONLY"},
        },
    }
