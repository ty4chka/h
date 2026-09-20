# core/langpacks/__init__.py
# Языковые паки модулей (поверхность core.langpacks из MCUB-fork).
# Единый движок: берём паки ядра hydra_kernel, если они доступны; иначе —
# пустой пак (модуль живёт на своих inline-strings).
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

# Каталог пользовательских языковых паков (как CUSTOM_LANGPACKS_DIR в MCUB-fork).
CUSTOM_LANGPACKS_DIR = str(Path("data/langpacks"))


def get_all_module_strings(module_name: str) -> Dict[str, Any]:
    """Все строки модуля из языковых паков: {locale: {key: value}}."""

    try:
        from hydra_kernel.api import lang as _lang

        pack = _lang.MODULE_PACKS.get(module_name, {})
        return {locale: dict(strings) for locale, strings in pack.items()}
    except ImportError:
        return {}


def get_module_strings(module_name: str, locale: str) -> Dict[str, Any]:
    """Строки модуля для конкретной локали (как в MCUB-fork)."""

    packs = get_all_module_strings(module_name)
    pack = packs.get(locale)
    if pack is not None:
        return dict(pack)
    fallback = packs.get("ru") or packs.get("en") or {}
    return dict(fallback)


def get_available_locales() -> List[str]:
    try:
        from hydra_kernel.api import lang as _lang

        return list(_lang.get_available_locales())
    except (ImportError, AttributeError):
        return ["ru", "en"]


def reload_packs() -> None:
    try:
        from hydra_kernel.api import lang as _lang

        _lang.reload_packs()
    except (ImportError, AttributeError):
        pass


__all__ = [
    "CUSTOM_LANGPACKS_DIR",
    "get_all_module_strings",
    "get_available_locales",
    "get_module_strings",
    "reload_packs",
]
