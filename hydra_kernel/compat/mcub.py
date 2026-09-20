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


class _MaterializedInlineMessage:
    """Local editable result of an MCUB inline form/query.

    Userbot accounts cannot receive native ``CallbackQuery`` updates for their
    own inline keyboards.  Hydra therefore materializes a form or first inline
    result as a normal message plus its ButtonBridge callbacks.  Some
    production MCUB modules (notably OpenAgent and Vector) immediately call
    ``sms.click(0)`` to turn that result into an editable status event;
    providing this tiny result object preserves that flow instead of making
    every command wait for a five-second timeout.
    """

    def __init__(self, iface: "McubKernelInterface", message: Any) -> None:
        self._iface = iface
        self._message = message
        self.chat_id = getattr(message, "chat_id", None)
        self.id = getattr(message, "id", getattr(message, "message_id", 0))
        self.message_id = self.id
        self.unit_id = str(self.id)
        self.form_id = self.unit_id

    @property
    def message(self) -> Any:
        return self._message

    @property
    def peer_id(self) -> Any:
        """Telethon message alias used by file/form-oriented MCUB modules."""

        return self.chat_id

    async def edit(self, text: str, buttons: Any = None, **kw: Any) -> "_MaterializedInlineMessage":
        if self.chat_id is None:
            return self
        if buttons is not None:
            kw["buttons"] = self._iface._normalize_buttons(buttons)
        edited = await self._iface.h.transport.edit(int(self.chat_id), int(self.message_id or 0), text, **kw)
        self._message = edited
        self.id = getattr(edited, "id", getattr(edited, "message_id", self.id))
        self.message_id = self.id
        return self

    async def delete(self) -> None:
        if self.chat_id is not None:
            await self._iface.h.transport.delete(int(self.chat_id), int(self.message_id or 0))

    async def click(self, index: Any = 0, *args: Any, **kw: Any) -> bool:
        """Programmatically press a materialized callback button.

        This mirrors the small ``InlineResult.click`` subset used by MCUB
        modules.  It routes through Hydra's normal callback dispatcher, so the
        callback receives a real :class:`CallbackQueryEvent` with an editable
        chat/message target.
        """

        rows = getattr(self._message, "buttons", None) or []
        flat = [button for row in rows for button in (row if isinstance(row, (list, tuple)) else [row])]
        if isinstance(index, (tuple, list)) and len(index) >= 2:
            try:
                button = rows[int(index[0])][int(index[1])]
            except (IndexError, TypeError, ValueError):
                return False
        else:
            try:
                button = flat[int(index)]
            except (IndexError, TypeError, ValueError):
                return False
        data = button.get("data") if isinstance(button, dict) else getattr(button, "data", None)
        if isinstance(data, bytes):
            data = data.decode(errors="replace")
        if not data or self.chat_id is None:
            return False
        return await self._iface.h._on_callback(
            str(data), self._iface.h.owner_id, int(self.chat_id), int(self.message_id or 0), None
        )


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


class _RegistrationScope:
    """Cleanup owned by one loaded MCUB source file.

    MCUB's historic kernel kept a single global list of subscriptions.  That
    made ``.mun`` unregister a record while its commands still answered.  A
    source-local scope lets the unified registry unload class-style and
    ``register(kernel)`` modules symmetrically.
    """

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name
        self._cleanups: list[Callable[[], Any]] = []
        self._closed = False

    def add(self, cleanup: Callable[[], Any]) -> None:
        if self._closed:
            result = cleanup()
            if inspect.isawaitable(result):
                result.close() if hasattr(result, "close") else None
            return
        self._cleanups.append(cleanup)

    async def unload(self, _module: Any = None) -> None:
        if self._closed:
            return
        self._closed = True
        for cleanup in reversed(self._cleanups):
            try:
                result = cleanup()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # noqa: BLE001 - one cleanup must not block the rest
                logger.debug("MCUB cleanup %s failed: %s", self.source_name, exc)
        self._cleanups.clear()


class _CompositeLifecycle:
    """Run normal ModuleBase hooks and adapter registrations on unload."""

    def __init__(self, primary: Any, scope: _RegistrationScope) -> None:
        self.primary = primary
        self.scope = scope

    async def unload(self, module: Any) -> None:
        if self.primary is not None:
            await self.primary.unload(module)
        await self.scope.unload(module)


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
            self._iface.register_bot_command(name, fn)
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
                        except Exception:  # noqa: BLE001
                            logger.exception("loop %s failed", getattr(fn, "__name__", "?"))
                    await asyncio.sleep(max(float(interval), 0.01))
                    if wait_before:
                        try:
                            await self._call_loop(fn)
                        except asyncio.CancelledError:
                            raise
                        except Exception:  # noqa: BLE001
                            logger.exception("loop %s failed", getattr(fn, "__name__", "?"))

            handle = LoopHandle(runner, autostart)
            self._iface._track_cleanup(handle.stop)
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

        def cleanup() -> None:
            self._iface.inline_callback_map.pop(token, None)

        self._iface._track_cleanup(cleanup)
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
        self._scope_stack: list[_RegistrationScope] = []
        self._loader = _McubLoaderView(self)
        self.log_chat_id = self.config.get("log_chat_id")
        self.register = KernelRegister(self)
        # kernel-уровневая фабрика кнопок (без привязки к модулю)
        self.Button = ButtonFactory(types.SimpleNamespace(name="kernel", ctx=None))
        # Backward-compatible fallback for registrations made outside a loader
        # call.  All normal sources use a per-module scope below.
        self._unsubs: List[Callable[[], None]] = []

    def begin_registration_scope(self, source_name: str) -> _RegistrationScope:
        scope = _RegistrationScope(source_name)
        self._scope_stack.append(scope)
        return scope

    def end_registration_scope(self, scope: _RegistrationScope) -> None:
        if self._scope_stack and self._scope_stack[-1] is scope:
            self._scope_stack.pop()
            return
        try:
            self._scope_stack.remove(scope)
        except ValueError:
            pass

    def _track_cleanup(self, cleanup: Callable[[], Any]) -> None:
        if self._scope_stack:
            self._scope_stack[-1].add(cleanup)
        else:
            self._unsubs.append(cleanup)

    def register_class_instance(self, key: str, module: Any) -> None:
        """Expose a class during its load and remove that temporary lookup on unload."""

        missing = object()
        previous = self._class_module_instances.get(key, missing)
        self._class_module_instances[key] = module

        def cleanup() -> None:
            if self._class_module_instances.get(key) is module:
                if previous is missing:
                    self._class_module_instances.pop(key, None)
                else:
                    self._class_module_instances[key] = previous

        self._track_cleanup(cleanup)

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
        missing = object()
        primary_previous = self.h.command_handlers.get(name, missing)
        primary_registered = False
        for cmd in [name, *(aliases or [])]:
            command_name = str(cmd)
            pattern = rf"(?i)^{re.escape(prefix)}{re.escape(command_name)}(?:\s|$)"

            async def wrapper(event: Any, _h=handler, _cmd=command_name) -> None:
                try:
                    result = _h(event)
                    if inspect.isawaitable(result):
                        await result
                except Exception as exc:  # noqa: BLE001
                    await self.handle_error(
                        exc, event=event, source=f"mcub command {_cmd} failed"
                    )

            unsubscribe = self.h.transport.subscribe(
                wrapper, pattern=pattern, incoming=True, outgoing=True
            )
            previous_owner = self.command_owners.get(command_name, missing)
            previous_alias = self.h.aliases.get(command_name, missing)
            self.command_owners[command_name] = str(owner)
            if command_name != name:
                self.h.aliases[command_name] = name

            def cleanup(
                _name=command_name,
                _unsubscribe=unsubscribe,
                _owner=owner,
                _previous_owner=previous_owner,
                _previous_alias=previous_alias,
                _is_alias=command_name != name,
            ) -> None:
                _unsubscribe()
                if self.command_owners.get(_name) == str(_owner):
                    if _previous_owner is missing:
                        self.command_owners.pop(_name, None)
                    else:
                        self.command_owners[_name] = _previous_owner
                if _is_alias and self.h.aliases.get(_name) == name:
                    if _previous_alias is missing:
                        self.h.aliases.pop(_name, None)
                    else:
                        self.h.aliases[_name] = _previous_alias

            self._track_cleanup(cleanup)
            primary_registered = primary_registered or command_name == name
        if primary_previous is missing:
            self.h.command_handlers[name] = handler

            def cleanup_primary() -> None:
                if self.h.command_handlers.get(name) is handler:
                    self.h.command_handlers.pop(name, None)

            if primary_registered:
                self._track_cleanup(cleanup_primary)

    def register_watcher(self, handler: Callable, **kw: Any) -> None:
        original = getattr(handler, "__original__", handler)
        instance = getattr(handler, "__bound_instance__", None) or getattr(handler, "__self__", None)
        owner = getattr(instance, "name", None) or getattr(original, "__module__", "mcub")
        handler_name = getattr(original, "__name__", getattr(handler, "__name__", "watcher"))

        async def wrapper(event: Any) -> None:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:  # noqa: BLE001
                logger.exception("mcub watcher %s.%s failed", owner, handler_name)

        # Transport telemetry uses __qualname__; retain the actual module and
        # watcher name instead of the opaque register_watcher.<locals>.wrapper.
        wrapper.__qualname__ = f"MCUB.{owner}.{handler_name}"
        options = {k: v for k, v in kw.items() if k in {"pattern", "incoming", "outgoing", "chats"}}
        self._track_cleanup(self.h.transport.subscribe(wrapper, **options))

    def register_inline_handler(self, name: str, handler: Callable) -> None:
        missing = object()
        original = getattr(handler, "__original__", handler)
        previous_owner = self._inline_owners.get(name, missing)
        previous_handler = self.h.inline_handlers.get(name, missing)
        owner = str(getattr(original, "__module__", "mcub"))
        self._inline_owners[name] = owner
        self.h.register_inline(name, handler)

        def cleanup() -> None:
            if self._inline_owners.get(name) == owner:
                if previous_owner is missing:
                    self._inline_owners.pop(name, None)
                else:
                    self._inline_owners[name] = previous_owner
            if self.h.inline_handlers.get(name) is handler:
                if previous_handler is missing:
                    self.h.inline_handlers.pop(name, None)
                else:
                    self.h.inline_handlers[name] = previous_handler

        self._track_cleanup(cleanup)

    def register_callback_handler(self, prefix: str | bytes, handler: Callable) -> None:
        normalized = prefix.decode(errors="replace") if isinstance(prefix, bytes) else str(prefix)

        async def wrapper(event: Any) -> Any:
            self._prepare_callback_event(event)
            result = handler(event)
            if inspect.isawaitable(result):
                return await result
            return result

        missing = object()
        previous = self.h.callback_handlers.get(normalized, missing)
        self.h.register_callback(normalized, wrapper)

        def cleanup() -> None:
            if self.h.callback_handlers.get(normalized) is wrapper:
                if previous is missing:
                    self.h.callback_handlers.pop(normalized, None)
                else:
                    self.h.callback_handlers[normalized] = previous

        self._track_cleanup(cleanup)

    def register_bot_command(self, name: str, handler: Callable) -> None:
        missing = object()
        previous = self.h.bot_commands.get(name, missing)
        self.h.bot_commands[name] = handler

        def cleanup() -> None:
            if self.h.bot_commands.get(name) is handler:
                if previous is missing:
                    self.h.bot_commands.pop(name, None)
                else:
                    self.h.bot_commands[name] = previous

        self._track_cleanup(cleanup)

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
        return True, _MaterializedInlineMessage(self, sent)

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
                    # ModuleBase.Button.input uses MCUB's temporary-inline
                    # registry.  Convert it to the textual ButtonBridge input
                    # protocol instead of leaving an inert private dict on the
                    # rendered form.
                    if btn.get("_mcub_input"):
                        source_token = str(btn.get("uuid") or "")
                        bridge = getattr(self.h, "bridge", None)
                        entry = self.inline_callback_map.get(source_token)
                        if source_token and bridge is not None and entry is not None:
                            token = f"mcub_it:{source_token}"

                            async def _input(call: Any, value: str, _token: str = source_token) -> Any:
                                self._prepare_callback_event(call)
                                temp_entry = self.inline_callback_map.get(_token)
                                if not temp_entry:
                                    return None
                                handler = temp_entry.get("handler")
                                if not callable(handler):
                                    return None
                                result = handler(call, value, temp_entry.get("data"))
                                if inspect.isawaitable(result):
                                    return await result
                                return result

                            bridge.register_input(token, _input, ())
                            out.append({"text": btn.get("text", "?"), "data": token, "input": True})
                        else:
                            # Keep an informative, non-clickable label if a
                            # third-party module supplied a stale temp token.
                            out.append({"text": btn.get("text", "?")})
                    else:
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
                        self._prepare_callback_event(call)
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

    def _prepare_callback_event(self, event: Any) -> Any:
        """Teach a generic Hydra callback event to render MCUB buttons.

        A module callback receives :class:`CallbackQueryEvent`, not the
        interface that created its Telethon-style ``Button`` objects.  Bind a
        one-shot edit adapter before executing it so ``event.edit(...,
        buttons=[Button.inline(...)])`` keeps its callbacks and text bridge.
        """

        if getattr(event, "_mcub_button_iface", None) is self:
            return event
        original_edit = getattr(event, "edit", None)
        if not callable(original_edit):
            return event

        async def edit(text: str, **kw: Any) -> Any:
            if "buttons" in kw:
                kw["buttons"] = self._normalize_buttons(kw["buttons"])
            return await original_edit(text, **kw)

        try:
            event.edit = edit
            event._mcub_button_iface = self
        except Exception:  # pragma: no cover - immutable third-party event
            pass
        return event

    async def inline_form(
        self,
        chat_id: int,
        text: Optional[str] = None,
        buttons: Any = None,
        *,
        title: Optional[str] = None,
        fields: Optional[dict[str, Any]] = None,
        **kw: Any,
    ) -> Tuple[bool, Any]:
        """Отправить MCUB form and return an editable materialized result."""

        body = title if title is not None else (text or "")
        if fields:
            body += "".join(f"\n{k}: {v}" for k, v in fields.items())
        try:
            sent = await self.h.transport.send(
                int(chat_id), body, buttons=self._normalize_buttons(buttons)
            )
            return True, _MaterializedInlineMessage(self, sent)
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
        missing = object()
        old_schema = self._module_config_schemas.get(name, missing)
        old_live = self._live_module_configs.get(name, missing)
        self._module_config_schemas[name] = config
        self._live_module_configs[name] = config

        def cleanup() -> None:
            if self._module_config_schemas.get(name) is config:
                if old_schema is missing:
                    self._module_config_schemas.pop(name, None)
                else:
                    self._module_config_schemas[name] = old_schema
            if self._live_module_configs.get(name) is config:
                if old_live is missing:
                    self._live_module_configs.pop(name, None)
                else:
                    self._live_module_configs[name] = old_live

        self._track_cleanup(cleanup)

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
        self.logger.error(
            "%s: %s",
            message,
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
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

    async def install_from_url(
        self, url: str, module_name: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Install a legacy MCUB URL through Hydra's checked control loader.

        Several class-style MCUB modules, including Vector, pass a suggested
        module name as a second positional argument.  The former one-argument
        stub raised TypeError before the safe Hydra scanner/loader could even
        reject or install the source.
        """

        record = self.h.registry.get("control")
        control = getattr(record, "module", None) if record is not None else None
        download = getattr(control, "_download_source", None)
        install = getattr(control, "_install_mcub_source", None)
        if not callable(download) or not callable(install):
            return False, "Модуль control не загружен; используйте .mload <URL>"
        try:
            source = await asyncio.to_thread(download, url)
            suggested_name = module_name or Path(url.split("?", 1)[0]).stem or "mcub_url"
            loaded, _path = await install(suggested_name, source)
            return True, f"Загружен: {getattr(loaded, 'name', suggested_name)}"
        except Exception as exc:  # noqa: BLE001 - return legacy-compatible result
            logger.exception("MCUB URL installation failed")
            return False, str(exc)[:300]


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

        # Real ``core.ModuleBase.args()`` asks the top-level ``utils`` package
        # for MCUB's stateful ArgumentParser (``get_flag()``, ``get_kwarg()``,
        # ``raw_args``).  Hydra's native utils intentionally only exposes the
        # simple list helpers, which made OpenAgent's `.oa`/`.agent` fail at
        # runtime with ``'list' object has no attribute 'get_flag'``.
        if not hasattr(utils_mod, "parse_arguments"):
            from mcub_engine.utils_inject import parse_arguments

            utils_mod.parse_arguments = parse_arguments

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
        scope = iface.begin_registration_scope(name)
        try:
            ns = self.exec_source(name, source)
            iface.set_module_exports(name, ns)

            if callable(ns.get("register")):
                res = ns["register"](iface)
                if inspect.isawaitable(res):
                    await res
                return iface, scope

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
                    # модуль той же волны мог его require_module().
                    module = cls(kernel=iface)
                    iface.register_class_instance(name, module)
                    module_name = str(getattr(module, "name", name))
                    if module_name != name and module_name not in iface._class_module_instances:
                        iface.register_class_instance(module_name, module)
                    for method in getattr(module, "_method_funcs", ()):
                        result = method(module)
                        if inspect.isawaitable(result):
                            await result
                    lifecycle = await self.h.load_module(module)
                    return module, _CompositeLifecycle(lifecycle, scope)
                module = cls(self.h.make_context(name))
                iface.register_class_instance(name, module)
                lifecycle = await self.h.load_module(module)
                return module, _CompositeLifecycle(lifecycle, scope)

            raise ValueError(f"mcub:{name}: нет ни register(), ни класса ModuleBase")
        except Exception:
            await scope.unload()
            raise
        finally:
            iface.end_registration_scope(scope)
