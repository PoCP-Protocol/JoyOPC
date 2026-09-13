from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import OPENAI_API_KEY, OPENAI_BASE_URL, JOYOPC_TEXT_MODEL


class AIProviderGateway:
    """统一文本模型入口。多模态仍走 MultimodalGateway；这里给 Listing / Agent 用。"""

    def status(self) -> dict[str, Any]:
        configured = bool(OPENAI_API_KEY)
        return {
            "active_provider": "openai-compatible" if configured else "local-template",
            "model": JOYOPC_TEXT_MODEL,
            "configured": configured,
        }

    def complete_json(self, instruction: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not OPENAI_API_KEY:
            return {"provider": "local-template", "model": "local", **payload}
        body = {
            "model": JOYOPC_TEXT_MODEL,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"{instruction}\nReturn ONLY valid JSON.\nINPUT:\n{json.dumps(payload, ensure_ascii=False)}",
                        }
                    ],
                }
            ],
        }
        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{OPENAI_BASE_URL.rstrip('/')}/responses",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        text = data.get("output_text") or ""
        if not text:
            chunks: list[str] = []
            for item in data.get("output", []) or []:
                for content in item.get("content", []) or []:
                    if isinstance(content.get("text"), str):
                        chunks.append(content["text"])
            text = "\n".join(chunks)
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.split("\n", 1)[-1]
        parsed = json.loads(text)
        parsed["provider"] = "openai-compatible"
        parsed["model"] = JOYOPC_TEXT_MODEL
        return parsed


ai_provider = AIProviderGateway()
