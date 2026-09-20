# core/lib/loader/module_base.py
# Полный порт MCUB-fork ModuleBase для Hydra (mcub_engine).
# Оригинал: MCUB-fork by MItrich && hairpin01 (MIT).
# Сохранена обратная совместимость со старым эмулятором Hydra
# (KernelMock / StringsMock / DBMock / LoopHandle).
"""
Модули MCUB импортируют отсюда:
    from core.lib.loader.module_base import ModuleBase, command, inline, callback, ...
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .decorators import (
    bot_command,
    callback,
    command,
    error_handler,
    event,
    inline,
    inline_temp,
    loop,
    method,
    on_install,
    on_uninstall,
    owner_only,
    permissions,
    watcher,
)

# Алиас для совместимости с документацией MCUB
permission = permissions

# Реэкспорт валидаторов (старые Hydra-модули импортируют их отсюда)
from .module_config import (
    Boolean,
    Choice,
    ConfigValue,
    DictType,
    Emoji,
    EntityLike,
    Float,
    Hidden,
    Integer,
    Link,
    List,
    ModuleConfig,
    MultiChoice,
    NoneType,
    Placeholders,
    RegExp,
    Secret,
    String,
    TelegramID,
    Union,
    ValidationError,
    Validator,
)


# ============================================================
# BACKWARD COMPAT (старый эмулятор Hydra)
# ============================================================

class LoopHandle:
    def __init__(self, func, interval, autostart):
        self._func = func
        self._interval = interval
        self._autostart = autostart
        self._task = None
        self._running = False

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run())

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run(self):
        while self._running:
            try:
                await self._func()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.getLogger("loop").error(f"Loop error: {e}")
            await asyncio.sleep(self._interval)


class StringsMock:
    def __init__(self, d): self.d = d or {}
    def __getitem__(self, k): return self.d.get(k, k)
    def __call__(self, k, **kw): return self.d.get(k, k).format(**kw)
    def get(self, k, default=None): return self.d.get(k, default or k)


class DBMock:
    _storage = {}
    async def db_get(self, module, key): return DBMock._storage.get(f"{module}:{key}", None)
    async def db_set(self, module, key, value): DBMock._storage[f"{module}:{key}"] = value


class KernelMock:
    """Ленивый мок ядра для модулей, созданных вне движка."""

    def __init__(self, parent_module=None):
        self.parent_module = parent_module
        self.config = {'language': 'ru', 'inline_bot_username': 'bot'}
        self.custom_prefix = '.'
        self.logger = logging.getLogger('mcub_kernel')

    @property
    def client(self):
        if getattr(self.parent_module, 'client', None):
            return self.parent_module.client
        try:
            from mcub_engine import get_kernel
            k = get_kernel()
            if k is not None:
                return k.client
        except Exception:
            pass
        return None

    async def get_module_config(self, name, default=None):
        p = Path('data/module_configs.json')
        if p.exists():
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f).get(name, default or {})
            except Exception:
                pass
        return default or {}

    def store_module_config_schema(self, name, config):
        pass

    async def save_module_config(self, name, cfg_dict):
        p = Path('data/module_configs.json')
        p.parent.mkdir(parents=True, exist_ok=True)
        all_cfg = {}
        if p.exists():
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    all_cfg = json.load(f)
            except Exception:
                pass
        all_cfg[name] = cfg_dict
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(all_cfg, f, ensure_ascii=False, indent=2)

    async def db_get(self, m, k): return None
    async def db_set(self, m, k, v): pass
    def is_bot_available(self): return False
    async def handle_error(self, *a, **kw): pass


# ============================================================
# STRINGS (упрощённый аналог utils.strings.Strings из MCUB)
# ============================================================

class _NestedGroup:
    """Группа вложенных строк: g('key') / g.get('key', def)."""

    def __init__(self, data: dict):
        self._data = data or {}

    def __call__(self, key: str, **kwargs):
        val = self._data.get(key, key)
        if isinstance(val, dict):
            return _NestedGroup(val)
        try:
            return str(val).format(**kwargs)
        except Exception:
            return str(val)

    def get(self, key: str, default=None):
        val = self._data.get(key)
        if val is None:
            return default if default is not None else key
        return _NestedGroup(val) if isinstance(val, dict) else val

    def __getitem__(self, key: str):
        return self(key)

    def has(self, key: str) -> bool:
        return key in self._data


class Strings:
    """Локализованные строки модуля: strings['ru']['key'] / strings('key')."""

    def __init__(self, kernel, strings_dict: dict, locale: str | None = None):
        self._kernel = kernel
        self._dict = strings_dict or {}
        if locale:
            self.locale = locale
        else:
            try:
                cfg = getattr(kernel, 'config', None)
                self.locale = cfg.get('language', 'ru') if hasattr(cfg, 'get') else 'ru'
            except Exception:
                self.locale = 'ru'

    def _lang_dict(self) -> dict:
        d = self._dict
        if self.locale in d and isinstance(d[self.locale], dict):
            return d[self.locale]
        for fallback in ('ru', 'en'):
            if fallback in d and isinstance(d[fallback], dict):
                return d[fallback]
        return d

    def _external_pack(self) -> dict:
        """Единый движок: языковые паки ядра (GLOBAL/MODULE) как fallback."""
        try:
            from hydra_kernel.api import lang as _lang
        except Exception:
            return {}
        mod = (self._dict or {}).get('name') or getattr(self._kernel, 'module_name', None)
        merged: dict = {}
        for pack in (_lang.GLOBAL_PACK, _lang.MODULE_PACKS.get(mod or '', {})):
            loc = pack.get(self.locale) or pack.get('ru') or {}
            for k, v in loc.items():
                merged.setdefault(k, v)
        # Паки MCUB-fork (core.langpacks) идут поверх встроенных: там лежат
        # строки модуля и общие группы (кнопки, ошибки), как в utils.strings.
        if mod:
            try:
                from core.langpacks import get_module_strings

                pack_strings = get_module_strings(str(mod), self.locale)
            except Exception:  # noqa: BLE001 - паки опциональны
                pack_strings = {}
            if isinstance(pack_strings, dict):
                merged.update(pack_strings)
        # ``tools/build_native.py`` may leave an older compiled api.lang
        # extension in place until the end of a build.  Real MCUB UpdatesMod
        # invokes this nested group during startup, so retain the essential
        # compatibility fallback even if that stale extension predates it.
        if not isinstance(merged.get("material_emoji"), dict):
            merged["material_emoji"] = {
                "process_bar_pr_1": "▰",
                "process_bar_pr_2": "▰",
                "process_bar_pr_3": "▰",
                "load_3": "🔭",
            }
        return merged

    @property
    def _active(self) -> dict:
        """Активный словарь строк текущей локали (как в настоящем MCUB)."""
        merged = dict(self._external_pack())
        merged.update(self._lang_dict())
        return merged

    def __call__(self, key: str, **kwargs):
        val = self._lang_dict().get(key)
        if val is None:
            val = self._external_pack().get(key, key)
        if isinstance(val, dict):
            return _NestedGroup(val)
        if kwargs:
            try:
                return str(val).format(**kwargs)
            except Exception:
                return str(val)
        return str(val)

    def __getitem__(self, key: str):
        return self(key)

    def get(self, key: str, default=None):
        val = self._lang_dict().get(key)
        if val is None:
            val = self._external_pack().get(key)
        if val is None:
            return default if default is not None else key
        return _NestedGroup(val) if isinstance(val, dict) else val

    def keys(self):
        return self._lang_dict().keys()

    @staticmethod
    def validate(strings_dict: dict) -> list:
        problems = []
        if not isinstance(strings_dict, dict):
            return ["strings is not a dict"]
        return problems


# ============================================================
# MODULE BASE (порт MCUB-fork core/lib/loader/base.py)
# ============================================================

class _ModuleLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"[{self.extra.get('module_name', 'Unnamed')}] {msg}", kwargs


class ModuleBase:
    """Базовый класс для class-style модулей MCUB."""

    name: str = "Unnamed"
    version: str = "1.0.0"
    author: str = "unknown"
    description: dict = {}
    dependencies: list = []
    banner_url: str | None = None

    strings: dict = {}
    config: Any = None

    _cmd_registry: list = []
    _inline_registry: list = []
    _callback_registry: list = []
    _watcher_registry: list = []
    _loop_registry: list = []
    _event_registry: list = []
    _method_registry: list = []
    _on_install_registry: list = []
    _uninstall_registry: list = []
    _bot_cmd_registry: list = []
    _owner_registry: list = []
    _permission_registry: list = []
    _error_handler_registry: list = []
    _inline_temp_registry: list = []

    def __getattribute__(self, name: str) -> Any:
        if name == "config":
            try:
                return object.__getattribute__(self, "_get_config")()
            except AttributeError:
                pass
        if name == "strings":
            try:
                return object.__getattribute__(self, "_get_strings")()
            except AttributeError:
                pass
        return object.__getattribute__(self, name)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._cmd_registry = []
        cls._inline_registry = []
        cls._callback_registry = []
        cls._watcher_registry = []
        cls._loop_registry = []
        cls._event_registry = []
        cls._method_registry = []
        cls._on_install_registry = []
        cls._uninstall_registry = []
        cls._bot_cmd_registry = []
        cls._owner_registry = []
        cls._permission_registry = []
        cls._error_handler_registry = []
        cls._inline_temp_registry = []

        for _name_attr, attr in cls.__dict__.items():
            if not callable(attr):
                continue
            if hasattr(attr, "_mcub_commands"):
                for pattern, kwargs_cmd in attr._mcub_commands:
                    cls._cmd_registry.append((pattern, attr, kwargs_cmd))
            if hasattr(attr, "_mcub_inline"):
                for pattern in attr._mcub_inline:
                    cls._inline_registry.append((pattern, attr))
            if hasattr(attr, "_mcub_callbacks"):
                for cb_info in attr._mcub_callbacks:
                    cls._callback_registry.append((attr, cb_info["ttl"]))
            if hasattr(attr, "_mcub_watchers"):
                for watcher_info in attr._mcub_watchers:
                    cls._watcher_registry.append(
                        (attr, watcher_info["bot_client"], watcher_info["tags"])
                    )
            if hasattr(attr, "_mcub_loops"):
                for loop_info in attr._mcub_loops:
                    cls._loop_registry.append(
                        (attr, loop_info["interval"], loop_info["autostart"], loop_info["wait_before"])
                    )
            if hasattr(attr, "_mcub_events"):
                for event_info in attr._mcub_events:
                    cls._event_registry.append(
                        (attr, event_info["event_type"], event_info["args"],
                         event_info["bot_client"], event_info["kwargs"])
                    )
            if hasattr(attr, "_mcub_methods"):
                cls._method_registry.append(attr)
            if hasattr(attr, "_mcub_inline_temp"):
                for temp_info in attr._mcub_inline_temp:
                    cls._inline_temp_registry.append(
                        (attr, temp_info["ttl"], temp_info.get("allow_user"),
                         temp_info.get("allow_ttl"), temp_info["article"], temp_info["data"])
                    )
            if hasattr(attr, "_mcub_on_install"):
                cls._on_install_registry.append(attr)
            if hasattr(attr, "_mcub_uninstall"):
                cls._uninstall_registry.append(attr)
            if hasattr(attr, "_mcub_bot_commands"):
                for cmd_info in attr._mcub_bot_commands:
                    cls._bot_cmd_registry.append((attr, cmd_info))
            if hasattr(attr, "_mcub_owner"):
                for owner_info in attr._mcub_owner:
                    cls._owner_registry.append((attr, owner_info))
            if hasattr(attr, "_mcub_permissions"):
                for permission_info in attr._mcub_permissions:
                    cls._permission_registry.append((attr, permission_info))
            if hasattr(attr, "_mcub_error_handler"):
                for handler_info in attr._mcub_error_handler:
                    cls._error_handler_registry.append((attr, handler_info))

    # --------------------------------------------------------
    # INIT — регистрация всех декорированных методов
    # --------------------------------------------------------

    def __init__(self, kernel=None, client=None, register=None):
        # Совместимость: старые Hydra-модули вызывают ModuleBase() без аргументов
        if kernel is None:
            kernel = KernelMock(self)
        self.kernel = kernel
        self._register = register or getattr(kernel, "register", None)
        self.client = client if client is not None else getattr(kernel, "client", None)

        self._loaded = False
        self._loops = []
        self._watchers = []
        self._uninstall_funcs = []
        self._on_install_funcs = []
        self._method_funcs = []
        self._callback_tokens = []
        self._inline_temp_ids = {}

        self._config = None
        self.name = type(self).name
        self.log = _ModuleLoggerAdapter(
            getattr(kernel, "logger", logging.getLogger("mcub")),
            {"module_name": self.name},
        )

        self.db = getattr(kernel, "db_manager", None) or DBMock()
        self.cache = getattr(kernel, "cache", None)

        # config / strings из класса
        module_class = type(self)
        for klass in module_class.__mro__:
            if "config" in klass.__dict__:
                val = klass.__dict__["config"]
                if not isinstance(val, property):
                    self._config = val
                    break

        self._strings = None
        strings_dict = None
        for klass in module_class.__mro__:
            if "strings" in klass.__dict__:
                val = klass.__dict__["strings"]
                if not isinstance(val, property):
                    strings_dict = val
                    break
        if strings_dict:
            try:
                self._strings = Strings(self.kernel, strings_dict)
            except Exception as e:
                self.log.error(f"strings init failed: {e}")

        # авторегистрация @utils.placeholders-декорированных методов
        try:
            from mcub_engine.utils_inject import register_decorated_placeholders
            register_decorated_placeholders(self.name, self)
        except Exception:
            pass

        if self._register is None:
            return  # standalone-режим без ядра

        owner_map = {}
        for func, owner_info in module_class._owner_registry:
            owner_map[func.__name__] = owner_info

        permission_map: dict[str, dict[str, Any]] = {}
        for func, permission_info in module_class._permission_registry:
            permission_map.setdefault(func.__name__, {}).update(permission_info)

        error_handler_map: dict[str, dict[str, Any]] = {}
        for func, handler_info in module_class._error_handler_registry:
            error_handler_map[func.__name__] = handler_info

        # --- команды ---
        for pattern, func, kwargs_cmd in module_class._cmd_registry:
            method_name = func.__name__

            async def wrapper(event, f=func, instance=self,
                              permission_tags=permission_map.get(method_name),
                              err_handler=error_handler_map.get(method_name)):
                if permission_tags and not instance._passes_permission_tags(event, permission_tags):
                    return
                if err_handler:
                    return await instance._run_with_error_handler(f, instance, event, err_handler)
                return await f(instance, event)

            wrapper.__original__ = func

            if method_name in owner_map:
                only_admin = owner_map[method_name].get("only_admin", False)

                async def owner_wrapper(event, f=wrapper, only_admin=only_admin):
                    sender_id = getattr(event, "sender_id", None)
                    if sender_id is None or not self.kernel.is_admin(int(sender_id)):
                        return
                    return await f(event)

                owner_wrapper.__original__ = func
                self._register.command(pattern, **kwargs_cmd)(owner_wrapper)
            else:
                self._register.command(pattern, **kwargs_cmd)(wrapper)

        # --- инлайн-хендлеры ---
        for pattern, func in module_class._inline_registry:
            async def inline_wrapper(event, f=func):
                return await f(self, event)

            inline_wrapper.__original__ = func
            self.kernel.register_inline_handler(pattern, inline_wrapper)

        # --- колбэки ---
        for func, ttl in module_class._callback_registry:
            self._register_callback(func, ttl)

        # --- циклы ---
        for func, interval, autostart, wait_before in module_class._loop_registry:
            self._register_loop(func, interval, autostart, wait_before)

        # --- вотчеры ---
        for func, bot_client, tags in module_class._watcher_registry:
            self._register_watcher(func, bot_client,
                                   permission_tags=permission_map.get(func.__name__),
                                   **tags)

        # --- кастомные события ---
        for func, event_type, args, bot_client, kwargs in module_class._event_registry:
            self._register_event(func, event_type, *args, bot_client=bot_client,
                                 permission_tags=permission_map.get(func.__name__),
                                 **kwargs)

        # --- методы установки ---
        for func in module_class._method_registry:
            self._method_funcs.append(func)

        # --- inline_temp ---
        for func, ttl, allow_user, allow_ttl, article, data in module_class._inline_temp_registry:
            form_id = self._register_inline_temp(func, ttl, allow_user, allow_ttl, article, data)
            self._inline_temp_ids[f"{self.name}:{func.__name__}"] = form_id

        for func in module_class._on_install_registry:
            self._on_install_funcs.append(func)
        for func in module_class._uninstall_registry:
            self._uninstall_funcs.append(func)

        # --- bot commands (без бота — только регистрируем) ---
        for func, cmd_info in module_class._bot_cmd_registry:
            if isinstance(cmd_info, tuple) and len(cmd_info) == 2:
                pattern, cmd_meta = cmd_info
            elif isinstance(cmd_info, dict):
                pattern, cmd_meta = cmd_info.get("pattern"), cmd_info
            else:
                continue
            if not pattern:
                continue
            kwargs_cmd = {k: v for k, v in {
                "alias": cmd_meta.get("alias"), "doc": cmd_meta.get("doc"),
                "doc_ru": cmd_meta.get("doc_ru"), "doc_en": cmd_meta.get("doc_en"),
            }.items() if v is not None}

            async def bwrapper(event, f=func):
                return await f(self, event)

            bwrapper.__original__ = func
            try:
                self._register.bot_command(pattern, **kwargs_cmd)(bwrapper)
            except Exception:
                pass

    # --------------------------------------------------------
    # ВНУТРЕННИЕ РЕГИСТРАТОРЫ
    # --------------------------------------------------------

    def _passes_permission_tags(self, event, tags: dict) -> bool:
        try:
            from mcub_engine.runtime import watcher_passes_filters
            return watcher_passes_filters(event, tags)
        except Exception as e:
            self.log.warning(f"permission filter failed for {tags}: {e}")
            return False

    async def _run_with_error_handler(self, func, instance, event, handler_config):
        try:
            return await func(instance, event)
        except Exception as e:
            log_level = handler_config.get("log_level", "error")
            message_template = handler_config.get("message")
            log_msg = (message_template.format(exc=str(e), func=func.__name__, module=self.name)
                       if message_template else f"Error in {func.__name__}: {e}")
            getattr(self.log, log_level, self.log.error)(log_msg)
            if handler_config.get("reraise"):
                raise

    def _register_event(self, func, event_type, *args, bot_client=False,
                        permission_tags=None, **kwargs):
        async def bound_wrapper(event):
            if permission_tags and not self._passes_permission_tags(event, permission_tags):
                return
            return await func(self, event)

        bound_wrapper.__original__ = func
        bound_wrapper.__bound_instance__ = self
        self._register.event(event_type, *args, bot_client=bot_client, **kwargs)(bound_wrapper)

    def _register_loop(self, func, interval, autostart, wait_before):
        async def bound_wrapper(kernel=None):
            return await func(self)

        bound_wrapper.__original__ = func
        bound_wrapper.__bound_instance__ = self
        lp = self._register.loop(interval, autostart, wait_before)(bound_wrapper)
        self._loops.append(lp)
        setattr(self, func.__name__, lp)
        return lp

    def _register_watcher(self, func, bot_client=False, permission_tags=None, **tags):
        async def bound_wrapper(event):
            if permission_tags and not self._passes_permission_tags(event, permission_tags):
                return
            return await func(self, event)

        bound_wrapper.__original__ = func
        bound_wrapper.__bound_instance__ = self
        self._watchers.append(bound_wrapper)
        self._register.watcher(bound_wrapper, bot_client=bot_client, **tags)

    def _register_inline_temp(self, func, ttl, allow_user, allow_ttl, article, data):
        async def bound_wrapper(event, args="", cb_data=None):
            return await func(self, event, args, cb_data)

        bound_wrapper.__original__ = func
        bound_wrapper.__bound_instance__ = self
        return self.kernel.register.inline_temp(
            bound_wrapper, ttl=ttl, article=article, data=data,
            allow_user=allow_user, allow_ttl=allow_ttl,
        )

    def inline_temp(self, func, ttl=300, allow_user=None, allow_ttl=100, article=None, data=None):
        async def bound_wrapper(event, *a, **kw):
            return await func(self, event, *a, **kw)

        bound_wrapper.__original__ = func
        bound_wrapper.__bound_instance__ = self
        return self.kernel.register.inline_temp(
            bound_wrapper, ttl=ttl, article=article, data=data,
            allow_user=allow_user, allow_ttl=allow_ttl,
        )

    def get_inline_temp_id(self, method_name: str, module_name: str | None = None) -> str | None:
        key = f"{module_name or self.name}:{method_name}"
        return getattr(self, "_inline_temp_ids", {}).get(key)

    # --------------------------------------------------------
    # CALLBACKS / BUTTONS
    # --------------------------------------------------------

    def _make_class_callback_wrapper(self, func, ttl):
        raw_func = getattr(func, "__original__", func)
        instance = self

        async def wrapper(event, *args, **kwargs):
            bound_to = getattr(raw_func, "__self__", None)
            if bound_to is not None:
                return await raw_func(event, *args, **kwargs)
            return await raw_func(instance, event, *args, **kwargs)

        wrapper.__original__ = func
        wrapper._ttl = ttl
        wrapper._is_class_callback = True
        wrapper._bound_instance = self
        return wrapper

    def _store_callback(self, token, data):
        k = self.kernel
        real = getattr(k, "_kernel", k)
        if not hasattr(real, "inline_callback_map"):
            real.inline_callback_map = {}
        real.inline_callback_map[token] = data
        self._callback_tokens.append(token)

    def _register_callback(self, func, ttl):
        tok = uuid.uuid4().hex
        self._store_callback(tok, {
            "handler": self._make_class_callback_wrapper(func, ttl),
            "args": [], "kwargs": {},
            "expires_at": time.time() + ttl if ttl else None,
        })

    def _make_callback_button(self, text, callback_func, *, ttl=900, allow_user=None,
                              allow_ttl=100, args=(), kwargs=None, data=None,
                              pass_event=True, auto_answer=None, style=None, icon=None,
                              **button_kwargs):
        from telethon import Button
        tok = uuid.uuid4().hex
        self._store_callback(tok, {
            "handler": self._make_class_callback_wrapper(callback_func, ttl),
            "args": list(args or []), "kwargs": dict(kwargs or {}), "data": data,
            "expires_at": time.time() + ttl if ttl else None,
        })
        try:
            return Button.inline(text, tok.encode(), **button_kwargs)
        except TypeError:
            return Button.inline(text, tok.encode())

    @property
    def Button(self):
        if not hasattr(self, "_button_factory"):
            button_class = getattr(type(self), "ButtonFactory", None)
            if isinstance(button_class, type) and issubclass(button_class, ModuleBase.ButtonFactory):
                self._button_factory = button_class(self)
            else:
                self._button_factory = ModuleBase.ButtonFactory(self)
        return self._button_factory

    class ButtonFactory:
        def __init__(self, outer):
            self._outer = outer

        def inline(self, text, callback_func, *, ttl=900, allow_user=None, allow_ttl=100,
                   args=(), kwargs=None, data=None, pass_event=True, auto_answer=None,
                   icon=None, style=None, **btn_kwargs):
            return self._outer._make_callback_button(
                text, callback_func, ttl=ttl, allow_user=allow_user, allow_ttl=allow_ttl,
                args=args, kwargs=kwargs, data=data, pass_event=pass_event,
                auto_answer=auto_answer, style=style, icon=icon, **btn_kwargs,
            )

        def url(self, text, url, *, icon=None, style=None):
            from telethon import Button as TButton
            return TButton.url(text, url)

        def text(self, text, *, resize=True, selective=False, icon=None, style=None):
            from telethon import Button as TButton
            return TButton.text(text, resize=resize, selective=selective)

        def switch(self, text, query="", *, same_peer=True, icon=None, style=None):
            from telethon import Button as TButton
            return TButton.switch_inline(text, query=query, same_peer=same_peer)

        def input(self, text, handler, *, placeholder="", ttl=900, allow_user=None,
                  allow_ttl=100, article=None, data=None, icon=None, style=None):
            temp_uuid = self._outer.kernel.register.inline_temp(
                handler, ttl=ttl, article=article, data=data,
                allow_user=allow_user, allow_ttl=allow_ttl,
            )
            btn = {"_mcub_input": True, "text": text, "uuid": temp_uuid,
                   "placeholder": placeholder}
            return btn

        def close(self, event=None, text=None, handler=None, *, icon=None, style=None,
                  allow_user=None, allow_ttl=100):
            label = text or "❌ Закрыть"

            async def on_close(cb_event, *_a, **_kw):
                try:
                    await cb_event.delete()
                except Exception:
                    pass

            return self.inline(label, handler or on_close, allow_user=allow_user,
                               allow_ttl=allow_ttl, style=style, icon=icon)

        # ---- дополнительные типы кнопок MCUB-fork ----

        def copy(self, text="Copy", copy_text=None, *, icon=None, style=None):
            """Кнопка «скопировать» (Telethon-MCUB Button.copy; fallback — answer)."""
            from telethon import Button as TButton

            factory = getattr(TButton, "copy", None)
            if callable(factory):
                return factory(text, copy_text=copy_text)

            async def _answer_copy(event, *_a, **_kw):
                try:
                    await event.answer(f"📋 {copy_text or ''}")
                except Exception:  # noqa: BLE001
                    pass

            return self.inline(text, _answer_copy)

        def request_phone(self, text="Share Phone", *, request_title=None, icon=None, style=None):
            from telethon import Button as TButton

            factory = getattr(TButton, "request_phone", None)
            if callable(factory):
                return factory(text)
            return {"text": text}

        def request_location(self, text="Share Location", *, request_title=None,
                             live_period=None, icon=None, style=None):
            from telethon import Button as TButton

            factory = getattr(TButton, "request_location", None)
            if callable(factory):
                return factory(text)
            return {"text": text}

        def request_poll(self, text="Create Poll", *, request_title=None, quiz=False,
                         icon=None, style=None):
            from telethon import Button as TButton

            factory = getattr(TButton, "request_poll", None)
            if callable(factory):
                return factory(text)
            return {"text": text}

        def game(self, text, *, game=None, icon=None, style=None):
            from telethon import Button as TButton

            factory = getattr(TButton, "game", None)
            if callable(factory):
                return factory(text)
            return {"text": text}

        def unknown(self, data: bytes, text="Button", *, icon=None, style=None):
            from telethon import Button as TButton

            if isinstance(data, str):
                data = data.encode()
            return TButton.inline(text, data=data)

        def with_icon(self, btn, icon):
            """DEPRECATED в MCUB-fork: используйте параметр icon напрямую."""
            return btn

        def style(self, btn, style):
            """DEPRECATED в MCUB-fork: используйте параметр style напрямую."""
            return btn

        def rich(self):
            """Button.rich() — фабрика кнопок rich-страниц Telegram (MCUB-fork)."""
            return self._outer.RichButtonFactory(self._outer)

    class RichButtonFactory:
        """Фабрика кнопок «rich-страниц» (core.lib.rich_buttons MCUB-fork).

        Спеки используют обычный inline-callback-map, поэтому TTL,
        allow_user и чистка при выгрузке модуля сохраняются.
        """

        def __init__(self, outer):
            self._outer = outer

        def inline(self, text, handler, *, args=(), kwargs=None, ttl=900,
                   allow_user=None, allow_ttl=100, data=None, pass_event=True,
                   auto_answer=None, icon=None, style=None, html_tag=False,
                   **button_kwargs):
            from core.lib.rich_buttons import (
                RichCallbackButton,
                render_rich_button,
                validate_rich_button,
            )

            spec = self._outer._make_callback_button(
                text, handler, ttl=ttl, allow_user=allow_user, allow_ttl=allow_ttl,
                args=args, kwargs=kwargs, data=data, pass_event=pass_event,
                auto_answer=auto_answer,
            )
            token = (
                getattr(spec, "data", None)
                or getattr(spec, "token", None)
                or (spec.get("data") if isinstance(spec, dict) else None)
            )
            if isinstance(token, bytes):
                token = token.decode()
            validate_rich_button(text, str(token), style if style in self._STYLES else None)
            rich_button = RichCallbackButton(
                text, str(token), style=style if style in self._STYLES else None
            )
            return render_rich_button(rich_button) if html_tag else rich_button

        _STYLES = frozenset({"primary", "danger", "success", "link"})
        _ALIGNMENTS = frozenset({"left", "center", "right"})

        def row(self, *buttons, align="center"):
            from core.lib.rich_buttons import (
                RichButtonRow,
                RichCallbackButton,
                RichPageButton,
            )

            if align not in self._ALIGNMENTS:
                raise ValueError("rich button row align must be left, center or right")
            if not buttons:
                raise ValueError("rich button row cannot be empty")
            if len(buttons) > 8:
                raise ValueError("rich button rows support at most 8 buttons")
            if not all(isinstance(b, (RichCallbackButton, RichPageButton)) for b in buttons):
                raise TypeError("rich button rows accept only Button.rich.inline specs")
            return RichButtonRow(tuple(buttons), align=align)

        def _page(self, text, type_, attrs=None, style=None, html_tag=False):
            from core.lib.rich_buttons import (
                RichPageButton,
                render_rich_page_button,
                validate_rich_page_button,
            )

            button = RichPageButton(text, type_, attrs, style)
            validate_rich_page_button(button)
            return render_rich_page_button(button) if html_tag else button

        def url(self, text, url, *, style=None, html_tag=False):
            return self._page(text, "url", {"url": url}, style, html_tag)

        def text(self, text, *, style=None, html_tag=False):
            return self._page(text, "text", None, style, html_tag)

        def switch(self, text, query="", *, same_peer=True, style=None, html_tag=False):
            return self._page(text, "switch", {"query": query}, style, html_tag)

        def copy(self, text="Copy", copy_text=None, *, style=None, html_tag=False):
            return self._page(text, "copy", {"copy_text": copy_text or ""}, style, html_tag)

        def game(self, text="Play Game", *, style=None, html_tag=False):
            return self._page(text, "game", None, style, html_tag)

        def unknown(self, text="Unsupported", *, style=None, html_tag=False):
            return self._page(text, "unknown", None, style, html_tag)

        def input(self, text, handler, *, placeholder="", ttl=900, allow_user=None,
                  allow_ttl=100, icon=None, style=None, **kw):
            return self._outer._button_factory.input(
                text, handler, placeholder=placeholder, ttl=ttl,
                allow_user=allow_user, allow_ttl=allow_ttl,
            )

        def close(self, text=None, **kw):
            return self.text(text or "Close")

        def request_phone(self, *args, **kwargs):
            raise NotImplementedError("request buttons недоступны в rich-фабрике")

        def request_location(self, *args, **kwargs):
            raise NotImplementedError("request buttons недоступны в rich-фабрике")

        def request_poll(self, *args, **kwargs):
            raise NotImplementedError("request buttons недоступны в rich-фабрике")

        def with_icon(self, *args, **kwargs):
            raise NotImplementedError("иконки недоступны в rich-фабрике")

    # --------------------------------------------------------
    # ХЕЛПЕРЫ (как в MCUB)
    # --------------------------------------------------------

    def _get_config(self):
        return self._config

    def _get_strings(self):
        if self._strings is not None:
            return self._strings
        return Strings(self.kernel, {})

    def get_prefix(self) -> str:
        return getattr(self.kernel, "custom_prefix", ".")

    def get_lang(self) -> str:
        config = getattr(self.kernel, "config", {})
        getter = getattr(config, "get", None)
        if callable(getter):
            return getter("language", "ru") or "ru"
        return "ru"

    def args(self, event):
        try:
            import utils
            text = getattr(event, "text", None) or getattr(event, "raw_text", "") or ""
            return utils.parse_arguments(text, prefix=self.get_prefix())
        except Exception:
            text = getattr(event, "text", "") or ""
            return text.split()[1:]

    def args_raw(self, event) -> str:
        text = getattr(event, "text", None) or getattr(event, "raw_text", "") or ""
        parts = text.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else ""

    def args_html(self, event) -> str:
        try:
            import utils
            return utils.get_args_html(event)
        except Exception:
            return self.args_raw(event)

    async def answer(self, event, text, **kwargs):
        try:
            import utils
            return await utils.answer(event, text, **kwargs)
        except Exception:
            pass
        reply_markup = kwargs.pop("reply_markup", None)
        if reply_markup is not None:
            kwargs["buttons"] = reply_markup
        if hasattr(event, "edit") and callable(event.edit):
            return await event.edit(text, **kwargs)
        return await event.reply(text, **kwargs)

    async def edit(self, event, text, **kwargs):
        reply_markup = kwargs.pop("reply_markup", None)
        as_html = kwargs.pop("as_html", False)
        if reply_markup is not None:
            kwargs["buttons"] = reply_markup
        if as_html:
            kwargs["parse_mode"] = "html"
        if hasattr(event, "edit") and callable(event.edit):
            return await event.edit(text, **kwargs)
        return await event.reply(text, **kwargs)

    async def reply(self, event, text, **kwargs):
        reply_markup = kwargs.pop("reply_markup", None)
        as_html = kwargs.pop("as_html", False)
        if reply_markup is not None:
            kwargs["buttons"] = reply_markup
        if as_html:
            kwargs["parse_mode"] = "html"
        return await event.reply(text, **kwargs)

    async def invoke(self, command, args=None, chat_id=None, reply_to=None):
        return await self._register.invoke(command, args=args, chat_id=chat_id, reply_to=reply_to)

    async def inline(self, chat_id, title, fields=None, buttons=None, auto_send=True,
                     ttl=200, reply_to=None, **kwargs):
        result = await self.kernel.inline_form(
            chat_id, title, fields=fields, buttons=buttons,
            auto_send=auto_send, ttl=ttl, reply_to=reply_to, **kwargs,
        )
        return result

    def lookup_module(self, module_name, *, all_loaded=False):
        needle = str(module_name).lower()
        k = self.kernel
        for name, inst in (getattr(k, "_class_module_instances", {}) or {}).items():
            if str(name).lower() == needle or str(getattr(inst, "name", "")).lower() == needle:
                return inst
        for collection_name in ("loaded_modules", "system_modules"):
            for name, module in (getattr(k, collection_name, {}) or {}).items():
                instance = getattr(module, "_class_instance", None)
                target = instance or module
                names = {str(name).lower(), str(getattr(target, "name", "")).lower(),
                         str(getattr(module, "__name__", "")).lower()}
                if needle in names:
                    return target
        return None

    def require_module(self, module_name, *, all_loaded=False):
        module = self.lookup_module(module_name, all_loaded=all_loaded)
        if module is None:
            raise LookupError(f"Required module '{module_name}' is not loaded")
        return module

    # --------------------------------------------------------
    # LIFECYCLE (переопределяются в модулях)
    # --------------------------------------------------------

    async def on_load(self):
        pass

    async def on_reload(self):
        pass

    async def on_unload(self):
        pass


__all__ = [
    "ModuleBase", "_ModuleLoggerAdapter", "Strings",
    "bot_command", "callback", "command", "error_handler", "event", "inline",
    "inline_temp", "loop", "method", "on_install", "on_uninstall", "owner_only",
    "permission", "permissions", "watcher",
    # backward compat
    "KernelMock", "StringsMock", "DBMock", "LoopHandle",
    # config
    "ModuleConfig", "ConfigValue", "Validator", "ValidationError",
    "Boolean", "Integer", "Float", "String", "Secret", "Choice", "MultiChoice",
    "Union", "List", "DictType", "Placeholders", "Link", "RegExp", "Emoji",
    "EntityLike", "NoneType", "Hidden", "TelegramID",
]
