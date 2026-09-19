# mcub_engine/runtime.py
"""
McubKernel — полная эмуляция ядра MCUB-fork поверх Telethon-клиента Hydra.
Покрывает весь API, который реально используют модули repo-MCUB-fork:
kernel.register.*, kernel.config.*, kernel.inline_form, kernel.client,
kernel.db_*, kernel.cache, kernel.handle_error, kernel.Colors и т.д.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("mcub_engine")


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ
# ============================================================

class CommandConflictError(Exception):
    def __init__(self, message, conflict_type="user", command=None):
        super().__init__(message)
        self.conflict_type = conflict_type
        self.command = command


class Colors:
    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(30, 38)
    RESET = "\033[0m"
    _MAP = {30: "\033[30m", 31: "\033[31m", 32: "\033[32m", 33: "\033[33m",
            34: "\033[34m", 35: "\033[35m", 36: "\033[36m", 37: "\033[37m"}

    @classmethod
    def wrap(cls, color, text):
        return f"{cls._MAP.get(color, '')}{text}{cls.RESET}"


class TTLCache:
    """Простой кэш с TTL (kernel.cache)."""

    def __init__(self, default_ttl=300):
        self._data: dict[str, tuple[Any, float | None]] = {}
        self._default_ttl = default_ttl

    def set(self, key, value, ttl=None):
        t = ttl if ttl is not None else self._default_ttl
        exp = time.time() + t if t else None
        self._data[str(key)] = (value, exp)

    def get(self, key, default=None):
        item = self._data.get(str(key))
        if not item:
            return default
        value, exp = item
        if exp and exp < time.time():
            self._data.pop(str(key), None)
            return default
        return value

    def delete(self, key):
        self._data.pop(str(key), None)

    def clear(self):
        self._data.clear()


class CallbackPermissionManager:
    def __init__(self):
        self._allowed: dict[int, dict[str, float]] = {}

    def allow(self, user_id, token, ttl=100):
        self._allowed.setdefault(int(user_id), {})[token] = time.time() + ttl

    def is_allowed(self, user_id, token) -> bool:
        exp = self._allowed.get(int(user_id), {}).get(token)
        return bool(exp and exp > time.time())


class JsonDB:
    """kernel.db_manager — простое KV-хранилище модулей (async)."""

    def __init__(self, base: Path):
        self._base = base
        self._base.mkdir(parents=True, exist_ok=True)

    def _path(self, module: str) -> Path:
        safe = re.sub(r"[^\w\-.]", "_", str(module))
        return self._base / f"{safe}.json"

    async def get(self, module, key, default=None):
        p = self._path(module)
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f).get(key, default)
            except Exception:
                pass
        return default

    async def set(self, module, key, value):
        p = self._path(module)
        data = {}
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        data[key] = value
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # Совместимость с DBMock-стилем
    async def db_get(self, module, key):
        return await self.get(module, key)

    async def db_set(self, module, key, value):
        await self.set(module, key, value)


class KernelConfig(dict):
    """kernel.config — dict + save()."""

    def __init__(self, kernel):
        super().__init__()
        self._kernel = kernel
        self._load()

    def _file(self) -> Path:
        return Path("data/mcub_kernel_config.json")

    def _load(self):
        p = self._file()
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    self.update(json.load(f))
            except Exception:
                pass
        self.setdefault("language", "ru")

    def save(self):
        p = self._file()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(dict(self), f, ensure_ascii=False, indent=2)


class TaskScheduler:
    """kernel.scheduler — планировщик задач (add_daily_task и т.п.)."""

    def __init__(self, kernel):
        self._kernel = kernel
        self._tasks: list[asyncio.Task] = []

    def add_daily_task(self, func, hour: int, minute: int = 0):
        """Запускать func() каждый день в hour:minute."""

        async def _daily():
            while True:
                now = asyncio.get_event_loop().time()
                import datetime as _dt
                n = _dt.datetime.now()
                target = n.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target <= n:
                    target += _dt.timedelta(days=1)
                await asyncio.sleep((target - n).total_seconds())
                try:
                    res = func()
                    if asyncio.iscoroutine(res):
                        await res
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"scheduler daily task error: {e}")

        try:
            t = asyncio.ensure_future(_daily())
            self._tasks.append(t)
        except RuntimeError:
            pass
        return func

    def add_interval_task(self, func, interval: float):
        async def _loop():
            while True:
                await asyncio.sleep(interval)
                try:
                    res = func()
                    if asyncio.iscoroutine(res):
                        await res
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"scheduler interval task error: {e}")

        try:
            t = asyncio.ensure_future(_loop())
            self._tasks.append(t)
        except RuntimeError:
            pass
        return func

    def add_task(self, func, delay: float = 0):
        async def _once():
            if delay:
                await asyncio.sleep(delay)
            try:
                res = func()
                if asyncio.iscoroutine(res):
                    await res
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"scheduler task error: {e}")

        try:
            t = asyncio.ensure_future(_once())
            self._tasks.append(t)
        except RuntimeError:
            pass
        return func

    def stop_all(self):
        for t in self._tasks:
            try:
                t.cancel()
            except Exception:
                pass
        self._tasks.clear()


class InfiniteLoop:
    """Управляемый фоновой цикл (kernel.register.loop)."""

    def __init__(self, func, interval, autostart, wait_before):
        self.func = func
        self.interval = interval
        self.autostart = autostart
        self._wait_before = wait_before
        self._task: asyncio.Task | None = None
        self._kernel = None
        self.status = False
        self.last_run = None
        self.last_error = None
        self.fail_count = 0

    @property
    def is_running(self):
        return bool(self._task and not self._task.done() and self.status)

    def start(self):
        if self._task and not self._task.done():
            return
        try:
            self._task = asyncio.ensure_future(self._run())
        except RuntimeError:
            pass

    def restart(self):
        self.stop()
        self.start()

    def stop(self):
        self.status = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _run(self):
        self.status = True
        try:
            while self.status:
                if self._wait_before:
                    await asyncio.sleep(self.interval)
                if not self.status:
                    break
                try:
                    self.last_run = time.time()
                    await self.func(self._kernel)
                    self.last_error = None
                    self.fail_count = 0
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    self.last_error = exc
                    self.fail_count += 1
                    logger.error(f"InfiniteLoop '{self.func.__name__}': {exc}")
                if not self._wait_before:
                    await asyncio.sleep(self.interval)
        finally:
            self.status = False


# ============================================================
# ФИЛЬТРЫ ВОТЧЕРОВ (порт _watcher_passes_filters из MCUB)
# ============================================================

def watcher_passes_filters(event, tags: dict) -> bool:
    msg = getattr(event, "message", event)

    if tags.get("out") and not getattr(msg, "out", False):
        return False
    if tags.get("incoming") and getattr(msg, "out", False):
        return False

    chat = getattr(event, "chat", None)
    is_pm = bool(chat) and not getattr(chat, "megagroup", False) \
        and not getattr(chat, "broadcast", False) and not getattr(chat, "gigagroup", False)
    is_group = getattr(chat, "megagroup", False) or getattr(chat, "gigagroup", False)
    is_channel = getattr(chat, "broadcast", False)

    if tags.get("only_pm") and not is_pm: return False
    if tags.get("no_pm") and is_pm: return False
    if tags.get("only_groups") and not is_group: return False
    if tags.get("no_groups") and is_group: return False
    if tags.get("only_channels") and not is_channel: return False
    if tags.get("no_channels") and is_channel: return False

    media = getattr(msg, "media", None)
    photo = media and hasattr(media, "photo")
    video = media and hasattr(media, "video")
    doc = media and hasattr(media, "document")
    audio = doc and getattr(getattr(media, "document", None), "mime_type", "").startswith("audio")
    sticker = doc and any(
        type(a).__name__ == "DocumentAttributeSticker"
        for a in getattr(getattr(media, "document", None), "attributes", [])
    )

    if tags.get("only_media") and not media: return False
    if tags.get("no_media") and media: return False
    if tags.get("only_photos") and not photo: return False
    if tags.get("no_photos") and photo: return False
    if tags.get("only_videos") and not video: return False
    if tags.get("no_videos") and video: return False
    if tags.get("only_audios") and not audio: return False
    if tags.get("no_audios") and audio: return False
    if tags.get("only_docs") and not doc: return False
    if tags.get("no_docs") and doc: return False
    if tags.get("only_stickers") and not sticker: return False
    if tags.get("no_stickers") and sticker: return False

    fwd = getattr(msg, "fwd_from", None)
    reply = getattr(msg, "reply_to", None)
    if tags.get("only_forwards") and not fwd: return False
    if tags.get("no_forwards") and fwd: return False
    if tags.get("only_reply") and not reply: return False
    if tags.get("no_reply") and reply: return False

    text = getattr(msg, "text", "") or ""
    if "regex" in tags and not re.search(tags["regex"], text): return False
    if "startswith" in tags and not text.startswith(tags["startswith"]): return False
    if "endswith" in tags and not text.endswith(tags["endswith"]): return False
    if "contains" in tags and tags["contains"] not in text: return False
    if "from_id" in tags and getattr(event, "sender_id", None) != tags["from_id"]: return False
    if "chat_id" in tags and getattr(event, "chat_id", None) != tags["chat_id"]: return False

    return True


# ============================================================
# REGISTER (порт Register из MCUB, привязка к Telethon)
# ============================================================

class Register:
    """kernel.register — команды/вотчеры/циклы/события/inline_temp."""

    def __init__(self, kernel):
        self.kernel = kernel

    # ---------------- команды ----------------

    @staticmethod
    def _normalize_cmd(pattern: str, prefix: str) -> str:
        """Достаёт «голое» имя команды из чего угодно: слова, ^\\.cmd$,
        (?i)^\\.cmd(?:\\s|$) и т.п. Всегда возвращает lowercase-слово,
        как его ищет _mcub_dispatcher."""
        p = pattern.strip()
        p = re.sub(r"^\(\?[a-zA-Z]+\)", "", p)   # (?i)
        p = re.sub(r"^\^", "", p)                # ^
        escaped_prefix = re.escape(prefix)
        p = re.sub(rf"^(\\)?{escaped_prefix}", "", p)  # \. или .
        p = re.split(r"(?:\(\?:|\\s|\$|\\b)", p, maxsplit=1)[0]
        return p.strip().lower()

    def command(self, pattern: str, **kwargs):
        def decorator(func):
            cmd = self._normalize_cmd(pattern, self.kernel.custom_prefix)
            owner = self.kernel.current_loading_module

            if cmd in self.kernel.command_handlers:
                existing = self.kernel.command_owners.get(cmd)
                if existing != owner:
                    raise CommandConflictError(
                        f"Command '{cmd}' already registered by '{existing}'",
                        conflict_type="user", command=cmd,
                    )
                # reload того же модуля — тихо заменяем
            self.kernel.command_handlers[cmd] = func
            self.kernel.command_owners[cmd] = owner

            alias = kwargs.get("alias")
            aliases = [alias] if isinstance(alias, str) else (alias or [])
            for a in aliases:
                self.kernel.aliases[a.strip().lower()] = cmd

            more = kwargs.get("more")
            if more:
                self.kernel.command_metadata[cmd] = more

            doc, doc_en, doc_ru = kwargs.get("doc"), kwargs.get("doc_en"), kwargs.get("doc_ru")
            if not (doc or doc_en or doc_ru):
                raw_doc = (getattr(func, "__doc__", None) or "").strip()
                if raw_doc:
                    first_line = raw_doc.splitlines()[0].strip()
                    if first_line:
                        doc_ru = doc_en = first_line
            if doc or doc_en or doc_ru:
                docs = {}
                if doc and isinstance(doc, dict):
                    docs.update(doc)
                if doc_en:
                    docs["en"] = doc_en
                if doc_ru:
                    docs["ru"] = doc_ru
                if docs:
                    self.kernel.command_docs[cmd] = docs
            return func

        return decorator

    def bot_command(self, pattern: str, **kwargs):
        def decorator(func):
            cmd = pattern.lstrip("/").split()[0] if " " in pattern else pattern.lstrip("/")
            self.kernel.bot_command_handlers[cmd] = (pattern, func)
            self.kernel.bot_command_owners[cmd] = self.kernel.current_loading_module
            return func

        return decorator

    # ---------------- вотчеры ----------------

    def watcher(self, func=None, bot_client=False, module=None, **tags):
        def decorator(f):
            from telethon import events as _events

            module_name = self.kernel.current_loading_module or "unknown"
            bound_instance = getattr(f, "__bound_instance__", None)
            raw_func = getattr(f, "__original__", f)

            async def _wrapper(event):
                if not watcher_passes_filters(event, tags):
                    return
                try:
                    if bound_instance is not None:
                        await raw_func(bound_instance, event)
                    else:
                        await f(event)
                except Exception as exc:
                    logger.error(f"Watcher '{f.__name__}' raised: {exc}")
                    await self.kernel.handle_error(exc, source="watcher")

            _wrapper.__name__ = f"watcher:{module_name}:{f.__name__}"
            _wrapper.__mcub_module__ = module_name

            event_obj = _events.NewMessage()
            client = self.kernel.client
            client.add_event_handler(_wrapper, event_obj)
            self.kernel._module_handlers.setdefault(module_name, []).append(
                (_wrapper, event_obj)
            )
            return f

        if func is not None and callable(func):
            return decorator(func)
        return decorator

    # ---------------- циклы ----------------

    def loop(self, interval=60, autostart=True, wait_before=False, module=None):
        def decorator(func):
            lp = InfiniteLoop(func, interval, autostart, wait_before)
            lp._kernel = self.kernel
            module_name = self.kernel.current_loading_module or "unknown"
            self.kernel._module_loops.setdefault(module_name, []).append(lp)
            return lp

        return decorator

    # ---------------- методы ----------------

    def method(self, func=None):
        def decorator(f):
            module_name = self.kernel.current_loading_module or "unknown"
            self.kernel._module_methods.setdefault(module_name, []).append(f)
            return f

        if func is None:
            return decorator
        return decorator(func)

    # ---------------- события ----------------

    def event(self, event_type, *args, bot_client=False, module=None, **kwargs):
        from telethon import events as _events

        def _ev(name, fallback=None):
            return getattr(_events, name, fallback or _events.Raw)

        EVENT_TYPE_MAP = {
            "newmessage": _events.NewMessage, "message": _events.NewMessage,
            "messageedited": _events.MessageEdited, "edited": _events.MessageEdited,
            "messagedeleted": _events.MessageDeleted, "deleted": _events.MessageDeleted,
            "messageread": _events.MessageRead, "read": _events.MessageRead,
            "userupdate": _events.UserUpdate, "user": _events.UserUpdate,
            "chataction": _events.ChatAction, "action": _events.ChatAction,
            "joinrequest": _ev("JoinRequest", _events.ChatAction),
            "request": _ev("JoinRequest", _events.ChatAction),
            "album": _ev("Album", _events.NewMessage),
            "inlinequery": _ev("InlineQuery"), "inline": _ev("InlineQuery"),
            "callbackquery": _ev("CallbackQuery"), "callback": _ev("CallbackQuery"),
            "raw": _events.Raw, "custom": _events.Raw,
        }

        def decorator(handler):
            key = event_type.lower()
            if key not in EVENT_TYPE_MAP:
                raise ValueError(f"Unknown event type: '{event_type}'")
            if key in ("inlinequery", "inline", "callbackquery", "callback"):
                # Юзербот не получает такие события — регистрируем, но предупреждаем
                self.kernel.logger.debug(
                    f"register.event('{event_type}') skipped: needs bot account"
                )
                return handler
            event_obj = EVENT_TYPE_MAP[key](*args, **kwargs)
            module_name = self.kernel.current_loading_module or "unknown"
            handler.__mcub_module__ = module_name
            self.kernel.client.add_event_handler(handler, event_obj)
            self.kernel._module_handlers.setdefault(module_name, []).append(
                (handler, event_obj)
            )
            return handler

        return decorator

    # ---------------- inline_temp ----------------

    def inline_temp(self, func, ttl=300, article=None, data=None,
                    allow_user=None, allow_ttl=100):
        form_id = uuid.uuid4().hex
        self.kernel._inline_temps[form_id] = {
            "func": func, "article": article, "data": data,
            "expires_at": time.time() + ttl if ttl else None,
            "allow_user": allow_user, "allow_ttl": allow_ttl,
        }
        return form_id

    # ---------------- invoke ----------------

    async def invoke(self, command, args=None, chat_id=None, reply_to=None):
        """Вызвать команду MCUB программно (как будто отправили .cmd args)."""
        prefix = self.kernel.custom_prefix
        cmd = command.lstrip(prefix)
        text = f"{prefix}{cmd}" + (f" {args}" if args else "")
        target = chat_id if chat_id is not None else "me"
        msg = await self.kernel.client.send_message(target, text)
        return msg


# ============================================================
# ЯДРО
# ============================================================

class McubKernel:
    """Эмуляция ядра MCUB для Hydra."""

    def __init__(self, client, prefix="."):
        from .proxies import ClientProxy

        self._real_client = client
        self.client = ClientProxy(client, self)
        self.bot_client = None

        self.custom_prefix = prefix
        self.config = KernelConfig(self)
        self.logger = logging.getLogger("mcub")
        self.Colors = Colors

        # команды
        self.command_handlers: dict[str, Callable] = {}
        self.command_owners: dict[str, str | None] = {}
        self.command_docs: dict[str, dict] = {}
        self.command_metadata: dict[str, Any] = {}
        self.aliases: dict[str, str] = {}
        self.bot_command_handlers: dict[str, tuple] = {}
        self.bot_command_owners: dict[str, str | None] = {}
        self.bot_command_docs: dict[str, dict] = {}
        self.current_loading_module: str | None = None
        self.system_modules: dict[str, Any] = {}
        self.load_kernel = "full"
        self.loaded_modules: dict[str, Any] = {}
        self._class_module_instances: dict[str, Any] = {}
        self._module_commands_index: dict[str, list] = {}

        # регистратор
        self.register = Register(self)

        # трекинг ресурсов модулей
        self._module_handlers: dict[str, list] = {}
        self._module_loops: dict[str, list] = {}
        self._module_methods: dict[str, list] = {}
        self._disabled_watchers: set = set()

        # инлайн
        self._inline_handlers: dict[str, Callable] = {}
        self._callback_handlers: dict[str, Callable] = {}
        self.inline_callback_map: dict[str, dict] = {}
        self._inline_cb_lock = threading.Lock()
        self.callback_permissions = CallbackPermissionManager()
        self._inline_temps: dict[str, dict] = {}
        self._inline_bot_username = None
        self._inline = None

        # конфиг/БД
        self._live_module_configs: dict[str, Any] = {}
        self._module_schemas: dict[str, Any] = {}
        self.db_manager = JsonDB(Path("data/db"))
        self.cache = TTLCache()
        self._db_conn = None

        # middleware
        self.middleware_chain: list[Callable] = []
        self.request_middleware_chain: list[Callable] = []

        # прочее
        self.scheduler = TaskScheduler(self)
        self.log_chat_id = None
        self.ADMIN_ID = None
        self.HTML_PARSER_AVAILABLE = True
        self.emoji_parser = None
        self._me = None

        # мост кнопок (поздняя инициализация)
        self._bridge = None

    # ---------------- базовое ----------------

    @property
    def bridge(self):
        if self._bridge is None:
            from .bridge import ButtonBridge
            self._bridge = ButtonBridge(self)
        return self._bridge

    @property
    def db_conn(self) -> sqlite3.Connection:
        if self._db_conn is None:
            Path("data").mkdir(exist_ok=True)
            self._db_conn = sqlite3.connect("data/mcub.db", check_same_thread=False)
        return self._db_conn

    async def get_me_cached(self):
        if self._me is None:
            try:
                self._me = await self._real_client.get_me()
                if self._me and self.ADMIN_ID is None:
                    self.ADMIN_ID = self._me.id
            except Exception:
                pass
        return self._me

    def cprint(self, text, color=None, **kwargs):
        if color is not None:
            print(Colors.wrap(color, text), **kwargs)
        else:
            print(text, **kwargs)

    def log_error(self, *a, **kw):
        self.logger.error(*a, **kw)

    def log_warning(self, *a, **kw):
        self.logger.warning(*a, **kw)

    def log_debug(self, *a, **kw):
        self.logger.debug(*a, **kw)

    def add_middleware(self, middleware_func: Callable) -> Callable:
        """kernel.add_middleware — middleware вида mw(event, next_handler)."""
        if middleware_func not in self.middleware_chain:
            self.middleware_chain.append(middleware_func)
        return middleware_func

    def add_event_middleware(self, middleware_func: Callable) -> Callable:
        return self.add_middleware(middleware_func)

    def middleware(self, middleware_func: Callable) -> Callable:
        return self.add_middleware(middleware_func)

    def remove_middleware(self, middleware_func: Callable) -> None:
        if middleware_func in self.middleware_chain:
            self.middleware_chain.remove(middleware_func)

    def add_request_middleware(self, middleware_func: Callable) -> Callable:
        if middleware_func not in self.request_middleware_chain:
            self.request_middleware_chain.append(middleware_func)
        try:
            self._real_client.add_request_middleware(middleware_func)
        except Exception:
            pass
        return middleware_func

    def request_middleware(self, middleware_func: Callable) -> Callable:
        return self.add_request_middleware(middleware_func)

    async def process_with_middleware(self, event, handler: Callable):
        """Прогон события через цепочку middleware перед хендлером."""
        for mw in self.middleware_chain:
            try:
                if await mw(event, handler) is False:
                    return False
            except Exception as e:
                self.logger.error(f"middleware error: {e}")
        return await handler(event)

    def is_admin(self, user_id) -> bool:
        try:
            if self.ADMIN_ID is None:
                return True
            return int(user_id) == int(self.ADMIN_ID)
        except Exception:
            return True

    def is_bot_available(self) -> bool:
        return self.bot_client is not None

    def set_loading_module(self, name, kind="user"):
        self.current_loading_module = name

    def clear_loading_module(self):
        self.current_loading_module = None

    # ---------------- ошибки ----------------

    async def handle_error(self, exc, *args, **kwargs):
        source = kwargs.get("source", "") or kwargs.get("message", "")
        self.logger.error(f"{source}: {exc}" if source else f"Module error: {exc}",
                          exc_info=exc if isinstance(exc, Exception) else None)
        event = kwargs.get("event") or kwargs.get("cb_event")
        text = f"<b>⚠️ Ошибка:</b> <code>{str(exc)[:300]}</code>"

        if event is None:
            return

        # Пробуем edit -> reply -> send_message, а не просто первый
        # доступный атрибут: сообщение могло быть уже удалено (например,
        # диспетчер вызывает event.delete() до обработки .it/.cb),
        # и тогда edit() упадёт даже при наличии атрибута.
        chat_id = getattr(event, "chat_id", None)

        if hasattr(event, "edit"):
            try:
                await event.edit(text, parse_mode="html")
                return
            except Exception:
                pass

        if hasattr(event, "reply"):
            try:
                await event.reply(text, parse_mode="html")
                return
            except Exception:
                pass

        if chat_id is not None:
            try:
                await self.client.send_message(chat_id, text, parse_mode="html")
            except Exception:
                pass

    # ---------------- HTML-хелперы ----------------

    async def edit_with_html(self, event, text, **kwargs):
        try:
            return await event.edit(text, parse_mode="html", **kwargs)
        except Exception as e:
            if "not modified" not in str(e).lower():
                raise

    async def reply_with_html(self, event, text, **kwargs):
        kwargs.setdefault("parse_mode", "html")
        return await event.reply(text, **kwargs)

    async def send_log_message(self, text, buttons=None, **kwargs):
        target = self.log_chat_id or "me"
        try:
            return await self.client.send_message(target, text, buttons=buttons, **kwargs)
        except Exception as e:
            self.logger.error(f"send_log_message failed: {e}")
            return None

    # ---------------- инлайн-хендлеры ----------------

    def register_inline_handler(self, name, func, owner=None):
        self._inline_handlers[name] = func
        if not hasattr(self, "_inline_owners"):
            self._inline_owners = {}
        self._inline_owners[name] = owner or self.current_loading_module
        self.logger.debug(f"inline handler registered: {name}")

    def get_module_inline_commands(self, module_name: str) -> list:
        """Список (cmd, description) инлайн-команд конкретного модуля.
        Используется man.py и подобными модулями."""
        owners = getattr(self, "_inline_owners", {})
        return [(name, None) for name, owner in owners.items() if owner == module_name]

    async def get_module_metadata(self, code: str) -> dict:
        """Best-effort извлечение метаданных модуля из исходного текста
        (версия/автор/описание). Модули (например man.py) сами дополняют
        результат данными из живого класса, так что здесь достаточно
        безопасного минимума, а не полного парсера."""
        import re as _re
        meta: dict = {}
        m = _re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', code)
        if m:
            meta["version"] = m.group(1).strip()
        m = _re.search(r'#\s*meta\s+developer\s*:\s*(.+)', code, _re.IGNORECASE)
        if m:
            meta["author"] = m.group(1).strip()
        m = _re.search(r'#\s*meta\s+name\s*:\s*(.+)', code, _re.IGNORECASE)
        if m:
            meta["name"] = m.group(1).strip()
        m = _re.search(r'"""(.*?)"""', code, _re.DOTALL)
        if m:
            desc = m.group(1).strip()
            if desc:
                meta["description"] = desc[:200]
        return meta

    def register_callback_handler(self, prefix, func):
        self._callback_handlers[prefix] = func
        self.logger.debug(f"callback handler registered: {prefix}")

    # --- proxy storage API (для ModuleBase/ядра) ---
    def store_inline_callback(self, token, callback_data):
        with self._inline_cb_lock:
            self.inline_callback_map[token] = callback_data

    def remove_inline_callback_tokens(self, tokens):
        with self._inline_cb_lock:
            for tok in tokens or []:
                self.inline_callback_map.pop(tok, None)

    def allow_inline_callback_user(self, user_id, token, allow_ttl=100):
        self.callback_permissions.allow(user_id, token, allow_ttl)

    async def inline_query_and_click(self, chat_id, query, *args, **kwargs):
        """Локальное выполнение инлайн-запроса без бота."""
        from .proxies import InlineQueryEventMock
        parts = str(query).split(maxsplit=1)
        name = parts[0] if parts else ""
        if name in self._inline_handlers:
            mock = InlineQueryEventMock(self, chat_id, query, query_name=name)
            try:
                await self._inline_handlers[name](mock)
                return True, None
            except Exception as e:
                return False, str(e)
        return False, f"Inline handler '{name}' не найден"

    async def inline_form(self, chat_id, title=None, fields=None, buttons=None,
                          auto_send=True, ttl=200, media=None, media_type="photo",
                          reply_to=None, parse_mode="html", **kwargs):
        """Отправка «инлайн-формы» — рендерится текстом + команды кнопок.
        Сигнатура как в MCUB: inline_form(chat_id, title, ...)."""
        # совместимость: text= как алиас title
        if title is None:
            title = kwargs.pop("text", "")
        body = str(title)
        if fields:
            if isinstance(fields, dict):
                fields = [{"title": k, "value": v} for k, v in fields.items()]
            for f in fields:
                if isinstance(f, dict):
                    t, v = f.get("title", ""), f.get("value", "")
                    body += f"\n▫️ <b>{t}:</b> {v}"
                else:
                    body += f"\n▫️ {f}"

        form_id = uuid.uuid4().hex
        if not auto_send:
            # как в MCUB: вернуть form_id без отправки
            self._inline_temps[form_id] = {
                "func": None, "article": None, "data": {"text": body, "buttons": buttons},
                "expires_at": time.time() + ttl if ttl else None,
            }
            return form_id

        if reply_to is not None and not isinstance(reply_to, int):
            if getattr(reply_to, "reply_to_top_id", None):
                reply_to = reply_to.reply_to_top_id
            elif getattr(reply_to, "reply_to_msg_id", None):
                reply_to = reply_to.reply_to_msg_id
            else:
                reply_to = None
        try:
            msg = await self.bridge.send_rendered(
                chat_id, body, buttons=buttons, reply_to=reply_to,
                parse_mode=parse_mode,
            )
            from .proxies import InlineMessageMock
            return True, InlineMessageMock(self, msg, form_id=form_id)
        except Exception as e:
            self.logger.error(f"inline_form failed: {e}")
            try:
                msg = await self._real_client.send_message(chat_id, body,
                                                           parse_mode="html")
                from .proxies import InlineMessageMock
                return True, InlineMessageMock(self, msg, form_id=form_id)
            except Exception as e2:
                return False, str(e2)

    async def conversation(self, chat_id, *args, **kwargs):
        from .proxies import ConversationMock
        return ConversationMock(self._real_client, chat_id)

    # ---------------- конфиги модулей ----------------

    async def get_module_config(self, name, default=None):
        p = Path("data/module_configs.json")
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f).get(name)
                    if data is not None:
                        return data
            except Exception:
                pass
        return default or {}

    def store_module_config_schema(self, name, config):
        self._module_schemas[name] = config
        try:
            from modules.cfg import register_module_schema
            schema = config.schema if hasattr(config, "schema") else config
            register_module_schema(name, schema)
        except Exception:
            pass

    async def save_module_config(self, name, cfg_dict):
        p = Path("data/module_configs.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        all_cfg = {}
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    all_cfg = json.load(f)
            except Exception:
                pass
        all_cfg[name] = cfg_dict
        with open(p, "w", encoding="utf-8") as f:
            json.dump(all_cfg, f, ensure_ascii=False, indent=2)

    async def set_module_config_key(self, name, key, value):
        cfg = await self.get_module_config(name, {})
        cfg[key] = value
        await self.save_module_config(name, cfg)

    # ---------------- KV-база ----------------

    async def db_get(self, module, key):
        return await self.db_manager.get(module, key)

    async def db_set(self, module, key, value):
        await self.db_manager.set(module, key, value)

    # ---------------- модули ----------------

    def lookup_module(self, module_name):
        needle = str(module_name).lower()
        for name, inst in self._class_module_instances.items():
            if str(name).lower() == needle or str(getattr(inst, "name", "")).lower() == needle:
                return inst
        for collection in (self.loaded_modules, self.system_modules):
            for name, module in collection.items():
                inst = getattr(module, "_class_instance", None)
                target = inst or module
                names = {str(name).lower(), str(getattr(target, "name", "")).lower(),
                         str(getattr(module, "__name__", "")).lower()}
                if needle in names:
                    return target
        return None

    async def install_from_url(self, url, module_name=None, auto_dependencies=True):
        from .loader import get_loader
        return await get_loader().install_from_url(url, module_name=module_name, auto_dependencies=auto_dependencies)

    # ---------------- выгрузка ----------------

    def unload_module_resources(self, module_name):
        """Снять Telethon-хендлеры и остановить циклы модуля."""
        for handler, event_obj in self._module_handlers.pop(module_name, []):
            try:
                self._real_client.remove_event_handler(handler, event_obj)
            except Exception:
                try:
                    self._real_client.remove_event_handler(handler)
                except Exception:
                    pass
        for lp in self._module_loops.pop(module_name, []):
            try:
                lp.stop()
            except Exception:
                pass
        self._module_methods.pop(module_name, None)
        for cmd in [c for c, o in self.command_owners.items() if o == module_name]:
            self.command_handlers.pop(cmd, None)
            self.command_docs.pop(cmd, None)
            self.command_metadata.pop(cmd, None)
        for cmd, owner in list(self.command_owners.items()):
            if owner == module_name:
                del self.command_owners[cmd]
        for alias, target in list(self.aliases.items()):
            if target not in self.command_handlers:
                del self.aliases[alias]
        # колбэки инлайна модуля
        inst = self._class_module_instances.get(module_name)
        if inst is not None:
            for tok in getattr(inst, "_callback_tokens", []) or []:
                self.inline_callback_map.pop(tok, None)


