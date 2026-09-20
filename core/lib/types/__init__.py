# core/lib/types/__init__.py
# Структурные типы MCUB-fork (core.lib.types) — Protocol-шимы для аннотаций.
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .inline_message import InlineMessage


@runtime_checkable
class Event(Protocol):
    """MCUB Event: нормализованное сообщение/колбэк."""

    text: str
    chat_id: Any
    sender_id: Any


@runtime_checkable
class Message(Protocol):
    """MCUB Message: message-объект с edit/reply/delete."""

    id: Any

    async def edit(self, text: str, **kw: Any) -> Any:  # pragma: no cover - протокол
        ...

    async def reply(self, text: str, **kw: Any) -> Any:  # pragma: no cover
        ...

    async def delete(self) -> None:  # pragma: no cover
        ...


@runtime_checkable
class Client(Protocol):
    """MCUB Client: Telethon-совместимый клиент."""

    async def send_message(self, entity: Any, message: Any, **kw: Any) -> Any:  # pragma: no cover
        ...


@runtime_checkable
class Kernel(Protocol):
    """MCUB Kernel: ядро с реестрами и клиентом."""

    client: Any
    config: dict


@runtime_checkable
class Register(Protocol):
    """MCUB Register: kernel.register."""

    def command(self, name: str, *args: Any, **kw: Any) -> Any:  # pragma: no cover
        ...

    def watcher(self, *args: Any, **kw: Any) -> Any:  # pragma: no cover
        ...


__all__ = [
    "Client",
    "Event",
    "InlineMessage",
    "Kernel",
    "Message",
    "Register",
]
