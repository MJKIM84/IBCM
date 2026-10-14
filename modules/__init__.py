"""IBCM 업무 모듈의 공개 규격과 레지스트리."""

from .base import ModuleContext, ModuleDefinition, ModuleResult
from .registry import MODULES, get_module, get_modules

__all__ = [
    "ModuleContext",
    "ModuleDefinition",
    "ModuleResult",
    "MODULES",
    "get_module",
    "get_modules",
]
