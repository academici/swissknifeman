"""Id space of the three-way rebase (planning §5.10, G1): values, references and the documents compared.

Owned by ``rebase.py`` and imported by nothing else. A document is normalized into records addressed by their
stable ``id``; every typed reference (``REFERENCE_FIELDS``) holds the id of its target, and the keys of items,
units and checks are split into their container and their local part. Equality of id-space values is canonical
JSON by target identity. Nothing here mutates its inputs.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Final, Literal, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.planning.domain.display_keys import parse_material_ref
from skm.modules.planning.domain.identity import ENTITY_ARRAYS, display_key_of, iter_entities
from skm.modules.planning.domain.references import (
    RefConverter,
    ReferenceField,
    RefKind,
    context_item,
    rewrite_refs,
)
from skm.modules.planning.domain.specification import EntityKind

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.json_types import JsonObject, JsonValue


class Absent(Enum):
    """A missing member: ``merge3`` compares it like any other value; in JSON the property is left out."""

    ABSENT = "absent"


ABSENT: Final = Absent.ABSENT

type Value = JsonValue | Absent
type Side = Literal["yours", "theirs"]

ARRAY_OF: Final[Mapping[EntityKind, str]] = {kind: array for array, kind in ENTITY_ARRAYS}
SEPARATOR: Final[Mapping[EntityKind, str]] = {
    EntityKind.ITEM: ".",
    EntityKind.UNIT: "/",
    EntityKind.CHECK: ":",
}


# Id-space markers are objects of their own types, never JSON: authored values (``extensions``, free text, any
# object whatever its member names) stay literal and opaque, and no spelling of them is taken for a marker.
@dataclass(frozen=True, slots=True)
class _Local:
    """A reference written locally (``U1``, ``V1``): the same target as its full spelling."""

    target: str


@dataclass(frozen=True, slots=True)
class _Unresolved:
    """A reference that names no entity of its document, kept as written."""

    text: str


@dataclass(frozen=True, slots=True)
class _AsWritten:
    """An item key that does not start with its phase (finding ``key_prefix_mismatch``), kept as written: it
    has no local part to rebuild from the phase, and rebuilding it would silently repair an authored error."""

    key: str


# A repeated ``id`` (a semantic finding, §5.2): the first occurrence is the entity (§5.1), a later one is the
# occurrence ``<id>~<document><n>`` of its own document only — matching the n-th repeats of two documents
# would invent a correspondence. It keeps its record, key and references and is written back with its ``id``
# as authored; its conflicts carry that ``id`` (the §5.10 formula), so a ``conflict_id`` may name two
# conflicts. A base or a current that repeats an ``id`` is refused (``refuse_repeated_revisions``): a
# published revision never holds one (I6); a repeat of base carried into both sides could only be duplicated
# or matched by a guess, and one of current could only be matched to a draft's repeat by a guess.
_OCCURRENCE: Final = "~"


def _tagged(value: object) -> object:
    """``value`` as plain JSON where a marker is an object whose member names no authored object can have:
    every authored member name gets a ``=`` prefix."""
    if isinstance(value, _Local):
        return {"local": value.target}
    if isinstance(value, _Unresolved):
        return {"unresolved": value.text}
    if isinstance(value, _AsWritten):
        return {"as_written": value.key}
    if isinstance(value, dict):
        return {f"={name}": _tagged(member) for name, member in cast("dict[str, object]", value).items()}
    if isinstance(value, list):
        return [_tagged(member) for member in cast("list[object]", value)]
    return value


def canon(value: object) -> str:
    """Canonical text of ``value``: equality that tells ``true`` from ``1``, absent from ``null`` and a marker
    from any authored JSON."""
    if isinstance(value, Absent):
        return "\x00absent"
    return json.dumps(_tagged(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _identity(value: Value) -> Value:
    """``value`` with every local reference replaced by its target: ``U1`` and ``P1.1/U1`` are one target."""
    if isinstance(value, _Local):
        return value.target
    if isinstance(value, dict):
        return {name: cast("JsonValue", _identity(member)) for name, member in value.items()}
    if isinstance(value, list):
        return [cast("JsonValue", _identity(member)) for member in value]
    return value


def same(a: Value, b: Value) -> bool:
    """Equality of id-space values: by target identity, whatever spelling a reference was written in."""
    return canon(_identity(a)) == canon(_identity(b))


def real_id(entity_id: str) -> str:
    """The authored ``id`` of an id-space entity (an occurrence of a repeated id included)."""
    return entity_id.partition(_OCCURRENCE)[0]


# ---------------------------------------------------------------------------------------------- id space


def _to_id(index: Mapping[str, str]) -> RefConverter:
    """Reference -> target id; a local form gives ``_Local(id)``, an unknown one ``_Unresolved(text)``."""

    def convert(ref_field: ReferenceField, value: JsonValue, context: str | None) -> JsonValue:
        if not isinstance(value, str):
            return value
        full, local, section = value, False, None
        if ref_field.ref is RefKind.UNIT_REF and "/" not in value and context is not None:
            full, local = f"{context}/{value}", True
        elif ref_field.ref in (RefKind.CHECK_REF, RefKind.CHECK_LOCAL) and ":" not in value and context:
            full, local = f"{context}:{value}", True
        elif ref_field.ref is RefKind.MATERIAL:
            try:
                full, section = parse_material_ref(value)
            except ValidationFailed:
                return cast("JsonValue", _Unresolved(value))
        target = index.get(full)
        if target is None:
            return cast("JsonValue", _Unresolved(value))
        if section is not None:
            target = f"{target}#{section}"
        return cast("JsonValue", _Local(target)) if local else target

    return convert


def ref_text(value: object, keys: Mapping[str, str]) -> str:
    """The display key a non-local id-space reference stands for."""
    if isinstance(value, _Unresolved):
        return value.text
    return keys.get(value, value) if isinstance(value, str) else ""


def to_key(keys: Mapping[str, str]) -> RefConverter:
    """Id-space reference -> key text; a local reference stays local only while its target is in the context.

    A local reference whose target left the context (a unit moved to another item, a check to another owner)
    is written in full, so it keeps naming its target: a unit's ``checks`` then fails the schema, which is
    reported as a ``schema`` conflict instead of silently binding the same local key of the new context.
    """

    def convert(ref_field: ReferenceField, value: JsonValue, context: str | None) -> JsonValue:
        local = False
        marker = cast("object", value)
        if isinstance(marker, _Unresolved):
            return marker.text
        if isinstance(marker, _Local):
            value, local = marker.target, True
        if not isinstance(value, str):
            return value
        target, _, section = value.partition("#")
        key = keys.get(target, target)
        if section:
            key = f"{key}#{section}"
        if not local:
            return key
        owner, _, rest = key.partition("/" if ref_field.ref is RefKind.UNIT_REF else ":")
        return rest if rest and owner == context else key

    return convert


@dataclass(frozen=True, slots=True)
class SideDoc:
    """One normalized document and its id space."""

    doc: JsonObject
    records: Mapping[EntityKind, Mapping[str, JsonObject]]  # kind -> id -> record, in array order
    entities: Mapping[EntityKind, Mapping[str, tuple[int, JsonObject]]]  # kind -> id -> (index, entity)
    keys: Mapping[str, str]  # id -> display key


def _occurrences(doc: JsonObject, role: str) -> list[tuple[EntityKind, int, JsonObject, str]]:
    """``(kind, index, entity, id-space id)`` of every entity; the n-th (n > 1) is ``<id>~<role><n>``."""
    seen: dict[str, int] = {}
    out: list[tuple[EntityKind, int, JsonObject, str]] = []
    for kind, position, entity in iter_entities(doc):
        raw = entity.get("id")
        if not isinstance(raw, str):
            continue
        seen[raw] = seen.get(raw, 0) + 1
        repeat = f"{raw}{_OCCURRENCE}{role}{seen[raw]}"
        out.append((kind, position, entity, raw if seen[raw] == 1 else repeat))
    return out


def _repeats(doc: JsonObject, name: str) -> list[JsonObject]:
    """An issue for every later occurrence of a repeated ``id`` in ``doc``, the argument called ``name``."""
    issues: list[JsonObject] = []
    for kind, position, _, entity_id in _occurrences(doc, name):
        if _OCCURRENCE in entity_id:
            issues.append({
                "pointer": f"/{name}/{ARRAY_OF[kind]}/{position}/id",
                "schema_pointer": "",
                "message": f"{name} repeats entity id {real_id(entity_id)} (duplicate_id)",
            })  # fmt: skip
    return issues


def refuse_repeated_revisions(base: JsonObject, theirs: JsonObject) -> None:
    """Refuse a base or a current that repeats an ``id``; the issues name the repeats of base, then current.

    Their occurrences cannot be told apart in the other documents: kept by both sides, a repeat of base would
    come back twice (each side's copy is an occurrence of its own document); matched by ordinal or by content,
    a repeat of base or of current would get an identity nobody gave it. Only a draft may hold findings (I6).
    """
    issues = _repeats(base, "base") + _repeats(theirs, "theirs")
    if issues:
        message = "a published revision repeats an entity id (duplicate_id)"
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, message, details={"issues": cast("JsonValue", issues)}
        )


def _item_key(entity: Mapping[str, JsonValue]) -> JsonValue:
    """Id-space ``item.key``: its local part under the phase it names, else the key as written."""
    key = str(entity.get("key", ""))
    phase, dot, local = key.partition(".")
    if dot and local and phase == entity.get("phase"):
        return local
    return cast("JsonValue", _AsWritten(key))


def side_doc(doc: JsonObject, role: str) -> SideDoc:
    """The id space of ``doc``; ``role`` (``b``, ``y``, ``t``) names the occurrences of its repeated ids."""
    occurrences = _occurrences(doc, role)
    index: dict[str, str] = {}
    for kind, _, entity, entity_id in occurrences:
        index.setdefault(display_key_of(kind, entity), entity_id)
    convert = _to_id(index)
    records: dict[EntityKind, dict[str, JsonObject]] = {kind: {} for _, kind in ENTITY_ARRAYS}
    entities: dict[EntityKind, dict[str, tuple[int, JsonObject]]] = {kind: {} for _, kind in ENTITY_ARRAYS}
    keys: dict[str, str] = {}
    for kind, position, entity, raw in occurrences:
        record = copy.deepcopy(entity)
        del record["id"]
        rewrite_refs(ARRAY_OF[kind], record, context_item(ARRAY_OF[kind], entity), convert)
        key = str(entity.get("key", ""))
        if kind is EntityKind.ITEM:
            record["key"] = _item_key(entity)
        elif kind is EntityKind.UNIT:
            item, _, local = key.partition("/")
            record["key"] = [index.get(item, cast("JsonValue", _Unresolved(item))), local]
        elif kind is EntityKind.CHECK:
            record["key"] = [record.pop("owner", cast("JsonValue", _Unresolved(""))), key]
        records[kind][raw] = record
        entities[kind][raw] = (position, entity)
        keys[raw] = display_key_of(kind, entity)
    return SideDoc(doc, records, entities, keys)


def container_of(kind: EntityKind, record: Mapping[str, JsonValue]) -> JsonValue:
    """The id-space container of a record: item -> phase, unit -> item, check / criterion -> owner."""
    if kind is EntityKind.ITEM:
        return record.get("phase")
    if kind in (EntityKind.UNIT, EntityKind.CHECK):
        key = record.get("key")
        return key[0] if isinstance(key, list) and key else None
    if kind is EntityKind.CRITERION:
        return record.get("owner")
    return None


def display_key(kind: EntityKind, record: Mapping[str, JsonValue], keys: Mapping[str, str]) -> str:
    key = record.get("key")
    marker = cast("object", key)
    if isinstance(marker, _AsWritten):
        return marker.key
    if kind is EntityKind.ITEM:
        return f"{ref_text(record.get('phase'), keys)}.{key}"
    if kind in (EntityKind.UNIT, EntityKind.CHECK):
        container, local = cast("list[JsonValue]", key)
        return f"{ref_text(container, keys)}{SEPARATOR[kind]}{local}"
    if kind is EntityKind.MATERIAL:
        return f"material/{key}"
    return str(key)


def positions(side: SideDoc, kind: EntityKind) -> tuple[dict[str, str], dict[str, str | None]]:
    """Per id of ``kind`` in ``side``: its container (canonical text) and its predecessor there."""
    containers: dict[str, str] = {}
    predecessors: dict[str, str | None] = {}
    last: dict[str, str] = {}
    for entity_id, record in side.records[kind].items():
        container = canon(container_of(kind, record))
        containers[entity_id] = container
        predecessors[entity_id] = last.get(container)
        last[container] = entity_id
    return containers, predecessors


# ---------------------------------------------------------------------------------------------- sets


def as_list(value: Value) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def _element(value: JsonValue) -> str:
    """Set identity of an id-space element: a local reference is the same element as the full one."""
    return canon(_identity(value))


def elements(values: list[JsonValue]) -> frozenset[str]:
    return frozenset(_element(x) for x in values)


def set_merge(base: list[JsonValue], yours: list[JsonValue], theirs: list[JsonValue]) -> list[JsonValue]:
    """``theirs`` without what the draft removed, then what the draft added (§5.10 step 6)."""
    in_base, in_yours, in_theirs = elements(base), elements(yours), elements(theirs)
    kept = [x for x in theirs if not (_element(x) in in_base and _element(x) not in in_yours)]
    added = [x for x in yours if _element(x) not in in_base and _element(x) not in in_theirs]
    return copy.deepcopy([*kept, *added])
