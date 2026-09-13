from __future__ import annotations

from typing import Any


class SaleorAdapter:
    """Commerce Kernel 边界。

    JoyOPC 的 OPC、三区选品、AI Workforce、利润智能等领域逻辑必须保留在 JoyOPC，
    Saleor 只负责成熟交易能力（商品/价格/库存/订单/促销等）。
    """

    def __init__(self, graphql_url: str | None = None, token: str | None = None):
        self.graphql_url = graphql_url
        self.token = token

    async def health(self) -> dict[str, Any]:
        if not self.graphql_url:
            return {"connected": False, "kernel": "saleor", "reason": "SALEOR_GRAPHQL_URL not configured"}
        return {"connected": False, "kernel": "saleor", "reason": "V0.1 adapter boundary only"}

    def ingest_webhook(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"accepted": True, "event": event, "order_id": payload.get("id")}


saleor_adapter = SaleorAdapter()
