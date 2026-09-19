# core_inline/lib/manager.py
"""InlineManager — регистрация и диспетчеризация инлайн-хендлеров."""
from __future__ import annotations

from typing import Any, Callable, Dict


class InlineManager:
    def __init__(self, kernel: Any):
        self.kernel = kernel
        self._handlers: Dict[str, Callable] = {}

    def register(self, name: str, handler: Callable) -> None:
        self._handlers[name] = handler
        reg = getattr(self.kernel, "register", None)
        inline = getattr(reg, "inline", None) if reg is not None else None
        if callable(inline):
            try:
                inline(name)(handler)
            except Exception:  # noqa: BLE001
                pass

    def get(self, name: str) -> Callable | None:
        return self._handlers.get(name)
