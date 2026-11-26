"""Ports of the level stores (settings §B.10) and the explicit empty pack source.

``ConfigStore`` and ``ScopeTree`` are repository ports: the bus creates them on the connection of the current
unit of work (``uow.repo(ConfigStore)``), so a resolution sees the uncommitted entries of that transaction.
Outside the bus they are only used through a short read-only unit of work. ``pending_writes`` tells the loader
that the transaction changed configuration that is not committed yet; such a snapshot never enters a cache
shared by other transactions.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol, cast
from uuid import UUID

from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import repository_port

from .keys import Chain, freeze_json
from .scopes import ScopeChain, ScopeRef
from .sources.packs import PackFragment

__all__ = [
    "ConfigStore",
    "EmptyPackConfigSource",
    "PackConfigSource",
    "ScopeTree",
    "StoredContribution",
    "StoredOp",
]

type StoredOp = Literal["set", "unset", "append"]

_STORED_OPS: Final = frozenset({"set", "unset", "append"})


@dataclass(frozen=True, slots=True)
class StoredContribution:
    """One row of ``skm_config.entries`` as the resolver sees it (no audit columns)."""

    entry_id: UUID
    key: str
    op: StoredOp
    value: JsonValue
    locked: bool
    row_version: int

    def __post_init__(self) -> None:
        if not isinstance(cast("object", self.entry_id), UUID):
            raise TypeError("entry_id must be a UUID")
        if not isinstance(cast("object", self.key), str) or not self.key:
            raise ValueError("key must be a non-empty string")
        if self.op not in _STORED_OPS:
            raise ValueError(f"op must be one of {sorted(_STORED_OPS)}")
        if self.op == "unset" and self.value is not None:
            raise ValueError("an unset entry carries no value")
        if not isinstance(cast("object", self.locked), bool):
            raise TypeError("locked must be a bool")
        version = cast("object", self.row_version)
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("row_version must be an integer >= 1")
        object.__setattr__(self, "value", freeze_json(self.value, self.key))


@repository_port
class ConfigStore(Protocol):
    def generation(self) -> int:
        """``skm_config.generation`` as this transaction sees it; every config write increments it."""
        ...

    def pending_writes(self) -> bool:
        """Whether this transaction changed entries or the generation without committing them yet.

        PostgreSQL: the generation row was updated by the current transaction. Memory: the working copy of the
        unit of work differs from the state it started from. Read-only transactions answer ``False``.
        """
        ...

    def entries_for(self, scope_ids: Sequence[UUID]) -> Mapping[UUID, Mapping[str, StoredContribution]]:
        """Entries of the given scopes by scope id, then key; scopes without entries may be absent."""
        ...


@repository_port
class ScopeTree(Protocol):
    def instance_scope(self) -> ScopeRef:
        """The instance scope (``NotFound`` until ``skm init`` ran)."""
        ...

    def chain_for(self, scope: ScopeRef, kind: Chain) -> ScopeChain:
        """work: ancestors up to instance (a host scope → ``ValidationFailed``); host: ``(instance, host)``,
        ``(instance)`` for the instance scope itself. Every scope carries its ``label``."""
        ...

    def label(self, scope: ScopeRef) -> str: ...


@repository_port
class PackConfigSource(Protocol):
    def generation(self) -> int:
        """Changes when packs are installed, removed or (de)activated."""
        ...

    def fragments(self, scope_chain: ScopeChain) -> tuple[PackFragment, ...]:
        """Fragments of the packs active in the chain (``extensions.packs.enabled``)."""
        ...


class EmptyPackConfigSource:
    """The pack source when extensions supply no fragments: generation ``0``, no fragments."""

    __slots__ = ()

    def generation(self) -> int:
        return 0

    def fragments(self, scope_chain: ScopeChain) -> tuple[PackFragment, ...]:  # noqa: ARG002 - the port
        return ()
