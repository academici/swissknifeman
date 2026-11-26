"""CLI group contract and discovery (cli §1.1).

``GROUPS`` is derived, never listed by hand: every public module of this package exports ``GROUP:
CommandGroup`` and the tuple is sorted by ``(order, name)``. A new group is a new file; this file does not
change. A module without ``GROUP`` or two groups with one name stop the start (``GroupRegistryError``).
"""

import argparse
import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType

__all__ = ["GROUPS", "CommandGroup", "GroupRegistryError", "SubParsers", "discover_groups"]

# cli §1.1 explicitly requires argparse's subparser action contract.
type SubParsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


@dataclass(frozen=True, slots=True)
class CommandGroup:
    name: str
    help: str
    register: Callable[[SubParsers], None]
    requires_backend: bool = True
    module: str | None = None
    order: int = 100


class GroupRegistryError(ValueError):
    """The command package is inconsistent (duplicate group name, missing or malformed ``GROUP``)."""


def discover_groups(package: ModuleType) -> tuple[CommandGroup, ...]:
    """The ``GROUP`` of every public module of ``package``, sorted by ``(order, name)``."""
    found: dict[str, tuple[str, CommandGroup]] = {}
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        module_name = f"{package.__name__}.{info.name}"
        group = getattr(importlib.import_module(module_name), "GROUP", None)
        if not isinstance(group, CommandGroup):
            raise GroupRegistryError(f"{module_name} must export GROUP: CommandGroup")
        if group.name in found:
            raise GroupRegistryError(
                f"command group {group.name!r} is declared by {found[group.name][0]} and {module_name}"
            )
        found[group.name] = (module_name, group)
    return tuple(sorted((group for _, group in found.values()), key=lambda group: (group.order, group.name)))


GROUPS: tuple[CommandGroup, ...] = discover_groups(importlib.import_module(__name__))
