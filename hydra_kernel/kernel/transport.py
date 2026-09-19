"""L0 — транспорт: абстракция над Telegram.

Transport — интерфейс. NullTransport — in-memory реализация для офлайн-сборки
и тестов (ядро обязано собираться и проходить smoke без сети и telethon).
TelethonTransport — боевая реализация, доступна только при установленном
telethon: импорт пакета от её отсутствия не падает.
"""

from __future__ import annotations

import asyncio
import itertools
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

Handler = Callable[["Message"], Awaitable[None]]


@dataclass
class Message:
    """Нормализованное сообщение, не зависящее от фреймворка."""

    chat_id: int
    sender_id: int
    text: str
    outgoing: bool = False
    message_id: int = 0
    raw: Any = None
    buttons: Any = None
    transport: Optional["Transport"] = field(default=None, repr=False)

    async def reply(self, text: str, **kw: Any) -> "Message":
        if self.transport is None:
            raise RuntimeError("Message не привязан к транспорту")
        return await self.transport.send(self.chat_id, text, **kw)

    async def edit(self, text: str, **kw: Any) -> "Message":
        if self.transport is None:
            raise RuntimeError("Message не привязан к транспорту")
        return await self.transport.edit(self.chat_id, self.message_id, text, **kw)

    async def delete(self) -> None:
        if self.transport is not None and hasattr(self.transport, "delete"):
            await self.transport.delete(self.chat_id, self.message_id)

    @property
    def message(self) -> "Message":
        """telethon-совместимость: event.message."""
        return self

    @property
    def raw_text(self) -> str:
        return self.text

    @property
    def peer_id(self) -> int:
        """Telethon-совместимый идентификатор диалога."""
        return self.chat_id

    @property
    def id(self) -> int:
        """Telethon-совместимый алиас ``Message.id``."""
        return self.message_id

    @property
    def reply_to_msg_id(self) -> Any:
        """ID сообщения, на которое отвечает команда, если оно есть.

        L2-адаптер передаёт модулям нормализованный ``Message``, тогда как
        исходные MCUB-модули ожидают поле Telethon ``reply_to_msg_id``. У
        ``NewMessage.Event`` оно может жить как на самом событии, так и на
        вложенном ``event.message`` — поддерживаем оба варианта.
        """

        raw_message = getattr(self.raw, "message", None)
        for source in (self.raw, raw_message):
            if source is None:
                continue
            value = getattr(source, "reply_to_msg_id", None)
            if value is not None:
                return value
            reply_to = getattr(source, "reply_to", None)
            value = getattr(reply_to, "reply_to_msg_id", None)
            if value is not None:
                return value
        return None

    @property
    def entities(self) -> list[Any]:
        """NullTransport не парсит разметку, но Hikka ждёт iterable."""
        return []

    def _raw_sources(self) -> tuple[Any, ...]:
        """Return both shapes used by Telethon events without exposing them.

        ``events.NewMessage.Event`` keeps most chat metadata on the event, but
        a few Telethon versions expose it on ``event.message`` instead.  Hydra
        hands modules a normalized :class:`Message`, so all compatibility
        aliases must check both locations.
        """

        raw_message = getattr(self.raw, "message", None)
        return tuple(source for source in (self.raw, raw_message) if source is not None)

    def _raw_flag(self, name: str) -> Optional[bool]:
        """Read a boolean Telethon chat flag, if the raw event has one."""

        for source in self._raw_sources():
            try:
                value = getattr(source, name, None)
            except Exception:  # pragma: no cover - foreign event descriptors
                continue
            if value is not None:
                return bool(value)
        return None

    async def get_reply_message(self) -> Any:
        """Вернуть исходный reply в live Telethon или ``None`` офлайн."""

        for source in self._raw_sources():
            getter = getattr(source, "get_reply_message", None)
            if not callable(getter):
                continue
            result = getter()
            if hasattr(result, "__await__"):
                return await result
            return result
        return None

    @property
    def client(self) -> Any:
        """Telethon-compatible ``event.client``.

        Native/core-style modules receive the same normalized event as MCUB
        modules.  They nevertheless legitimately use ``event.client`` for
        operations such as ``send_file``.  In production prefer the exact
        client attached to the raw Telethon event; the transport client is the
        deterministic offline fallback used by setup-style modules as well.
        """

        for source in self._raw_sources():
            try:
                client = getattr(source, "client", None)
            except Exception:  # pragma: no cover - foreign event descriptors
                continue
            if client is not None:
                return client
        return getattr(self.transport, "client", None) if self.transport is not None else None

    @property
    def is_group(self) -> bool:
        """Whether this event belongs to a basic group or a megagroup."""

        flag = self._raw_flag("is_group")
        if flag is not None:
            return flag
        # Telethon's normalized IDs are negative for group/channel peers.  A
        # raw event always wins above; this fallback makes offline smoke events
        # useful without pretending that an ordinary private chat is a group.
        return self.chat_id < 0

    @property
    def is_private(self) -> bool:
        """Telethon-compatible private-chat predicate."""

        flag = self._raw_flag("is_private")
        if flag is not None:
            return flag
        return self.chat_id > 0

    @property
    def is_channel(self) -> bool:
        """Telethon-compatible channel predicate when available."""

        flag = self._raw_flag("is_channel")
        if flag is not None:
            return flag
        # ``-100…`` is Telegram's marked channel/supergroup ID range.  This is
        # only an offline approximation; raw Telethon metadata takes priority.
        return self.chat_id <= -100_000_000_000

    @property
    def sender(self) -> Any:
        """telethon-совместимость: event.sender (если raw-событие даёт его)."""
        raw_message = getattr(self.raw, "message", None)
        return getattr(self.raw, "sender", None) or getattr(raw_message, "sender", None)

    @property
    def mentioned(self) -> bool:
        """Whether Telegram marked this message as mentioning the account."""

        flag = self._raw_flag("mentioned")
        return bool(flag)

    async def _raw_getter(self, name: str) -> Any:
        """Call a Telethon getter on the raw event/message when available."""

        for source in self._raw_sources():
            getter = getattr(source, name, None)
            if not callable(getter):
                continue
            result = getter()
            if hasattr(result, "__await__"):
                return await result
            return result
        return None

    async def get_chat(self) -> Any:
        """Telethon-compatible lazy chat lookup."""

        result = await self._raw_getter("get_chat")
        if result is not None:
            return result
        for source in self._raw_sources():
            chat = getattr(source, "chat", None)
            if chat is not None:
                return chat
        return None

    async def get_sender(self) -> Any:
        """Telethon-compatible lazy sender lookup."""

        result = await self._raw_getter("get_sender")
        return result if result is not None else self.sender

    @property
    def is_reply(self) -> bool:
        raw_message = getattr(self.raw, "message", None)
        return bool(
            getattr(self.raw, "is_reply", False)
            or getattr(raw_message, "is_reply", False)
            or self.reply_to_msg_id is not None
        )

    @property
    def out(self) -> bool:
        return self.outgoing


class Transport:
    """Интерфейс транспорта. Реализации: NullTransport, TelethonTransport."""

    async def start(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    async def stop(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    @property
    def me_id(self) -> int:  # pragma: no cover - interface
        raise NotImplementedError

    async def send(self, chat_id: int, text: str, **kw: Any) -> Message:
        raise NotImplementedError

    async def edit(self, chat_id: int, message_id: int, text: str, **kw: Any) -> Message:
        raise NotImplementedError

    def subscribe(
        self,
        handler: Handler,
        *,
        pattern: Optional[str] = None,
        incoming: bool = True,
        outgoing: bool = False,
        chats: Optional[List[int]] = None,
    ) -> Callable[[], None]:
        raise NotImplementedError

    def subscribe_inline(self, handler: Callable) -> Callable[[], None]:
        """handler(text, sender_id, raw)."""
        raise NotImplementedError

    def subscribe_callback(self, handler: Callable) -> Callable[[], None]:
        """handler(data, sender_id, chat_id, message_id, raw)."""
        raise NotImplementedError

    # Совместимые алиасы в стиле старого ядра
    async def send_message(self, entity: Any, text: str, **kw: Any) -> Message:
        return await self.send(int(entity), text, **kw)

    async def edit_message(self, entity: Any, message: Any, text: str, **kw: Any) -> Message:
        mid = message if isinstance(message, int) else getattr(message, "message_id", 0)
        return await self.edit(int(entity), mid, text, **kw)


class _StubClient:
    """Small offline stand-in for a Telethon client.

    Setup-style modules register event handlers on it, while core-style
    handlers can access it through ``event.client``.  It deliberately keeps
    network/RPC operations out of offline tests, but maps ordinary message and
    file sends to :class:`NullTransport` so presentation-only commands can be
    smoke-tested faithfully.
    """

    def __init__(self, transport: "NullTransport") -> None:
        self._transport = transport
        self.handlers: List[Any] = []

    def _chat_id(self, entity: Any) -> int:
        if entity in (None, "me", "self"):
            return self._transport.me_id
        try:
            return int(entity)
        except (TypeError, ValueError):
            return self._transport.me_id

    def add_event_handler(self, fn: Any, event: Any = None) -> Any:
        self.handlers.append((fn, event))
        return fn

    def remove_event_handler(self, fn: Any, event: Any = None) -> None:
        """Mirror Telethon cleanup so setup modules can be hot-unloaded offline."""

        try:
            self.handlers.remove((fn, event))
        except ValueError:
            pass

    def on(self, event: Any) -> Callable:
        def reg(fn: Any) -> Any:
            self.handlers.append((fn, event))
            return fn

        return reg

    async def get_me(self) -> Any:
        class _Me:
            username = None
            first_name = "Hydra"

        me = _Me()
        me.id = self._transport.me_id
        return me

    async def send_message(self, entity: Any, text: str, **kw: Any) -> Message:
        return await self._transport.send(self._chat_id(entity), text, **kw)

    async def send_file(self, entity: Any, file: Any, **kw: Any) -> Message:
        # NullTransport has no media store.  Preserve the visible caption so a
        # UI command such as `.start` is still meaningfully testable.
        caption = kw.pop("caption", None)
        text = str(caption if caption is not None else file)
        return await self._transport.send(self._chat_id(entity), text, **kw)

    async def edit_message(self, entity: Any, message: Any, text: str, **kw: Any) -> Message:
        message_id = message if isinstance(message, int) else getattr(message, "id", 0)
        return await self._transport.edit(self._chat_id(entity), int(message_id or 0), text, **kw)

    async def delete_messages(self, entity: Any, messages: Any, **kw: Any) -> list[Any]:
        ids = messages if isinstance(messages, (list, tuple, set)) else [messages]
        for message in ids:
            message_id = message if isinstance(message, int) else getattr(message, "id", 0)
            if message_id:
                await self._transport.delete(self._chat_id(entity), int(message_id))
        return []


class NullTransport(Transport):
    """In-memory транспорт: очередь исходящих + inject() входящих."""

    def __init__(self, me_id: int = 1000):
        self._me = me_id
        self._stub_client: Optional[_StubClient] = None
        self._ids = itertools.count(1)
        self.sent: List[Message] = []
        self._subs: List[Dict[str, Any]] = []
        self._inline_subs: List[Callable] = []
        self._callback_subs: List[Callable] = []
        self.inline_answers: List[Any] = []
        self.callback_answers: List[Any] = []
        self.deleted: List[Any] = []
        # текстовый мост кнопок (ButtonBridge): hook (msg) -> новый текст
        self.menu_renderer: Optional[Callable] = None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        self._subs.clear()

    @property
    def me_id(self) -> int:
        return self._me

    @property
    def client(self) -> Any:
        """Stub-клиент для setup(client)-модулей в офлайн-режиме."""
        if getattr(self, "_stub_client", None) is None:
            self._stub_client = _StubClient(self)
        return self._stub_client

    async def send(self, chat_id: int, text: str, **kw: Any) -> Message:
        msg = Message(
            chat_id=chat_id,
            sender_id=self._me,
            text=text,
            outgoing=True,
            message_id=next(self._ids),
            buttons=kw.pop("buttons", None),
            transport=self,
        )
        self.sent.append(msg)
        self._decorate_menu(msg)
        return msg

    async def edit(self, chat_id: int, message_id: int, text: str, **kw: Any) -> Message:
        buttons_supplied = "buttons" in kw
        buttons = kw.pop("buttons", None)
        for m in self.sent:
            if m.chat_id == chat_id and m.message_id == message_id:
                m.text = text
                if buttons_supplied:
                    m.buttons = buttons
                self._decorate_menu(m)
                return m
        if buttons_supplied:
            kw["buttons"] = buttons
        return await self.send(chat_id, text, **kw)

    def _decorate_menu(self, msg: "Message") -> None:
        """Текстовый мост кнопок: меню .cb N M прямо в тексте сообщения."""
        if self.menu_renderer is None or not msg.buttons:
            return
        try:
            msg.text = self.menu_renderer(msg)
        except Exception:  # noqa: BLE001 - мост не должен ронять отправку
            pass

    def subscribe(
        self,
        handler: Handler,
        *,
        pattern: Optional[str] = None,
        incoming: bool = True,
        outgoing: bool = False,
        chats: Optional[List[int]] = None,
    ) -> Callable[[], None]:
        rec = {
            "handler": handler,
            "pattern": re.compile(pattern) if pattern else None,
            "incoming": incoming,
            "outgoing": outgoing,
            "chats": chats,
        }
        self._subs.append(rec)

        def unsubscribe() -> None:
            if rec in self._subs:
                self._subs.remove(rec)

        return unsubscribe

    async def inject(
        self,
        chat_id: int,
        text: str,
        sender_id: Optional[int] = None,
        outgoing: bool = False,
        raw: Any = None,
    ) -> Message:
        """Симулировать входящее сообщение и раздать его подписчикам."""
        msg = Message(
            chat_id=chat_id,
            sender_id=sender_id if sender_id is not None else self._me,
            text=text,
            outgoing=outgoing,
            message_id=next(self._ids),
            raw=raw,
            transport=self,
        )
        for rec in list(self._subs):
            if not self._match(rec, msg):
                continue
            await rec["handler"](msg)
        # setup(client)-модули повесили обработчики на stub-клиент —
        # раздаём и им, эмулируя телеграфную семантику NewMessage
        stub = getattr(self, "_stub_client", None)
        if stub is not None:
            for fn, ev in list(stub.handlers):
                if ev is None or type(ev).__name__ != "NewMessage":
                    continue
                pat = getattr(ev, "pattern", None)
                if pat is not None and not pat(text):
                    continue
                if getattr(ev, "outgoing", None) is True and not outgoing:
                    continue
                if getattr(ev, "outgoing", None) is False and outgoing:
                    continue
                await fn(msg)
        return msg

    # ---------------- inline / callback (офлайн-симуляция) ----------------

    def subscribe_inline(self, handler: Callable) -> Callable[[], None]:
        self._inline_subs.append(handler)
        return lambda: self._inline_subs.remove(handler) if handler in self._inline_subs else None

    def subscribe_callback(self, handler: Callable) -> Callable[[], None]:
        self._callback_subs.append(handler)
        return lambda: self._callback_subs.remove(handler) if handler in self._callback_subs else None

    async def inject_inline(self, text: str, sender_id: int) -> None:
        """Симулировать inline-запрос пользователя."""
        for handler in list(self._inline_subs):
            await handler(text, sender_id, None)

    async def inject_callback(
        self, data: str, sender_id: int, chat_id: int = 0, message_id: int = 0
    ) -> None:
        """Симулировать нажатие инлайн-кнопки."""
        for handler in list(self._callback_subs):
            await handler(data, sender_id, chat_id, message_id, None)

    async def answer_inline(self, event: Any, results: List[Any], **kw: Any) -> bool:
        self.inline_answers.append(
            (event.name, [getattr(r, "title", "") for r in results])
        )
        return True

    async def answer_callback(
        self, event: Any, text: Optional[str] = None, alert: bool = False, **kw: Any
    ) -> bool:
        self.callback_answers.append((event.data, text, alert))
        return True

    async def delete(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))
        self.sent = [
            m for m in self.sent if not (m.chat_id == chat_id and m.message_id == message_id)
        ]

    @staticmethod
    def _match(rec: Dict[str, Any], msg: Message) -> bool:
        if msg.outgoing and not rec["outgoing"]:
            return False
        if not msg.outgoing and not rec["incoming"]:
            return False
        if rec["chats"] is not None and msg.chat_id not in rec["chats"]:
            return False
        if rec["pattern"] is not None and not rec["pattern"].search(msg.text):
            return False
        return True


try:  # pragma: no cover - зависит от окружения
    from telethon import TelegramClient, events  # type: ignore

    _HAVE_TELETHON = True
except ImportError:  # pragma: no cover
    TelegramClient = None  # type: ignore
    events = None  # type: ignore
    _HAVE_TELETHON = False


class TelethonTransport(Transport):  # pragma: no cover - нужна сеть/telethon
    """Боевой транспорт поверх Telethon.

    Либо создаёт свой клиент (session/api_id/api_hash), либо оборачивает
    уже авторизованный внешний клиент (client=...) — режим для m.py,
    где вход уже выполнен TUI-шкой.
    """

    def __init__(
        self,
        session: Optional[str] = None,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
        *,
        client: Any = None,
        **client_kw: Any,
    ):
        if not _HAVE_TELETHON:
            raise RuntimeError(
                "telethon не установлен: для офлайн-сборки используйте NullTransport"
            )
        if client is not None:
            self._client = client
            self._own = False
        else:
            self._client = TelegramClient(session, api_id, api_hash, **client_kw)
            self._own = True
        self._me_id = 0
        self._unsubs: List[Callable[[], None]] = []
        # текстовый мост кнопок (ButtonBridge): hook (msg) -> новый текст
        self.menu_renderer: Optional[Callable] = None
        # хук (msg, old_id): меню записалось с временным id, после отправки
        # транспорт сообщает боевой message_id
        self._id_fixup: Optional[Callable] = None

    async def start(self) -> None:
        if self._own:
            await self._client.start()
        me = await self._client.get_me()
        self._me_id = me.id

    async def stop(self) -> None:
        if self._own:
            await self._client.disconnect()

    @property
    def me_id(self) -> int:
        return self._me_id

    @property
    def client(self) -> Any:
        return self._client

    def _decorate_menu(self, msg: "Message") -> None:
        """Текстовый мост кнопок: меню .cb N M прямо в тексте сообщения."""
        if self.menu_renderer is None or not msg.buttons:
            return
        try:
            msg.text = self.menu_renderer(msg)
        except Exception:  # noqa: BLE001 - мост не должен ронять отправку
            pass

    async def send(self, chat_id: int, text: str, **kw: Any) -> Message:
        msg = Message(
            chat_id=chat_id,
            sender_id=self._me_id,
            text=text,
            outgoing=True,
            message_id=0,
            buttons=kw.pop("buttons", None),
            transport=self,
        )
        self._decorate_menu(msg)  # меню вшивается в текст ДО отправки в TG
        raw = await self._client.send_message(chat_id, msg.text, **kw)
        old = msg.message_id
        msg.message_id = raw.id
        msg.raw = raw
        if old != raw.id and self._id_fixup is not None:
            self._id_fixup(msg, old)
        return msg

    async def edit(self, chat_id: int, message_id: int, text: str, **kw: Any) -> Message:
        msg = Message(
            chat_id=chat_id,
            sender_id=self._me_id,
            text=text,
            outgoing=True,
            message_id=message_id,
            buttons=kw.pop("buttons", None),
            transport=self,
        )
        self._decorate_menu(msg)
        raw = await self._client.edit_message(chat_id, message_id, msg.text, **kw)
        msg.raw = raw
        return msg

    async def delete(self, chat_id: int, message_id: int) -> None:
        await self._client.delete_messages(chat_id, message_id)

    def subscribe(
        self,
        handler: Handler,
        *,
        pattern: Optional[str] = None,
        incoming: bool = True,
        outgoing: bool = False,
        chats: Optional[List[int]] = None,
    ) -> Callable[[], None]:
        """Подписать L0 handler на одно или оба направления сообщений.

        Telethon считает ``NewMessage(incoming=True, outgoing=True)``
        взаимоисключающим фильтром: такая подписка не получает *ни одного*
        события. Hydra использует обе стороны для команд/моста кнопок, поэтому
        разворачиваем этот случай в две корректные Telethon-подписки.
        """

        base_kw: Dict[str, Any] = {}
        if pattern:
            base_kw["pattern"] = pattern
        if chats:
            base_kw["chats"] = chats

        directions: List[Dict[str, bool]] = []
        if incoming:
            directions.append({"incoming": True})
        if outgoing:
            directions.append({"outgoing": True})
        if not directions:
            return lambda: None

        async def wrapper(event: Any) -> None:
            raw_message = getattr(event, "message", None)
            is_outgoing = bool(getattr(event, "out", getattr(raw_message, "out", False)))
            sender_id = getattr(event, "sender_id", None) or getattr(raw_message, "sender_id", None)
            # Telegram иногда не заполняет sender_id у собственного outgoing
            # сообщения. Иначе PermissionManager бесшумно отбросит команду.
            if not sender_id and is_outgoing:
                sender_id = self._me_id
            text = (
                getattr(event, "raw_text", None)
                or getattr(event, "text", None)
                or getattr(raw_message, "message", None)
                or ""
            )
            msg = Message(
                chat_id=getattr(event, "chat_id", 0) or 0,
                sender_id=sender_id or 0,
                text=str(text),
                outgoing=is_outgoing,
                message_id=getattr(raw_message, "id", getattr(event, "id", 0)) or 0,
                raw=event,
                transport=self,
            )
            await handler(msg)

        registrations: List[Any] = []
        for direction in directions:
            builder = events.NewMessage(**base_kw, **direction)
            self._client.add_event_handler(wrapper, builder)
            registrations.append(builder)

        def unsubscribe() -> None:
            remove = getattr(self._client, "remove_event_handler", None)
            if not callable(remove):
                return
            for builder in registrations:
                try:
                    remove(wrapper, builder)
                except Exception:  # noqa: BLE001 - cleanup must stay best-effort
                    pass

        return unsubscribe

    def subscribe_inline(self, handler: Callable) -> Callable[[], None]:  # pragma: no cover
        async def wrapper(event: Any) -> None:
            await handler(event.text or "", event.sender_id or 0, event)

        self._client.on(events.InlineQuery)(wrapper)
        return lambda: None

    def subscribe_callback(self, handler: Callable) -> Callable[[], None]:  # pragma: no cover
        async def wrapper(event: Any) -> None:
            data = event.data.decode() if isinstance(event.data, bytes) else str(event.data)
            await handler(data, event.sender_id or 0, event.chat_id or 0, event.message_id, event)

        self._client.on(events.CallbackQuery)(wrapper)
        return lambda: None

    async def answer_inline(self, event: Any, results: List[Any], **kw: Any) -> Any:  # pragma: no cover
        raw = event.raw
        if raw is not None and hasattr(raw, "answer"):
            converted = [r.to_telethon() for r in results if hasattr(r, "to_telethon")] or list(results)
            return await raw.answer(converted, **kw)
        return None

    async def answer_callback(  # pragma: no cover
        self, event: Any, text: Optional[str] = None, alert: bool = False, **kw: Any
    ) -> Any:
        raw = event.raw
        if raw is not None and hasattr(raw, "answer"):
            return await raw.answer(text, alert=alert, **kw)
        return None
