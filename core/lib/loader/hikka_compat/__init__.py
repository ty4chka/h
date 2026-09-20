# core/lib/loader/hikka_compat/__init__.py
# Мост «core.lib.loader.hikka_compat из MCUB-fork» -> hikka-совместимость Hydra.
# В MCUB-fork это полноценный пакет совместимости с модулями Hikka; в Hydra
# загрузку hikka-модулей выполняет единый движок (hydra.loader / hydra.module_ops),
# поэтому здесь тонкие обёртки с той же семантикой.
from __future__ import annotations

import re
from pathlib import Path


def is_hikka_module(code: str) -> bool:
    """Эвристика определения Hikka-модуля по исходнику."""

    if not isinstance(code, str):
        return False
    has_loader = "from .. import loader" in code or "import loader" in code
    has_module = re.search(r"class\s+\w+\s*\(\s*loader\.Module\s*\)", code) is not None
    return has_loader and has_module


async def load_hikka_module(kernel, path, name=None, timeout: int = 30):
    """Загрузить hikka-модуль: маршрутизация в единый движок Hydra."""

    path = Path(path)
    code = path.read_text(encoding="utf-8")
    h = getattr(kernel, "h", kernel)

    class _Iface:
        name = name or path.stem

    try:
        from hydra import loader as hloader

        instance = await hloader.load_source(h, code, source_name=_Iface.name, framework="hikka")
        return instance is not None, None
    except Exception:  # noqa: BLE001
        # fallback: прямая загрузка через hikka_compat пакет Hydra
        try:
            from hikka_compat.loader import HikkaModuleAdapter  # noqa: F401
        except Exception:
            raise
        raise


async def unload_hikka_module(kernel, name: str, path=None) -> bool:
    h = getattr(kernel, "h", kernel)
    try:
        return await h.module_ops.unload(str(name))
    except Exception:  # noqa: BLE001
        return False


try:
    from core.lib.loader.hikka_compat import fake_package
except Exception:  # noqa: BLE001
    fake_package = None

__all__ = [
    "fake_package",
    "is_hikka_module",
    "load_hikka_module",
    "unload_hikka_module",
]
