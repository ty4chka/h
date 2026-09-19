"""L2 — адаптер MCUB (hairpin01/MCUB-fork).

Поддерживает три стиля:
  1. функциональный `def register(kernel)`;
  2. функциональный с `kernel.register.command(...)` (KernelRegister);
  3. class-style `from core.lib.loader.module_base import ModuleBase, command...`
     с декораторами и хелперами — через shim legacy_hydra.

McubKernelInterface повторяет поверхность kernel.md из MCUB-fork:
реестры, custom_prefix, config, handle_error, inline_form,
inline_query_and_click, Button, log_*, conversation и т.д.
"""

from __future__ import annotations

import logging
import re
import time
import types
from typing import Any, Callable, List, Optional, Tuple

from .base import ClientProxy, CompatAdapter
from .legacy_hydra import ButtonFactory, ModuleBase as McubModuleBase, install_legacy_imports
from ..api.module_base import ModuleBase
from ..api.permissions import ADMIN

logger = logging.getLogger("hydra_kernel.compat.mcub")


class ConversationShim:
    """conversation() как в MCUB: context manager + send_message/get_response."""

    def __init__(self, transport: Any, chat_id: int):
        self._t = transport
        self.chat_id = chat_id
        self._messages: List[Any] = []

    async def __aenter__(self) -> "ConversationShim":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def send_message(self, text: str, **kw: Any) -> Any:
        msg = await self._t.send(self.chat_id, text, **kw)
        self._messages.append(msg)
        return msg

    async def send(self, text: str, **kw: Any) -> Any:
        return await self.send_message(text, **kw)

    async def get_response(self, timeout: float = 30) -> Any:  # pragma: no cover
        raise NotImplementedError("conversation.get_response требует живой транспорт")


class KernelRegister:
    """kernel.register.command(...) / .watcher(...) — функциональный стиль."""

    def __init__(self, iface: "McubKernelInterface"):
        self._iface = iface

    def command(self, name: str, *args: Any, **kw: Any) -> Callable:
        alias = kw.get("alias")
        aliases = list(alias) if isinstance(alias, (list, tuple)) else ([alias] if alias else None)

        def deco(fn: Callable) -> Callable:
            self._iface.register_command(name, fn, aliases)
            return fn

        return deco

    def on_load(self, *args: Any, **kw: Any) -> Callable:
        """Декоратор из MCUB: выполняем сразу — модуль и так ставится."""

        def deco(fn: Callable) -> Callable:
            return fn

        if args and callable(args[0]):
            return args[0]
        return deco

    def uninstall(self, *args: Any, **kw: Any) -> Callable:
        return self.on_unload(*args, **kw)

    def on_unload(self, *args: Any, **kw: Any) -> Callable:
        def deco(fn: Callable) -> Callable:
            return fn

        if args and callable(args[0]):
            return args[0]
        return deco

    def watcher(self, *args: Any, **kw: Any) -> Callable:
        def deco(fn: Callable) -> Callable:
            self._iface.register_watcher(fn)
            return fn

        return deco

    def loop(self, interval: int = 60, autostart: bool = True, wait_before: bool = False) -> Callable:
        """register.loop из MCUB: фоновая периодическая задача."""
        import asyncio

        def deco(fn: Callable) -> Callable:
            async def runner() -> None:
                while True:
                    if not wait_before:
                        try:
                            await fn()
                        except Exception as e:  # noqa: BLE001
                            logger.error("loop %s failed: %s", getattr(fn, "__name__", "?"), e)
                    await asyncio.sleep(interval)
                    if wait_before:
                        try:
                            await fn()
                        except Exception as e:  # noqa: BLE001
                            logger.error("loop %s failed: %s", getattr(fn, "__name__", "?"), e)

            if autostart:
                try:
                    task = asyncio.get_running_loop().create_task(runner())
                    self._iface._unsubs.append(task.cancel)
                except RuntimeError:
                    pass
            return fn

        return deco


class McubKernelInterface:
    """То, что MCUB-модуль видит как `kernel` (по kernel.md MCUB-fork)."""

    VERSION = "0.1.0-hydra"

    def __init__(self, hydra: Any):
        self.h = hydra
        self.client = ClientProxy(hydra.transport)
        self.parent_module = None
        self.custom_prefix = hydra.prefix
        self.config = hydra.config
        self.logger = logging.getLogger("mcub_kernel")
        self.start_time = time.time()
        self.bot_client = None
        self.inline_bot = None
        self.scheduler = None
        self.MODULES_DIR = "modules"
        self.MODULES_LOADED_DIR = "modules_loaded"
        self.register = KernelRegister(self)
        # kernel-уровневая фабрика кнопок (без привязки к модулю)
        self.Button = ButtonFactory(types.SimpleNamespace(name="kernel", ctx=None))
        self._unsubs: List[Callable[[], None]] = []

    # -- реестры (прокси в ядро) --
    @property
    def loaded_modules(self) -> dict:
        return {n: r.module for n, r in self._records().items()}

    @property
    def system_modules(self) -> dict:
        return {}

    @property
    def command_handlers(self) -> dict:
        return self.h.command_handlers

    @property
    def inline_handlers(self) -> dict:
        return self.h.inline_handlers

    @property
    def callback_handlers(self) -> dict:
        return self.h.callback_handlers

    @property
    def aliases(self) -> dict:
        return self.h.aliases

    def _records(self) -> dict:
        return getattr(self.h.registry, "_records", {})

    # -- команды / обработчики --
    def register_command(self, name: str, handler: Callable, aliases: Optional[List[str]] = None) -> None:
        prefix = self.h.prefix
        for cmd in [name, *(aliases or [])]:
            pattern = rf"(?i)^{re.escape(prefix)}{re.escape(cmd)}(?:\s|$)"

            async def wrapper(event: Any, _h=handler) -> None:
                try:
                    await _h(event)
                except Exception as e:  # noqa: BLE001
                    logger.error("mcub command %s failed: %s", cmd, e)
                    await self.handle_error(e, event=event)

            self._unsubs.append(
                self.h.transport.subscribe(wrapper, pattern=pattern, incoming=True, outgoing=True)
            )
        self.h.command_handlers.setdefault(name, handler)

    def register_watcher(self, handler: Callable, **kw: Any) -> None:
        async def wrapper(event: Any) -> None:
            try:
                await handler(event)
            except Exception as e:  # noqa: BLE001
                logger.error("mcub watcher failed: %s", e)

        self._unsubs.append(self.h.transport.subscribe(wrapper, **kw))

    def register_inline_handler(self, name: str, handler: Callable) -> None:
        self.h.register_inline(name, handler)

    def register_callback_handler(self, prefix: str, handler: Callable) -> None:
        self.h.register_callback(prefix, handler)

    # -- inline инструменты (как в MCUB-fork) --
    async def inline_query_and_click(self, chat_id: int, query: str, *args: Any, **kw: Any) -> Tuple[bool, Optional[str]]:
        return await self.h._on_inline(query, chat_id, None), None

    def _normalize_buttons(self, buttons: Any) -> Any:
        """telethon KeyboardInlineButton (data=uuid-токен) -> dict-кнопки ядра."""
        if not buttons:
            return buttons
        rows = []
        n = 0
        for row in buttons:
            if not isinstance(row, (list, tuple)):
                row = [row]
            out = []
            for btn in row:
                if isinstance(btn, dict):
                    out.append(btn)
                    continue
                data = getattr(btn, "data", None)
                if data is None:
                    data = getattr(getattr(btn, "type", None), "data", None)
                text = getattr(btn, "text", str(btn))
                if isinstance(data, bytes):
                    src_tok = data.decode()
                    n += 1
                    token = f"mcub_cb{n}:{src_tok}"

                    async def _cb(call, _tok=src_tok):
                        entry = getattr(self, "inline_callback_map", {}).get(_tok)
                        if not entry:
                            return
                        kwargs = dict(entry.get("kwargs", {}))
                        if entry.get("data") is not None and "data" not in kwargs:
                            import inspect

                            try:
                                target = getattr(
                                    entry["handler"], "__original__", entry["handler"]
                                )
                                sig = inspect.signature(target)
                                if "data" in sig.parameters:
                                    kwargs["data"] = entry["data"]
                            except (TypeError, ValueError):
                                pass
                        await entry["handler"](
                            call, *entry.get("args", []), **kwargs
                        )

                    self.h.register_callback(token, _cb)
                    out.append({"text": text, "data": token})
                else:
                    out.append({"text": text})
            rows.append(out)
        return rows

    async def inline_form(self, chat_id: int, text: str, buttons: Any = None, **kw: Any) -> Tuple[bool, Optional[str]]:
        try:
            await self.h.transport.send(
                int(chat_id), text, buttons=self._normalize_buttons(buttons)
            )
            return True, None
        except Exception as e:  # noqa: BLE001
            return False, str(e)

    # -- db / config --
    async def db_get(self, ns: str, key: str) -> Any:
        return await self.h.db.get(ns, key)

    async def db_set(self, ns: str, key: str, value: Any) -> None:
        await self.h.db.set(ns, key, value)

    async def get_module_config(self, module: str, default: Any = None) -> Any:
        return await self.h.db.get("config", module, default if default is not None else {})

    async def save_module_config(self, module: str, cfg: Any) -> None:
        await self.h.db.set("config", module, cfg)

    def store_module_config_schema(self, name: str, config: Any) -> None:
        return None

    def save_config(self) -> None:
        self.h.save_config()

    # -- разное --
    def is_admin(self, user_id: int) -> bool:
        return self.h.permissions.check(user_id, ADMIN)

    def is_bot_available(self) -> bool:
        return False

    async def conversation(self, chat_id: int, *args: Any, **kw: Any) -> ConversationShim:
        return ConversationShim(self.h.transport, int(chat_id))

    async def handle_error(self, exc: Exception, *args: Any, **kw: Any) -> None:
        message = kw.get("message") or kw.get("source") or "Module error"
        event = kw.get("event")
        self.logger.error("%s: %s", message, exc)
        if event is not None and hasattr(event, "reply"):
            try:
                await event.reply(f"<b>Error:</b> <code>{str(exc)[:200]}</code>")
            except Exception:  # noqa: BLE001
                pass

    async def get_thread_id(self, event: Any) -> Optional[int]:
        return getattr(event, "reply_to_msg_id", None)

    async def get_user_info(self, user_id: int) -> str:
        return f"user#{user_id}"

    def cprint(self, *args: Any, **kw: Any) -> None:
        print(*args, **kw)

    def log_error(self, *args: Any, **kw: Any) -> None:
        self.logger.error(*args, **kw)

    def log_warning(self, *args: Any, **kw: Any) -> None:
        self.logger.warning(*args, **kw)

    def log_info(self, *args: Any, **kw: Any) -> None:
        self.logger.info(*args, **kw)

    def log_debug(self, *args: Any, **kw: Any) -> None:
        self.logger.debug(*args, **kw)

    async def install_from_url(self, url: str) -> Tuple[bool, str]:
        return False, "Используйте загрузчик Hydra для установки модулей"


class McubAdapter(CompatAdapter):
    framework = "mcub"

    def install(self) -> None:
        install_legacy_imports()
        self._install_utils_strings()
        self._install_telethon_shim()

    def _install_utils_strings(self) -> None:
        """utils.strings как в MCUB: Strings, get_available_locales, reload_packs."""
        import sys

        from ..api.lang import Strings, get_available_locales, reload_packs

        if "utils.strings" in sys.modules:
            return
        # не топчем настоящий пакет utils: shim только если его нет
        import importlib

        try:
            utils_mod = importlib.import_module("utils")
        except ImportError:
            utils_mod = self._put_module("utils")
        strings_mod = self._put_module("utils.strings")
        for key, value in {
            "Strings": Strings,
            "get_available_locales": get_available_locales,
            "reload_packs": reload_packs,
        }.items():
            setattr(strings_mod, key, value)
        utils_mod.strings = strings_mod

        # поверхность самого utils, которую ждут настоящие MCUB-модули
        if not hasattr(utils_mod, "Strings"):
            utils_mod.Strings = Strings

        if not hasattr(utils_mod, "answer"):
            async def _answer(event: Any, text: str, **kw: Any) -> Any:
                if hasattr(event, "answer"):
                    try:
                        return await event.answer(text, **kw)
                    except Exception:  # noqa: BLE001
                        pass
                if hasattr(event, "edit") and getattr(event, "outgoing", False):
                    return await event.edit(text, **kw)
                if hasattr(event, "reply"):
                    return await event.reply(text, **kw)
                return None

            utils_mod.answer = _answer

        if not hasattr(utils_mod, "restart_kernel"):
            def _restart_kernel() -> None:
                import os
                import sys

                os.execv(sys.executable, [sys.executable, *sys.argv])

            utils_mod.restart_kernel = _restart_kernel

    def _install_telethon_shim(self) -> None:
        """Синтетический telethon (только если настоящего нет): events-плейсхолдеры."""
        import sys

        if "telethon" in sys.modules:
            return
        tel = self._put_module("telethon")
        events = types.SimpleNamespace(
            NewMessage=types.SimpleNamespace(Event=object),
            CallbackQuery=types.SimpleNamespace(Event=object),
            ChatAction=types.SimpleNamespace(Event=object),
        )

        class _Button:
            @staticmethod
            def inline(text: str, data: Any = None, **kw: Any) -> dict:
                return {"text": text, "data": data}

            @staticmethod
            def url(text: str, url: str) -> dict:
                return {"text": text, "url": url}

        tel.events = events
        tel.Button = _Button

    async def load_source(self, name: str, source: str) -> Tuple[Any, Any]:
        iface = McubKernelInterface(self.h)
        ns = self.exec_source(name, source)

        if callable(ns.get("register")):
            res = ns["register"](iface)
            if res is not None and hasattr(res, "__await__"):
                await res
            return iface, None

        # class-style: shim-ModuleBase ИЛИ подкласс настоящего core ModuleBase
        cls = None
        for value in ns.values():
            if (
                isinstance(value, type)
                and value is not ModuleBase
                and value is not McubModuleBase
                and getattr(value, "__module__", "") == name
                and (
                    issubclass(value, ModuleBase)
                    or hasattr(value, "_cmd_registry")  # настоящий core-style
                )
            ):
                cls = value
                break
        if cls is not None:
            if hasattr(cls, "_cmd_registry") and not issubclass(cls, ModuleBase):
                # настоящий core ModuleBase: __init__(kernel=iface) сам
                # регистрирует команды/owner_only/permissions через iface.register
                module = cls(kernel=iface)
                lifecycle = await self.h.load_module(module)
                return module, lifecycle
            module = cls(self.h.make_context(name))
            lifecycle = await self.h.load_module(module)
            return module, lifecycle

        raise ValueError(f"mcub:{name}: нет ни register(), ни класса ModuleBase")
