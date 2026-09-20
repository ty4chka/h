"""L1 — EventBus: pub/sub для межмодульного взаимодействия."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Union

Listener = Callable[..., Union[Awaitable[None], None]]
logger = logging.getLogger("hydra_kernel.bus")


class EventBus:
    def __init__(self) -> None:
        self._subs: Dict[str, List[Listener]] = {}

    def subscribe(self, event: str, listener: Listener) -> Callable[[], None]:
        self._subs.setdefault(event, []).append(listener)

        def unsubscribe() -> None:
            lst = self._subs.get(event, [])
            if listener in lst:
                lst.remove(listener)

        return unsubscribe

    async def emit(self, event: str, **payload: Any) -> List[Any]:
        """Вызывает слушателей event и '*'. Ошибки слушателей логируются,
        но не валят эмиттера. Возвращает список результатов."""
        results: List[Any] = []
        for name in (event, "*"):
            for listener in list(self._subs.get(name, [])):
                try:
                    res = listener(event, **payload)
                    if asyncio.iscoroutine(res):
                        res = await res
                    results.append(res)
                except Exception:  # noqa: BLE001 — шина не должна падать
                    logger.exception("listener %r for %r failed", listener, event)
        return results
