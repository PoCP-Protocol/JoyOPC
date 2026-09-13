from __future__ import annotations

from typing import Any

# Caps transcribed from clawnify/open-listing-studio `src/server/amazon-limits.ts`.
# Implementation stays in JoyOPC; we do not import or patch the vendor clone.

AMAZON_LIMITS = {
    "title": 200,
    "bullet": 250,
    "bullet_count": 5,
    "description": 2000,
    "backend_keyword_bytes": 249,
}

SHOPIFY_LIMITS = {"title": 255, "body_html": 65535}
TIKTOK_LIMITS = {"short_title": 255}


def _cut(text: str, max_chars: int) -> str:
    value = text or ""
    if len(value) <= max_chars:
        return value
    sliced = value[:max_chars]
    last_space = sliced.rfind(" ")
    return (sliced[:last_space] if last_space > max_chars * 0.6 else sliced).strip()


def _keyword_bytes(text: str, max_bytes: int) -> str:
    encoded = (text or "").encode("utf-8")
    if len(encoded) <= max_bytes:
        return text or ""
    words = (text or "").split()
    out = ""
    for word in words:
        nxt = f"{out} {word}".strip()
        if len(nxt.encode("utf-8")) > max_bytes:
            break
        out = nxt
    return out


def enforce_amazon_copy(copy: dict[str, Any]) -> dict[str, Any]:
    bullets = [str(item).strip() for item in (copy.get("bullets") or []) if str(item).strip()]
    bullets = [_cut(item, AMAZON_LIMITS["bullet"]) for item in bullets]
    while len(bullets) < AMAZON_LIMITS["bullet_count"]:
        bullets.append("Designed for everyday family play with on-device AI.")
    return {
        "title": _cut(str(copy.get("title") or ""), AMAZON_LIMITS["title"]),
        "bullets": bullets[: AMAZON_LIMITS["bullet_count"]],
        "description": _cut(str(copy.get("description") or ""), AMAZON_LIMITS["description"]),
        "search_terms": _keyword_bytes(str(copy.get("search_terms") or copy.get("backend_keywords") or ""), AMAZON_LIMITS["backend_keyword_bytes"]),
    }


def validate_amazon_copy(copy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    title = str(copy.get("title") or "")
    if not title.strip():
        errors.append("title is empty")
    elif len(title) > AMAZON_LIMITS["title"]:
        errors.append(f"title is {len(title)} chars (max {AMAZON_LIMITS['title']})")
    bullets = copy.get("bullets") or []
    if len(bullets) != AMAZON_LIMITS["bullet_count"]:
        errors.append(f"must have exactly {AMAZON_LIMITS['bullet_count']} bullets")
    description = str(copy.get("description") or "")
    if len(description) > AMAZON_LIMITS["description"]:
        errors.append("description exceeds Amazon cap")
    kw = str(copy.get("search_terms") or copy.get("backend_keywords") or "")
    if len(kw.encode("utf-8")) > AMAZON_LIMITS["backend_keyword_bytes"]:
        errors.append("backend keywords exceed Amazon byte cap")
    return errors
