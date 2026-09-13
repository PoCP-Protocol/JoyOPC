from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from PIL import Image
from pypdf import PdfReader


@dataclass(slots=True)
class AssetContext:
    path: Path
    filename: str
    mime_type: str
    asset_type: str


class MultimodalProvider(Protocol):
    name: str

    def analyze(self, product_name: str, assets: list[AssetContext], context: dict[str, Any]) -> dict[str, Any]: ...


def extract_asset_text(asset: AssetContext) -> str:
    if asset.asset_type == "PDF":
        reader = PdfReader(str(asset.path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:12])
        return text[:24000]
    if asset.asset_type == "TEXT":
        return asset.path.read_text(encoding="utf-8", errors="ignore")[:24000]
    return ""


class LocalStructuredProvider:
    name = "local-structured"

    def analyze(self, product_name: str, assets: list[AssetContext], context: dict[str, Any]) -> dict[str, Any]:
        texts = []
        image_meta = []
        for asset in assets:
            if asset.asset_type in {"PDF", "TEXT"}:
                text = extract_asset_text(asset)
                if text:
                    texts.append(text)
            elif asset.asset_type == "IMAGE":
                try:
                    with Image.open(asset.path) as im:
                        image_meta.append({"filename": asset.filename, "width": im.width, "height": im.height, "format": im.format})
                except Exception:
                    image_meta.append({"filename": asset.filename})

        joined = "\n".join(texts)
        features = []
        for line in re.split(r"[\n。;；]", joined):
            line = line.strip(" -•\t")
            if 5 <= len(line) <= 90 and any(k in line.lower() for k in ["ai", "voice", "bluetooth", "wifi", "battery", "语音", "互动", "陪伴", "故事", "学习", "蓝牙", "续航"]):
                features.append(line)
        features = list(dict.fromkeys(features))[:8]

        return {
            "provider": self.name,
            "product_name": product_name,
            "category": "AI Toy",
            "summary": f"已结构化解析 {len(assets)} 个商品资产；本地模式不会凭空识别图片语义，图片将由真实视觉Provider增强。",
            "features": features,
            "image_metadata": image_meta,
            "document_excerpt": joined[:1800],
            "suggested_scores": {
                "uniqueness": context.get("uniqueness", 50),
                "content_advantage": min(100, float(context.get("content_advantage", 50)) + (5 if image_meta else 0)),
                "compliance_risk": context.get("compliance_risk", 35),
                "return_risk": context.get("return_risk", 35),
            },
            "confidence": 45 if image_meta and not texts else 58,
            "warnings": ["LOCAL_PROVIDER_NO_IMAGE_SEMANTIC_INFERENCE"] if image_meta else [],
        }


class OpenAIResponsesVisionProvider:
    name = "openai-responses-vision"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("JOYOPC_MULTIMODAL_MODEL", "gpt-5.6-luna").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

    @staticmethod
    def _data_url(asset: AssetContext) -> str:
        mime = asset.mime_type or mimetypes.guess_type(asset.filename)[0] or "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(asset.path.read_bytes()).decode('ascii')}"

    @staticmethod
    def _extract_output_text(payload: dict[str, Any]) -> str:
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]
        chunks: list[str] = []
        for item in payload.get("output", []) or []:
            for content in item.get("content", []) or []:
                text = content.get("text") or content.get("output_text")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks)

    def analyze(self, product_name: str, assets: list[AssetContext], context: dict[str, Any]) -> dict[str, Any]:
        documents = []
        images = []
        for asset in assets:
            if asset.asset_type in {"PDF", "TEXT"}:
                txt = extract_asset_text(asset)
                if txt:
                    documents.append(f"[{asset.filename}]\n{txt[:12000]}")
            elif asset.asset_type == "IMAGE" and len(images) < 6:
                images.append(asset)

        prompt = f"""You are JoyOPC's AI toy product intelligence analyst. Analyze supplier product assets and return ONLY valid JSON.
Product: {product_name}
Current structured context: {json.dumps(context, ensure_ascii=False)}
Documents:\n{chr(10).join(documents)[:30000]}
Return keys: category, summary, features (array), target_users (array), materials (array), capabilities (array), compliance_clues (array), risk_flags (array), suggested_scores with uniqueness/content_advantage/compliance_risk/return_risk each 0-100, confidence 0-100. Do not invent certifications or specifications that are not visible in the supplied assets."""

        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for image in images:
            content.append({"type": "input_image", "image_url": self._data_url(image)})
        body = {"model": self.model, "input": [{"role": "user", "content": content}]}
        with httpx.Client(timeout=90) as client:
            response = client.post(f"{self.base_url}/responses", headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json=body)
            response.raise_for_status()
            payload = response.json()
        text = self._extract_output_text(payload).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
        result = json.loads(text)
        result["provider"] = self.name
        result["model"] = self.model
        return result


class MultimodalGateway:
    def status(self) -> dict[str, Any]:
        configured = bool(os.getenv("OPENAI_API_KEY", "").strip())
        return {
            "active_provider": "openai-responses-vision" if configured else "local-structured",
            "real_vision_configured": configured,
            "model": os.getenv("JOYOPC_MULTIMODAL_MODEL", "gpt-5.6-luna"),
        }

    def provider(self, requested: str = "auto") -> MultimodalProvider:
        if requested in {"openai", "real", "auto"} and os.getenv("OPENAI_API_KEY", "").strip():
            return OpenAIResponsesVisionProvider()
        if requested in {"openai", "real"}:
            raise RuntimeError("Real multimodal provider requested but OPENAI_API_KEY is not configured")
        return LocalStructuredProvider()
