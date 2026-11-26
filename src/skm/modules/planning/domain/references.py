"""Typed references between document entities and the rewrite/scrub machinery (planning §5.3 items 4 and 6).

References are resolved by *kind* from the table ``REFERENCE_FIELDS``: a string is never rewritten because it
happens to look like a key. A reference that nobody rewrites stays as written and becomes ``ref_unknown`` at
validation; title or path equality never creates a mapping.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.modules.planning.domain.display_keys import (
    KeyKind,
    parse_entity_id,
    parse_key,
    parse_material_ref,
)
from skm.modules.planning.domain.identity import ENTITY_ARRAYS, display_key_of, iter_entities
from skm.modules.planning.domain.specification import EntityKind

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from skm.kernel.json_types import JsonObject, JsonValue


class RefKind(StrEnum):
    PHASE = "phase"
    ITEM = "item"
    WORK = "work"  # phase | item | unit
    ENTITY = "entity"  # phase | item | unit | decision | requirement | criterion
    UNIT_REF = "unit_ref"  # local ``U<k>`` (inside the owning item) or the full unit key
    CHECK_REF = "check_ref"  # ``V<n>`` (owner implied by context) or ``<owner>:V<n>``
    CHECK_LOCAL = "check_local"  # unit.checks: ``V<n>`` of the unit's own item
    REQUIREMENT = "requirement"
    DECISION = "decision"
    MATERIAL = "material"  # ``material/<key>[#section]``


@dataclass(frozen=True, slots=True)
class ReferenceField:
    """One reference-carrying member. ``path`` segments ending in ``[]`` iterate an array.

    ``when`` restricts the field to objects whose sibling member has the given value (read/evidence ``kind``).
    """

    array: str
    path: tuple[str, ...]
    ref: RefKind
    when: tuple[str, str] | None = None


def _reads(array: str, member: str) -> tuple[ReferenceField, ...]:
    return (
        ReferenceField(array, (f"{member}[]", "ref"), RefKind.MATERIAL, ("kind", "material")),
        ReferenceField(array, (f"{member}[]", "ref"), RefKind.ENTITY, ("kind", "plan_entity")),
    )


REFERENCE_FIELDS: Final[tuple[ReferenceField, ...]] = (
    ReferenceField("phases", ("depends_on[]",), RefKind.PHASE),
    ReferenceField("phases", ("batches[]", "items[]"), RefKind.ITEM),
    *_reads("phases", "supporting"),
    ReferenceField("items", ("phase",), RefKind.PHASE),
    ReferenceField("items", ("depends_on[]",), RefKind.ITEM),
    ReferenceField("items", ("relations[]", "target"), RefKind.ENTITY),
    ReferenceField("items", ("implements[]",), RefKind.REQUIREMENT),
    ReferenceField("items", ("decisions[]",), RefKind.DECISION),
    ReferenceField("items", ("review", "covers[]"), RefKind.ITEM),
    *_reads("items", "reads"),
    *_reads("items", "examples"),
    ReferenceField("units", ("parent",), RefKind.UNIT_REF),
    ReferenceField("units", ("depends_on[]",), RefKind.UNIT_REF),
    ReferenceField("units", ("checks[]",), RefKind.CHECK_LOCAL),
    ReferenceField("units", ("implements[]",), RefKind.REQUIREMENT),
    *_reads("units", "reads"),
    ReferenceField("checks", ("owner",), RefKind.WORK),
    ReferenceField("criteria", ("owner",), RefKind.WORK),
    ReferenceField("criteria", ("checks[]",), RefKind.CHECK_REF),
    ReferenceField("criteria", ("requirements[]",), RefKind.REQUIREMENT),
    ReferenceField("requirements", ("owners[]",), RefKind.WORK),
    ReferenceField("decisions", ("applies_to[]",), RefKind.WORK),
    ReferenceField("decisions", ("supersedes[]",), RefKind.DECISION),
    ReferenceField("decisions", ("evidence[]", "ref"), RefKind.ENTITY, ("kind", "entity")),
    ReferenceField("decisions", ("evidence[]", "ref"), RefKind.MATERIAL, ("kind", "material")),
    ReferenceField("materials", ("applies_to[]",), RefKind.WORK),
)

_KEY_KIND_OF: Final = {
    EntityKind.PHASE: KeyKind.PHASE,
    EntityKind.ITEM: KeyKind.ITEM,
    EntityKind.UNIT: KeyKind.UNIT,
    EntityKind.REQUIREMENT: KeyKind.REQUIREMENT,
    EntityKind.CRITERION: KeyKind.CRITERION,
    EntityKind.CHECK: KeyKind.CHECK,
    EntityKind.DECISION: KeyKind.DECISION,
    EntityKind.MATERIAL: KeyKind.MATERIAL,
}


@dataclass(frozen=True, slots=True)
class EntityLocation:
    kind: EntityKind
    index: int
    key: str

    @property
    def array(self) -> str:
        return next(field for field, kind in ENTITY_ARRAYS if kind is self.kind)

    @property
    def pointer(self) -> str:
        return f"/{self.array}/{self.index}"


def key_kind_of(kind: EntityKind) -> KeyKind:
    return _KEY_KIND_OF[kind]


def find_entity(doc: Mapping[str, JsonValue], ref: str) -> EntityLocation | None:
    """Locate an entity by display key or ``entity:<uuid>`` in ``doc``; ``None`` when there is none."""
    wanted_id = str(parse_entity_id(ref)) if ref.startswith("entity:") else None
    for kind, index, entity in iter_entities(doc):
        key = display_key_of(kind, entity)
        if (wanted_id is not None and entity.get("id") == wanted_id) or (wanted_id is None and key == ref):
            return EntityLocation(kind, index, key)
    return None


def resolve_ref(doc: Mapping[str, JsonValue], ref: str, *, change_index: int | None = None) -> EntityLocation:
    """Resolve a display key or ``entity:<uuid>`` (``INVALID_REFERENCE`` / ``NOT_FOUND``)."""
    if ref.startswith("entity:"):
        try:
            UUID(ref[len("entity:") :])
        except ValueError:
            raise ValidationFailed(
                ErrorCode.INVALID_REFERENCE, "not a valid reference", details={"text": ref}
            ) from None
    else:
        parse_key(ref)
    found = find_entity(doc, ref)
    if found is None:
        details: dict[str, JsonValue] = {"kind": "entity", "ref": ref}
        if change_index is not None:
            details["change_index"] = change_index
        raise NotFound(ErrorCode.NOT_FOUND, "entity not found", details=details)
    return found


# ---------------------------------------------------------------------------------------------- walking

_DELETE: Final = object()
type _Transform = Callable[[ReferenceField, str, str | None], object]


@dataclass(frozen=True, slots=True)
class _Leaf:
    container: list[JsonValue] | dict[str, JsonValue]
    key: str | int
    holder: Mapping[str, JsonValue]
    ancestors: tuple[tuple[list[JsonValue], int], ...]


def _walk(
    node: JsonValue, segments: tuple[str, ...], ancestors: tuple[tuple[list[JsonValue], int], ...]
) -> Iterator[_Leaf]:
    if not isinstance(node, dict):
        return
    segment = segments[0]
    iterate = segment.endswith("[]")
    name = segment.removesuffix("[]")
    child = node.get(name)
    if child is None:
        return
    last = len(segments) == 1
    if iterate:
        if not isinstance(child, list):
            return
        for index, element in enumerate(child):
            if last:
                yield _Leaf(child, index, node, ancestors)
            else:
                yield from _walk(element, segments[1:], (*ancestors, (child, index)))
    elif last:
        yield _Leaf(node, name, node, ancestors)
    else:
        yield from _walk(child, segments[1:], ancestors)


def context_item(array: str, entity: Mapping[str, JsonValue]) -> str | None:
    """The item whose scope a local reference of ``entity`` is written in."""
    if array == "units":
        return str(entity.get("key", "")).split("/", 1)[0]
    if array == "criteria":
        return str(entity.get("owner", "")).split("/", 1)[0]
    return None


def _get(leaf: _Leaf) -> JsonValue:
    container, key = leaf.container, leaf.key
    if isinstance(container, list) and isinstance(key, int):
        return container[key]
    if isinstance(container, dict) and isinstance(key, str):
        return container[key]
    return None


def _set(leaf: _Leaf, value: str) -> None:
    container, key = leaf.container, leaf.key
    if isinstance(container, list) and isinstance(key, int):
        container[key] = value
        return
    if isinstance(container, dict) and isinstance(key, str):
        container[key] = value


def _unset(leaf: _Leaf) -> None:
    if isinstance(leaf.container, dict) and isinstance(leaf.key, str):
        del leaf.container[leaf.key]


def _apply(doc: JsonObject, transform: _Transform) -> None:
    """Visit every reference leaf of ``doc`` in place; ``transform`` returns the new value or ``_DELETE``."""
    removals: dict[int, tuple[list[JsonValue], set[int]]] = {}
    for field in REFERENCE_FIELDS:
        entities = doc.get(field.array)
        if not isinstance(entities, list):
            continue
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            context = context_item(field.array, entity)
            for leaf in _walk(entity, field.path, ()):
                if field.when is not None and leaf.holder.get(field.when[0]) != field.when[1]:
                    continue
                value = _get(leaf)
                if not isinstance(value, str):
                    continue
                new = transform(field, value, context)
                if new is _DELETE:
                    target = leaf.ancestors[-1] if leaf.ancestors else None
                    if isinstance(leaf.container, list) and isinstance(leaf.key, int):
                        target = (leaf.container, leaf.key)
                    if target is None:
                        _unset(leaf)
                    else:
                        removals.setdefault(id(target[0]), (target[0], set()))[1].add(target[1])
                elif isinstance(new, str) and new != value:
                    _set(leaf, new)
    for container, indexes in removals.values():
        for index in sorted(indexes, reverse=True):
            del container[index]


def _full_unit(value: str, context: str | None) -> str:
    return value if "/" in value or context is None else f"{context}/{value}"


def _full_check(value: str, context: str | None) -> str:
    return value if ":" in value or context is None else f"{context}:{value}"


def _canonical(field: ReferenceField, value: str, context: str | None) -> str:
    """The comparable form of a reference: local forms are completed by the context item."""
    match field.ref:
        case RefKind.UNIT_REF:
            return _full_unit(value, context)
        case RefKind.CHECK_REF | RefKind.CHECK_LOCAL:
            return _full_check(value, context)
        case RefKind.MATERIAL:
            try:
                return parse_material_ref(value)[0]
            except ValidationFailed:
                return value
        case _:
            return value


# ---------------------------------------------------------------------------------------------- scrub


def scrub_references(doc: JsonObject, removed: frozenset[str]) -> None:
    """Remove from ``doc`` every reference to a key in ``removed`` (cascade remove, planning §5.3 item 4).

    ``removed`` holds display keys (``owner:Vn`` for checks, ``material/<key>`` for materials). A list member
    that holds a reference — a string, a relation, a read, an evidence entry — is dropped; an optional scalar
    is unset.
    """

    def transform(field: ReferenceField, value: str, context: str | None) -> object:
        return _DELETE if _canonical(field, value, context) in removed else value

    _apply(doc, transform)
    phases = doc.get("phases")
    for phase in phases if isinstance(phases, list) else ():
        batches = phase.get("batches") if isinstance(phase, dict) else None
        if isinstance(batches, list) and isinstance(phase, dict):
            phase["batches"] = [b for b in batches if not (isinstance(b, dict) and b.get("items") == [])]


# ---------------------------------------------------------------------------------------------- rekey


@dataclass(frozen=True, slots=True)
class RekeyPlan:
    """Old -> new display keys of everything one rekey renames."""

    kind: EntityKind
    keys: Mapping[str, str]  # phase / item / unit / requirement / criterion / decision
    checks: Mapping[str, str]  # ``owner:Vn`` of checks
    materials: Mapping[str, str]  # ``material/<key>``


def _plan_rekey(doc: Mapping[str, JsonValue], target: EntityLocation, new: str) -> RekeyPlan:
    old = target.key
    keys: dict[str, str] = {}
    checks: dict[str, str] = {}
    materials: dict[str, str] = {}
    match target.kind:
        case EntityKind.PHASE:
            keys[old] = new
            for kind, _, entity in iter_entities(doc):
                key = display_key_of(kind, entity)
                if kind is EntityKind.ITEM and entity.get("phase") == old:
                    keys[key] = f"{new}.{key.split('.', 1)[1]}"
        case EntityKind.ITEM:
            keys[old] = new
        case EntityKind.CHECK:
            checks[old] = new
        case EntityKind.MATERIAL:
            materials[old] = new
        case _:
            keys[old] = new
    if target.kind in (EntityKind.PHASE, EntityKind.ITEM):
        for kind, _, entity in iter_entities(doc):
            key = display_key_of(kind, entity)
            if kind is EntityKind.UNIT and key.split("/", 1)[0] in keys:
                keys[key] = f"{keys[key.split('/', 1)[0]]}/{key.split('/', 1)[1]}"
        for kind, _, entity in iter_entities(doc):
            if kind is EntityKind.CHECK and entity.get("owner") in keys:
                checks[display_key_of(kind, entity)] = f"{keys[str(entity['owner'])]}:{entity['key']}"
    return RekeyPlan(target.kind, keys, checks, materials)


def _check_collisions(doc: Mapping[str, JsonValue], plan: RekeyPlan) -> None:
    moved = {*plan.keys, *plan.checks, *plan.materials}
    destinations = {*plan.keys.values(), *plan.checks.values(), *plan.materials.values()}
    taken = {display_key_of(kind, entity) for kind, _, entity in iter_entities(doc)}
    for destination in sorted(destinations):
        if destination in taken and destination not in moved:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "key already exists", details={"key": destination})


def rekey_document(doc: JsonObject, old: str, new: str) -> tuple[JsonObject, tuple[str, ...]]:
    """Rename ``old`` to ``new`` in a copy of ``doc`` and rewrite every typed reference to it (§5.3 item 6).

    The renamed entity keeps its id. Returns the copy and the notes of references that
    could not be carried over (a unit's local check reference whose check moved to another owner).
    """
    target = resolve_ref(doc, old)
    new = _normalise_new_key(target, new)
    if new == old:
        return copy.deepcopy(doc), ()
    if find_entity(doc, new) is not None:
        raise Conflict(ErrorCode.ALREADY_EXISTS, "key already exists", details={"key": new})
    plan = _plan_rekey(doc, target, new)
    _check_collisions(doc, plan)
    result = copy.deepcopy(doc)
    notes: list[str] = []

    def transform(field: ReferenceField, value: str, context: str | None) -> object:
        return _rewrite(plan, field, value, context, notes)

    _apply(result, transform)
    _rename_entities(result, plan)
    return result, tuple(notes)


def _normalise_new_key(target: EntityLocation, new: str) -> str:
    if target.kind is EntityKind.MATERIAL and "/" not in new:
        new = f"material/{new}"
    if target.kind is EntityKind.CHECK and new.count(":") == 0:
        new = f"{target.key.split(':', 1)[0]}:{new}"
    parsed = parse_key(new)
    if parsed.kind is not key_kind_of(target.kind):
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "new key is of another kind",
            details={"text": new, "reason": "kind_mismatch", "expected": key_kind_of(target.kind).value},
        )
    return new


def _rewrite(
    plan: RekeyPlan, field: ReferenceField, value: str, context: str | None, notes: list[str]
) -> object:
    ref = field.ref
    if ref in (
        RefKind.PHASE,
        RefKind.ITEM,
        RefKind.WORK,
        RefKind.ENTITY,
        RefKind.REQUIREMENT,
        RefKind.DECISION,
    ):
        return plan.keys.get(value, value)
    if ref is RefKind.UNIT_REF:
        full = _full_unit(value, context)
        mapped = plan.keys.get(full, full)
        if "/" not in value and context is not None:
            owner = plan.keys.get(context, context)
            if mapped.startswith(f"{owner}/"):
                return mapped[len(owner) + 1 :]
        return mapped
    if ref in (RefKind.CHECK_REF, RefKind.CHECK_LOCAL):
        return _rewrite_check(plan, field, value, context, notes)
    head, section = parse_material_ref(value)
    mapped = plan.materials.get(head, head)
    return mapped if section is None else f"{mapped}#{section}"


def _rewrite_check(
    plan: RekeyPlan, field: ReferenceField, value: str, context: str | None, notes: list[str]
) -> object:
    full = _full_check(value, context)
    mapped = plan.checks.get(full, full)
    if ":" in value or context is None:
        return mapped
    owner = plan.keys.get(context, context)
    if mapped.startswith(f"{owner}:"):
        return mapped[len(owner) + 1 :]
    if field.ref is RefKind.CHECK_LOCAL:
        moved_to = mapped.split(":")[0]
        notes.append(f"removed check reference {value} of a unit of {context}: the check moved to {moved_to}")
        return _DELETE
    return mapped


def _rename_entities(doc: JsonObject, plan: RekeyPlan) -> None:
    for field, kind in ENTITY_ARRAYS:
        entities = doc.get(field)
        if not isinstance(entities, list):
            continue
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            old_key = display_key_of(kind, entity)
            if kind is EntityKind.CHECK:
                old_owner = str(entity.get("owner", ""))
                if old_key in plan.checks:
                    owner, _, local = plan.checks[old_key].partition(":")
                    entity["owner"], entity["key"] = owner, local
                elif old_owner in plan.keys:
                    entity["owner"] = plan.keys[old_owner]
            elif kind is EntityKind.MATERIAL:
                if old_key in plan.materials:
                    entity["key"] = plan.materials[old_key].removeprefix("material/")
            elif old_key in plan.keys:
                entity["key"] = plan.keys[old_key]
                if kind is EntityKind.ITEM:
                    entity["phase"] = plan.keys[old_key].split(".", 1)[0]


type RefConverter = Callable[[ReferenceField, JsonValue, str | None], JsonValue]
"""``convert(field, value, context)``: the new value of one reference leaf."""


def _ref_leaves(
    node: JsonValue, path: tuple[str, ...]
) -> Iterator[tuple[dict[str, JsonValue] | list[JsonValue], str | int, dict[str, JsonValue]]]:
    """``(container, member, holder)`` of every value at ``path`` (``name[]`` iterates an array)."""
    if not isinstance(node, dict):
        return
    segment, rest = path[0], path[1:]
    name = segment.removesuffix("[]")
    child = node.get(name)
    if child is None:
        return
    if segment.endswith("[]"):
        if not isinstance(child, list):
            return
        for index, element in enumerate(child):
            if rest:
                yield from _ref_leaves(element, rest)
            else:
                yield child, index, node
    elif rest:
        yield from _ref_leaves(child, rest)
    else:
        yield node, name, node


def rewrite_refs(array: str, record: JsonObject, context: str | None, convert: RefConverter) -> None:
    """Replace every typed reference of an ``array`` entry by ``convert(field, value, context)``."""
    for ref_field in REFERENCE_FIELDS:
        if ref_field.array != array:
            continue
        for container, member, holder in list(_ref_leaves(record, ref_field.path)):
            if ref_field.when is not None and holder.get(ref_field.when[0]) != ref_field.when[1]:
                continue
            if isinstance(container, list):
                index = cast("int", member)
                container[index] = convert(ref_field, container[index], context)
            else:
                name = cast("str", member)
                container[name] = convert(ref_field, container[name], context)
