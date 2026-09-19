"""Мини-pyrogram для настоящих модулей Dragon Userbot.

Dragon-модули пишутся под pyrogram: `@Client.on_message(filters.command([...], prefix)
& filters.me)`. Шим предоставляет Client/filters/types, собирает регистрации
в реестр, а адаптер раскладывает их по подпискам транспорта hydra_kernel.
"""
from __future__ import annotations

import sys
import types
from typing import Any, Callable, List, Optional, Tuple


class Filter:
    """Узел фильтра (pyrogram.filters.*)."""

    def __init__(self, kind: str = "custom", **data: Any):
        self.kind = kind
        self.data = data

    def __and__(self, other: "Filter") -> "Combo":
        return Combo("~" if False else "&", [self, other])

    def __or__(self, other: "Filter") -> "Combo":
        return Combo("|", [self, other])

    def __invert__(self) -> "Combo":
        return Combo("~", [self])


class Combo(Filter):
    def __init__(self, op: str, parts: List[Filter]):
        super().__init__("combo")
        self.op = op
        self.parts = parts


def extract(filt: Optional[Filter]) -> Tuple[Optional[List[str]], Optional[bool], str]:
    """(команды, me-флаг, префикс) из дерева фильтров."""
    commands: Optional[List[str]] = None
    me: Optional[bool] = None
    prefix = "."

    def walk(node: Optional[Filter], neg: bool = False) -> None:
        nonlocal commands, me, prefix
        if node is None:
            return
        if isinstance(node, Combo):
            if node.op == "~":
                walk(node.parts[0], not neg)
            else:
                for part in node.parts:
                    walk(part, neg)
            return
        if node.kind == "command" and not neg:
            commands = list(node.data.get("commands") or [])
            prefix = node.data.get("prefix") or "."
        elif node.kind == "me":
            if me is None:
                me = not neg

    walk(filt)
    return commands, me, prefix


class _Client:
    """pyrogram.Client-заглушка: собирает регистрации декораторами."""

    registry: List[Tuple[Callable, Any]] = []

    @classmethod
    def on_message(cls, flt: Any = None) -> Callable:
        def deco(fn: Callable) -> Callable:
            cls.registry.append((fn, flt))
            return fn

        return deco

    @classmethod
    def on_callback_query(cls, flt: Any = None) -> Callable:
        def deco(fn: Callable) -> Callable:
            cls.registry.append((fn, flt))
            return fn

        return deco


def _filters_ns() -> Any:
    ns = types.SimpleNamespace()

    def command(cmds: Any, prefix: str = ".", **kw: Any) -> Filter:
        if isinstance(cmds, str):
            cmds = [cmds]
        return Filter("command", commands=list(cmds), prefix=prefix)

    def create(fn: Callable, name: Optional[str] = None, **kw: Any) -> Filter:
        return Filter("custom", fn=fn, name=name)

    ns.command = command
    ns.create = create
    for simple in (
        "me", "private", "group", "channel", "bot", "mentioned", "incoming",
        "outgoing", "text", "photo", "video", "audio", "document", "sticker",
        "animation", "voice", "forwarded", "reply", "service", "new_chat_members",
    ):
        setattr(ns, simple, Filter(simple))
    return ns


def install() -> type:
    """Ставит pyrogram-шим в sys.modules, возвращает _Client (с registry)."""
    existing = sys.modules.get("pyrogram")
    if existing is not None and getattr(existing, "_hydra_shim", False):
        return _Client
    if existing is not None:
        # настоящий pyrogram — не мешаем
        return _Client

    pg = types.ModuleType("pyrogram")
    pg._hydra_shim = True
    pg.Client = _Client
    pg.filters = _filters_ns()

    tg = types.ModuleType("pyrogram.types")
    tg.Message = object
    tg.CallbackQuery = object
    tg.InlineKeyboardMarkup = object
    tg.InlineKeyboardButton = object
    pg.types = tg

    sys.modules["pyrogram"] = pg
    sys.modules["pyrogram.types"] = tg
    sys.modules["pyrogram.filters"] = pg.filters
    return _Client
