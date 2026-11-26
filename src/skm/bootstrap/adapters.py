"""Factory tables (kernel-platform §5.2): one per backend, merged from the adapter packages.

``memory_repository_table`` merges the ``REPOSITORIES`` of ``adapters.memory.core`` and of every named module
whose memory package already exports one; ``postgres_repository_table`` does the same over
``adapters.postgres`` (its factories take the unit-of-work connection). A module without ``REPOSITORIES`` has
no repositories of that backend yet (its owner leaf adds them) and contributes nothing. Two packages claiming
one port are a composition error.
"""

import importlib
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import cast

from skm.application_bus.ports import AuditLog, ConsumerReceipts, EventReader, IdempotencyStore, OutboxStore
from skm.kernel.scopes import ScopeRegistry

__all__ = [
    "CORE_PORTS",
    "REPOSITORY_TABLE",
    "RepositoryFactory",
    "memory_repository_table",
    "postgres_repository_table",
]

type RepositoryFactory = Callable[[object], object]

CORE_PORTS: tuple[type[object], ...] = (
    ScopeRegistry,
    IdempotencyStore,
    AuditLog,
    EventReader,
    OutboxStore,
    ConsumerReceipts,
)
REPOSITORY_TABLE: Mapping[type[object], RepositoryFactory] = MappingProxyType({})


def _exported(package: str) -> Mapping[type[object], RepositoryFactory]:
    found = cast(
        "Mapping[type[object], RepositoryFactory] | None",
        getattr(importlib.import_module(package), "REPOSITORIES", None),
    )
    return {} if found is None else found


def _merged(backend: str, modules: Sequence[str]) -> Mapping[type[object], RepositoryFactory]:
    table: dict[type[object], RepositoryFactory] = {}
    root = f"skm.adapters.{backend}"
    for package in (f"{root}.core", *(f"{root}.{name}" for name in modules)):
        for port, factory in _exported(package).items():
            if port in table:
                raise ValueError(
                    f"repository port {port.__qualname__} is bound twice (second owner {package})"
                )
            table[port] = factory
    return MappingProxyType(table)


def postgres_repository_table(modules: Sequence[str]) -> Mapping[type[object], RepositoryFactory]:
    return _merged("postgres", modules)


def memory_repository_table(modules: Sequence[str]) -> Mapping[type[object], RepositoryFactory]:
    return _merged("memory", modules)
