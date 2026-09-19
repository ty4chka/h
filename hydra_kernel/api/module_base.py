"""L1 — ModuleBase: базовый класс модуля Hydra и его контекст."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from ..kernel.transport import Message, Transport
from ..kernel.db import MemoryDB
from ..kernel.runtime import Runtime
from .config import ModuleConfig
from .event_bus import EventBus
from .permissions import PermissionManager


@dataclass
class ModuleContext:
    """Всё, что ядро даёт модулю. Ничего сверх L0+L1."""

    name: str
    transport: Transport
    db: MemoryDB
    bus: EventBus
    runtime: Runtime
    permissions: PermissionManager
    config: ModuleConfig = field(default_factory=ModuleConfig)
    prefix: str = "."
    hydra: Any = None  # композиция верхнего уровня: для inline/callback-регистрации


class ModuleBase:
    """Базовый класс модуля Hydra (L4 пишется против этого)."""

    name: str = ""
    version: str = "0.0.0"
    dependencies: List[str] = []
    strings: Any = {}

    def __init__(self, ctx: ModuleContext):
        self.ctx = ctx
        self.client = ctx.transport  # совместимое имя
        self.db = ctx.db
        self.bus = ctx.bus
        self.config = ctx.config
        if not self.name:
            self.name = type(self).__name__.lower()

    def __getattribute__(self, item: str) -> Any:
        """self.strings — живой Strings-объект (семантика MCUB i18n)."""
        if item == "strings":
            from .lang import Strings

            packs: Any = {}
            for klass in type(self).__mro__:
                if "strings" in klass.__dict__:
                    packs = klass.__dict__["strings"]
                    break
            if not isinstance(packs, dict):
                packs = {}
            kernel = object.__getattribute__(self, "ctx").hydra
            name = object.__getattribute__(self, "name")
            return Strings(kernel, packs, module_name=name)
        return object.__getattribute__(self, item)

    @property
    def kernel(self) -> Any:
        return self.ctx.hydra

    def t(self, key: str, **kw: Any) -> Any:
        """self.t('key', name=...) — форматированная строка активной локали."""
        return self.strings(key, **kw)

    # -- аргументы команд --
    @staticmethod
    def _raw_after(event: Any) -> str:
        text = getattr(event, "text", "") or ""
        parts = text.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else ""

    def args_raw(self, event: Any) -> str:
        """Сырые аргументы после имени команды."""
        return self._raw_after(event)

    def args(self, event: Any) -> List[Any]:
        """Аргументы с приведением к int/float, где возможно."""
        out: List[Any] = []
        for part in self._raw_after(event).split():
            for cast in (int, float):
                try:
                    out.append(cast(part))
                    break
                except ValueError:
                    continue
            else:
                out.append(part)
        return out

    # -- хуки жизненного цикла (переопределяются модулем) --
    async def on_load(self) -> None:
        pass

    async def on_unload(self) -> None:
        pass

    async def on_install(self) -> None:
        pass

    async def on_uninstall(self) -> None:
        pass

    # -- удобства --
    @property
    def prefix(self) -> str:
        return self.ctx.prefix

    async def send(self, chat_id: int, text: str, **kw: Any) -> Message:
        return await self.ctx.transport.send(chat_id, text, **kw)

    async def reply(self, event: Message, text: str, **kw: Any) -> Message:
        return await event.reply(text, **kw)

    async def get_config(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    async def set_config(self, key: str, value: Any) -> None:
        self.config.set(key, value)

    # -- инлайн-формы с кнопками (callable-callback получает call) --
    async def form(self, chat_id: int, text: str, buttons: Any = None, **kw: Any) -> Message:
        """Отправить форму с кнопками.

        buttons: ряды из dict {"text", "callback"(callable)/"url"/"data"}.
        Callable вызывается как callback(call, *args из btn["args"]).
        """
        hydra = self.ctx.hydra
        bridge = getattr(hydra, "bridge", None) if hydra is not None else None
        rows: List[Any] = []
        n = 0
        for row in buttons or []:
            new_row: List[Any] = []
            for btn in row:
                if isinstance(btn, dict) and callable(btn.get("callback")):
                    n += 1
                    token = f"{self.name}_fm{n}:"
                    cb, args = btn["callback"], btn.get("args", ())

                    async def wrapper(call: Any, _cb: Any = cb, _args: Any = args) -> None:
                        await _cb(call, *_args)

                    if hydra is not None:
                        hydra.register_callback(token, wrapper)
                    new_row.append({"text": btn.get("text", "?"), "data": token})
                elif isinstance(btn, dict) and callable(btn.get("input")):
                    # кнопка ввода: в текстовом режиме жмётся через .it N текст
                    n += 1
                    token = f"{self.name}_in{n}:"
                    if bridge is not None:
                        bridge.register_input(token, btn["input"], btn.get("args", ()))
                    new_row.append(
                        {"text": btn.get("text", "?"), "data": token, "input": True}
                    )
                else:
                    new_row.append(btn)
            rows.append(new_row)
        return await self.ctx.transport.send(int(chat_id), text, buttons=rows, **kw)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Module {self.name} v{self.version}>"
