# core/langpacks/__init__.py
# Языковые паки модулей. Единый движок: берём паки ядра hydra_kernel,
# если они доступны; иначе — пустой пак (модуль живёт на своих strings).
from __future__ import annotations

from typing import Any, Dict


def get_all_module_strings(module_name: str) -> Dict[str, Any]:
    """Все строки модуля из языковых паков: {locale: {key: value}}."""
    try:
        from hydra_kernel.api import lang as _lang

        pack = _lang.MODULE_PACKS.get(module_name, {})
        return {locale: dict(strings) for locale, strings in pack.items()}
    except ImportError:
        return {}


__all__ = ["get_all_module_strings"]
