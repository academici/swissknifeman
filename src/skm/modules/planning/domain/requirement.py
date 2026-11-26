"""Requirements: typed record and document form (planning §4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from skm.modules.planning.domain.reads import compact, entity_id_of

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Literal

    from skm.kernel.ids import EntityId
    from skm.kernel.json_types import JsonObject, JsonValue


class Priority(StrEnum):
    MUST = "must"
    SHOULD = "should"
    COULD = "could"


@dataclass(frozen=True, slots=True)
class RequirementSource:
    kind: Literal["brief_message", "owner", "derived", "external"]
    ref: str | None


@dataclass(frozen=True, slots=True)
class Requirement:
    id: EntityId
    key: str
    statement: str
    priority: Priority
    source: RequirementSource
    owners: tuple[str, ...]


def requirement_from_doc(doc: Mapping[str, JsonValue]) -> Requirement:
    source = cast("Mapping[str, JsonValue]", doc["source"])
    ref = source.get("ref")
    return Requirement(
        id=entity_id_of(doc),
        key=str(doc["key"]),
        statement=str(doc["statement"]),
        priority=Priority(str(doc["priority"])),
        source=RequirementSource(
            cast("Literal['brief_message', 'owner', 'derived', 'external']", source["kind"]),
            None if ref is None else str(ref),
        ),
        owners=tuple(str(v) for v in cast("list[JsonValue]", doc.get("owners", []))),
    )


def requirement_to_doc(requirement: Requirement) -> JsonObject:
    return compact(
        {
            "id": str(requirement.id),
            "key": requirement.key,
            "statement": requirement.statement,
            "priority": requirement.priority.value,
            "source": compact({"kind": requirement.source.kind, "ref": requirement.source.ref}),
            "owners": list(requirement.owners),
        }
    )
