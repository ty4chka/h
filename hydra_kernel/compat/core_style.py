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


# Setup-style modules register raw Telethon handlers themselves, whereas core
# and Hydra modules expose their command metadata to the kernel directly.  Keep
# a lightweight shared catalogue so built-in discovery commands can describe
# *all* active commands without spinning up a second dispatcher.
_COMMAND_FROM_PATTERN = re.compile(r"\\\.([A-Za-z0-9_]+)")


def _command_from_builder(builder: Any) -> str | None:
    """Extract a simple ``.command`` name from a NewMessage builder.

    Native setup modules in this repository deliberately use exact patterns
    such as ``(?i)^\\.cfg(?:\\s|$)``.  Do not attempt to interpret arbitrary
    Telethon regexes: if a handler does not have this unambiguous shape it is
    simply absent from the presentation catalogue, never from dispatch.
    """

    pattern = getattr(builder, "pattern", None)
    if hasattr(pattern, "pattern"):
        pattern = pattern.pattern
    if not isinstance(pattern, str):
        kwargs = getattr(builder, "kwargs", None)
        if isinstance(kwargs, dict):
            pattern = kwargs.get("pattern")
    if not isinstance(pattern, str):
        return None
    match = _COMMAND_FROM_PATTERN.search(pattern)
    return match.group(1).lower() if match else None


class _CleanupLifecycle:
    """Small per-record lifecycle for native setup/core subscriptions."""

    def __init__(self, cleanups: list[Any]) -> None:
        self._cleanups = cleanups

    async def unload(self, _module: Any) -> None:
        for cleanup in reversed(self._cleanups):
            try:
                result = cleanup()
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:  # noqa: BLE001 - keep unloading remaining handlers
                logger.debug("native handler cleanup failed: %s", exc)
        self._cleanups.clear()


class _SetupClientCatalogProxy:
    """Pass-through Telethon client with per-module registration cleanup."""

    def __init__(self, client: Any, hydra: Any) -> None:
        self._client = client
        self._hydra = hydra
        self._registrations: list[tuple[Any, Any]] = []
        self._catalog_cleanups: list[Any] = []

    def _record(self, callback: Any, builder: Any) -> None:
        command = _command_from_builder(builder)
        if not command or command in self._hydra.command_handlers:
            return
        self._hydra.command_handlers[command] = callback

        def cleanup() -> None:
            if self._hydra.command_handlers.get(command) is callback:
                self._hydra.command_handlers.pop(command, None)

        self._catalog_cleanups.append(cleanup)

    def add_event_handler(self, callback: Any, builder: Any = None) -> Any:
        result = self._client.add_event_handler(callback, builder)
        self._registrations.append((callback, builder))
        self._record(callback, builder)
        return result

    def on(self, builder: Any) -> Any:
        native_on = getattr(self._client, "on", None)
        if not callable(native_on):
            raise AttributeError("client has no on()")
        native_decorator = native_on(builder)

        def decorator(callback: Any) -> Any:
            result = native_decorator(callback)
            self._registrations.append((callback, builder))
            self._record(callback, builder)
            return result

        return decorator

    def cleanup(self) -> None:
        remove = getattr(self._client, "remove_event_handler", None)
        if callable(remove):
            for callback, builder in reversed(self._registrations):
                try:
                    remove(callback, builder)
                except Exception as exc:  # noqa: BLE001 - foreign client cleanup is best effort
                    logger.debug("setup handler cleanup failed: %s", exc)
        self._registrations.clear()
        for cleanup in reversed(self._catalog_cleanups):
            cleanup()
        self._catalog_cleanups.clear()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


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
        # Native handlers still receive the underlying Telegram client through
        # event.client.  This marker lets management code deliberately use the
        # already-running unified engine instead of creating a legacy one.
        try:
            setattr(client, "_hydra_kernel", self.h)
        except Exception:  # pragma: no cover - foreign client may be sealed
            pass
        setup_client = _SetupClientCatalogProxy(client, self.h)
        try:
            result = setup(setup_client)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            setup_client.cleanup()
            raise
        return mod, _CleanupLifecycle([setup_client.cleanup])


class CoreStyleAdapter:
    """Конвенция родного лоадера: async def <cmd>_handler(event) -> .<cmd>."""

    def __init__(self, hydra: Any):
        self.h = hydra

    def install(self) -> None:  # pragma: no cover - тривиально
        pass

    async def load_source(self, name: str, source: str) -> Tuple[Any, Any]:
        mod = _import_module(name)
        prefix = re.escape(self.h.prefix)
        count = 0
        cleanups: list[Any] = []
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
            cleanups.append(unsub)
            if cmd not in self.h.command_handlers:
                self.h.command_handlers[cmd] = wrapper

                def cleanup_catalog(_cmd=cmd, _wrapper=wrapper) -> None:
                    if self.h.command_handlers.get(_cmd) is _wrapper:
                        self.h.command_handlers.pop(_cmd, None)

                cleanups.append(cleanup_catalog)
            count += 1
        if count == 0:
            for cleanup in reversed(cleanups):
                cleanup()
            raise ValueError(f"{name}: не нашлось ни одного <cmd>_handler")
        logger.info("core-style %s: %d команд", name, count)
        return mod, _CleanupLifecycle(cleanups)
