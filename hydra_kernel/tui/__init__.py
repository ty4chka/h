"""TUI Hydra: терминальный GUI-редактор модулей, стартует с юзерботом."""

from .model import EditorModel
from .app import run_tui

__all__ = ["EditorModel", "run_tui"]
