from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# Shot grammar borrowed from ronchen0927/AI-E-Commerce-Media-Studio storyboard fallback:
# Hook → Demo → Proof → CTA. Local render uses Pillow cards + optional ffmpeg concat.
# Wan i2v / Replicate stay behind env later; we never fake a cinematic product video.


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def ffmpeg_bin() -> str | None:
    return shutil.which("ffmpeg")


def build_storyboard(product: dict[str, Any], listings: dict[str, Any] | None = None) -> dict[str, Any]:
    name = str(product.get("name") or "AI Toy")
    sku = str(product.get("sku") or "")
    tiktok = ((listings or {}).get("tiktok_shop") or {})
    script = str(tiktok.get("video_script") or "")
    points = tiktok.get("selling_points") or []
    shots = [
        {"id": "hook", "duration_sec": 2.5, "camera": "push-in", "on_screen": f"Hook: {name}", "voice": f"Meet {name} — an on-device AI playmate."},
        {"id": "demo", "duration_sec": 3.0, "camera": "static", "on_screen": points[0] if points else "One-tap stories", "voice": script or f"{name} talks, sings, and answers kids safely."},
        {"id": "proof", "duration_sec": 2.5, "camera": "slow pan", "on_screen": "On-device AI · parent controls", "voice": "No cloud chats required for core play. Parents stay in control."},
        {"id": "cta", "duration_sec": 2.0, "camera": "hold", "on_screen": "Tap to shop", "voice": f"Shop {sku or name} today."},
    ]
    return {
        "sku": sku,
        "title": name,
        "aspect": "9:16",
        "total_sec": sum(s["duration_sec"] for s in shots),
        "shots": shots,
        "inspired_by": "https://github.com/ronchen0927/AI-E-Commerce-Media-Studio",
        "mode": "local-storyboard",
        "note": "Cinematic i2v (Wan) is opt-in later. This pack always produces a usable TikTok-shaped storyboard.",
    }


def _scene_card(shot: dict[str, Any], size: tuple[int, int], hero: Image.Image | None) -> Image.Image:
    w, h = size
    im = Image.new("RGB", size, (16, 18, 32))
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 0, w, 120), fill=(79, 124, 255))
    draw.text((40, 36), shot["id"].upper(), fill=(255, 255, 255), font=_font(36))
    if hero is not None:
        fitted = hero.convert("RGBA")
        ratio = min((w * 0.7) / fitted.width, (h * 0.45) / fitted.height)
        nw, nh = max(1, int(fitted.width * ratio)), max(1, int(fitted.height * ratio))
        fitted = fitted.resize((nw, nh), Image.Resampling.LANCZOS)
        im.paste(fitted, ((w - nw) // 2, 180), fitted if fitted.mode == "RGBA" else None)
    draw.text((48, h - 280), shot["on_screen"][:48], fill=(245, 245, 255), font=_font(40))
    draw.text((48, h - 160), shot["voice"][:70], fill=(180, 190, 220), font=_font(26))
    return im


def render_listing_video(
    *,
    storyboard: dict[str, Any],
    out_dir: Path,
    hero_path: str | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    size = (1080, 1920)
    hero = None
    if hero_path and Path(hero_path).exists():
        hero = Image.open(hero_path).convert("RGBA")
    frames: list[Path] = []
    for shot in storyboard["shots"]:
        card = _scene_card(shot, size, hero)
        path = out_dir / f"shot-{shot['id']}.jpg"
        card.save(path, "JPEG", quality=90)
        frames.append(path)
        shot["frame_url"] = f"/api/content/media/{out_dir.name}/{path.name}"
    result: dict[str, Any] = {
        "storyboard": storyboard,
        "frames": [str(p) for p in frames],
        "ffmpeg": bool(ffmpeg_bin()),
        "status": "STORYBOARD_ONLY",
        "video_url": None,
    }
    ff = ffmpeg_bin()
    if not ff or not frames:
        return result
    concat = out_dir / "concat.txt"
    lines = []
    for shot, frame in zip(storyboard["shots"], frames):
        lines.append(f"file '{frame.resolve().as_posix()}'")
        lines.append(f"duration {shot['duration_sec']}")
    lines.append(f"file '{frames[-1].resolve().as_posix()}'")
    concat.write_text("\n".join(lines), encoding="utf-8")
    mp4 = out_dir / f"{storyboard.get('sku') or 'listing'}-tiktok.mp4"
    cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
        result["status"] = "RENDERED"
        result["video_url"] = f"/api/content/media/{out_dir.name}/{mp4.name}"
        result["video_path"] = str(mp4)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        result["status"] = "STORYBOARD_ONLY"
        result["error"] = str(exc)[:400]
    return result
