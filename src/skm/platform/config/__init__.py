"""Public configuration interfaces (declarations only, settings spec part B)."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .effective import EffectiveConfig
    from .loader import ConfigLoader
    from .registry import SectionValidatorFn, SettingsRegistry
    from .secrets import SecretResolver
    from .store import ConfigStore, PackConfigSource, ScopeTree

__all__ = [
    "ConfigLoader",
    "ConfigStore",
    "EffectiveConfig",
    "PackConfigSource",
    "ScopeTree",
    "SecretResolver",
    "SectionValidatorFn",
    "SettingsRegistry",
]

_EXPORTS: dict[str, str] = {
    "ConfigLoader": ".loader",
    "ConfigStore": ".store",
    "EffectiveConfig": ".effective",
    "PackConfigSource": ".store",
    "ScopeTree": ".store",
    "SecretResolver": ".secrets",
    "SectionValidatorFn": ".registry",
    "SettingsRegistry": ".registry",
}


def __getattr__(name: str) -> object:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
