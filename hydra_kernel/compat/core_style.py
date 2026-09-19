"""L2 — compat: родные модули HYDRA под hydra_kernel (один движок).

Два родных стиля:
  * setup(client)      — модуль сам вешает telethon-обработчики (cfg, hloader);
  * <cmd>_handler      — конвенция: async def lang_handler -> команда .lang.

Модули ИМПОРТИРУЮТСЯ как пакеты modules.*, чтобы общее состояние
(translator и т.п.) оставалось единственным.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import re
from typing import Any, Tuple

logger = logging.getLogger("hydra_kernel.compat.core")


def _import_module(name: str) -> Any:
    # Родные L4-модули могут импортировать Telethon/aiohttp/psutil только для
    # аннотаций или редких сетевых команд.  В smoke-режиме эти зависимости
    # намеренно необязательны, поэтому сначала ставим shims отсутствующих
    # пакетов (на реальные установленный пакеты это не влияет).
    from .offline_deps import ensure_offline_dependencies

    ensure_offline_dependencies()
    return importlib.import_module(f"modules.{name}")


class NoopAdapter:
    """Библиотеки/заготовки без обработчиков (adapter.py и т.п.)."""

    def __init__(self, hydra: Any):
        self.h = hydra

    def install(self) -> None:  # pragma: no cover - тривиально
        pass

    async def load_source(self, name: str, source: str) -> Tuple[Any, Any]:
        mod = _import_module(name)
        return mod, None


class SetupAdapter:
    """Модули с def setup(client): вешают обработчики сами."""

    def __init__(self, hydra: Any):
        self.h = hydra

    def install(self) -> None:  # pragma: no cover - тривиально
        pass

    async def load_source(self, name: str, source: str) -> Tuple[Any, Any]:
        mod = _import_module(name)
        setup = getattr(mod, "setup", None)
        if setup is None:
            raise ValueError(f"{name}: нет setup(client)")
        client = getattr(self.h.transport, "client", None)
        if client is None:
            raise ValueError(f"{name}: транспорту нечего отдать в setup(client)")
        result = setup(client)
        if asyncio.iscoroutine(result):
            await result
        return mod, None


class CoreStyleAdapter:
    """Конвенция родного лоадера: async def <cmd>_handler(event) -> .<cmd>."""

    def __init__(self, hydra: Any):
        self.h = hydra
        self._unsubs: list = []

    def install(self) -> None:  # pragma: no cover - тривиально
        pass

    async def load_source(self, name: str, source: str) -> Tuple[Any, Any]:
        mod = _import_module(name)
        prefix = re.escape(self.h.prefix)
        count = 0
        for attr_name in dir(mod):
            if not attr_name.endswith("_handler"):
                continue
            fn = getattr(mod, attr_name)
            if not asyncio.iscoroutinefunction(fn):
                continue
            cmd = attr_name[: -len("_handler")]
            if not cmd:
                continue

            async def wrapper(msg: Any, _fn=fn) -> None:
                # владелец юзера — хозяин команд; чужие входящие не трогаем,
                # если модуль не подписан на incoming сам по себе
                await _fn(msg)

            unsub = self.h.transport.subscribe(
                wrapper,
                pattern=rf"(?i)^{prefix}{re.escape(cmd)}(?:\s|$)",
                outgoing=True,
                incoming=False,
            )
            self._unsubs.append(unsub)
            count += 1
        if count == 0:
            raise ValueError(f"{name}: не нашлось ни одного <cmd>_handler")
        logger.info("core-style %s: %d команд", name, count)
        return mod, None
