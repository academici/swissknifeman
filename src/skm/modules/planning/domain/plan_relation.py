"""Relations between plans: typed record and document form (planning §4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from skm.modules.planning.domain.reads import compact

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.json_types import JsonObject, JsonValue


class PlanRelationKind(StrEnum):
    PREDECESSOR = "predecessor"
    SUPERSEDES = "supersedes"
    RELATED = "related"


@dataclass(frozen=True, slots=True)
class PlanRelation:
    kind: PlanRelationKind
    target: str
    note: str | None


def plan_relation_from_doc(doc: Mapping[str, JsonValue]) -> PlanRelation:
    note = doc.get("note")
    return PlanRelation(
        PlanRelationKind(str(doc["kind"])), str(doc["target"]), None if note is None else str(note)
    )


def plan_relation_to_doc(relation: PlanRelation) -> JsonObject:
    return compact({"kind": relation.kind.value, "target": relation.target, "note": relation.note})
