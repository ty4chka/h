# core/lib/loader/__init__.py
"""
📦 Пакет эмулятора ядра MCUB для Hydra
"""

from .module_base import (
    ModuleBase,
    command,
    loop,
    on_install,
    on_uninstall,
    StringsMock,
    DBMock,
    KernelMock,
)

from .module_config import (
    ModuleConfig,
    ConfigValue,
    String,
    Choice,
    Integer,
    Secret,
    Boolean,
    Placeholders,
    List,
    Float,
)

__all__ = [
    'ModuleBase',
    'command',
    'loop',
    'on_install',
    'on_uninstall',
    'StringsMock',
    'DBMock',
    'KernelMock',
    'ModuleConfig',
    'ConfigValue',
    'String',
    'Choice',
    'Integer',
    'Secret',
    'Boolean',
    'Placeholders',
    'List',
    'Float',
]
