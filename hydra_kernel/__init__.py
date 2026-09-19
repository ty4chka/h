"""Hydra Kernel — общее ядро для Hydra и совместимых фреймворков.

Слои:
  L0 hydra_kernel.kernel   — транспорт, event loop, DB, runtime, logging
  L1 hydra_kernel.api      — ModuleBase, config, decorators, permissions,
                             lifecycle, EventBus, inline
  L2 hydra_kernel.compat   — MCUB / Hikka / Heroku / Dragon / legacy Hydra
  L3 hydra_kernel.pkg      — loader, registry, installer, resolver, manifest,
                             security scanner

Ядро не импортирует ничего из Hydra и фреймворков: зависимости направлены
строго вниз (L4 -> L3 -> L2 -> L1 -> L0).
"""

__version__ = "0.1.0"

from .app import Kernel, Hydra  # noqa: E402  (composition roots)

__all__ = ["Kernel", "Hydra", "__version__"]
