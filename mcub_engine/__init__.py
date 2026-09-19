# mcub_engine/__init__.py
"""
MCUB Engine for Hydra UserBot
=============================

Полная эмуляция ядра MCUB-fork (github.com/hairpin01/MCUB-fork)
поверх Telethon-клиента Hydra. Модули repo-MCUB-fork работают
БЕЗ модификации кода; инлайн-кнопки превращаются в команды.

Использование:
    from mcub_engine import install, get_kernel
    kernel = install(client)          # один раз при старте
"""

from __future__ import annotations

import logging

logger = logging.getLogger("mcub_engine")

_kernel = None
_installed = False


def get_kernel():
    return _kernel


def install(client, prefix: str | None = None):
    """Инициализировать движок (идемпотентно). Возвращает McubKernel."""
    global _kernel, _installed
    if _installed and _kernel is not None:
        return _kernel

    if prefix is None:
        prefix = "."
        try:
            import config
            prefix = getattr(config, "prefix", ".") or "."
        except Exception:
            pass

    # 1. инъекция utils API
    from .utils_inject import inject_utils
    inject_utils()

    # 2. ядро
    from .runtime import McubKernel
    _kernel = McubKernel(client, prefix=prefix)

    # 3. ПЕРЕДАЁМ ЯДРО В ЗАГРУЗЧИК (КРИТИЧЕСКИ ВАЖНО!)
    from .loader import set_loader_kernel
    set_loader_kernel(_kernel)

    _installed = True
    logger.info(f"MCUB Engine installed (prefix={prefix!r})")
    return _kernel


def is_installed() -> bool:
    return _installed


__all__ = ["install", "get_kernel", "is_installed"]
