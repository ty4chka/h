# core_inline/bot.py
"""InlineBot — обёртка над инлайн-ботом ядра (минимальная поверхность MCUB)."""
from __future__ import annotations

from typing import Any


class InlineBot:
    def __init__(self, kernel: Any):
        self.kernel = kernel
        cfg = getattr(kernel, "config", {}) or {}
        getter = getattr(cfg, "get", None)
        self.username = getter("inline_bot_username", None) if callable(getter) else None
        self._started = False

    @property
    def available(self) -> bool:
        return bool(self.username)

    async def start(self) -> bool:
        self._started = self.available
        return self._started

    async def stop(self) -> None:
        self._started = False
