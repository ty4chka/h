"""L2 — база адаптеров и shim-объекты клиента/БД."""

from __future__ import annotations

import sys
import types
from typing import Any, Dict, List, Optional, Tuple

from ..kernel.transport import NullTransport, Transport
from ..kernel.db import MemoryDB


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
        return types.SimpleNamespace(
            id=self._t.me_id,
            first_name="Hydra",
            username="hydra",
            premium=False,
        )

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
