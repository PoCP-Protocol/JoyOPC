from __future__ import annotations

from typing import Any

import httpx

from app.config import ROOT_DIR, SALEOR_APP_TOKEN, SALEOR_GRAPHQL_URL, SALEOR_MCP_URL


class SaleorMcpAdapter:
    """官方 saleor-mcp 边界：AI 只读商品/订单/渠道，写操作仍走 JoyOPC Runtime。"""

    vendor_path = ROOT_DIR / "vendor" / "saleor-mcp"

    def __init__(self, url: str | None = None) -> None:
        self.url = (url if url is not None else SALEOR_MCP_URL).rstrip()

    def status(self) -> dict[str, Any]:
        return {
            "name": "saleor-mcp",
            "source": "https://github.com/saleor/saleor-mcp",
            "cloned": self.vendor_path.exists(),
            "url": self.url or None,
            "mode": "http" if self.url else "vendor-clone",
            "readonly": True,
            "requires": {"X-Saleor-API-URL": bool(SALEOR_GRAPHQL_URL), "X-Saleor-Auth-Token": bool(SALEOR_APP_TOKEN)},
        }

    async def health(self) -> dict[str, Any]:
        base = self.status()
        if not self.url:
            return {**base, "connected": False, "reason": "SALEOR_MCP_URL not configured; clone lives in vendor/saleor-mcp"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self.url, headers={"Accept": "text/event-stream"})
            return {**base, "connected": response.status_code < 500, "http_status": response.status_code}
        except Exception as exc:  # noqa: BLE001
            return {**base, "connected": False, "reason": str(exc)}


saleor_mcp = SaleorMcpAdapter()
