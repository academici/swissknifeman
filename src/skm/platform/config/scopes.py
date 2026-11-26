"""Stored scopes of a resolution chain (settings §B.1).

A stored level always has a UUID scope: ``default``, ``pack`` and ``invocation`` layers carry no scope and
never appear here. The engine type is independent of ``skm.kernel.scopes.ScopeRef`` (kind, id): it speaks the
config vocabulary (``Level``) and carries a display label.
"""

from dataclasses import dataclass, field
from typing import cast
from uuid import UUID

from .keys import CHAIN_LEVELS, STORED_LEVELS, Chain, Level

__all__ = ["ScopeChain", "ScopeRef"]


@dataclass(frozen=True, slots=True)
class ScopeRef:
    level: Level  # one of STORED_LEVELS
    scope_id: UUID
    label: str = field(default="", compare=False)  # "workspace:personal"; display only, not part of equality

    def __post_init__(self) -> None:
        level = Level(self.level)
        if level not in STORED_LEVELS:
            raise ValueError(f"scope level {level.value!r} is not a stored level")
        if not isinstance(cast("object", self.scope_id), UUID):
            raise TypeError(f"scope_id must be a UUID, not {type(self.scope_id).__name__}")
        object.__setattr__(self, "level", level)


@dataclass(frozen=True, slots=True)
class ScopeChain:
    kind: Chain
    scopes: tuple[ScopeRef, ...]  # farthest first: instance, (workspace, project, [plan], run) | (host)

    def __post_init__(self) -> None:
        kind = Chain(self.kind)
        scopes = tuple(self.scopes)
        levels = tuple(scope.level for scope in scopes)
        stored = tuple(level for level in CHAIN_LEVELS[kind] if level in STORED_LEVELS)
        adhoc = kind is Chain.WORK and levels == (Level.INSTANCE, Level.WORKSPACE, Level.PROJECT, Level.RUN)
        if not adhoc and (levels != stored[: len(levels)] or levels[:1] != (Level.INSTANCE,)):
            raise ValueError(f"{kind.value} chain scopes must be a prefix of {[x.value for x in stored]}")
        if len({scope.scope_id for scope in scopes}) != len(scopes):
            raise ValueError("scope ids in a chain must be distinct")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "scopes", scopes)

    @property
    def target(self) -> ScopeRef:
        return self.scopes[-1]

    def ids(self) -> tuple[UUID, ...]:
        return tuple(scope.scope_id for scope in self.scopes)
