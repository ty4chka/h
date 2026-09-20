# core/lib/base/__init__.py
# Поверхность core.lib.base из MCUB-fork.
from core.lib.base.permissions import CallbackPermissionManager

try:
    from core.lib.base.permissions import check_trust
except ImportError:  # pragma: no cover
    check_trust = None

__all__ = ["CallbackPermissionManager", "check_trust"]
