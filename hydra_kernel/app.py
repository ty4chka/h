"""Composition roots: Kernel (L0) и Hydra (L0+L1+L3).

Kernel — только транспорт/DB/runtime. Hydra добавляет шину, права,
реестр и лоадер. Совместимые фреймворки (L2) подключаются поверх Hydra.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .kernel.transport import NullTransport, Transport
from .kernel.db import MemoryDB
from .kernel.runtime import Runtime, setup_logging
from .api.event_bus import EventBus
from .api.permissions import PermissionManager
from .api.lifecycle import Lifecycle
from .api.module_base import ModuleContext, ModuleBase
from .api.config import ModuleConfig
from .api.inline import InlineQueryEvent, CallbackQueryEvent
from .pkg.registry import Registry

logger = logging.getLogger("hydra_kernel")


class Kernel:
    """L0-композиция: транспорт + DB + runtime."""

    def __init__(self, transport: Optional[Transport] = None, db: Optional[MemoryDB] = None):
        self.transport = transport or NullTransport()
        self.db = db if db is not None else MemoryDB()
        self.runtime = Runtime()
        setup_logging()

    async def start(self) -> None:
        await self.transport.start()
        self.runtime.me_id = self.transport.me_id

    async def stop(self) -> None:
        await self.transport.stop()


class Hydra(Kernel):
    """Полный стек: L0 + L1 (API) + L3 (пакетная система)."""

    def __init__(
        self,
        transport: Optional[Transport] = None,
        db: Optional[MemoryDB] = None,
        owner_id: int = 1000,
        prefix: str = ".",
    ):
        super().__init__(transport, db)
        self.bus = EventBus()
        self.permissions = PermissionManager(owner_id)
        self.prefix = prefix
        self.config: Dict[str, Any] = {
            "language": "ru",
            "lang_custom": {},
            "inline_bot_username": "bot",
        }
        self.registry = Registry()
        self.inline_handlers: Dict[str, Any] = {}
        self.callback_handlers: Dict[str, Any] = {}
        self.command_handlers: Dict[str, Any] = {}
        self.bot_commands: Dict[str, Any] = {}
        self.aliases: Dict[str, str] = {}
        self.bridge: Any = None  # ButtonBridge, ставится в start()
        from .pkg.loader import Loader  # локальный импорт: L3 -> L1

        self.loader = Loader(self)

    def make_context(self, name: str, config: Optional[ModuleConfig] = None) -> ModuleContext:
        return ModuleContext(
            name=name,
            transport=self.transport,
            db=self.db,
            bus=self.bus,
            runtime=self.runtime,
            permissions=self.permissions,
            config=config or ModuleConfig(),
            prefix=self.prefix,
            hydra=self,
        )

    # ---------------- inline / callback: реестр и роутинг ----------------

    def register_inline(self, name: str, handler: Any) -> None:
        """Как в MCUB: handler(InlineQueryEvent)."""
        self.inline_handlers[name] = handler

    @property
    def owner_id(self) -> int:
        return self.permissions.owner_id

    def register_callback(self, prefix: str, handler: Any) -> None:
        """Как в MCUB: handler(CallbackQueryEvent), роутинг по префиксу data."""
        self.callback_handlers[prefix] = handler

    async def _on_inline(self, text: str, sender_id: int, raw: Any) -> bool:
        name = text.split(maxsplit=1)[0] if text else ""
        handler = self.inline_handlers.get(name)
        if handler is None:
            return False
        event = InlineQueryEvent(
            name=name, query=text, sender_id=sender_id, transport=self.transport, raw=raw
        )
        await handler(event)
        return True

    async def _on_callback(
        self, data: str, sender_id: int, chat_id: int, message_id: int, raw: Any
    ) -> bool:
        best: Optional[tuple] = None
        for prefix, handler in self.callback_handlers.items():
            if data.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
                best = (prefix, handler)
        if best is None:
            return False
        event = CallbackQueryEvent(
            data=data,
            sender_id=sender_id,
            chat_id=chat_id,
            message_id=message_id,
            transport=self.transport,
            raw=raw,
        )
        await best[1](event)
        return True

    async def start(self) -> None:
        await super().start()
        self.transport.subscribe_inline(self._on_inline)
        self.transport.subscribe_callback(self._on_callback)
        # текстовый мост кнопок (.cb N M / .it / .cbf / .iqs / .iq)
        if hasattr(self.transport, "menu_renderer"):
            import re

            from .api.button_bridge import ButtonBridge

            self.bridge = ButtonBridge(self)
            self.transport.menu_renderer = self.bridge.render
            if hasattr(self.transport, "_id_fixup"):
                self.transport._id_fixup = self.bridge.rebind
            p = re.escape(self.prefix)
            for name, fn in (
                ("cb", self.bridge.handle_cb),
                ("it", self.bridge.handle_it),
                ("cbf", self.bridge.handle_cbf),
                ("iqs", self.bridge.handle_iqs),
                ("iq", self.bridge.handle_iq),
            ):
                self.transport.subscribe(
                    fn, pattern=rf"(?i)^{p}{name}(?:\s|$)", outgoing=True, incoming=True
                )

    async def load_module(self, module: ModuleBase) -> Lifecycle:
        lifecycle = Lifecycle()
        await lifecycle.load(module)
        return lifecycle

    async def unload_module(self, name: str) -> bool:
        return await self.loader.unload(name)

    def save_config(self) -> None:
        """Персист конфига ядра (language, lang_custom и т.д.)."""
        import json
        from pathlib import Path

        path = Path("data/kernel_config.json")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:  # pragma: no cover
            logger.warning("не удалось сохранить конфиг")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Hydra modules={len(self.registry)}>"
