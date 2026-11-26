"""Acceptance criteria: typed record and document form (planning §4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from skm.modules.planning.domain.reads import compact, entity_id_of

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.ids import EntityId
    from skm.kernel.json_types import JsonObject, JsonValue


class VerificationMode(StrEnum):
    CHECK = "check"
    REVIEW = "review"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class Criterion:
    id: EntityId
    key: str
    owner: str
    statement: str
    verification_mode: VerificationMode
    checks: tuple[str, ...]
    requirements: tuple[str, ...]


def criterion_from_doc(doc: Mapping[str, JsonValue]) -> Criterion:
    return Criterion(
        id=entity_id_of(doc),
        key=str(doc["key"]),
        owner=str(doc["owner"]),
        statement=str(doc["statement"]),
        verification_mode=VerificationMode(str(doc["verification_mode"])),
        checks=tuple(str(v) for v in cast("list[JsonValue]", doc.get("checks", []))),
        requirements=tuple(str(v) for v in cast("list[JsonValue]", doc.get("requirements", []))),
    )


def criterion_to_doc(criterion: Criterion) -> JsonObject:
    return compact(
        {
            "id": str(criterion.id),
            "key": criterion.key,
            "owner": criterion.owner,
            "statement": criterion.statement,
            "verification_mode": criterion.verification_mode.value,
            "checks": list(criterion.checks),
            "requirements": list(criterion.requirements),
        }
    )
