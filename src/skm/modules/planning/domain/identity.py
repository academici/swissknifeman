"""Stable entity identities (planning §5.2): assignment in the normative traversal order, no key guessing."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from uuid import UUID

from skm.kernel.ids import EntityId
from skm.modules.planning.domain.specification import EntityKind
from skm.modules.planning.domain.validation.findings import Finding, Severity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.id_generator import IdGenerator
    from skm.kernel.json_types import JsonObject, JsonValue

# (document array, entity kind): the order is the id assignment order.
ENTITY_ARRAYS: Final = (
    ("phases", EntityKind.PHASE),
    ("items", EntityKind.ITEM),
    ("units", EntityKind.UNIT),
    ("requirements", EntityKind.REQUIREMENT),
    ("criteria", EntityKind.CRITERION),
    ("checks", EntityKind.CHECK),
    ("decisions", EntityKind.DECISION),
    ("materials", EntityKind.MATERIAL),
)


@dataclass(frozen=True, slots=True)
class AssignedId:
    pointer: str
    entity_kind: EntityKind
    key: str
    entity_id: EntityId


def display_key_of(kind: EntityKind, entity: Mapping[str, JsonValue]) -> str:
    """Display key of a document entity (``owner:key`` for a check, ``material/<key>`` for a material)."""
    key = str(entity.get("key", ""))
    if kind is EntityKind.CHECK:
        return f"{entity.get('owner', '')}:{key}"
    if kind is EntityKind.MATERIAL:
        return f"material/{key}"
    return key


def iter_entities(doc: Mapping[str, JsonValue]):
    """Yield ``(kind, index, entity)`` in the normative traversal order."""
    for field, kind in ENTITY_ARRAYS:
        entities = doc.get(field)
        if isinstance(entities, list):
            for index, entity in enumerate(entities):
                if isinstance(entity, dict):
                    yield kind, index, entity


def _array_of(kind: EntityKind) -> str:
    return next(field for field, array_kind in ENTITY_ARRAYS if array_kind is kind)


def assign_missing_ids(doc: JsonObject, ids: IdGenerator) -> tuple[JsonObject, tuple[AssignedId, ...]]:
    """Return a copy of ``doc`` in which every entity without ``id`` has a fresh one; ``doc`` is not mutated.

    An ``id`` that is already present is kept as is, whatever its kind.
    """
    result = copy.deepcopy(doc)
    assigned: list[AssignedId] = []
    for kind, index, entity in iter_entities(result):
        if "id" in entity:
            continue
        new_id = ids.new_id()
        entity["id"] = str(new_id)
        assigned.append(
            AssignedId(f"/{_array_of(kind)}/{index}/id", kind, display_key_of(kind, entity), EntityId(new_id))
        )
    return result, tuple(assigned)


def missing_existing_ids(previous: JsonObject, new: JsonObject) -> tuple[str, ...]:
    """Pointers ``<entity>/id`` of entities of ``previous`` (same kind and key) that lack ``id`` in ``new``.

    A previous id is never guessed from a key or text (planning §5.2): the caller refuses the save instead.
    """
    existing = {(kind, display_key_of(kind, entity)) for kind, _, entity in iter_entities(previous)}
    return tuple(
        f"/{_array_of(kind)}/{index}/id"
        for kind, index, entity in iter_entities(new)
        if "id" not in entity and (kind, display_key_of(kind, entity)) in existing
    )


def identity_findings(
    doc: Mapping[str, JsonValue], known: Mapping[EntityId, EntityKind] | None = None
) -> tuple[Finding, ...]:
    """``duplicate_id`` (one id, two objects) and ``entity_kind_changed`` (a known id of another kind)."""
    findings: list[Finding] = []
    seen: dict[str, str] = {}
    for kind, index, entity in iter_entities(doc):
        raw = entity.get("id")
        if not isinstance(raw, str):
            continue
        key = display_key_of(kind, entity)
        pointer = f"/{_array_of(kind)}/{index}/id"
        entity_id = EntityId(UUID(raw))
        if raw in seen:
            findings.append(
                Finding(
                    "duplicate_id",
                    Severity.ERROR,
                    "two entities share one id",
                    key,
                    entity_id,
                    pointer,
                    {"first": seen[raw]},
                )
            )
        else:
            seen[raw] = key
        if known is not None and known.get(entity_id, kind) is not kind:
            findings.append(
                Finding(
                    "entity_kind_changed",
                    Severity.ERROR,
                    "id belongs to an entity of another kind",
                    key,
                    entity_id,
                    pointer,
                    {"known_kind": known[entity_id].value, "kind": kind.value},
                )
            )
    return tuple(findings)
