"""L2 — адаптеры Hikka-подобных фреймворков: Hikka, Heroku, Dragon.

Все три пишутся против `from <pkg> import loader` с loader.Module и
декораторами loader.command()/loader.watcher(). Подмена sys.modules
позволяет скомпилировать и выполнить такой модуль без установки фреймворка.
"""

from __future__ import annotations

import html as _html
import logging
import re
import sys
import types
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("hydra_kernel.compat.frameworks")

from .base import ClientProxy, CompatAdapter, DbShim
from ..api.decorators import META_ATTR
from ..api.inline import CallbackQueryEvent
from ..api.module_base import ModuleBase


def _strip_cmd(name: str) -> str:
    return name[: -len("cmd")] if name.endswith("cmd") else name


def html_escape_off(text: str) -> str:
    """utils.escape в hikka — это экранирование; держим обе семантики."""
    return _html.escape(str(text))


def html_escape_on(text: str) -> str:
    return _html.escape(str(text))


def get_inner_text(message: Any) -> str:
    return getattr(message, "text", "") or ""


class KeyFallbackDict(dict):
    """self.strings['missing'] -> 'missing' (поведение hikka/MCUB).

    Настоящие модули ещё и вызывают strings("key", **kw) — поддерживаем.
    """

    def __missing__(self, key: str) -> str:
        return key

    def __call__(self, key: str, **kw: Any) -> str:
        value = self.get(key, key)
        if isinstance(value, dict):
            return str(value)
        try:
            return str(value).format(**kw) if kw else str(value)
        except (KeyError, IndexError, ValueError):
            return str(value)


class SyncDbShim:
    """Синхронный self.db/self._db как в Heroku (Database с sync-фасадом)."""

    def __init__(self, db: Any, ns: str = "heroku"):
        self._db = db
        self._ns = ns

    def get(self, key: str, *rest: Any) -> Any:
        # get(key[, default]) или get(ns, key[, default]) — как зовут модули
        if len(rest) == 2:
            return self._db.get_sync(key, rest[0], rest[1])
        default = rest[0] if rest else None
        return self._db.get_sync(self._ns, key, default)

    def set(self, key: str, *rest: Any) -> None:
        if len(rest) == 2:  # set(ns, key, value)
            self._db.set_sync(key, rest[0], rest[1])
        elif len(rest) == 1:  # set(key, value)
            self._db.set_sync(self._ns, key, rest[0])

    # hikka-модули иногда ждут и async-вариант
    async def aget(self, key: str, default: Any = None) -> Any:
        return self.get(key, default)


def chunks(lst: List[Any], n: int) -> List[List[Any]]:
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def check_url(text: Any) -> bool:
    return bool(re.match(r"https?://", str(text or "")))


def get_args_raw(message: Any) -> str:
    text = getattr(message, "text", "") or ""
    parts = text.split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


def get_lang_flag(lang: str) -> str:
    lang = (lang or "").strip().lower()[:2]
    if len(lang) != 2 or not lang.isalpha():
        return "🏴"
    points = [ord(c) % 32 + 0x1F1E6 for c in lang]
    return chr(points[0]) + chr(points[1])


class LoaderShim:
    """Объект `loader` чужого фреймворка."""

    SHIM_META = "_shim_meta"

    class Module:
        strings: Dict[str, Any] = {}

    def __init__(self, hydra: Any):
        self.h = hydra

    def command(self, name: Optional[str] = None):
        def deco(fn: Any) -> Any:
            setattr(
                fn,
                self.SHIM_META,
                {"kind": "command", "name": name or _strip_cmd(fn.__name__)},
            )
            return fn

        return deco

    def watcher(self, **kw: Any):
        def deco(fn: Any) -> Any:
            setattr(fn, self.SHIM_META, {"kind": "watcher", **kw})
            return fn

        return deco

    def inline_handler(self, name: str):
        def deco(fn: Any) -> Any:
            setattr(fn, self.SHIM_META, {"kind": "inline", "name": name})
            return fn

        return deco

    def callback(self, prefix: str):
        def deco(fn: Any) -> Any:
            setattr(fn, self.SHIM_META, {"kind": "callback", "prefix": prefix})
            return fn

        return deco

    # Heroku-специфика
    def callback_handler(self, prefix: str):
        return self.callback(prefix)

    def loop(self, interval: float = 60):
        def deco(fn: Any) -> Any:
            setattr(fn, self.SHIM_META, {"kind": "loop", "interval": interval})
            return fn

        return deco

    def ratelimit(self, limit: int = 0, *args: Any, **kw: Any):
        """В ядре rate-limit аппроксимируется no-op."""
        if callable(limit):
            return limit

        def deco(fn: Any) -> Any:
            return fn

        return deco

    def tag(self, *args: Any, **kw: Any):
        def deco(fn: Any) -> Any:
            return fn

        return deco


class InlineShim:
    """self.inline для Hikka-подобных: form/gallery/list с callable-кнопками.

    Кнопка {"text":..., "callback": fn} получает уникальный data-префикс,
    нажатие (inject_callback) вызывает fn(call, *args) — семантика hikka.
    """

    def __init__(self, hydra: Any, module_name: str):
        self.h = hydra
        self.module_name = module_name
        self._n = 0
        self.bot_username = "hydra_bot"

    def _register(self, cb: Any, args: Any) -> str:
        self._n += 1
        token = f"{self.module_name}_ik{self._n}:"

        async def wrapper(call: Any, _cb: Any = cb, _args: Any = args) -> None:
            await _cb(call, *_args)

        self.h.register_callback(token, wrapper)
        return token

    def _convert_markup(self, reply_markup: Any) -> Any:
        rows = []
        bridge = getattr(self.h, "bridge", None)
        for row in reply_markup or []:
            new_row = []
            for btn in row:
                if isinstance(btn, dict):
                    text = btn.get("text", "?")
                    cb = btn.get("callback")
                    url = btn.get("url")
                    if callable(cb):
                        new_row.append({"text": text, "data": self._register(cb, btn.get("args", ()))})
                    elif callable(btn.get("input")) and bridge is not None:
                        self._n += 1
                        token = f"{self.module_name}_in{self._n}:"
                        bridge.register_input(token, btn["input"], btn.get("args", ()))
                        new_row.append({"text": text, "data": token, "input": True})
                    elif url:
                        new_row.append({"text": text, "url": url})
                    else:
                        new_row.append({"text": text, "data": btn.get("data")})
                else:
                    new_row.append(btn)
            rows.append(new_row)
        return rows

    async def form(self, text: str, message: Any, reply_markup: Any = None, **kw: Any) -> Any:
        chat_id = message if isinstance(message, int) else getattr(message, "chat_id", 0)
        return await self.h.transport.send(int(chat_id), text, buttons=self._convert_markup(reply_markup))

    async def gallery(self, text: str, message: Any, reply_markup: Any = None, **kw: Any) -> Any:
        return await self.form(text, message, reply_markup, **kw)

    async def list(self, text: str, message: Any, reply_markup: Any = None, **kw: Any) -> Any:
        return await self.form(text, message, reply_markup, **kw)

    def generate_markup(self, buttons: Any) -> Any:
        return self._convert_markup(buttons)


class HikkaLikeAdapter(CompatAdapter):
    pkg = "hikka"

    def install(self) -> None:
        root = self._put_module(self.pkg)
        loader_mod = self._put_module(f"{self.pkg}.loader")
        utils_mod = self._put_module(f"{self.pkg}.utils")
        db_mod = self._put_module(f"{self.pkg}.db")

        self.shim = LoaderShim(self.h)
        root.loader = loader_mod
        root.utils = utils_mod
        root.db = db_mod
        loader_mod.Module = self.shim.Module
        loader_mod.command = self.shim.command
        loader_mod.watcher = self.shim.watcher
        loader_mod.tds = lambda cls: cls  # translatable docstring marker
        from ..api.config import ModuleConfig, ConfigValue

        loader_mod.ModuleConfig = ModuleConfig
        loader_mod.ConfigValue = ConfigValue
        loader_mod.inline_handler = self.shim.inline_handler
        loader_mod.callback = self.shim.callback
        loader_mod.callback_handler = self.shim.callback_handler
        loader_mod.loop = self.shim.loop
        loader_mod.ratelimit = self.shim.ratelimit
        loader_mod.tag = self.shim.tag
        loader_mod.validators = self._make_validators()

        # настоящие hikka-модули: hikkatl = их форк telethon — алиас
        import importlib
        import sys as _sys

        try:
            # Используем реальный Telethon, а при офлайн-сборке — совместимый
            # shim. Не полагаемся на то, что атрибут ``tl`` уже материализован.
            from .offline_deps import ensure_offline_dependencies

            ensure_offline_dependencies()
            tel = importlib.import_module("telethon")
            for dotted, mod in (
                ("hikkatl", tel),
                ("hikkatl.tl", tel.tl),
                ("hikkatl.tl.types", tel.tl.types),
                ("hikkatl.tl.functions", tel.tl.functions),
                ("hikkatl.utils", tel.utils),
                ("hikkatl.events", tel.events),
                ("hikkatl.errors", tel.errors),
            ):
                _sys.modules.setdefault(dotted, mod)
        except (ImportError, AttributeError):
            # Адаптер не требует Telethon для простых Hikka/Heroku-модулей.
            pass

        async def edit_or_reply(event: Any, text: str, **kw: Any) -> Any:
            try:
                return await event.edit(text, **kw)
            except Exception:  # noqa: BLE001
                return await event.reply(text, **kw)

        self.utils_inline = InlineShim(self.h, "utils")
        utils_mod.edit_or_reply = edit_or_reply
        utils_mod.reply = edit_or_reply
        utils_mod.escape = html_escape_off
        utils_mod.escape_html = html_escape_on
        utils_mod.get_inner_text = get_inner_text
        utils_mod.chunks = chunks
        utils_mod.check_url = check_url
        utils_mod.get_args_raw = get_args_raw
        utils_mod.get_lang_flag = get_lang_flag
        utils_mod.get_base_dir = lambda: "."
        utils_mod.answer = self._make_answer()
        db_mod.MemoryDB = type(self.h.db)

        if self.pkg == "heroku":
            self._install_heroku_context(root)

    @staticmethod
    def _make_validators() -> Any:
        """loader.validators.* как в hikka: валидаторы-заглушки."""
        import types as _types

        class _Validator:
            def __init__(self, *args: Any, **kw: Any) -> None:
                self.args, self.kw = args, kw

            def validate(self, value: Any, config: Any = None) -> Any:
                return value

        ns = _types.SimpleNamespace()
        for vname in (
            "Boolean", "Integer", "Float", "String", "Choice", "Series",
            "Union", "NoneType", "Link", "RegExp", "Emoji", "TelegramID",
            "EntityLike", "Placeholders",
        ):
            setattr(ns, vname, type(vname, (_Validator,), {}))
        return ns

    def _make_answer(self):
        inline_shim = InlineShim(self.h, "utils")

        async def answer(message: Any, response: Any = None, *, reply_markup: Any = None, **kw: Any) -> Any:
            if response is None:
                response = kw.pop("text", "")
            if isinstance(message, CallbackQueryEvent):
                return await message.edit(response)
            chat_id = message if isinstance(message, int) else getattr(message, "chat_id", 0)
            return await inline_shim.form(response, chat_id, reply_markup=reply_markup)

        return answer

    def _install_heroku_context(self, root: Any) -> None:
        """Пакетный контекст Heroku: heroku.translations/version/main/inline,
        herokutl — чтобы настоящие модули (from .. import ...) исполнялись."""
        trans = self._put_module(f"{self.pkg}.translations")
        trans.SUPPORTED_LANGUAGES = {
            "en": "🇬 English",
            "ru": "🇷🇺 Русский",
            "uk": "🇺🇦 Українська",
            "de": "🇩🇪 Deutsch",
            "fr": "🇫🇷 Français",
            "ja": "🇯🇵 日本語",
        }
        trans.MEME_LANGUAGES = {"tt": "🥟 Tatar", "uz": "🇺🇿 Uzbek"}
        trans.normalize_language = lambda l: (l or "").lower()[:2]
        trans.normalize_language_token = lambda t: (t or "").lower()
        root.translations = trans

        ver = self._put_module(f"{self.pkg}.version")
        ver.VERSION = "1.7.2-hydra"
        root.version = ver

        main = self._put_module(f"{self.pkg}.main")
        main.Modules = object
        root.main = main

        inline_pkg = self._put_module(f"{self.pkg}.inline")
        inline_types = self._put_module(f"{self.pkg}.inline.types")
        inline_types.InlineCall = CallbackQueryEvent
        inline_pkg.types = inline_types
        root.inline = inline_pkg

        herokutl = self._put_module("herokutl")
        tl = self._put_module("herokutl.tl")
        tl_types = self._put_module("herokutl.tl.types")

        class _Msg:
            pass

        tl_types.Message = _Msg
        tl_types.User = _Msg
        tl.types = tl_types
        herokutl.tl = tl
        ext = self._put_module("herokutl.extensions")
        ext.html = types.SimpleNamespace(escape=_html.escape, unescape=_html.unescape)
        herokutl.extensions = ext

    def _allmodules(self, name: str) -> Any:
        async def reload_translations() -> bool:
            return True

        return types.SimpleNamespace(
            db=SyncDbShim(self.h.db, name),
            client=ClientProxy(self.h.transport),
            lookup=self._lookup,
            get_prefix=lambda: self.h.prefix,
            get_prefixes=lambda: {self.h.prefix},
            inline=InlineShim(self.h, name),
            allclients=[],
            commands=self.h.command_handlers,
            reload_translations=reload_translations,
        )

    async def load_source(self, name: str, source: str) -> Tuple[Any, Any]:
        dotted = f"{self.pkg}.modules.{name}"
        ns = self.exec_source(dotted, source, package=f"{self.pkg}.modules")
        cls = None
        for value in ns.values():
            if (
                isinstance(value, type)
                and issubclass(value, self.shim.Module)
                and value is not self.shim.Module
                and getattr(value, "__module__", "") == dotted
            ):
                cls = value
                break
        if cls is None:
            raise ValueError(f"{self.pkg}: в модуле нет подкласса loader.Module")

        foreign = cls()
        foreign.allmodules = self._allmodules(name)
        if hasattr(foreign, "internal_init"):
            foreign.internal_init()  # как в Heroku: раздаёт client/db/inline
        foreign.client = ClientProxy(self.h.transport)
        foreign._client = foreign.client  # hikka-модули зовут self._client
        foreign._db = SyncDbShim(self.h.db, name)
        if not isinstance(getattr(foreign, "db", None), SyncDbShim):
            foreign.db = foreign._db
        foreign.get_prefix = lambda: self.h.prefix
        foreign.get_prefixes = lambda: {self.h.prefix}
        foreign.lookup = self._lookup
        foreign.translate = lambda key, **kw: key
        foreign.inline = InlineShim(self.h, name)
        strings = getattr(cls, "strings", None)
        foreign.strings = KeyFallbackDict(strings if isinstance(strings, dict) else {})
        foreign.strings.setdefault("name", name)

        wrapped = ModuleBase(self.h.make_context(name))
        wrapped.name = name
        wrapped._foreign = foreign
        for attr in dir(cls):
            fn = getattr(cls, attr, None)
            meta = getattr(fn, LoaderShim.SHIM_META, None)
            if not callable(fn) or meta is None:
                continue
            bound = getattr(foreign, attr)
            l1_meta = self._to_l1(meta)

            async def handler(event: Any, _bound=bound) -> None:
                await _bound(event)

            handler.__name__ = f"shim_{attr}"
            setattr(handler, META_ATTR, l1_meta)
            setattr(wrapped, f"_{attr}", handler)

        lifecycle = await self.h.load_module(wrapped)
        return wrapped, lifecycle

    @staticmethod
    def _to_l1(meta: Dict[str, Any]) -> Dict[str, Any]:
        if meta["kind"] == "command":
            return {
                "kind": "command",
                "name": meta["name"],
                "aliases": tuple(meta.get("aliases", ())),
                "desc": meta.get("desc", ""),
                "required_level": meta.get("required_level", 1),
            }
        if meta["kind"] in ("inline", "callback"):
            return dict(meta)
        return {
            "kind": "watcher",
            "pattern": meta.get("pattern"),
            "incoming": meta.get("incoming", True),
            "outgoing": meta.get("outgoing", False),
            "chats": meta.get("chats"),
        }

    def _lookup(self, module_name: str) -> Any:
        rec = self.h.registry.get(module_name) or self.h.registry.get(module_name.lower())
        return rec.module if rec else None

    @staticmethod
    async def _anoop(*args: Any, **kw: Any) -> None:
        return None


class HikkaAdapter(HikkaLikeAdapter):
    framework = "hikka"
    pkg = "hikka"


class HerokuAdapter(HikkaLikeAdapter):
    framework = "heroku"
    pkg = "heroku"


class DragonAdapter(HikkaLikeAdapter):
    framework = "dragon"
    pkg = "dragon"

    def install(self) -> None:
        super().install()
        # настоящие модули Dragon пишутся под pyrogram
        from .pyrogram_shim import install as pg_install

        self._pg_client = pg_install()

        import importlib

        try:
            misc = importlib.import_module("utils.misc")
        except ImportError:
            misc = self._put_module("utils.misc")
        if not hasattr(misc, "modules_help"):
            misc.modules_help = {}
        if not hasattr(misc, "prefix"):
            misc.prefix = self.h.prefix
        if "utils.db" not in sys.modules:
            try:
                importlib.import_module("utils.db")
            except ImportError:
                self._put_module("utils.db")

    async def load_source(self, name: str, source: str) -> Tuple[Any, Any]:
        self._pg_client.registry.clear()
        try:
            return await super().load_source(name, source)
        except ValueError:
            pass
        entries = list(self._pg_client.registry)
        if not entries:
            raise ValueError(f"dragon:{name}: ни loader.Module, ни pyrogram-хендлеров")

        import re

        from .pyrogram_shim import extract

        client_stub = ClientProxy(self.h.transport)
        unsubs = []
        for fn, flt in entries:
            commands, me, prefix = extract(flt)

            async def wrapper(event: Any, _fn=fn) -> None:
                try:
                    await _fn(client_stub, event)
                except Exception as e:  # noqa: BLE001
                    logger.error("dragon %s failed: %s", name, e)

            if commands:
                alts = "|".join(re.escape(c) for c in commands)
                pattern = rf"(?i)^{re.escape(prefix)}(?:{alts})(?:\s|$)"
                unsubs.append(
                    self.h.transport.subscribe(
                        wrapper,
                        pattern=pattern,
                        incoming=me is not True,   # filters.me = исходящие
                        outgoing=me is not False,
                    )
                )
            else:
                unsubs.append(
                    self.h.transport.subscribe(
                        wrapper, pattern=None, incoming=True, outgoing=False
                    )
                )

        stub = types.SimpleNamespace(name=name, _pyrogram=True, _unsubs=unsubs)
        return stub, None
