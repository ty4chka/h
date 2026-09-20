# core_inline/api/inline.py
# Порт core_inline.api.inline из MCUB-fork (MIT) для mcub_engine.
"""make_cb_button — кнопки-колбэки, хранимые в kernel.inline_callback_map.
Мост mcub_engine превращает их в команды .cb N."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any


def _get_real_kernel(kernel):
    if type(kernel).__name__ == "ModuleKernelProxy":
        return object.__getattribute__(kernel, "_kernel")
    return kernel


# Глобальный реестр колбэков для вызовов в стиле MCUB-fork
# make_cb_button(text, callback) — без явного kernel (как в upstream).
_global_cb_handlers: dict = {}


def _find_active_kernel():
    """Найти активное ядро MCUB для привязки токена к его callback map."""
    try:
        import core_inline as _root

        state = getattr(_root, "_core", None)
        bot = getattr(state, "bot", None)
        kernel = getattr(bot, "kernel", None) or getattr(bot, "_kernel", None)
        if kernel is not None:
            return kernel
    except Exception:  # noqa: BLE001
        pass
    return None


def _store_global_cb(tok: str, entry: dict) -> None:
    now = time.time()
    expired = [
        k for k, v in list(_global_cb_handlers.items())
        if v.get("expires_at") and v["expires_at"] < now
    ]
    for k in expired:
        _global_cb_handlers.pop(k, None)
    _global_cb_handlers[tok] = entry


def default_ttl(ttl: int | None) -> int:
    """TTL по умолчанию (MCUB-fork совместимость)."""

    try:
        return int(ttl) if ttl else 900
    except (TypeError, ValueError):
        return 900


def make_cb_button(*call_args, args=None, kwargs=None,
                   ttl: int = 900, token: str | None = None, icon: Any = None,
                   style: Any = None):
    """Создать Button.inline с автогенерацией токена колбэка.

    Реальная сигнатура MCUB-fork: ``make_cb_button(text, callback)``.
    Ранее в Hydra использовался вызов ``make_cb_button(kernel, text, callback)``;
    обе формы поддерживаются.
    """
    if len(call_args) == 2 and isinstance(call_args[0], str) and callable(call_args[1]):
        kernel, text, callback = _find_active_kernel(), call_args[0], call_args[1]
    elif len(call_args) >= 3:
        kernel, text, callback = call_args[0], call_args[1], call_args[2]
    elif len(call_args) == 2 and callable(call_args[0]) is False:
        raise TypeError("make_cb_button: ожидается (text, callback) или (kernel, text, callback)")
    else:
        raise TypeError("make_cb_button: ожидается (text, callback) или (kernel, text, callback)")

    if not callable(callback):
        raise TypeError("callback must be callable")

    tok = token or uuid.uuid4().hex
    now = time.time()
    entry = {
        "handler": callback,
        "args": list(args or []),
        "kwargs": dict(kwargs or {}),
        "expires_at": now + default_ttl(ttl) if ttl else None,
    }
    if kernel is None:
        # Режим upstream без явного ядра: глобальный реестр-мост.
        _store_global_cb(tok, entry)
        real_kernel = None
    else:
        real_kernel = _get_real_kernel(kernel)
        if not hasattr(real_kernel, "_inline_cb_lock"):
            real_kernel._inline_cb_lock = threading.Lock()

        with real_kernel._inline_cb_lock:
            cb_map = getattr(real_kernel, "inline_callback_map", None)
            if cb_map is None:
                cb_map = {}
                real_kernel.inline_callback_map = cb_map
            expired = [k for k, v in list(cb_map.items())
                       if v.get("expires_at") and v["expires_at"] < now]
            for k in expired:
                cb_map.pop(k, None)
            cb_map[tok] = entry

    from telethon import Button
    try:
        return Button.inline(text, tok.encode(), icon=icon, style=style)
    except TypeError:
        return Button.inline(text, tok.encode())


def build_button_switch(text: str, query: str, hint: str = "",
                        emoji: str | None = None, same_peer: bool = False):
    from telethon import Button
    label = f"{emoji} {text}" if emoji else text
    return Button.switch_inline(label, query=query, same_peer=same_peer)
