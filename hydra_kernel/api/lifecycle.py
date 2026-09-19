"""L1 — lifecycle: подключение/отключение модуля к транспорту и шине.

Сканирует методы ModuleBase с метаданными `_hydra_meta` и подписывает их
на транспорт. Ошибки хуков логируются и не ломают загрузку соседей.
"""

from __future__ import annotations

import asyncio
import logging
import re
from enum import Enum
from typing import Any, Callable, List

from .decorators import META_ATTR
from .module_base import ModuleBase
from ..kernel.transport import Message

logger = logging.getLogger("hydra_kernel.lifecycle")


class ModuleState(Enum):
    UNLOADED = "unloaded"
    LOADED = "loaded"


class Lifecycle:
    def __init__(self) -> None:
        self._unsubs: List[Callable[[], None]] = []
        self._tasks: List[asyncio.Task] = []
        self._hooks_uninstall: List[Callable] = []
        self.state = ModuleState.UNLOADED

    async def load(self, module: ModuleBase) -> None:
        """Подписывает обработчики и дёргает on_install/on_load."""
        hooks_install, hooks_uninstall = [], []
        for attr in dir(module):
            fn = getattr(module, attr, None)
            meta = getattr(fn, META_ATTR, None)
            if not callable(fn) or meta is None:
                continue
            kind = meta["kind"]
            if kind == "command":
                self._bind_command(module, fn, meta)
            elif kind == "watcher":
                self._bind_watcher(module, fn, meta)
            elif kind == "loop":
                self._start_loop(module, fn, meta)
            elif kind == "inline":
                reg = getattr(module.ctx, "hydra", None)
                if reg is not None:
                    reg.register_inline(meta["name"], fn)
            elif kind == "callback":
                reg = getattr(module.ctx, "hydra", None)
                if reg is not None:
                    reg.register_callback(meta["prefix"], fn)
            elif kind == "bot_command":
                reg = getattr(module.ctx, "hydra", None)
                if reg is not None:
                    reg.bot_commands[meta["name"]] = fn
            elif kind == "method":
                await self._safe_hook(fn)  # setup-методы класса (MCUB @method)
            elif kind == "hook_install":
                hooks_install.append(fn)
            elif kind == "hook_uninstall":
                hooks_uninstall.append(fn)

        self._hooks_uninstall = hooks_uninstall
        for hook in hooks_install:
            await self._safe_hook(hook)
        await self._safe_hook(getattr(module, "on_install", None))
        await self._safe_hook(getattr(module, "on_load", None))
        self.state = ModuleState.LOADED
        logger.info("module %s loaded", getattr(module, "name", module.__class__.__name__))

    async def unload(self, module: ModuleBase) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        await self._safe_hook(getattr(module, "on_unload", None))
        await self._safe_hook(getattr(module, "on_uninstall", None))
        for hook in getattr(self, "_hooks_uninstall", []):
            await self._safe_hook(hook)
        self.state = ModuleState.UNLOADED
        logger.info("module %s unloaded", module.name)

    # -- приватное --

    def _bind_command(self, module: ModuleBase, fn: Callable, meta: dict) -> None:
        prefix = module.ctx.prefix
        names = [meta["name"], *meta.get("aliases", ())]
        required = meta.get("required_level", 1)
        hydra = getattr(module.ctx, "hydra", None)
        for cmd in names:
            pattern = rf"(?i)^{re.escape(prefix)}{re.escape(cmd)}(?:\s|$)"

            async def wrapper(event: Message, _fn=fn, _req=required) -> None:
                if not module.ctx.permissions.check(event.sender_id, _req):
                    return
                try:
                    await _fn(event)
                except Exception as e:  # noqa: BLE001
                    logger.error("command %s failed: %s", meta["name"], e)
                    try:
                        await event.reply(f"<b>Error:</b> <code>{str(e)[:100]}</code>")
                    except Exception:  # pragma: no cover
                        pass

            self._unsubs.append(
                module.ctx.transport.subscribe(wrapper, pattern=pattern, outgoing=True, incoming=True)
            )
            if hydra is not None:
                if cmd == meta["name"]:
                    hydra.command_handlers[cmd] = wrapper
                else:
                    hydra.aliases[cmd] = meta["name"]

    def _bind_watcher(self, module: ModuleBase, fn: Callable, meta: dict) -> None:
        async def wrapper(event: Message) -> None:
            try:
                await fn(event)
            except Exception as e:  # noqa: BLE001
                logger.error("watcher of %s failed: %s", module.name, e)

        self._unsubs.append(
            module.ctx.transport.subscribe(
                wrapper,
                pattern=meta.get("pattern"),
                incoming=meta.get("incoming", True),
                outgoing=meta.get("outgoing", False),
                chats=meta.get("chats"),
            )
        )

    def _start_loop(self, module: ModuleBase, fn: Callable, meta: dict) -> None:
        interval = float(meta["interval"])

        async def runner() -> None:
            while True:
                await asyncio.sleep(interval)
                try:
                    await fn()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    logger.error("loop of %s failed: %s", module.name, e)

        self._tasks.append(asyncio.create_task(runner()))

    @staticmethod
    async def _safe_hook(hook: Callable) -> None:
        if hook is None:
            return
        try:
            await hook()
        except Exception as e:  # noqa: BLE001
            logger.error("hook %r failed: %s", hook, e)
