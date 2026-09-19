# core/events/dispatcher.py
"""
Event Dispatcher - tsentralizovannaya sistema obrabotki sobytiy.
"""

import asyncio
import logging
from typing import Callable, Dict, List, Any

from telethon import events

logger = logging.getLogger(__name__)


class EventDispatcher:
    """
    Tsentralizovannyy dispatcher sobytiy.

    Pozvolyayet registrerovat obrabotchiki s prioritetami,
    filtrami i middleware.
    """

    def __init__(self, client):
        self.client = client
        self._handlers: Dict[str, List[Dict]] = {}
        self._middleware: List[Callable] = []
        self._running = False

    def add_handler(
        self,
        event_type: str,
        handler: Callable,
        priority: int = 0,
        filters: List[Callable] = None,
    ):
        """Dobavleniye obrabotchika sobytiya."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        self._handlers[event_type].append({
            'handler': handler,
            'priority': priority,
            'filters': filters or [],
        })

        # Sortirovka po prioritetu
        self._handlers[event_type].sort(
            key=lambda x: x['priority'], reverse=True
        )

    def add_middleware(self, middleware: Callable):
        """Dobavleniye middleware dlya vsekh sobytiy."""
        self._middleware.append(middleware)

    async def dispatch(self, event_type: str, event):
        """Otpravka sobytiya vsem obrabotchikam."""
        handlers = self._handlers.get(event_type, [])

        for h in handlers:
            # Primeneniye middleware
            for mw in self._middleware:
                event = await mw(event)
                if event is None:
                    break

            if event is None:
                continue

            # Primeneniye fil'trov
            skip = False
            for f in h['filters']:
                if not await f(event):
                    skip = True
                    break

            if skip:
                continue

            # Vypolneniye obrabotchika
            try:
                await h['handler'](event)
            except Exception as e:
                logger.error(f"Handler error: {e}", exc_info=True)

    def remove_handler(self, event_type: str, handler: Callable):
        """Udaleniye obrabotchika."""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type]
                if h['handler'] != handler
            ]
