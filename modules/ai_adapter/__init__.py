"""
Hydra AI Adapter - Умная адаптация модулей
"""

from .ast_analyzer import ModuleASTAnalyzer
from .model import MicroHydraModel
from .llm_converter import LLMConverter, llm_converter
from .model_trainer import ModelTrainer
from .github_collector import GitHubCollector

__all__ = [
    'ModuleASTAnalyzer',
    'MicroHydraModel',
    'LLMConverter',
    'llm_converter',
    'ModelTrainer',
    'GitHubCollector'
]
