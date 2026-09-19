"""L2 — база адаптеров и shim-объекты клиента/БД."""

from __future__ import annotations

import sys
import types
from typing import Any, Dict, List, Optional, Tuple

from ..kernel.transport import NullTransport, Transport
from ..kernel.db import MemoryDB


class _ConversationGuard:
    """Обёртка Telethon Conversation, безопасная при timeout/cancel.

    ``asyncio.wait_for(conv.get_response(), ...)`` отменяет Future ожидания.
    В ряде версий Telethon отменённый Future остаётся в private pending-map,
    а запоздалый ответ бота затем вызывает ``InvalidStateError`` внутри
    диспетчера обновлений. Совместимые MCUB-модули часто используют именно
    такой паттерн, поэтому чистим только уже завершённые Future до того, как
    Telethon увидит следующий апдейт.
    """

    _PENDING_ATTRS = (
        "_pending_responses",
        "_pending_replies",
        "_pending_edits",
        "_pending_reads",
        "_custom",
    )

    def __init__(self, conversation: Any):
        self._conversation = conversation

    def _discard_finished_waiters(self) -> None:
        for attr in self._PENDING_ATTRS:
            pending = getattr(self._conversation, attr, None)
            if not isinstance(pending, dict):
                continue
            for key, item in list(pending.items()):
                # Telethon stores ``(event_builder, future)`` in _custom,
                # while the other maps hold the Future directly.
                future = item[-1] if isinstance(item, tuple) and item else item
                done = getattr(future, "done", None)
                if callable(done) and done():
                    pending.pop(key, None)

    async def __aenter__(self) -> "_ConversationGuard":
        await self._conversation.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        try:
            return await self._conversation.__aexit__(exc_type, exc, tb)
        finally:
            self._discard_finished_waiters()

    async def send_message(self, *args: Any, **kwargs: Any) -> Any:
        return await self._conversation.send_message(*args, **kwargs)

    async def send_file(self, *args: Any, **kwargs: Any) -> Any:
        return await self._conversation.send_file(*args, **kwargs)

    async def _await_and_cleanup(self, method: str, *args: Any, **kwargs: Any) -> Any:
        try:
            return await getattr(self._conversation, method)(*args, **kwargs)
        finally:
            self._discard_finished_waiters()

    async def get_response(self, *args: Any, **kwargs: Any) -> Any:
        return await self._await_and_cleanup("get_response", *args, **kwargs)

    async def get_reply(self, *args: Any, **kwargs: Any) -> Any:
        return await self._await_and_cleanup("get_reply", *args, **kwargs)

    async def get_edit(self, *args: Any, **kwargs: Any) -> Any:
        return await self._await_and_cleanup("get_edit", *args, **kwargs)

    async def wait_read(self, *args: Any, **kwargs: Any) -> Any:
        return await self._await_and_cleanup("wait_read", *args, **kwargs)

    async def wait_event(self, *args: Any, **kwargs: Any) -> Any:
        return await self._await_and_cleanup("wait_event", *args, **kwargs)

    def cancel(self) -> Any:
        try:
            return self._conversation.cancel()
        finally:
            self._discard_finished_waiters()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conversation, name)


class ClientProxy:
    """Клиент в глазах чужого модуля: только то, что умеет транспорт."""

    def __init__(self, transport: Transport):
        self._t = transport

    @property
    def is_offline(self) -> bool:
        """True when no Telegram RPC client exists behind this proxy.

        Compatibility modules can use this to avoid provisioning chats, making
        HTTP calls, or otherwise attempting a Telegram-only side effect during
        a ``NullTransport`` smoke run.
        """

        return isinstance(self._t, NullTransport)

    def _native_client(self) -> Any:
        """Return the underlying Telethon client when the transport has one."""

        if self.is_offline:
            return None
        client = getattr(self._t, "client", None)
        return client if client is not self else None

    def __getattr__(self, name: str) -> Any:
        """Expose the live client's extended Telethon surface when available.

        ``ClientProxy`` intentionally owns the normalized methods below, while
        this fallback keeps MCUB modules able to use operations such as
        ``iter_dialogs`` and ``get_input_entity`` with ``TelethonTransport``.
        Special methods are not delegated by Python, so ``__call__`` is
        implemented explicitly below.
        """

        client = self._native_client()
        if client is not None:
            return getattr(client, name)
        raise AttributeError(f"{type(self).__name__} has no attribute {name!r} in offline mode")

    async def __call__(self, request: Any) -> Any:
        """Forward raw Telethon requests on a live transport.

        A clear exception is preferable to Python's opaque ``not callable``
        when a module accidentally tries Telegram RPC during an offline run.
        """

        client = self._native_client()
        if callable(client):
            result = client(request)
            if hasattr(result, "__await__"):
                return await result
            return result
        raise RuntimeError("Telegram RPC requests require a live transport")

    @property
    def me_id(self) -> int:
        return self._t.me_id

    @property
    def tg_id(self) -> int:
        return self._t.me_id

    async def get_me(self) -> Any:
        """Возвращать настоящий профиль в live-режиме, stub — только офлайн."""

        client = self._native_client()
        getter = getattr(client, "get_me", None) if client is not None else None
        if callable(getter):
            result = getter()
            if hasattr(result, "__await__"):
                return await result
            return result
        return types.SimpleNamespace(
            id=self._t.me_id,
            first_name="Hydra",
            username="hydra",
            premium=False,
        )

    def conversation(self, *args: Any, **kwargs: Any) -> _ConversationGuard:
        """Открыть защищённый live Telethon conversation.

        Это намеренно не отдаётся через ``__getattr__``: wrapper нужен, чтобы
        таймаут модуля не оставлял отменённый waiter внутри Telethon.
        """

        client = self._native_client()
        factory = getattr(client, "conversation", None) if client is not None else None
        if not callable(factory):
            raise RuntimeError("Telegram conversations require a live transport")
        return _ConversationGuard(factory(*args, **kwargs))

    async def translate(self, *args: Any, **kw: Any) -> str:
        """Детерминированный офлайн-fallback для Hikka ``client.translate``.

        Реальный перевод — ответственность Telegram/Telethon. Для тестового
        транспорта сохраняем текст и помечаем запрошенный язык, вместо того
        чтобы выбрасывать AttributeError и оставлять команду без ответа.
        """

        text = str(kw.get("raw_text") or "")
        language = str(args[2]) if len(args) > 2 else str(kw.get("lang") or "")
        return f"[{language}] {text}".strip()

    async def send_message(self, entity: Any, text: str, **kw: Any) -> Any:
        return await self._t.send(int(entity), text, **kw)

    async def edit_message(self, entity: Any, message: Any, text: str, **kw: Any) -> Any:
        mid = message if isinstance(message, int) else getattr(message, "message_id", 0)
        return await self._t.edit(int(entity), mid, text, **kw)

    async def delete_messages(self, entity: Any, messages: Any, **kw: Any) -> Any:
        """Telethon-compatible deletion, including a deterministic offline no-op."""

        client = self._native_client()
        native_delete = getattr(client, "delete_messages", None) if client is not None else None
        if callable(native_delete):
            result = native_delete(entity, messages, **kw)
            if hasattr(result, "__await__"):
                return await result
            return result
        ids = messages if isinstance(messages, (list, tuple, set)) else [messages]
        affected = []
        for message in ids:
            mid = message if isinstance(message, int) else getattr(message, "message_id", 0)
            if mid:
                await self._t.delete(int(entity), int(mid))
                # Старый MCUB суммирует ``pts_count`` у результата удаления.
                affected.append(types.SimpleNamespace(pts_count=1))
        return affected


class DbShim:
    """Async get/set в пространстве имён модуля (стиль hikka)."""

    def __init__(self, db: MemoryDB, ns: str):
        self._db = db
        self._ns = ns

    async def get(self, key: str, default: Any = None) -> Any:
        return await self._db.get(self._ns, key, default)

    async def set(self, key: str, value: Any) -> None:
        await self._db.set(self._ns, key, value)


class CompatAdapter:
    """База: установка shim-модулей в sys.modules и exec исходника."""

    framework = "base"

    def __init__(self, hydra: Any):
        self.h = hydra
        self._mods: List[str] = []

    def _put_module(self, dotted: str) -> types.ModuleType:
        mod = types.ModuleType(dotted)
        sys.modules[dotted] = mod
        self._mods.append(dotted)
        if "." in dotted:
            parent, _, child = dotted.rpartition(".")
            if parent in sys.modules:
                setattr(sys.modules[parent], child, mod)
        return mod

    def install(self) -> None:
        pass

    def uninstall(self) -> None:
        for dotted in self._mods:
            sys.modules.pop(dotted, None)
        self._mods.clear()

    def exec_source(self, name: str, source: str, package: Optional[str] = None) -> Dict[str, Any]:
        code = compile(source, f"<{self.framework}:{name}>", "exec")
        ns: Dict[str, Any] = {"__name__": name}
        # __file__ ждут некоторые MCUB-модули (loader.py)
        from pathlib import Path as _P

        real = _P("modules") / f"{name}.py"
        ns["__file__"] = str(real) if real.exists() else f"<{self.framework}:{name}>.py"
        if package:
            ns["__package__"] = package  # для `from .. import loader` у Heroku
        exec(code, ns)  # noqa: S102 — исходник уже просканирован L3
        return ns

    async def load_source(self, name: str, source: str) -> Tuple[Any, Any]:
        raise NotImplementedError
