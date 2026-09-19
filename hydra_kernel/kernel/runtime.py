"""L0 — runtime: метаданные процесса, event loop, logging."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Coroutine, Optional


@dataclass
class Runtime:
    version: str = "0.1.0"
    me_id: int = 0
    started_at: float = field(default_factory=time.time)

    @property
    def uptime(self) -> float:
        return time.time() - self.started_at


def setup_logging(level: str = "INFO", logfile: Optional[str] = None) -> logging.Logger:
    """Единая настройка логгера ядра (без побочных эффектов при импорте)."""
    logger = logging.getLogger("hydra_kernel")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
        if logfile:
            fh = logging.FileHandler(logfile, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        logger.propagate = False
    return logger


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Точка входа в event loop с корректной остановкой на Ctrl-C."""
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        return None
