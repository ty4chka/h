# core/lib/loader/placeholders.py
"""
Система плейсхолдеров как в MCUB.
Регистрирует глобальные плейсхолдеры: {prefix}, {time}, {date}, {my_name}, {random} и др.
Поддержка кастомных плейсхолдеров из других модулей (изображения, медиа и т.д.)
"""

import re
import random
import time
import asyncio
from datetime import datetime
from collections.abc import Callable
from typing import Any

_TOKEN_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")

_REGISTRY: dict[str, dict[str, dict[str, Any]]] = {}
_MEDIA_REGISTRY: dict[str, dict[str, Any]] = {}


def register_placeholder(scope: str, key: str, callback: Callable, **kwargs):
    """Регистрация плейсхолдера."""
    if scope not in _REGISTRY:
        _REGISTRY[scope] = {}
    _REGISTRY[scope][key] = {
        "callback": callback,
        "timeout": kwargs.get("timeout"),
        "description": kwargs.get("description", ""),
        "required": kwargs.get("required", False),
    }


def register_media_placeholder(scope: str, key: str, media_type: str, callback: Callable, **kwargs):
    """Регистрация медиа-плейсхолдера (изображения, стикеры и т.д.)."""
    if scope not in _MEDIA_REGISTRY:
        _MEDIA_REGISTRY[scope] = {}
    _MEDIA_REGISTRY[scope][key] = {
        "callback": callback,
        "media_type": media_type,
        "description": kwargs.get("description", ""),
        "mime_type": kwargs.get("mime_type", "image/jpeg"),
    }


def unregister_scope(scope: str) -> int:
    removed = len(_REGISTRY.get(scope, {}))
    _REGISTRY.pop(scope, None)
    _MEDIA_REGISTRY.pop(scope, None)
    return removed


def list_placeholder_keys(scope: str) -> list:
    keys = list(_REGISTRY.get(scope, {}).keys())
    keys.extend(_MEDIA_REGISTRY.get(scope, {}).keys())
    return sorted(keys)


def get_media_placeholder(scope: str, key: str) -> dict | None:
    """Получить медиа-плейсхолдер."""
    for s in [scope, "global", *_MEDIA_REGISTRY.keys()]:
        if s in _MEDIA_REGISTRY and key in _MEDIA_REGISTRY[s]:
            return _MEDIA_REGISTRY[s][key]
    return None


async def resolve_placeholders(scope: str, template: str, data: dict = None, strict: bool = False) -> str:
    """Разрешить текстовые плейсхолдеры."""
    if not template:
        return template
    data = data or {}
    tokens = {m.group(1) for m in _TOKEN_RE.finditer(str(template))}

    for token in tokens:
        if token in data:
            continue

        meta = None
        for s in [scope, "global", *_REGISTRY.keys()]:
            if s in _REGISTRY and token in _REGISTRY[s]:
                meta = _REGISTRY[s][token]
                break

        if meta is None:
            continue

        try:
            callback = meta["callback"]
            result = callback(data) if callable(callback) else callback
            if asyncio.iscoroutine(result):
                result = await result
            data[token] = str(result)
        except Exception:
            if strict:
                raise
            data[token] = "{" + token + "}"

    def repl(match):
        token = match.group(1)
        if token in data:
            return str(data[token])
        return match.group(0)

    return _TOKEN_RE.sub(repl, str(template or ""))


async def resolve_media_placeholders(scope: str, data: dict = None) -> dict:
    """Разрешить медиа-плейсхолдеры. Возвращает dict {key: {url, type, ...}}."""
    data = data or {}
    result = {}
    for s in [scope, "global", *_MEDIA_REGISTRY.keys()]:
        if s not in _MEDIA_REGISTRY:
            continue
        for key, meta in _MEDIA_REGISTRY[s].items():
            if key in result:
                continue
            try:
                callback = meta["callback"]
                value = callback(data) if callable(callback) else callback
                if asyncio.iscoroutine(value):
                    value = await value
                result[key] = {
                    "url": str(value),
                    "type": meta.get("media_type", "image"),
                    "mime_type": meta.get("mime_type", "image/jpeg"),
                }
            except Exception:
                pass
    return result


def _now():
    return datetime.now()


def _register_builtins():
    if "global" in _REGISTRY:
        return

    def _prefix(data):
        return "."

    def _time(data):
        return _now().strftime("%H:%M:%S")

    def _date(data):
        return _now().strftime("%d.%m.%Y")

    def _datetime(data):
        return _now().strftime("%d.%m.%Y %H:%M:%S")

    def _timestamp(data):
        return str(int(time.time()))

    def _my_name(data):
        return data.get("my_name", "User")

    def _my_id(data):
        return str(data.get("my_id", 0))

    def _random(data):
        return str(random.randint(0, 999999))

    def _chat_id(data):
        return str(data.get("chat_id", 0))

    def _chat_title(data):
        return data.get("chat_title", "Unknown")

    def _weekday(data):
        days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        return days[_now().weekday()]

    def _month(data):
        months = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
        return months[_now().month - 1]

    builtins = {
        "prefix": _prefix,
        "time": _time,
        "date": _date,
        "datetime": _datetime,
        "timestamp": _timestamp,
        "my_name": _my_name,
        "my_id": _my_id,
        "random": _random,
        "chat_id": _chat_id,
        "chat_title": _chat_title,
        "weekday": _weekday,
        "month": _month,
    }

    _REGISTRY["global"] = {
        k: {"callback": v, "timeout": None, "description": "", "required": False}
        for k, v in builtins.items()
    }


_register_builtins()
