from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ChannelAdapter(ABC):
    """JoyOPC 对外电商平台统一动作契约。

    Adapter 返回统一 envelope。真实凭证永远从环境变量读取，不落数据库。
    """

    @abstractmethod
    async def check_connection(self) -> dict[str, Any]: ...

    @abstractmethod
    async def publish_product(self, product: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    async def update_price(self, external_listing_id: str, price: float, *, external_variant_id: str = "") -> dict[str, Any]: ...

    @abstractmethod
    async def update_inventory(self, external_listing_id: str, quantity: int, *, external_variant_id: str = "") -> dict[str, Any]: ...

    @abstractmethod
    async def pull_orders(self, *, since_iso: str | None = None) -> list[dict[str, Any]]: ...

    async def acknowledge_order(self, external_order_id: str) -> dict[str, Any]:
        return {"status": "UNSUPPORTED", "order": external_order_id}

    async def ship_order(self, external_order_id: str, tracking_no: str) -> dict[str, Any]:
        return {"status": "UNSUPPORTED", "order": external_order_id, "tracking": tracking_no}

    async def pull_metrics(self) -> dict[str, Any]:
        return {"status": "UNSUPPORTED"}
