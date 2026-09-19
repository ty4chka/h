"""L2 — legacy Hydra + MCUB class-style (hairpin01/MCUB-fork) shim.

Регистрирует в sys.modules пакеты `core.lib.loader.module_base` /
`module_config` с поверхностью, совместимой и со старыми модулями Hydra,
и с class-style MCUB: ModuleBase с хелперами (args/answer/edit/invoke/
lookup_module/Button/subinline/log) и декораторы command/bot_command/
owner_only/event/method/on_install/on_uninstall/inline/callback/watcher/loop.

Декораторы пишут L1-метаданные `_hydra_meta`, поэтому зарегистрированные
методы подключаются штатным Lifecycle без отдельного интерпретатора.
"""

from __future__ import annotations

import html
import logging
import sys
import types
from typing import Any, Callable, List, Optional

from ..api.decorators import META_ATTR
from ..api.module_base import ModuleBase as _L1ModuleBase
from ..api.permissions import OWNER
from ..api import (
    ModuleConfig,
    ConfigValue,
    String,
    Boolean,
    Integer,
    Float,
    Choice,
    Secret,
    loop as _l1_loop,
    watcher as _l1_watcher,
    callback as _l1_callback,
    inline_handler as _l1_inline,
)

_CREATED: List[str] = []


# ------------------------------------------------------------------ декораторы

def command(
    name: Optional[str] = None,
    *_,
    alias: Any = None,
    aliases: Any = (),
    doc_ru: str = "",
    doc_en: str = "",
    desc: str = "",
    **__kw: Any,
) -> Callable:
    """Совместим с L1 command() и с MCUB command(name, doc_ru, doc_en, alias)."""

    def deco(fn: Callable) -> Callable:
        extra: tuple = ()
        if isinstance(alias, str):
            extra = (alias,)
        elif isinstance(alias, (list, tuple)):
            extra = tuple(alias)
        meta = {
            "kind": "command",
            "name": name or fn.__name__,
            "aliases": tuple(aliases or ()) + extra,
            "desc": desc or doc_en or doc_ru,
            "required_level": 1,
        }
        old = getattr(fn, META_ATTR, None)
        if old and old.get("required_level"):
            meta["required_level"] = old["required_level"]
        setattr(fn, META_ATTR, meta)
        return fn

    return deco


def bot_command(name: str, *_, **__kw: Any) -> Callable:
    def deco(fn: Callable) -> Callable:
        setattr(fn, META_ATTR, {"kind": "bot_command", "name": name})
        return fn

    return deco


def owner_only(only_admin: bool = True, **__kw: Any) -> Callable:
    def deco(fn: Callable) -> Callable:
        meta = getattr(fn, META_ATTR, None)
        if meta is None:
            meta = {
                "kind": "command",
                "name": fn.__name__,
                "aliases": (),
                "desc": "",
                "required_level": OWNER,
            }
        else:
            meta["required_level"] = OWNER
        setattr(fn, META_ATTR, meta)
        return fn

    return deco


permissions = owner_only
permission = owner_only


def event(ev_type: Optional[str] = None, incoming: bool = True, outgoing: bool = False, **__kw: Any) -> Callable:
    """MCUB @event: не-NewMessage типы аппроксимируем watcher'ом."""
    return _l1_watcher(pattern=None, incoming=incoming, outgoing=outgoing)


def method(fn: Callable) -> Callable:
    setattr(fn, META_ATTR, {"kind": "method"})
    return fn


def on_install() -> Callable:
    def deco(fn: Callable) -> Callable:
        setattr(fn, META_ATTR, {"kind": "hook_install"})
        return fn

    return deco


def on_uninstall() -> Callable:
    def deco(fn: Callable) -> Callable:
        setattr(fn, META_ATTR, {"kind": "hook_uninstall"})
        return fn

    return deco


def error_handler(fn: Callable) -> Callable:
    setattr(fn, META_ATTR, {"kind": "error_handler"})
    return fn


def inline(name: Optional[str] = None) -> Callable:
    return _l1_inline(name or "")


def callback(prefix: Optional[str] = None) -> Callable:
    """MCUB @callback() без префикса: роутинг идёт через Button.inline(data)."""
    if prefix is None:
        def deco(fn: Callable) -> Callable:
            setattr(fn, META_ATTR, {"kind": "callback_unbound"})
            return fn

        return deco
    return _l1_callback(prefix)


inline_temp = inline
watcher = _l1_watcher
loop = _l1_loop


# ------------------------------------------------------------------ ButtonFactory

class ButtonFactory:
    """Кнопки в стиле MCUB: callable-callback получает свой префикс data."""

    def __init__(self, module: "ModuleBase"):
        self._m = module
        self._n = 0

    def inline(self, text: str, callback: Any = None, args: Any = (), style: Any = None, data: Any = None, url: Any = None, **__kw: Any) -> dict:
        if url:
            return {"text": text, "url": url}
        if callable(callback):
            self._n += 1
            token = f"{self._m.name}_bf{self._n}:"
            hydra = getattr(self._m.ctx, "hydra", None)

            async def wrapper(ev: Any, _cb: Any = callback, _args: Any = args, _data: Any = data) -> None:
                if _data is not None:
                    await _cb(ev, _data)
                else:
                    await _cb(ev, *_args)

            if hydra is not None:
                hydra.register_callback(token, wrapper)
            return {"text": text, "data": token}
        return {"text": text, "data": data if isinstance(data, (str, bytes)) else text}

    def url(self, text: str, url: str) -> dict:
        return {"text": text, "url": url}

    def text(self, text: str) -> dict:
        return {"text": text}


class SubInline:
    """self.subinline.form / rich_form (обёртка kernel.inline_form)."""

    def __init__(self, module: "ModuleBase"):
        self._m = module

    async def form(
        self,
        chat_id: int,
        title: str,
        fields: Optional[dict] = None,
        buttons: Any = None,
        auto_send: bool = True,
        ttl: int = 200,
        reply_to: Any = None,
        **__kw: Any,
    ) -> Any:
        text = f"<b>{title}</b>"
        for key, value in (fields or {}).items():
            text += f"\n{key}: {value}"
        msg = await self._m.ctx.transport.send(int(chat_id), text, buttons=buttons)
        return None, msg

    async def rich_form(self, chat_id: int, rich_text: str, buttons: Any = None, **__kw: Any) -> Any:
        return await self.form(chat_id, rich_text, buttons=buttons)


# ------------------------------------------------------------------ ModuleBase

class ModuleBase(_L1ModuleBase):
    """Class-style MCUB ModuleBase поверх L1: хелперы как в MCUB-fork."""

    author: str = "unknown"
    description: Any = {}
    banner_url: Optional[str] = None
    strings: dict = {}

    # -- окружение --
    def get_prefix(self) -> str:
        return self.ctx.prefix

    def get_lang(self) -> str:
        return "ru"

    @property
    def log(self) -> logging.Logger:
        return logging.getLogger(f"module.{self.name}")

    @property
    def kernel(self) -> Any:
        return getattr(self.ctx, "hydra", None)

    # -- аргументы --
    @staticmethod
    def _raw_after(event: Any) -> str:
        text = getattr(event, "text", "") or ""
        parts = text.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else ""

    def args_raw(self, event: Any) -> str:
        return self._raw_after(event)

    def args_html(self, event: Any) -> str:
        return html.escape(self._raw_after(event))

    def args(self, event: Any) -> List[Any]:
        out: List[Any] = []
        for part in self._raw_after(event).split():
            try:
                out.append(int(part))
                continue
            except ValueError:
                pass
            try:
                out.append(float(part))
                continue
            except ValueError:
                out.append(part)
        return out

    # -- ответы --
    async def answer(self, event: Any, text: str, **kw: Any) -> Any:
        try:
            return await event.edit(text, **kw)
        except Exception:  # noqa: BLE001
            return await event.reply(text, **kw)

    async def edit(self, event: Any, text: str, as_html: bool = False, **kw: Any) -> Any:
        kw.pop("parse_mode", None)
        return await event.edit(text, **kw)

    async def reply(self, event: Any, text: str, as_html: bool = False, **kw: Any) -> Any:
        return await event.reply(text, **kw)

    # -- взаимодействие --
    async def invoke(self, cmd: str, args: Any = None, chat_id: Any = None, reply_to: Any = None) -> Any:
        text = f"{self.get_prefix()}{cmd}"
        if args:
            text += f" {args}"
        target = int(chat_id) if chat_id else self.ctx.transport.me_id
        return await self.ctx.transport.inject(target, text, sender_id=self.ctx.transport.me_id, outgoing=True)

    def lookup_module(self, module_name: str, *, all_loaded: bool = False) -> Any:
        hydra = getattr(self.ctx, "hydra", None)
        if hydra is None:
            return None
        rec = hydra.registry.get(module_name) or hydra.registry.get(module_name.lower())
        return rec.module if rec else None

    def require_module(self, module_name: str, *, all_loaded: bool = False) -> Any:
        mod = self.lookup_module(module_name, all_loaded=all_loaded)
        if mod is None:
            raise LookupError(f"модуль не найден: {module_name}")
        return mod

    # -- инлайн --
    @property
    def Button(self) -> ButtonFactory:
        factory = self.__dict__.get("_button_factory")
        if factory is None:
            factory = ButtonFactory(self)
            self.__dict__["_button_factory"] = factory
        return factory

    @property
    def subinline(self) -> SubInline:
        sub = self.__dict__.get("_subinline")
        if sub is None:
            sub = SubInline(self)
            self.__dict__["_subinline"] = sub
        return sub

    async def inline(self, chat_id: int, text: str, buttons: Any = None, ttl: int = 900, parse_mode: str = "html", **__kw: Any) -> Any:
        return None, await self.ctx.transport.send(int(chat_id), text, buttons=buttons)


# ------------------------------------------------------------------ моки старого ядра

class StringsMock(dict):
    def get(self, key: str, default: Any = "") -> Any:
        return super().get(key, default)


class DBMock:
    def __init__(self) -> None:
        self._data: dict = {}

    async def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        self._data[key] = value


_EXPORTS = {
    "ModuleBase": ModuleBase,
    "ModuleConfig": ModuleConfig,
    "ConfigValue": ConfigValue,
    "String": String,
    "Boolean": Boolean,
    "Integer": Integer,
    "Float": Float,
    "Choice": Choice,
    "Secret": Secret,
    "command": command,
    "bot_command": bot_command,
    "owner_only": owner_only,
    "permissions": permissions,
    "permission": permission,
    "event": event,
    "method": method,
    "on_install": on_install,
    "on_uninstall": on_uninstall,
    "error_handler": error_handler,
    "watcher": watcher,
    "loop": loop,
    "callback": callback,
    "inline": inline,
    "inline_temp": inline_temp,
    "inline_handler": _l1_inline,
    "StringsMock": StringsMock,
    "DBMock": DBMock,
}


def install_legacy_imports() -> None:
    """Создаёт core / core.lib / core.lib.loader / ...module_base|module_config."""
    # настоящий core есть в репе/на устройстве — shim только когда его нет
    import importlib

    try:
        importlib.import_module("core.lib.loader.module_config")
        return
    except ImportError:
        pass
    for dotted in (
        "core",
        "core.lib",
        "core.lib.loader",
        "core.lib.loader.module_base",
        "core.lib.loader.module_config",
    ):
        mod = types.ModuleType(dotted)
        if dotted.endswith(("module_base", "module_config")):
            for key, value in _EXPORTS.items():
                setattr(mod, key, value)
        sys.modules[dotted] = mod
        if dotted not in _CREATED:
            _CREATED.append(dotted)
        if "." in dotted:
            parent, _, child = dotted.rpartition(".")
            if parent in sys.modules:
                setattr(sys.modules[parent], child, mod)


def uninstall_legacy_imports() -> None:
    for dotted in _CREATED:
        sys.modules.pop(dotted, None)
    _CREATED.clear()
