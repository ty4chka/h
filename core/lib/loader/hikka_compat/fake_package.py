# core/lib/loader/hikka_compat/fake_package.py
# Минимальный is_hikka_module — переэкспорт из пакета.
from core.lib.loader.hikka_compat import is_hikka_module

__all__ = ["is_hikka_module"]
