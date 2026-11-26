"""Atomic batch authoring of a draft document (planning §5.3).

Every operation works on one copy of the document; the first failing operation discards the copy, so a saved
document never contains a successful prefix of a failed batch. The schema is checked once, on the final
document.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, SkmError, ValidationFailed
from skm.modules.planning.domain.identity import ENTITY_ARRAYS, display_key_of
from skm.modules.planning.domain.item import Effort, ModelClass
from skm.modules.planning.domain.references import (
    EntityLocation,
    find_entity,
    rekey_document,
    resolve_ref,
    scrub_references,
)
from skm.modules.planning.domain.review_requirement import ReviewMode
from skm.modules.planning.domain.specification import EntityKind
from skm.modules.planning.domain.text_edits import apply_replace_text

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from skm.kernel.json_types import JsonObject, JsonValue


class ChangeOp(StrEnum):
    PATCH = "patch"
    ADD = "add"
    REMOVE = "remove"
    MOVE = "move"
    REKEY = "rekey"
    REPLACE_TEXT = "replace_text"


@dataclass(frozen=True, slots=True)
class PatchChange:
    target: str
    merge_patch: JsonObject


@dataclass(frozen=True, slots=True)
class AddChange:
    kind: EntityKind | Literal["plan_relation"]
    entity: JsonObject
    after: str | None


@dataclass(frozen=True, slots=True)
class RemoveChange:
    target: str
    cascade: bool


@dataclass(frozen=True, slots=True)
class MoveChange:
    target: str
    after: str | None
    before: str | None


@dataclass(frozen=True, slots=True)
class RekeyChange:
    target: str
    new_key: str


@dataclass(frozen=True, slots=True)
class ReplaceTextChange:
    target: str
    pointer: str
    expected_text_digest: str
    old_text: str
    new_text: str


@dataclass(frozen=True, slots=True)
class ItemDefaults:
    route_class: ModelClass
    route_effort: Effort
    review_mode: ReviewMode


@dataclass(frozen=True, slots=True)
class ChangeOutcome:
    document: JsonObject
    notes: tuple[str, ...]


type DraftChange = PatchChange | AddChange | RemoveChange | MoveChange | RekeyChange | ReplaceTextChange


_PLAN_OWNED: Final = frozenset({"schema", *(field for field, _ in ENTITY_ARRAYS)})
_ENTITY_OWNED: Final = {
    EntityKind.ITEM: frozenset({"id", "key", "phase"}),
    EntityKind.CHECK: frozenset({"id", "key", "owner"}),
}
_SECTIONS: Final = ("plan", "brief", "execution_constraints")


def merge_patch(target: JsonValue, patch: JsonValue) -> JsonValue:
    """RFC 7396: objects merge member by member, ``null`` deletes a member, anything else replaces."""
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    merged: JsonObject = copy.deepcopy(target) if isinstance(target, dict) else {}
    for name, value in patch.items():
        if value is None:
            merged.pop(name, None)
        else:
            merged[name] = merge_patch(merged.get(name), value)
    return merged


def _owned_guard(
    label: str, current: Mapping[str, JsonValue], patch: JsonObject, owned: frozenset[str]
) -> JsonObject:
    """``patch`` minus the owned members it leaves as they are; a changed owned member is ``FIELD_OWNED``."""
    allowed: JsonObject = {}
    for name, value in patch.items():
        if name not in owned:
            allowed[name] = value
        elif current.get(name) != value:
            raise ValidationFailed(
                ErrorCode.FIELD_OWNED, "field is owned", details={"target": label, "field": name}
            )
    return allowed


def _array_of(kind: EntityKind) -> str:
    return next(field for field, array_kind in ENTITY_ARRAYS if array_kind is kind)


def _list(doc: JsonObject, array: str) -> list[JsonValue]:
    value = doc.get(array)
    if not isinstance(value, list):
        value = []
        doc[array] = value
    return value


def _patch(doc: JsonObject, change: PatchChange, index: int) -> None:
    if change.target == "plan":
        merged = merge_patch(doc, _owned_guard("plan", doc, change.merge_patch, _PLAN_OWNED))
        if isinstance(merged, dict):
            doc.clear()
            doc.update(merged)
    elif change.target in _SECTIONS:
        merged = merge_patch(doc.get(change.target, {}), change.merge_patch)
        doc[change.target] = merged
    else:
        location = resolve_ref(doc, change.target, change_index=index)
        entity = _list(doc, location.array)[location.index]
        owned = _ENTITY_OWNED.get(location.kind, frozenset({"id", "key"}))
        allowed = _owned_guard(
            change.target, entity if isinstance(entity, dict) else {}, change.merge_patch, owned
        )
        _list(doc, location.array)[location.index] = merge_patch(entity, allowed)


def _default_route_and_review(entity: JsonObject, defaults: ItemDefaults) -> None:
    if "route" not in entity:
        entity["route"] = {"class": defaults.route_class.value, "effort": defaults.route_effort.value}
    if "review" not in entity:
        review: JsonObject = {"mode": defaults.review_mode.value}
        if defaults.review_mode is ReviewMode.SELF:
            review["reason"] = "planning.defaults.review_mode"
        elif defaults.review_mode is ReviewMode.WAIVED:
            review["reason"] = "planning.defaults.review_mode"
            review["waived_by"] = "planning.defaults"
        entity["review"] = review


def _kind_error(ref: str, expected: str, reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.INVALID_REFERENCE,
        "neighbour is not an entity of the same kind",
        details={"text": ref, "reason": reason, "expected": expected},
    )


def _neighbour(doc: JsonObject, kind: EntityKind, ref: str, group: str | None, index: int) -> EntityLocation:
    found = resolve_ref(doc, ref, change_index=index)
    if found.kind is not kind:
        raise _kind_error(ref, kind.value, "kind_mismatch")
    if group is not None and _group(kind, _list(doc, found.array)[found.index]) != group:
        raise _kind_error(ref, kind.value, "other_group")
    return found


def _group(kind: EntityKind, entity: JsonValue) -> str | None:
    """The sibling group an entity is ordered in: the phase of an item, the item of a unit."""
    if not isinstance(entity, dict):
        return None
    if kind is EntityKind.ITEM:
        return str(entity.get("phase", ""))
    if kind is EntityKind.UNIT:
        return str(entity.get("key", "")).split("/", 1)[0]
    return None


def _add(doc: JsonObject, change: AddChange, defaults: ItemDefaults, index: int) -> None:
    entity = copy.deepcopy(change.entity)
    if change.kind == "plan_relation":
        if change.after is not None:
            raise _kind_error(change.after, "plan_relation", "no_anchor")
        _list(doc, "plan_relations").append(entity)
        return
    kind = EntityKind(change.kind)
    key = display_key_of(kind, entity)
    if "key" in entity and find_entity(doc, key) is not None:
        raise Conflict(ErrorCode.ALREADY_EXISTS, "key already exists", details={"key": key})
    if kind is EntityKind.ITEM:
        _default_route_and_review(entity, defaults)
    array = _list(doc, _array_of(kind))
    group = _group(kind, entity)
    if change.after is not None:
        anchor = _neighbour(doc, kind, change.after, group, index)
        array.insert(anchor.index + 1, entity)
        return
    positions = [i for i, other in enumerate(array) if group is not None and _group(kind, other) == group]
    array.insert(positions[-1] + 1 if positions else len(array), entity)


def _descendants(doc: JsonObject, root: EntityLocation) -> frozenset[str]:
    """Display keys of ``root`` and of what it owns (items of a phase; units, checks, criteria)."""
    removed = {root.key}
    changed = True
    while changed:
        changed = False
        for field, kind in ENTITY_ARRAYS:
            for entity in _list(doc, field):
                if not isinstance(entity, dict):
                    continue
                key = display_key_of(kind, entity)
                parent = _parent(kind, entity)
                if key not in removed and parent in removed:
                    removed.add(key)
                    changed = True
    return frozenset(removed)


def _parent(kind: EntityKind, entity: Mapping[str, JsonValue]) -> str | None:
    if kind is EntityKind.ITEM:
        return str(entity.get("phase"))
    if kind is EntityKind.UNIT:
        return str(entity.get("key", "")).split("/", 1)[0]
    if kind in (EntityKind.CHECK, EntityKind.CRITERION):
        return str(entity.get("owner"))
    return None


def _remove(doc: JsonObject, change: RemoveChange, index: int) -> None:
    target = resolve_ref(doc, change.target, change_index=index)
    removed = _descendants(doc, target) if change.cascade else frozenset({target.key})
    for field, kind in ENTITY_ARRAYS:
        array = _list(doc, field)
        array[:] = [e for e in array if not (isinstance(e, dict) and display_key_of(kind, e) in removed)]
    if change.cascade:
        scrub_references(doc, removed)


def _move(doc: JsonObject, change: MoveChange, index: int) -> None:
    if change.after is not None and change.before is not None:
        raise _kind_error(change.before, "after or before", "move_anchor")
    target = resolve_ref(doc, change.target, change_index=index)
    array = _list(doc, target.array)
    entity = array[target.index]
    group = _group(target.kind, entity)
    anchor_ref = change.after if change.after is not None else change.before
    anchor = None if anchor_ref is None else _neighbour(doc, target.kind, anchor_ref, group, index)
    if anchor is not None and anchor.index == target.index:
        raise _kind_error(anchor_ref or "", target.kind.value, "move_anchor")
    del array[target.index]
    if anchor is None:
        siblings = [
            i for i, other in enumerate(array) if group is not None and _group(target.kind, other) == group
        ]
        array.insert(siblings[0] if siblings else min(target.index, len(array)), entity)
        return
    position = anchor.index - 1 if anchor.index > target.index else anchor.index
    array.insert(position + 1 if change.after is not None else position, entity)


def _annotate(error: SkmError, index: int) -> SkmError:
    """``error`` of the same class with the batch position and ``applied=false``."""
    details: dict[str, JsonValue] = {"change_index": index, **error.details, "applied": False}
    return type(error)(error.code, error.message, details=details, retryable=error.retryable)


def apply_changes(
    doc: JsonObject,
    changes: Sequence[DraftChange],
    *,
    defaults: ItemDefaults,
    validate: Callable[[JsonObject], None] | None = None,
) -> ChangeOutcome:
    """Apply ``changes`` in order to a copy of ``doc``; ``doc`` is never mutated.

    ``validate`` checks the *final* document once (the caller passes the schema check); its error is
    reported as
    it is plus ``applied=false`` and is not attributed to any operation. Any other failure carries
    ``change_index`` and ``applied=false`` and discards the whole batch.
    """
    work = copy.deepcopy(doc)
    notes: list[str] = []
    for index, change in enumerate(changes):
        try:
            match change:
                case PatchChange():
                    _patch(work, change, index)
                case AddChange():
                    _add(work, change, defaults, index)
                case RemoveChange():
                    _remove(work, change, index)
                case MoveChange():
                    _move(work, change, index)
                case RekeyChange():
                    work, produced = rekey_document(
                        work, _resolve_key(work, change.target, index), change.new_key
                    )
                    notes.extend(produced)
                case ReplaceTextChange():
                    apply_replace_text(work, change, index)
        except SkmError as error:
            raise _annotate(error, index) from error
    if validate is not None:
        try:
            validate(work)
        except SkmError as error:
            raise type(error)(
                error.code, error.message, details={**error.details, "applied": False}
            ) from error
    return ChangeOutcome(work, tuple(notes))


def _resolve_key(doc: JsonObject, ref: str, index: int) -> str:
    """Display key of the entity ``ref`` addresses (a display key or ``entity:<uuid>``)."""
    return resolve_ref(doc, ref, change_index=index).key


def rekey(doc: JsonObject, old: str, new: str) -> ChangeOutcome:
    """Rename ``old`` to ``new`` and rewrite every reference to it (planning §5.3 item 6)."""
    renamed, notes = rekey_document(doc, _resolve_key(doc, old, 0), new)
    return ChangeOutcome(renamed, notes)
