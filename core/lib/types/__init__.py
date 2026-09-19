# core/lib/types/__init__.py
# Минимальный шим типов MCUB для mcub_engine.
from typing import Any

from .inline_message import InlineMessage

# Как в настоящем MCUB: Event/Kernel — типы-алиасы для аннотаций модулей.
Event = Any
Kernel = Any

__all__ = ["InlineMessage", "Event", "Kernel"]
