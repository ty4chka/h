"""L0 — runtime: метаданные процесса, event loop, logging."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
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
    """Configure useful, shared logging without creating duplicate handlers.

    Production normally configures the root logger in :mod:`m`; library and
    offline callers get a modest stdout fallback.  When a path is supplied the
    file is bounded so a long-running Termux process cannot fill phone storage.
    """

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric_level)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if not root.handlers:
        stream = logging.StreamHandler(sys.stdout)
        stream.setLevel(numeric_level)
        stream.setFormatter(fmt)
        root.addHandler(stream)

    if logfile:
        path = Path(logfile).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        already_present = any(
            isinstance(handler, RotatingFileHandler)
            and Path(getattr(handler, "baseFilename", "")).resolve() == path
            for handler in root.handlers
        )
        if not already_present:
            file_handler = RotatingFileHandler(
                path,
                maxBytes=2 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(fmt)
            root.addHandler(file_handler)

    logger = logging.getLogger("hydra_kernel")
    logger.setLevel(numeric_level)
    # Let transport/lifecycle/module logs reach the same file and console as
    # Telethon and the launcher.  Older code installed a private console-only
    # handler here, which silently excluded the useful diagnostics from file.
    logger.propagate = True
    return logger


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Точка входа в event loop с корректной остановкой на Ctrl-C."""
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        return None
