"""L2 — Compatibility: адаптеры чужих фреймворков поверх ядра.

MCUB, Hikka, Heroku, Dragon, legacy Hydra. Адаптер подменяет импорт
фреймворка shim-модулями и заворачивает чужой модуль в L1 ModuleBase.
"""

from .base import CompatAdapter, ClientProxy, DbShim
from .mcub import McubAdapter
from .frameworks import HikkaAdapter, HerokuAdapter, DragonAdapter
from .legacy_hydra import install_legacy_imports

__all__ = [
    "CompatAdapter",
    "ClientProxy",
    "DbShim",
    "McubAdapter",
    "HikkaAdapter",
    "HerokuAdapter",
    "DragonAdapter",
    "install_legacy_imports",
]
