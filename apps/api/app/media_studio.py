from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.config import JOYOPC_REMBG

# Canvas sizes follow Ouple/product_card_processor marketplace-card practice
# plus Amazon main-image / TikTok Shop vertical norms.
CHANNEL_CANVAS = {
    "amazon": {"size": (1600, 1600), "bg": (255, 255, 255), "fit": 0.86},
    "shopify": {"size": (2048, 2048), "bg": (248, 246, 242), "fit": 0.84},
    "tiktok_shop": {"size": (1080, 1440), "bg": (18, 18, 28), "fit": 0.72, "dark": True},
}


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def rembg_status() -> dict[str, Any]:
    try:
        import rembg  # noqa: F401

        return {"installed": True, "enabled": JOYOPC_REMBG, "package": "https://github.com/danielgatis/rembg"}
    except Exception:
        return {"installed": False, "enabled": False, "package": "https://github.com/danielgatis/rembg"}


def try_cutout(image: Image.Image) -> tuple[Image.Image, str]:
    """Optional neural cutout. Default off so tests never download u2net."""
    rgba = image.convert("RGBA")
    if not JOYOPC_REMBG:
        return rgba, "passthrough"
    try:
        from rembg import remove

        cut = remove(rgba)
        if not isinstance(cut, Image.Image):
            cut = Image.open(cut).convert("RGBA")
        return cut.convert("RGBA"), "rembg"
    except Exception:
        return rgba, "passthrough"


def synthesize_hero(title: str, size: tuple[int, int] = (1200, 1200)) -> Image.Image:
    """Honest placeholder when no product photo exists — not a fake product shot."""
    im = Image.new("RGB", size, (236, 242, 255))
    draw = ImageDraw.Draw(im)
    cx, cy = size[0] // 2, size[1] // 2 - 40
    draw.ellipse((cx - 220, cy - 220, cx + 220, cy + 220), fill=(79, 124, 255))
    draw.ellipse((cx - 150, cy - 150, cx + 150, cy + 150), fill=(255, 255, 255))
    label = (title or "AI Toy")[:28]
    font = _font(42)
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((size[0] - tw) / 2, size[1] - 160), label, fill=(30, 40, 70), font=font)
    draw.text((40, 36), "JoyOPC synthetic hero · not a real photo", fill=(90, 100, 130), font=_font(22))
    return im


def _fit_on_canvas(product: Image.Image, canvas_w: int, canvas_h: int, fit: float) -> Image.Image:
    product = product.convert("RGBA")
    max_w, max_h = int(canvas_w * fit), int(canvas_h * fit)
    ratio = min(max_w / product.width, max_h / product.height)
    nw, nh = max(1, int(product.width * ratio)), max(1, int(product.height * ratio))
    return product.resize((nw, nh), Image.Resampling.LANCZOS)


def compose_card(product: Image.Image, *, channel: str, title: str = "", sku: str = "") -> Image.Image:
    spec = CHANNEL_CANVAS[channel]
    w, h = spec["size"]
    bg = Image.new("RGB", (w, h), spec["bg"])
    cut, _mode = try_cutout(product)
    fitted = _fit_on_canvas(cut, w, h, spec["fit"])
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    x = (w - fitted.width) // 2
    y = (h - fitted.height) // 2
    sdraw.rounded_rectangle((x + 18, y + 28, x + fitted.width + 18, y + fitted.height + 28), radius=40, fill=(0, 0, 0, 40))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    composed = Image.alpha_composite(bg.convert("RGBA"), shadow)
    composed.paste(fitted, (x, y), fitted)
    draw = ImageDraw.Draw(composed)
    fill = (245, 245, 255) if spec.get("dark") else (40, 48, 70)
    if title:
        draw.text((48, 40), title[:42], fill=fill, font=_font(36 if w >= 1600 else 28))
    if sku:
        draw.text((48, h - 70), sku, fill=fill, font=_font(24))
    return composed.convert("RGB")


def prepare_channel_images(
    source: Path | None,
    out_dir: Path,
    *,
    title: str,
    sku: str,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if source and Path(source).exists():
        with Image.open(source) as raw:
            hero = raw.convert("RGBA")
        origin = "product_photo"
    else:
        hero = synthesize_hero(title).convert("RGBA")
        origin = "synthetic_hero"
    cut, cut_mode = try_cutout(hero)
    files = {}
    for channel in CHANNEL_CANVAS:
        card = compose_card(cut, channel=channel, title=title, sku=sku)
        name = f"{sku or 'SKU'}-{channel}.jpg"
        path = out_dir / name
        card.save(path, "JPEG", quality=92)
        files[channel] = {
            "path": str(path),
            "url": f"/api/content/media/{out_dir.name}/{name}",
            "width": card.width,
            "height": card.height,
        }
    return {
        "origin": origin,
        "cutout": cut_mode,
        "inspired_by": [
            "https://github.com/Ouple/product_card_processor",
            "https://github.com/clawnify/open-listing-studio",
        ],
        "channels": files,
        "rembg": rembg_status(),
    }
