from __future__ import annotations

from typing import Any

from .base import ChannelAdapter, ChannelResult


class DryRunMixin(ChannelAdapter):
    """未配置凭证时返回 DRY_RUN，避免把 JoyOPC 绑死在某个 SDK 版本。"""

    def _mode(self) -> str:
        return "OK" if self.configured() else "DRY_RUN"

    def _unconfigured(self, action: str, **data: Any) -> ChannelResult:
        return self._result(
            action,
            "DRY_RUN",
            "credentials not configured; payload accepted for local orchestration",
            **data,
        )
