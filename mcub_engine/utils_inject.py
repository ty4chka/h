# mcub_engine/utils_inject.py
"""
Инъекция MCUB-совместимых функций в пакет `utils` Hydra.

Модули MCUB делают `import utils` и ждут MCUB-шное API
(utils.answer, utils.parse_arguments, utils.get_args_raw и т.д.).
У Hydra свой пакет utils/ — мы НЕ заменяем его, а добавляем
недостающие функции как атрибуты + регистрируем подмодули
(utils.arg_parser, utils.strings, utils.placeholders...) в sys.modules.
"""

from __future__ import annotations

import html as _html
import logging
import re
import shlex
import sys
import types
from typing import Any

logger = logging.getLogger("mcub_engine.utils_inject")

_injected = False


# ============================================================
# РЕАЛИЗАЦИИ (порты utils/helpers.py из MCUB)
# ============================================================

def _get_kernel():
    try:
        from . import get_kernel
        return get_kernel()
    except Exception:
        return None


def get_args_raw(event) -> str:
    text = getattr(event, "text", None) or getattr(event, "raw_text", "") or ""
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


def get_args(event) -> list:
    raw = get_args_raw(event)
    return raw.split() if raw else []


def get_args_html(event) -> str:
    if not hasattr(event, "message") or not getattr(event.message, "entities", None):
        return get_args_raw(event)
    try:
        raw_text = event.raw_text
        k = _get_kernel()
        prefix = getattr(k, "custom_prefix", ".") if k else "."
        cmd_start = raw_text.index(prefix)
        cmd_end = raw_text.index(" ", cmd_start + 1) + 1
        return raw_text[cmd_end:]
    except (ValueError, IndexError):
        return get_args_raw(event)


async def answer(event, text, *, reply_markup=None, file=None, caption=None,
                 as_html=False, as_emoji=False, kernel=None, **kwargs):
    if file:
        return await answer_file(event, file, caption or text, as_html=as_html, **kwargs)
    if reply_markup is not None:
        kwargs["buttons"] = reply_markup
    if as_html:
        kwargs["parse_mode"] = "html"
    if hasattr(event, "edit") and callable(getattr(event, "edit")):
        try:
            return await event.edit(text, **kwargs)
        except Exception:
            pass
    return await event.reply(text, **kwargs)


async def answer_file(event, file, caption=None, *, as_html=False, **kwargs):
    kwargs.pop("buttons", None)
    if caption and as_html:
        kwargs["parse_mode"] = "html"
    chat_id = getattr(event, "chat_id", None)
    client = getattr(event, "client", None)
    if client is None:
        k = _get_kernel()
        client = k._real_client if k else None
    reply_to = getattr(event, "id", None)
    return await client.send_file(chat_id, file, caption=caption,
                                  reply_to=reply_to, **kwargs)


def escape_html(text) -> str:
    return _html.escape(str(text))


def escape_quotes(text) -> str:
    return str(text).replace('"', "&quot;")


def format_time(seconds, detailed: bool = False) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} сек"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m} мин {s} сек" if detailed else f"{m} мин"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} ч {m} мин" if detailed else f"{h} ч"
    d, h = divmod(h, 24)
    return f"{d} дн {h} ч" if detailed else f"{d} дн"


def format_date(ts=None) -> str:
    from datetime import datetime
    if ts is None:
        ts = datetime.now()
    if isinstance(ts, (int, float)):
        ts = datetime.fromtimestamp(ts)
    return ts.strftime("%d.%m.%Y %H:%M")


def format_relative_time(seconds) -> str:
    return format_time(seconds, detailed=True)


def get_chat_id(event):
    return getattr(event, "chat_id", None)


async def get_thread_id(event):
    msg = getattr(event, "message", event)
    reply_to = getattr(msg, "reply_to", None)
    if reply_to and getattr(reply_to, "forum_topic", False):
        return getattr(reply_to, "reply_to_top_id", None) or getattr(reply_to, "reply_to_msg_id", None)
    return None


def pipe_edit(event, raw, pretty):
    return event.edit(pretty)


def get_prefix(target=None) -> str:
    if target is not None:
        k = getattr(target, "kernel", None)
        if k is not None:
            return getattr(k, "custom_prefix", ".")
        if hasattr(target, "custom_prefix"):
            return target.custom_prefix
    k = _get_kernel()
    return getattr(k, "custom_prefix", ".") if k else "."


def get_lang(target=None, default="ru") -> str:
    k = getattr(target, "kernel", None) if target is not None else None
    k = k or (target if hasattr(target, "config") else None) or _get_kernel()
    config = getattr(k, "config", None)
    getter = getattr(config, "get", None)
    if callable(getter):
        return getter("language", default) or default
    return default


def relocate_entities(entities, offset, text):
    return entities  # упрощённо: Telethon сам сдвинет при parse_mode


def make_button(text, data=None, url=None):
    from telethon import Button
    if url:
        return Button.url(text, url)
    return Button.inline(text, data or b"")


def make_buttons(rows):
    return [[make_button(**b) if isinstance(b, dict) else b for b in row] for row in rows]


async def resolve_peer(client, peer):
    return await client.get_entity(peer)


async def get_sender_info(event):
    sender = await event.get_sender()
    if sender is None:
        return {"id": getattr(event, "sender_id", None)}
    return {
        "id": sender.id,
        "first_name": getattr(sender, "first_name", ""),
        "last_name": getattr(sender, "last_name", ""),
        "username": getattr(sender, "username", ""),
    }


async def get_admins(client, chat):
    from telethon.tl.types import ChannelParticipantsAdmins
    return await client.get_participants(chat, filter=ChannelParticipantsAdmins())


# ---------- arg_parser ----------

class ArgumentParser:
    """Small stateful port of MCUB's command argument parser.

    In addition to sequential tokens, current MCUB modules rely on the raw
    command tail and ``--key=value`` lookups.  Keep both representations: flag
    helpers may consume parsed tokens without corrupting the user prompt held
    in :attr:`raw_args`.
    """

    def __init__(self, tokens=None, raw_args: str | None = None):
        self._tokens = list(tokens or [])
        self.raw_args = str(raw_args if raw_args is not None else " ".join(self._tokens))
        self._pos = 0

    def __iter__(self):
        return iter(self._tokens)

    def __len__(self):
        return len(self._tokens)

    def __getitem__(self, i):
        return self._tokens[i]

    def next(self, default=None):
        if self._pos < len(self._tokens):
            tok = self._tokens[self._pos]
            self._pos += 1
            return tok
        return default

    def rest(self) -> str:
        rest = " ".join(self._tokens[self._pos:])
        self._pos = len(self._tokens)
        return rest

    def peek(self, default=None):
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return default

    def get_int(self, default=None):
        tok = self.next()
        try:
            return int(tok)
        except (TypeError, ValueError):
            return default

    def get_float(self, default=None):
        tok = self.next()
        try:
            return float(tok)
        except (TypeError, ValueError):
            return default

    def get_flag(self, name: str, default: bool = False) -> bool:
        """Ищет флаг вида --name среди токенов, удаляет его из потока
        и возвращает True, если он присутствовал.

        parser.get_flag("clear")  ->  ищет "--clear" (или "-clear")
        """
        needle_long = f"--{name}"
        needle_short = f"-{name}"
        for i, tok in enumerate(self._tokens):
            if tok == needle_long or tok == needle_short:
                del self._tokens[i]
                if i < self._pos:
                    self._pos -= 1
                return True
        return default

    def get_kwarg(self, name: str, default=None):
        """Return and consume ``--name=value`` or ``--name value``.

        MCUB modules commonly use this for opt-in internal modes while still
        treating everything else as a free-form prompt.  Supporting both long
        and single-dash spellings mirrors :meth:`get_flag` and avoids leaking
        the option itself into a subsequent token consumer.
        """

        needles = (f"--{name}", f"-{name}")
        for i, token in enumerate(self._tokens):
            for needle in needles:
                prefix = f"{needle}="
                if token.startswith(prefix):
                    value = token[len(prefix):]
                    del self._tokens[i]
                    if i < self._pos:
                        self._pos -= 1
                    return value
                if token == needle:
                    if i + 1 >= len(self._tokens):
                        del self._tokens[i]
                        if i < self._pos:
                            self._pos -= 1
                        return default
                    value = self._tokens[i + 1]
                    del self._tokens[i:i + 2]
                    if i < self._pos:
                        self._pos = max(0, self._pos - 2)
                    return value
        return default

    def has_flag(self, name: str) -> bool:
        """Проверяет наличие флага без удаления его из токенов."""
        needle_long = f"--{name}"
        needle_short = f"-{name}"
        return needle_long in self._tokens or needle_short in self._tokens

    def all(self):
        return list(self._tokens)


def parse_arguments(text, prefix=".") -> ArgumentParser:
    """Parse a command tail while retaining its exact, user-visible text."""

    text = str(text or "")
    raw_args = text
    if prefix and text.startswith(prefix):
        parts = text.split(maxsplit=1)
        raw_args = parts[1] if len(parts) > 1 else ""
    try:
        tokens = shlex.split(raw_args)
    except ValueError:
        # An unfinished quote should not make a command silently disappear.
        tokens = raw_args.split()
    return ArgumentParser(tokens, raw_args=raw_args)


# ---------- placeholders bridge ----------

async def resolve_placeholders(scope, text, data=None, strict=False):
    try:
        from core.lib.loader.placeholders import resolve_placeholders as _r
        return await _r(scope, text, data=data or {}, strict=strict)
    except Exception:
        pass
    result = str(text)
    for k, v in (data or {}).items():
        result = result.replace("{" + str(k) + "}", str(v))
    return result


def register_placeholder(scope, key, callback, **kwargs):
    try:
        from core.lib.loader.placeholders import register_placeholder as _r
        return _r(scope, key, callback, **kwargs)
    except Exception:
        pass


def unregister_placeholder(scope, key=None):
    try:
        from core.lib.loader.placeholders import unregister_placeholder as _u
        return _u(scope, key)
    except Exception:
        pass


def unregister_scope(scope):
    try:
        from core.lib.loader.placeholders import unregister_scope as _u
        return _u(scope)
    except Exception:
        return 0


async def format_placeholders(text, data=None, scope="any"):
    return await resolve_placeholders(scope, text, data=data)


def placeholders(key, *, timeout=None, description=None, cache_ttl=None,
                 required=False, on_error="keep"):
    """Декоратор @utils.placeholders('key', description=...) — порт MCUB."""
    if on_error not in {"keep", "empty", "raise"}:
        raise ValueError("on_error must be one of: keep, empty, raise")

    def decorator(func):
        meta = list(getattr(func, "__custom_placeholders__", []))
        meta.append({
            "key": key, "timeout": timeout, "description": description,
            "cache_ttl": cache_ttl, "required": required, "on_error": on_error,
        })
        func.__custom_placeholders__ = meta
        return func

    return decorator


def register_decorated_placeholders(scope, obj):
    """Сканирует объект на методы с __custom_placeholders__ и регистрирует их."""
    count = 0
    for attr_name in dir(obj):
        try:
            attr = getattr(obj, attr_name)
        except Exception:
            continue
        metas = getattr(attr, "__custom_placeholders__", None)
        if not metas:
            continue
        for meta in metas:
            callback = attr
            try:
                register_placeholder(scope, meta["key"], callback,
                                     description=meta.get("description"),
                                     timeout=meta.get("timeout"),
                                     cache_ttl=meta.get("cache_ttl"),
                                     required=meta.get("required", False),
                                     on_error=meta.get("on_error", "keep"))
                count += 1
            except Exception as e:
                logger.debug(f"placeholder register failed ({scope}:{meta['key']}): {e}")
    return count


def get_placeholders(scope=None):
    try:
        from core.lib.loader.placeholders import get_placeholders as _g
        return _g(scope) if scope else _g()
    except Exception:
        return {}


def list_placeholder_keys(scope=None):
    try:
        from core.lib.loader.placeholders import list_placeholder_keys as _l
        return _l(scope)
    except Exception:
        return []


def config_placeholders(*a, **kw):
    return {}


# ---------- misc ----------

async def restart_kernel(*args, **kwargs):
    logger.warning("utils.restart_kernel вызван — полный рестарт не поддерживается в Hydra")
    return False


def telegram_to_html(text, entities=None):
    return _html.escape(str(text))


def parse_html(text):
    return str(text), []


# ============================================================
# ИНЪЕКЦИЯ
# ============================================================

_HELPERS_FUNCS = {
    "answer": answer, "answer_file": answer_file,
    "escape_html": escape_html, "escape_quotes": escape_quotes,
    "format_time": format_time, "format_date": format_date,
    "format_relative_time": format_relative_time,
    "get_args": get_args, "get_args_raw": get_args_raw, "get_args_html": get_args_html,
    "get_chat_id": get_chat_id, "get_thread_id": get_thread_id,
    "get_prefix": get_prefix, "get_lang": get_lang,
    "make_button": make_button, "make_buttons": make_buttons,
    "pipe_edit": pipe_edit, "relocate_entities": relocate_entities,
    "resolve_peer": resolve_peer, "get_sender_info": get_sender_info,
    "get_admins": get_admins, "parse_arguments": parse_arguments,
    "resolve_placeholders": resolve_placeholders,
    "register_placeholder": register_placeholder,
    "unregister_placeholder": unregister_placeholder,
    "unregister_scope": unregister_scope,
    "format_placeholders": format_placeholders,
    "register_decorated_placeholders": register_decorated_placeholders,
    "get_placeholders": get_placeholders,
    "list_placeholder_keys": list_placeholder_keys,
    "placeholders": placeholders,
    "config_placeholders": config_placeholders,
    "restart_kernel": restart_kernel,
    "telegram_to_html": telegram_to_html,
    "parse_html": parse_html,
}


def _mk_module(name, attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    return mod


def inject_utils():
    """Внедрить MCUB API в пакет utils Hydra. Идемпотентно."""
    global _injected
    if _injected:
        return True
    try:
        import utils as hydra_utils
    except ImportError:
        logger.error("Пакет utils Hydra не найден — инъекция невозможна")
        return False

    # 1. функции как атрибуты пакета (не перезаписываем существующие Hydra-функции,
    #    кроме случаев, где MCUB-семантика критична и в Hydra её нет)
    for name, func in _HELPERS_FUNCS.items():
        if not hasattr(hydra_utils, name):
            setattr(hydra_utils, name, func)

    # 2. подмодули
    from core.lib.loader.module_base import Strings

    sys.modules.setdefault(
        "utils.arg_parser",
        _mk_module("utils.arg_parser", {
            "ArgumentParser": ArgumentParser,
            "parse_arguments": parse_arguments,
        }),
    )
    sys.modules.setdefault(
        "utils.strings",
        _mk_module("utils.strings", {"Strings": Strings}),
    )
    sys.modules.setdefault(
        "utils.helpers",
        _mk_module("utils.helpers", dict(_HELPERS_FUNCS)),
    )
    sys.modules.setdefault(
        "utils.custom_placeholders",
        _mk_module("utils.custom_placeholders", {
            "register_placeholder": register_placeholder,
            "unregister_placeholder": unregister_placeholder,
            "unregister_scope": unregister_scope,
            "resolve_placeholders": resolve_placeholders,
            "format_placeholders": format_placeholders,
            "register_decorated_placeholders": register_decorated_placeholders,
            "get_placeholders": get_placeholders,
            "list_placeholder_keys": list_placeholder_keys,
            "placeholders": placeholders,
            "config_placeholders": config_placeholders,
        }),
    )
    sys.modules.setdefault(
        "utils.restart",
        _mk_module("utils.restart", {"restart_kernel": restart_kernel}),
    )
    sys.modules.setdefault(
        "utils.html_parser",
        _mk_module("utils.html_parser", {
            "parse_html": parse_html,
            "telegram_to_html": telegram_to_html,
        }),
    )
    sys.modules.setdefault(
        "utils.emoji_parser",
        _mk_module("utils.emoji_parser", {
            "is_emoji_tag": lambda t: False,
            "parse_to_entities": lambda t: (t, []),
        }),
    )
    sys.modules.setdefault(
        "utils.platform",
        _mk_module("utils.platform", {
            "is_termux": lambda: True,
            "is_mobile": lambda: True,
            "is_desktop": lambda: False,
            "is_docker": lambda: False,
            "is_vds": lambda: False,
            "is_wsl": lambda: False,
            "is_virtualized": lambda: False,
            "get_platform": lambda: "termux",
            "get_platform_name": lambda: "Termux",
            "get_platform_info": lambda: {"platform": "termux"},
            "PlatformDetector": type("PlatformDetector", (), {}),
        }),
    )

    # utils.placeholders — прокси к core.lib.loader.placeholders (он есть в Hydra)
    if "utils.placeholders" not in sys.modules:
        try:
            from core.lib.loader import placeholders as _ph
            sys.modules["utils.placeholders"] = _ph
        except Exception:
            sys.modules["utils.placeholders"] = _mk_module(
                "utils.placeholders", {
                    "register_placeholder": register_placeholder,
                    "resolve_placeholders": resolve_placeholders,
                    "unregister_scope": unregister_scope,
                },
            )

    _injected = True
    logger.info("MCUB utils API инъектирован в пакет utils")
    return True

