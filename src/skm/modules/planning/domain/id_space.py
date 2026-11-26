"""Id-space normalization of specification documents for structural diffing (planning §5.8, G1).

Every entity is indexed by its stable ``id``; typed references declared in ``REFERENCE_FIELDS`` are rewritten
to target entity IDs so references that only followed a ``rekey`` compare equal in id-space while references
that switched to another entity render their ``before``/``after`` values as canonical ``display_key`` strings.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast
from uuid import UUID

from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import EntityId
from skm.modules.planning.domain.canonical import normalize_document
from skm.modules.planning.domain.display_keys import parse_material_ref
from skm.modules.planning.domain.identity import ENTITY_ARRAYS, display_key_of, iter_entities
from skm.modules.planning.domain.references import (
    RefConverter,
    ReferenceField,
    RefKind,
    context_item,
    rewrite_refs,
)
from skm.modules.planning.domain.specification import SPECIFICATION_URN, EntityKind

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.json_types import JsonObject, JsonValue

__all__ = [
    "PLAN_LEVEL_FIELDS",
    "IdSpaceDocument",
    "IdSpaceEntity",
    "container_of",
    "from_id_space",
    "to_id_space",
]

PLAN_LEVEL_FIELDS: Final = (
    "title",
    "goal",
    "context_md",
    "non_goals",
    "rules",
    "brief",
    "execution_constraints",
    "sections",
    "extensions",
    "plan_relations",
)

_ARRAY_OF: Final[Mapping[EntityKind, str]] = MappingProxyType({kind: array for array, kind in ENTITY_ARRAYS})
_UNRESOLVED_KEY: Final = "unresolved"
_AS_WRITTEN_KEY: Final = "as_written"


@dataclass(frozen=True, slots=True)
class IdSpaceEntity:
    """One entity in both id-space (for comparison) and display-key-space (for rendering changes)."""

    entity_id: EntityId
    kind: EntityKind
    position: int
    display_key: str
    id_record: JsonObject
    key_record: JsonObject


@dataclass(frozen=True, slots=True)
class IdSpaceDocument:
    """Normalized specification projected into id-space and display-key-space."""

    doc: JsonObject
    plan_fields: JsonObject
    key_plan_fields: JsonObject
    entities: Mapping[EntityKind, Mapping[EntityId, IdSpaceEntity]]
    id_to_key: Mapping[str, str]
    key_to_id: Mapping[str, str]


def _to_id_converter(key_to_id: Mapping[str, str]) -> RefConverter:
    def convert(ref_field: ReferenceField, value: JsonValue, context: str | None) -> JsonValue:
        if not isinstance(value, str):
            return value
        full = value
        section: str | None = None
        if ref_field.ref is RefKind.UNIT_REF and "/" not in value and context:
            full = f"{context}/{value}"
        elif ref_field.ref in (RefKind.CHECK_REF, RefKind.CHECK_LOCAL) and ":" not in value and context:
            full = f"{context}:{value}"
        elif ref_field.ref is RefKind.MATERIAL:
            try:
                full, section = parse_material_ref(value)
            except ValidationFailed:
                return {_UNRESOLVED_KEY: value}
        target = key_to_id.get(full)
        if target is None:
            return {_UNRESOLVED_KEY: value}
        return f"{target}#{section}" if section is not None else target

    return convert


def _to_display_key_converter(id_to_key: Mapping[str, str]) -> RefConverter:
    def convert(ref_field: ReferenceField, value: JsonValue, context: str | None) -> JsonValue:
        if isinstance(value, dict) and _UNRESOLVED_KEY in value:
            return value[_UNRESOLVED_KEY]
        if not isinstance(value, str):
            return value
        target_id, sep, section = value.partition("#")
        display = id_to_key.get(target_id, target_id)
        if sep:
            return f"{display}#{section}"
        if ref_field.ref is RefKind.CHECK_LOCAL and context and display.startswith(f"{context}:"):
            return display[len(context) + 1 :]
        if ref_field.ref is RefKind.UNIT_REF and context and display.startswith(f"{context}/"):
            return display[len(context) + 1 :]
        return display

    return convert


def _parse_entity_id(raw: JsonValue) -> EntityId | None:
    if not isinstance(raw, str):
        return None
    try:
        return EntityId(UUID(raw))
    except ValueError:
        return None


def _ref_to_key(val: JsonValue, id_to_key: Mapping[str, str]) -> str:
    if isinstance(val, dict) and _UNRESOLVED_KEY in val:
        return str(val[_UNRESOLVED_KEY])
    if isinstance(val, str):
        return id_to_key.get(val, val)
    return str(val)


def container_of(kind: EntityKind, record: Mapping[str, JsonValue]) -> JsonValue:
    """Return the id-space container of ``record``: item -> phase, unit -> item, check/criterion -> owner."""
    if kind is EntityKind.ITEM:
        return record.get("phase")
    if kind in (EntityKind.UNIT, EntityKind.CHECK):
        key = record.get("key")
        return key[0] if isinstance(key, list) and key else None
    if kind is EntityKind.CRITERION:
        return record.get("owner")
    return None


def _decompose_key(
    kind: EntityKind,
    entity: Mapping[str, JsonValue],
    id_rec: JsonObject,
    key_to_id: Mapping[str, str],
) -> None:
    raw_key = str(entity.get("key", ""))
    if kind is EntityKind.ITEM:
        phase_part, dot, local = raw_key.partition(".")
        if dot and local and phase_part == entity.get("phase"):
            id_rec["key"] = local
        else:
            id_rec["key"] = {_AS_WRITTEN_KEY: raw_key}
    elif kind is EntityKind.UNIT:
        item_key, _, local = raw_key.partition("/")
        item_target: JsonValue = key_to_id.get(item_key) or cast("JsonValue", {_UNRESOLVED_KEY: item_key})
        id_rec["key"] = [item_target, local]
    elif kind is EntityKind.CHECK:
        owner_raw = str(entity.get("owner", ""))
        owner_id: JsonValue = id_rec.get("owner") or cast("JsonValue", {_UNRESOLVED_KEY: owner_raw})
        id_rec["key"] = [owner_id, raw_key]


def _project_to_key_space(
    kind: EntityKind,
    id_rec: Mapping[str, JsonValue],
    id_to_key: Mapping[str, str],
    to_disp: RefConverter,
) -> JsonObject:
    rec: JsonObject = copy.deepcopy(dict(id_rec))
    raw_key = rec.get("key")
    if kind is EntityKind.ITEM:
        if isinstance(raw_key, dict) and _AS_WRITTEN_KEY in raw_key:
            rec["key"] = raw_key[_AS_WRITTEN_KEY]
        else:
            phase_disp = _ref_to_key(rec.get("phase"), id_to_key)
            rec["key"] = f"{phase_disp}.{raw_key}"
    elif kind is EntityKind.UNIT and isinstance(raw_key, list) and len(raw_key) == 2:
        item_disp = _ref_to_key(raw_key[0], id_to_key)
        rec["key"] = f"{item_disp}/{raw_key[1]}"
    elif kind is EntityKind.CHECK and isinstance(raw_key, list) and len(raw_key) == 2:
        rec["owner"] = raw_key[0]
        rec["key"] = raw_key[1]

    context: str | None = None
    if kind is EntityKind.UNIT:
        context = str(rec.get("key", "")).split("/", 1)[0]
    elif kind is EntityKind.CRITERION:
        context = _ref_to_key(rec.get("owner"), id_to_key).split("/", 1)[0]

    rewrite_refs(_ARRAY_OF[kind], rec, context, to_disp)
    return rec


def to_id_space(doc: Mapping[str, JsonValue]) -> IdSpaceDocument:
    """Project a specification document into id-space."""
    raw_doc: JsonObject = copy.deepcopy(dict(doc))
    key_to_id: dict[str, str] = {}
    id_to_key: dict[str, str] = {}
    raw_items: list[tuple[EntityKind, int, JsonObject, EntityId, str]] = []

    for kind, position, entity in iter_entities(raw_doc):
        entity_id = _parse_entity_id(entity.get("id"))
        if entity_id is None:
            continue
        disp = display_key_of(kind, entity)
        id_str = str(entity_id)
        if disp not in key_to_id:
            key_to_id[disp] = id_str
        if id_str not in id_to_key:
            id_to_key[id_str] = disp
        raw_items.append((kind, position, entity, entity_id, disp))

    to_id = _to_id_converter(key_to_id)
    to_disp = _to_display_key_converter(id_to_key)
    by_kind: dict[EntityKind, dict[EntityId, IdSpaceEntity]] = {kind: {} for _, kind in ENTITY_ARRAYS}

    for kind, position, entity, entity_id, disp in raw_items:
        if entity_id in by_kind[kind]:
            continue
        array = _ARRAY_OF[kind]
        context = context_item(array, entity)
        id_rec = copy.deepcopy(entity)
        id_rec.pop("id", None)
        rewrite_refs(array, id_rec, context, to_id)
        _decompose_key(kind, entity, id_rec, key_to_id)

        key_rec = _project_to_key_space(kind, id_rec, id_to_key, to_disp)

        by_kind[kind][entity_id] = IdSpaceEntity(
            entity_id=entity_id,
            kind=kind,
            position=position,
            display_key=disp,
            id_record=id_rec,
            key_record=key_rec,
        )

    plan_fields: JsonObject = {
        field: copy.deepcopy(raw_doc[field]) for field in PLAN_LEVEL_FIELDS if field in raw_doc
    }
    return IdSpaceDocument(
        doc=raw_doc,
        plan_fields=plan_fields,
        key_plan_fields=copy.deepcopy(plan_fields),
        entities=MappingProxyType({k: MappingProxyType(v) for k, v in by_kind.items()}),
        id_to_key=MappingProxyType(id_to_key),
        key_to_id=MappingProxyType(key_to_id),
    )


def from_id_space(id_doc: IdSpaceDocument) -> JsonObject:
    """Reconstruct a normalized specification document by projecting ``id_doc`` through ``id_to_key``."""
    to_disp = _to_display_key_converter(id_doc.id_to_key)
    out: JsonObject = {
        "schema": id_doc.doc.get("schema", SPECIFICATION_URN),
        **copy.deepcopy(id_doc.plan_fields),
    }
    for array, kind in ENTITY_ARRAYS:
        items: list[JsonValue] = [
            {
                "id": str(ent.entity_id),
                **_project_to_key_space(kind, ent.id_record, id_doc.id_to_key, to_disp),
            }
            for ent in id_doc.entities[kind].values()
        ]
        if items or array in ("phases", "items"):
            out[array] = items
    return normalize_document(out)
