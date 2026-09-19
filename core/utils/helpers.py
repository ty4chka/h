# core/utils/helpers.py
"""
Utility helpers dlya Hydra Core.
"""

import asyncio
import importlib
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def safe_import(module_path: str, default=None) -> Optional[Any]:
    """Bezopasnyy import s fallback."""
    try:
        return importlib.import_module(module_path)
    except ImportError as e:
        logger.debug(f"Import failed: {module_path} - {e}")
        return default


def get_event_loop():
    """Polucheniye event loop s sozdaniyem novogo esli nuzhno."""
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def run_async(coro):
    """Zapusk korutiny v event loop."""
    loop = get_event_loop()
    return loop.run_until_complete(coro)
