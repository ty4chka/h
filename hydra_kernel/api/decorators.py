"""L1 — decorators: метки обработчиков на методах ModuleBase.

Декоратор ничего не регистрирует сам — только вешает метаданные
`_hydra_meta`; регистрацию выполняет Lifecycle (см. lifecycle.py).
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Tuple

META_ATTR = "_hydra_meta"


def _mark(fn: Callable, kind: str, **opts: Any) -> Callable:
    meta = {"kind": kind, **opts}
    setattr(fn, META_ATTR, meta)
    return fn


def command(name: Optional[str] = None, aliases: Tuple[str, ...] = (), desc: str = "", required_level: int = 1) -> Callable:
    def deco(fn: Callable) -> Callable:
        cmd = name or fn.__name__
        return _mark(fn, "command", name=cmd, aliases=tuple(aliases), desc=desc, required_level=required_level)

    return deco


def watcher(pattern: Optional[str] = None, incoming: bool = True, outgoing: bool = False, chats=None) -> Callable:
    def deco(fn: Callable) -> Callable:
        return _mark(fn, "watcher", pattern=pattern, incoming=incoming, outgoing=outgoing, chats=chats)

    return deco


def inline_handler(name: str) -> Callable:
    def deco(fn: Callable) -> Callable:
        return _mark(fn, "inline", name=name)

    return deco


def callback(prefix: str) -> Callable:
    def deco(fn: Callable) -> Callable:
        return _mark(fn, "callback", prefix=prefix)

    return deco


def loop(interval: float) -> Callable:
    def deco(fn: Callable) -> Callable:
        return _mark(fn, "loop", interval=interval)

    return deco
