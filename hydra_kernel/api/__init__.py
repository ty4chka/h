"""L1 — Hydra API: то, на чём пишутся модули.

ModuleBase, config, decorators, permissions, lifecycle, EventBus, inline.
Слой знает только L0.
"""

from .event_bus import EventBus
from .permissions import PermissionManager, OWNER, ADMIN, USER, GUEST
from .config import (
    ConfigValue,
    ModuleConfig,
    String,
    Boolean,
    Integer,
    Float,
    Choice,
    Secret,
)
from .decorators import command, watcher, inline_handler, callback, loop
from .module_base import ModuleBase, ModuleContext
from .inline import InlineButton, InlineResult
from .lifecycle import Lifecycle, ModuleState

__all__ = [
    "EventBus",
    "PermissionManager",
    "OWNER",
    "ADMIN",
    "USER",
    "GUEST",
    "ConfigValue",
    "ModuleConfig",
    "String",
    "Boolean",
    "Integer",
    "Float",
    "Choice",
    "Secret",
    "command",
    "watcher",
    "inline_handler",
    "callback",
    "loop",
    "ModuleBase",
    "ModuleContext",
    "InlineButton",
    "InlineResult",
    "Lifecycle",
    "ModuleState",
]
