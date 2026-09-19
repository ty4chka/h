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


def make_cb_button(kernel, text: str, callback, *, args=None, kwargs=None,
                   ttl: int = 900, token: str | None = None, icon: Any = None,
                   style: Any = None):
    """Создать Button.inline с автогенерацией токена колбэка."""
    if not callable(callback):
        raise TypeError("callback must be callable")

    real_kernel = _get_real_kernel(kernel)
    if not hasattr(real_kernel, "_inline_cb_lock"):
        real_kernel._inline_cb_lock = threading.Lock()

    with real_kernel._inline_cb_lock:
        cb_map = getattr(real_kernel, "inline_callback_map", None)
        if cb_map is None:
            cb_map = {}
            real_kernel.inline_callback_map = cb_map
        now = time.time()
        expired = [k for k, v in list(cb_map.items())
                   if v.get("expires_at") and v["expires_at"] < now]
        for k in expired:
            cb_map.pop(k, None)
        tok = token or uuid.uuid4().hex
        cb_map[tok] = {
            "handler": callback,
            "args": list(args or []),
            "kwargs": dict(kwargs or {}),
            "expires_at": now + ttl if ttl else None,
        }

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
