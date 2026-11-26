"""Contract declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skm.kernel.ids import EntityId
    from skm.modules.planning.domain.specification import EntityKind


@dataclass(frozen=True, slots=True)
class MemberRef:
    entity_id: EntityId
    entity_kind: EntityKind
    display_key: str
    position: int


@dataclass(frozen=True, slots=True)
class EntityLinks:
    prerequisites: tuple[MemberRef, ...]
    dependents: tuple[MemberRef, ...]
    criteria: tuple[MemberRef, ...]
    checks: tuple[MemberRef, ...]
    decisions: tuple[MemberRef, ...]
    materials: tuple[MemberRef, ...]
    requirements: tuple[MemberRef, ...]
