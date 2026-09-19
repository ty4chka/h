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

import asyncio
import inspect
import logging
import re
import time
import types
import uuid
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from .base import ClientProxy, CompatAdapter
from .legacy_hydra import ButtonFactory, ModuleBase as McubModuleBase, install_legacy_imports
from ..api.module_base import ModuleBase
from ..api.permissions import ADMIN

logger = logging.getLogger("hydra_kernel.compat.mcub")


class Colors:
    """Безопасная ANSI-поверхность MCUB.

    В боевом терминале цвета не обязательны для логики модуля, а в
    NullTransport escape-последовательности только засоряют smoke-вывод.
    Поэтому значения — пустые строки, при этом API ``Colors.RED``/``wrap``
    остаётся совместимым.
    """

    BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = ""
    RESET = ""

    @classmethod
    def wrap(cls, _color: Any, text: Any) -> str:
        return str(text)


class TTLCache:
    """Небольшой синхронный cache как ``kernel.cache`` из MCUB-fork."""

    def __init__(self, default_ttl: Optional[float] = 300) -> None:
        self._items: dict[str, tuple[Any, Optional[float]]] = {}
        self._default_ttl = default_ttl

    def get(self, key: Any, default: Any = None) -> Any:
        item = self._items.get(str(key))
        if item is None:
            return default
        value, expires_at = item
        if expires_at is not None and expires_at <= time.monotonic():
            self._items.pop(str(key), None)
            return default
        return value

    def set(self, key: Any, value: Any, ttl: Optional[float] = None) -> None:
        lifetime = self._default_ttl if ttl is None else ttl
        expires_at = time.monotonic() + float(lifetime) if lifetime else None
        self._items[str(key)] = (value, expires_at)

    def delete(self, key: Any) -> None:
        self._items.pop(str(key), None)

    def clear(self) -> None:
        self._items.clear()


class CallbackPermissions:
    """Минимальный менеджер разрешений callback-кнопок MCUB."""

    def __init__(self) -> None:
        self._allowed: dict[int, dict[str, float]] = {}
        self._prohibited: set[int] = set()

    def allow(
        self,
        user_id: int,
        token: str = "",
        ttl: Optional[float] = None,
        duration_seconds: Optional[float] = None,
        **_kw: Any,
    ) -> None:
        duration = duration_seconds if duration_seconds is not None else (ttl if ttl is not None else 100)
        uid = int(user_id)
        self._prohibited.discard(uid)
        self._allowed.setdefault(uid, {})[str(token)] = time.monotonic() + float(duration)

    def prohibit(self, user_id: int) -> None:
        uid = int(user_id)
        self._prohibited.add(uid)
        self._allowed.pop(uid, None)

    def is_allowed(self, user_id: int, token: str = "") -> bool:
        uid = int(user_id)
        if uid in self._prohibited:
            return False
        expires_at = self._allowed.get(uid, {}).get(str(token))
        return bool(expires_at and expires_at > time.monotonic())


class VersionManager:
    """Офлайн-реализация API version_manager, нужная info/log-модулям."""

    def __init__(self, hydra: Any) -> None:
        self._hydra = hydra

    async def detect_branch(self) -> str:
        return "hydra"

    async def get_commit_sha(self) -> str:
        return "offline"

    async def get_github_commit_url(self) -> str:
        return ""


class LoopHandle:
    """Управляемая задача, которую MCUB-модули могут вызвать через ``.start()``."""

    def __init__(self, runner: Callable[[], Any], autostart: bool) -> None:
        self._runner = runner
        self._task: Optional[asyncio.Task[Any]] = None
        if autostart:
            self.start()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> "LoopHandle":
        if not self.is_running:
            self._task = asyncio.get_running_loop().create_task(self._runner())
        return self

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
        self._task = None

    def restart(self) -> "LoopHandle":
        self.stop()
        return self.start()


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


class _McubLoaderView:
    """Маленькая совместимая поверхность ``kernel._loader`` для MCUB.

    Настоящий MCUB ``man`` использует её для списка команд и метаданных.
    Hydra хранит эти сведения иначе, поэтому адаптируем реестр, не запуская
    второй старый движок.
    """

    def __init__(self, kernel: "McubKernelInterface") -> None:
        self.kernel = kernel

    def _names_for(self, module_name: str) -> set[str]:
        names = {str(module_name)}
        module = self.kernel.lookup_module(module_name)
        if module is None:
            return names
        names.add(str(getattr(module, "name", "")))
        names.add(str(getattr(type(module), "__module__", "")))
        for name, instance in self.kernel._class_module_instances.items():
            if instance is module:
                names.add(str(name))
        names.discard("")
        return names

    @staticmethod
    def pick_localized_text(value: Any, lang: str = "ru", fallback: str = "") -> str:
        if isinstance(value, dict):
            return str(value.get(lang) or value.get("ru") or value.get("en") or fallback)
        if isinstance(value, str) and value.strip():
            return value
        return fallback

    def get_module_path(self, module_name: str) -> Optional[str]:
        """Найти owned source по имени без предположения о cwd пользователя."""

        here = Path(__file__).resolve().parents[2]
        candidates = self._names_for(module_name)
        for root in (here / "modules" / "mcub_mods", here / "modules", here / "extras" / "mcub_pack"):
            for name in candidates:
                source = root / f"{name}.py"
                if source.is_file():
                    return str(source)
        return None

    def get_module_commands(self, module_name: str, lang: str = "ru") -> tuple[list[str], dict, dict]:
        names = self._names_for(module_name)
        commands = [
            command
            for command, owner in self.kernel.command_owners.items()
            if str(owner) in names
        ]
        aliases_info: dict[str, list[str]] = {}
        for alias, command in self.kernel.aliases.items():
            if command in commands:
                aliases_info.setdefault(command, []).append(alias)

        descriptions: dict[str, str] = {}
        for command in commands:
            handler = self.kernel.h.command_handlers.get(command)
            original = getattr(handler, "__original__", handler)
            for pattern, meta in getattr(original, "_mcub_commands", ()):
                if str(pattern) != command:
                    continue
                doc = meta.get("doc") if isinstance(meta, dict) else None
                descriptions[command] = self.pick_localized_text(
                    doc,
                    lang,
                    (meta.get(f"doc_{lang}") or meta.get("doc_ru") or meta.get("doc_en") or "")
                    if isinstance(meta, dict)
                    else "",
                )
                break
            else:
                descriptions[command] = ""
        return commands, aliases_info, descriptions


class KernelRegister:
    """``kernel.register``: декораторы и служебные вызовы MCUB-fork."""

    def __init__(self, iface: "McubKernelInterface"):
        self._iface = iface

    def command(self, name: str, *args: Any, **kw: Any) -> Callable:
        alias = kw.get("alias")
        aliases = list(alias) if isinstance(alias, (list, tuple)) else ([alias] if alias else None)

        def deco(fn: Callable) -> Callable:
            self._iface.register_command(name, fn, aliases)
            return fn

        return deco

    def bot_command(self, name: str, *args: Any, **kw: Any) -> Callable:
        def deco(fn: Callable) -> Callable:
            self._iface.h.bot_commands[name] = fn
            return fn

        return deco

    def on_load(self, *args: Any, **kw: Any) -> Callable:
        """Декоратор остаётся маркером: lifecycle уже вызывает ``on_load``."""

        def deco(fn: Callable) -> Callable:
            return fn

        return args[0] if args and callable(args[0]) else deco

    def uninstall(self, *args: Any, **kw: Any) -> Callable:
        return self.on_unload(*args, **kw)

    def on_unload(self, *args: Any, **kw: Any) -> Callable:
        def deco(fn: Callable) -> Callable:
            return fn

        return args[0] if args and callable(args[0]) else deco

    def watcher(self, func: Optional[Callable] = None, *args: Any, **kw: Any) -> Callable:
        # Настоящий ModuleBase вызывает register.watcher(bound_wrapper, ...),
        # а функциональные модули используют @kernel.register.watcher(...).
        def deco(fn: Callable) -> Callable:
            options = {k: v for k, v in kw.items() if k in {"pattern", "incoming", "outgoing", "chats"}}
            self._iface.register_watcher(fn, **options)
            return fn

        return deco(func) if callable(func) else deco

    def event(self, _event_type: str, *args: Any, **kw: Any) -> Callable:
        """L0 содержит NewMessage-модель; остальные MCUB events — watcher."""

        return self.watcher(
            None,
            pattern=kw.get("pattern"),
            incoming=kw.get("incoming", True),
            outgoing=kw.get("outgoing", False),
            chats=kw.get("chats"),
        )

    async def _call_loop(self, fn: Callable) -> None:
        """В MCUB циклы получают kernel, в старых модулях аргументов нет."""

        try:
            signature = inspect.signature(fn)
            positional = [
                p
                for p in signature.parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                and p.default is p.empty
            ]
            accepts_varargs = any(p.kind is p.VAR_POSITIONAL for p in signature.parameters.values())
            result = fn(self._iface) if positional or accepts_varargs else fn()
        except (TypeError, ValueError):
            result = fn(self._iface)
        if inspect.isawaitable(result):
            await result

    def loop(self, interval: int = 60, autostart: bool = True, wait_before: bool = False) -> Callable:
        """register.loop с ``LoopHandle.start/stop`` и правильным kernel-аргументом."""

        def deco(fn: Callable) -> LoopHandle:
            async def runner() -> None:
                while True:
                    if not wait_before:
                        try:
                            await self._call_loop(fn)
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:  # noqa: BLE001
                            logger.error("loop %s failed: %s", getattr(fn, "__name__", "?"), exc)
                    await asyncio.sleep(max(float(interval), 0.01))
                    if wait_before:
                        try:
                            await self._call_loop(fn)
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:  # noqa: BLE001
                            logger.error("loop %s failed: %s", getattr(fn, "__name__", "?"), exc)

            handle = LoopHandle(runner, autostart)
            self._iface._unsubs.append(handle.stop)
            return handle

        return deco

    def inline_temp(
        self,
        func: Callable,
        ttl: int = 300,
        article: Any = None,
        data: Any = None,
        allow_user: Any = None,
        allow_ttl: int = 100,
        **_kw: Any,
    ) -> str:
        token = uuid.uuid4().hex
        self._iface.inline_callback_map[token] = {
            "handler": func,
            "args": [],
            "kwargs": {},
            "data": data,
            "article": article,
            "allow_user": allow_user,
            "expires_at": time.monotonic() + ttl if ttl else None,
            "allow_ttl": allow_ttl,
        }
        return token

    async def invoke(self, command: str, args: Any = None, chat_id: Any = None, **_kw: Any) -> Any:
        text = f"{self._iface.custom_prefix}{str(command).lstrip(self._iface.custom_prefix)}"
        if args:
            text += f" {args}"
        target = int(chat_id) if chat_id is not None else self._iface.h.transport.me_id
        return await self._iface.h.transport.inject(
            target,
            text,
            sender_id=self._iface.h.transport.me_id,
            outgoing=True,
        )


class McubKernelInterface:
    """То, что MCUB-модуль видит как `kernel` (по kernel.md MCUB-fork)."""

    VERSION = "0.1.0-hydra"

    def __init__(self, hydra: Any):
        self.h = hydra
        # Настоящий core.ModuleBase хранит callback map на ``kernel._kernel``.
        # У адаптера сам интерфейс и есть этот kernel.
        self._kernel = self
        self.client = ClientProxy(hydra.transport)
        # Явный capability marker для модулей с Telegram-only startup work
        # (создание чата, запросы к bot API и т.п.). Lifecycle всё ещё
        # вызывается в NullTransport, но такие side effects можно честно no-op.
        self.is_offline = self.client.is_offline
        self.db_manager = hydra.db
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
        self.load_kernel = "full"
        self.Colors = Colors
        self.cache = TTLCache()
        self.version_manager = VersionManager(hydra)
        self.callback_permissions = CallbackPermissions()
        self.inline_callback_map: dict[str, dict[str, Any]] = {}
        self._class_module_instances: dict[str, Any] = {}
        self._live_module_configs: dict[str, Any] = {}
        self._module_config_schemas: dict[str, Any] = {}
        self._user_emoji: dict[Any, Any] = {}
        self.command_owners: dict[str, str] = {}
        self._inline_owners: dict[str, str] = {}
        self._loader = _McubLoaderView(self)
        self.log_chat_id = self.config.get("log_chat_id")
        self.register = KernelRegister(self)
        # kernel-уровневая фабрика кнопок (без привязки к модулю)
        self.Button = ButtonFactory(types.SimpleNamespace(name="kernel", ctx=None))
        self._unsubs: List[Callable[[], None]] = []

    @property
    def USER_EMOJI(self) -> dict[Any, Any]:
        """Совместимость с модулями, которые берут эмодзи из config.py."""

        return self._user_emoji

    def set_module_exports(self, name: str, namespace: dict[str, Any]) -> None:
        """Сохранить безопасные module-level константы функционального модуля."""

        if name == "config" and isinstance(namespace.get("USER_EMOJI"), dict):
            self._user_emoji = dict(namespace["USER_EMOJI"])

    # -- реестры (прокси в ядро) --
    @property
    def loaded_modules(self) -> dict:
        # Класс попадает сюда ещё до registry.register(), поэтому on_load одного
        # MCUB-модуля может require_module() другой модуль той же волны.
        records = {n: r.module for n, r in self._records().items()}
        return {**records, **self._class_module_instances}

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

    def get_module_inline_commands(self, module_name: str) -> list[tuple[str, None]]:
        names = self._loader._names_for(module_name)
        return [
            (name, None)
            for name, owner in self._inline_owners.items()
            if str(owner) in names
        ]

    async def get_module_metadata(self, code: str) -> dict:
        """Best-effort metadata extractor expected by MCUB's man module."""

        metadata: dict[str, Any] = {}
        version = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', code)
        if version:
            metadata["version"] = version.group(1).strip()
        author = re.search(r"#\s*meta\s+developer\s*:\s*(.+)", code, re.IGNORECASE)
        if author:
            metadata["author"] = author.group(1).strip()
        name = re.search(r"#\s*meta\s+name\s*:\s*(.+)", code, re.IGNORECASE)
        if name:
            metadata["name"] = name.group(1).strip()
        description = re.search(r'"""(.*?)"""', code, re.DOTALL)
        if description and description.group(1).strip():
            metadata["description"] = description.group(1).strip()[:200]
        return metadata

    # -- команды / обработчики --
    def register_command(self, name: str, handler: Callable, aliases: Optional[List[str]] = None) -> None:
        prefix = self.h.prefix
        owner = getattr(getattr(handler, "__bound_instance__", None), "name", None)
        owner = owner or getattr(getattr(handler, "__self__", None), "name", None)
        original = getattr(handler, "__original__", handler)
        owner = owner or getattr(original, "__module__", None) or "mcub"
        for cmd in [name, *(aliases or [])]:
            command_name = str(cmd)
            pattern = rf"(?i)^{re.escape(prefix)}{re.escape(command_name)}(?:\s|$)"

            async def wrapper(event: Any, _h=handler, _cmd=command_name) -> None:
                try:
                    result = _h(event)
                    if inspect.isawaitable(result):
                        await result
                except Exception as exc:  # noqa: BLE001
                    logger.error("mcub command %s failed: %s", _cmd, exc)
                    await self.handle_error(exc, event=event)

            self._unsubs.append(
                self.h.transport.subscribe(wrapper, pattern=pattern, incoming=True, outgoing=True)
            )
            self.command_owners[command_name] = str(owner)
            if command_name != name:
                self.h.aliases[command_name] = name
        self.h.command_handlers.setdefault(name, handler)

    def register_watcher(self, handler: Callable, **kw: Any) -> None:
        async def wrapper(event: Any) -> None:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                logger.error("mcub watcher failed: %s", exc)

        options = {k: v for k, v in kw.items() if k in {"pattern", "incoming", "outgoing", "chats"}}
        self._unsubs.append(self.h.transport.subscribe(wrapper, **options))

    def register_inline_handler(self, name: str, handler: Callable) -> None:
        original = getattr(handler, "__original__", handler)
        self._inline_owners[name] = str(getattr(original, "__module__", "mcub"))
        self.h.register_inline(name, handler)

    def register_callback_handler(self, prefix: str | bytes, handler: Callable) -> None:
        normalized = prefix.decode(errors="replace") if isinstance(prefix, bytes) else str(prefix)
        self.h.register_callback(normalized, handler)

    # -- inline инструменты (как в MCUB-fork) --
    async def inline_query_and_click(self, chat_id: int, query: str, *args: Any, **kw: Any) -> Tuple[bool, Any]:
        """Локально выполнить inline handler и отрисовать его первый результат.

        У обычного userbot-клиента нет своего CallbackQuery на команду ``.man``.
        Старый MCUB использует inline-bot, а Hydra обеспечивает эквивалентную
        текстовую форму с теми же callback-кнопками.
        """

        from ..api.inline import InlineQueryEvent

        text = str(query or "").strip()
        name = text.split(maxsplit=1)[0] if text else ""
        handler = self.h.inline_handlers.get(name)
        if handler is None:
            return False, f"Inline handler '{name}' не найден"

        event = InlineQueryEvent(
            name=name,
            query=text,
            sender_id=self.h.transport.me_id,
            transport=None,
            raw=None,
        )
        try:
            await handler(event)
        except Exception as exc:  # noqa: BLE001 - API возвращает ошибку вызывающему модулю
            return False, str(exc)
        if not event.results:
            return False, f"Inline handler '{name}' не вернул результатов"

        result = event.results[0]
        body = getattr(result, "text", None) or getattr(result, "body", None) or ""
        if not body:
            return False, f"Inline handler '{name}' вернул пустой результат"
        send_kw: dict[str, Any] = {
            "buttons": self._normalize_buttons(getattr(result, "buttons", None)),
            "parse_mode": getattr(result, "parse_mode", "html"),
        }
        if kw.get("reply_to") is not None:
            send_kw["reply_to"] = kw["reply_to"]
        sent = await self.h.transport.send(int(chat_id), str(body), **send_kw)
        return True, sent

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

    async def inline_form(
        self,
        chat_id: int,
        text: Optional[str] = None,
        buttons: Any = None,
        *,
        title: Optional[str] = None,
        fields: Optional[dict[str, Any]] = None,
        **kw: Any,
    ) -> Tuple[bool, Optional[str]]:
        """Отправить MCUB form; ``title/fields`` — вариант настоящего ModuleBase."""

        body = title if title is not None else (text or "")
        if fields:
            body += "".join(f"\n{k}: {v}" for k, v in fields.items())
        try:
            await self.h.transport.send(
                int(chat_id), body, buttons=self._normalize_buttons(buttons)
            )
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    # -- db / config --
    async def db_get(self, ns: str, key: str) -> Any:
        return await self.h.db.get(ns, key)

    async def db_set(self, ns: str, key: str, value: Any) -> None:
        await self.h.db.set(ns, key, value)

    async def get_module_config(self, module: str, default: Any = None) -> Any:
        return await self.h.db.get("config", module, default if default is not None else {})

    async def save_module_config(self, module: str, cfg: Any) -> None:
        await self.h.db.set("config", module, cfg)
        live = self._live_module_configs.get(module)
        if live is None and cfg is not None:
            self._live_module_configs[module] = cfg

    def store_module_config_schema(self, name: str, config: Any) -> None:
        self._module_config_schemas[name] = config
        self._live_module_configs[name] = config

    def lookup_module(self, module_name: str) -> Any:
        needle = str(module_name).lower()
        for name, module in self.loaded_modules.items():
            if str(name).lower() == needle or str(getattr(module, "name", "")).lower() == needle:
                return module
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
        # Один interface на Hydra, как одно MCUB-ядро: иначе class-модули не
        # видят друг друга через require_module()/loaded_modules.
        self.iface = McubKernelInterface(self.h)
        from .offline_deps import ensure_offline_dependencies

        ensure_offline_dependencies()
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
        """Обеспечить полноценный offline Telethon shim, не затирая реальный."""

        from .offline_deps import ensure_offline_dependencies

        ensure_offline_dependencies()

    async def load_source(self, name: str, source: str) -> Tuple[Any, Any]:
        iface = self.iface
        ns = self.exec_source(name, source)
        iface.set_module_exports(name, ns)

        if callable(ns.get("register")):
            res = ns["register"](iface)
            if inspect.isawaitable(res):
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
                # Настоящий core ModuleBase сам регистрирует декораторы через
                # iface.register. Сохраняем объект *до* on_load, чтобы другой
                # модуль той же загрузочной волны мог его require_module().
                module = cls(kernel=iface)
                iface._class_module_instances[name] = module
                iface._class_module_instances.setdefault(getattr(module, "name", name), module)
                for method in getattr(module, "_method_funcs", ()):
                    result = method(module)
                    if inspect.isawaitable(result):
                        await result
                lifecycle = await self.h.load_module(module)
                return module, lifecycle
            module = cls(self.h.make_context(name))
            iface._class_module_instances[name] = module
            lifecycle = await self.h.load_module(module)
            return module, lifecycle

        raise ValueError(f"mcub:{name}: нет ни register(), ни класса ModuleBase")
