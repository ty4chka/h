"""
Core Module Registry
"""
from typing import Dict, Any
_MODULES: Dict[str, Any] = {}

def register(name: str, module):
    _MODULES[name] = module

def get(name: str):
    return _MODULES.get(name)

def all_modules():
    return dict(_MODULES)

def unregister(name: str):
    _MODULES.pop(name, None)
