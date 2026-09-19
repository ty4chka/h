"""Небольшие офлайн-замены для *необязательных* runtime-зависимостей.

Ядро должно уметь прогонять smoke-тесты без сети, Telethon и пакетов,
которые нужны только боевым модулям.  Этот модуль никогда не заменяет
установленную зависимость: shim создаётся исключительно после
``ModuleNotFoundError`` для корневого пакета.

Это не реализация Telegram или HTTP.  Цель — дать импортам и простым
офлайн-командам предсказуемую поверхность API; попытка сделать сетевой запрос
через aiohttp shim завершается понятной ``ClientError``.
"""

from __future__ import annotations

import importlib
import os
import re
import sys
import types
from types import SimpleNamespace
from typing import Any, Callable


class OfflineDependencyError(RuntimeError):
    """Операция требует зависимость, которой нет в офлайн-режиме."""


def _is_missing_root(exc: ModuleNotFoundError, root: str) -> bool:
    """Не маскируем ошибку *внутри* установленного пакета."""

    return exc.name in (None, root)


def _import_or_none(root: str) -> types.ModuleType | None:
    try:
        return importlib.import_module(root)
    except ModuleNotFoundError as exc:
        if not _is_missing_root(exc, root):
            raise
        return None


def _put_package(name: str) -> types.ModuleType:
    """Создать importable package и привязать его к уже созданному родителю."""

    current = sys.modules.get(name)
    if isinstance(current, types.ModuleType):
        return current
    mod = types.ModuleType(name)
    mod.__package__ = name
    mod.__path__ = []  # type: ignore[attr-defined] -- маркер package для importlib
    sys.modules[name] = mod
    parent, dot, child = name.rpartition(".")
    if dot and parent in sys.modules:
        setattr(sys.modules[parent], child, mod)
    return mod


def _put_module(name: str) -> types.ModuleType:
    current = sys.modules.get(name)
    if isinstance(current, types.ModuleType):
        return current
    mod = types.ModuleType(name)
    mod.__package__ = name.rpartition(".")[0]
    sys.modules[name] = mod
    parent, dot, child = name.rpartition(".")
    if dot and parent in sys.modules:
        setattr(sys.modules[parent], child, mod)
    return mod


def _value_class(name: str, base: type = object) -> type:
    """Лёгкий TL-объект: сохраняет позиционные/именованные аргументы."""

    class Value(base):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs
            for key, value in kwargs.items():
                setattr(self, key, value)

        def __repr__(self) -> str:  # pragma: no cover - диагностический путь
            return f"<{name} offline stub>"

    Value.__name__ = name
    Value.__qualname__ = name
    return Value


def _dynamic_types(module: types.ModuleType, *, base: type = object) -> None:
    """`from telethon.tl.types import NewThing` для редко используемых TL типов."""

    def get_attr(name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        value = _value_class(name, base)
        setattr(module, name, value)
        return value

    module.__getattr__ = get_attr  # type: ignore[attr-defined]


def _install_telethon() -> None:
    if _import_or_none("telethon") is not None:
        return

    root = _put_package("telethon")
    root.__offline_shim__ = True
    root.__version__ = "offline"

    class _Button:
        def __init__(self, text: str, data: Any = None, **kwargs: Any) -> None:
            self.text = text
            self.data = data
            self.kwargs = kwargs

        def __repr__(self) -> str:  # pragma: no cover - diagnostics only
            return f"<Button {self.text!r}>"

    class Button:
        @staticmethod
        def inline(text: str, data: Any = None, **kwargs: Any) -> _Button:
            return _Button(text, data, **kwargs)

        @staticmethod
        def url(text: str, url: str, **kwargs: Any) -> _Button:
            return _Button(text, None, url=url, **kwargs)

        @staticmethod
        def text(text: str, **kwargs: Any) -> _Button:
            return _Button(text, None, **kwargs)

        @staticmethod
        def switch_inline(text: str, query: str = "", **kwargs: Any) -> _Button:
            return _Button(text, None, query=query, **kwargs)

    class _EventBuilder:
        Event = object

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.outgoing = kwargs.get("outgoing")
            self.incoming = kwargs.get("incoming")
            pattern = kwargs.get("pattern")
            self.pattern: Callable[[str], Any] | None
            if isinstance(pattern, str):
                self.pattern = re.compile(pattern).match
            else:
                self.pattern = pattern
            self.kwargs = kwargs

    class NewMessage(_EventBuilder):
        pass

    class CallbackQuery(_EventBuilder):
        pass

    class ChatAction(_EventBuilder):
        pass

    class Raw(_EventBuilder):
        pass

    events = _put_module("telethon.events")
    events.NewMessage = NewMessage
    events.CallbackQuery = CallbackQuery
    events.ChatAction = ChatAction
    events.Raw = Raw
    events.MessageEdited = type("MessageEdited", (_EventBuilder,), {})
    events.Album = type("Album", (_EventBuilder,), {})

    tl = _put_package("telethon.tl")
    TLRequest = _value_class("TLRequest")
    tl.TLRequest = TLRequest
    types_mod = _put_module("telethon.tl.types")
    _dynamic_types(types_mod)
    functions_mod = _put_package("telethon.tl.functions")
    _dynamic_types(functions_mod, base=TLRequest)
    tl.types = types_mod
    tl.functions = functions_mod

    for part in ("account", "channels", "contacts", "messages", "photos", "stories"):
        child = _put_module(f"telethon.tl.functions.{part}")
        _dynamic_types(child, base=TLRequest)
        setattr(functions_mod, part, child)

    # Некоторые модули используют короткий путь `telethon.types`.
    sys.modules["telethon.types"] = types_mod
    root.types = types_mod
    root.tl = tl
    root.events = events
    root.Button = Button
    root.TLRequest = TLRequest

    errors = _put_package("telethon.errors")

    class RPCError(Exception):
        pass

    def errors_getattr(name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        error = type(name, (RPCError,), {})
        setattr(errors, name, error)
        return error

    errors.RPCError = RPCError
    errors.__getattr__ = errors_getattr  # type: ignore[attr-defined]
    rpcerrorlist = _put_module("telethon.errors.rpcerrorlist")
    rpcerrorlist.DataInvalidError = type("DataInvalidError", (RPCError,), {})
    rpcerrorlist.MessageNotModifiedError = type("MessageNotModifiedError", (RPCError,), {})
    errors.rpcerrorlist = rpcerrorlist
    root.errors = errors

    client_pkg = _put_package("telethon.client")
    protection = _put_module("telethon.client.protection")
    protection.STRICT_DANGEROUS_REQUESTS = frozenset()
    protection.build_protection_policy = lambda *args, **kwargs: {
        "strict": bool(kwargs.get("strict", False)),
        "requests": tuple(args),
    }
    client_pkg.protection = protection
    root.client = client_pkg

    utils = _put_module("telethon.utils")
    utils.get_display_name = lambda entity: getattr(entity, "first_name", None) or getattr(entity, "title", None) or str(entity)
    root.utils = utils

    class TelegramClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise OfflineDependencyError("telethon не установлен; TelegramClient недоступен в офлайн-режиме")

    root.TelegramClient = TelegramClient


def _install_aiohttp() -> None:
    if _import_or_none("aiohttp") is not None:
        return

    aiohttp = _put_module("aiohttp")
    aiohttp.__offline_shim__ = True

    class ClientError(OfflineDependencyError):
        pass

    class ClientTimeout:
        def __init__(self, total: Any = None, **kwargs: Any) -> None:
            self.total = total
            self.kwargs = kwargs

    class _Content:
        async def iter_chunked(self, _size: int):  # pragma: no cover - defensive
            if False:
                yield b""

    class _Response:
        status = 503
        content_length = 0
        headers: dict[str, str] = {}
        url = ""
        content = _Content()

        async def __aenter__(self) -> "_Response":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        def raise_for_status(self) -> None:
            raise ClientError("aiohttp не установлен; HTTP недоступен в офлайн-режиме")

        async def json(self) -> Any:
            return {}

        async def text(self) -> str:
            return ""

        async def read(self) -> bytes:
            return b""

    class ClientSession:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self) -> "ClientSession":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def close(self) -> None:
            return None

        def get(self, *args: Any, **kwargs: Any) -> _Response:
            return _Response()

        def post(self, *args: Any, **kwargs: Any) -> _Response:
            return _Response()

        def request(self, *args: Any, **kwargs: Any) -> _Response:
            return _Response()

    aiohttp.ClientError = ClientError
    aiohttp.ClientResponseError = ClientError
    aiohttp.ClientTimeout = ClientTimeout
    aiohttp.ClientSession = ClientSession
    aiohttp.FormData = dict


def _install_psutil() -> None:
    if _import_or_none("psutil") is not None:
        return

    psutil = _put_module("psutil")
    psutil.__offline_shim__ = True

    def memory() -> Any:
        total = 0
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            pages = os.sysconf("SC_PHYS_PAGES")
            total = int(page_size) * int(pages)
        except (AttributeError, OSError, ValueError):
            total = 0
        available = total
        return SimpleNamespace(total=total, available=available, used=0, free=available, percent=0.0)

    def disk(_path: str = "/") -> Any:
        return SimpleNamespace(total=0, used=0, free=0, percent=0.0)

    psutil.virtual_memory = memory
    psutil.disk_usage = disk
    psutil.cpu_count = lambda logical=True: os.cpu_count() or 1
    psutil.cpu_percent = lambda interval=None: 0.0
    psutil.boot_time = lambda: 0.0
    psutil.pids = lambda: []


def ensure_offline_dependencies() -> None:
    """Установить только отсутствующие shims, нужные для офлайн-smoke."""

    _install_telethon()
    _install_aiohttp()
    _install_psutil()
