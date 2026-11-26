"""Pure three-way rebase of a draft onto the current revision (planning §5.10, G1).

The three documents are normalized and compared in *id space*: an entity is a record addressed by its stable
``id``, every typed reference (``REFERENCE_FIELDS``) holds the id of its target, and the keys of items, units
and checks are split into their container and their local part, so a rekey of a target is not an edit of the
entities that refer to it. Plan fields and entity properties merge with ``merge3``; reference sets merge as
sets without conflicts; presence, containers, order and display keys follow the numbered steps of §5.10.

Nothing here mutates its inputs. A conflict that ``resolutions`` do not settle leaves ``document = None``.
The id space itself (values, references, the compared documents) is ``rebase_helpers``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal, Protocol, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import EntityId
from skm.modules.planning.domain.canonical import normalize_document
from skm.modules.planning.domain.display_keys import key_kind
from skm.modules.planning.domain.identity import ENTITY_ARRAYS, display_key_of
from skm.modules.planning.domain.rebase_helpers import (
    ABSENT,
    ARRAY_OF,
    SEPARATOR,
    Absent,
    Side,
    SideDoc,
    Value,
    as_list,
    canon,
    container_of,
    display_key,
    elements,
    positions,
    real_id,
    ref_text,
    refuse_repeated_revisions,
    same,
    set_merge,
    side_doc,
    to_key,
)
from skm.modules.planning.domain.references import key_kind_of, rewrite_refs
from skm.modules.planning.domain.specification import SPECIFICATION_URN, EntityKind

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from skm.kernel.json_types import JsonObject, JsonValue


class ConflictKind(StrEnum):
    FIELD = "field"
    MODIFY_DELETE = "modify_delete"
    DELETE_MODIFY = "delete_modify"
    KEY_COLLISION = "key_collision"
    SCHEMA = "schema"


@dataclass(frozen=True, slots=True)
class RebaseConflict:
    conflict_id: str
    kind: ConflictKind
    entity_id: EntityId | None
    entity_kind: EntityKind | None
    key: str | None
    field: str | None
    pointer: str | None
    base: Value
    yours: Value
    theirs: Value
    resolutions: tuple[Literal["yours", "theirs", "rekey"], ...]
    colliding_entity_id: EntityId | None
    children_kept: tuple[EntityId, ...]
    issues: tuple[JsonObject, ...]


@dataclass(frozen=True, slots=True)
class RebaseResolution:
    conflict_id: str
    keep: Literal["yours", "theirs"] | None
    new_key: str | None


@dataclass(frozen=True, slots=True)
class RebaseOutcome:
    document: JsonObject | None
    conflicts: tuple[RebaseConflict, ...]
    taken_from_current: int
    kept_from_draft: int
    resolved: int


class SchemaIssueLike(Protocol):
    @property
    def pointer(self) -> str: ...
    @property
    def schema_pointer(self) -> str: ...
    @property
    def message(self) -> str: ...


class SchemaValidator(Protocol):
    """The ``SPECIFICATION_URN`` validator (``SchemaRegistry.validator``); domain code may not import it."""

    def issues(self, instance: object) -> Sequence[SchemaIssueLike]: ...


PLAN_FIELDS: Final = (
    "title", "goal", "context_md", "non_goals", "rules", "brief", "execution_constraints", "sections",
    "extensions", "plan_relations",
)  # fmt: skip

# Members merged as one unit; a conflict names the first member.
_GROUPS: Final[Mapping[EntityKind, tuple[tuple[str, ...], ...]]] = {
    EntityKind.CHECK: (("kind", "definition"),),
    EntityKind.UNIT: (("unit_kind", "command"),),
    EntityKind.MATERIAL: (
        ("kind", "file_version_id", "mount", "path", "url", "retrieved_at", "content_digest", "freshness"),
    ),
}
# Members merged as sets; ``phase.depends_on`` only when all three documents hold it.
_SETS: Final[Mapping[EntityKind, frozenset[str]]] = {
    EntityKind.PHASE: frozenset({"depends_on"}),
    EntityKind.ITEM: frozenset({"depends_on", "implements", "decisions"}),
    EntityKind.UNIT: frozenset({"depends_on", "checks", "implements"}),
    EntityKind.CRITERION: frozenset({"checks", "requirements"}),
    EntityKind.REQUIREMENT: frozenset({"owners"}),
    EntityKind.DECISION: frozenset({"applies_to", "supersedes"}),
    EntityKind.MATERIAL: frozenset({"applies_to", "required_for"}),
}
# Containers, innermost first: a container is checked after the containers of its children (§5.10 step 7).
_CONTAINERS: Final = (EntityKind.UNIT, EntityKind.ITEM, EntityKind.PHASE)
# The kinds a key of an item / unit / check may name as its container.
_CONTAINER_KINDS: Final[Mapping[EntityKind, tuple[EntityKind, ...]]] = {
    EntityKind.ITEM: (EntityKind.PHASE,),
    EntityKind.UNIT: (EntityKind.ITEM,),
    EntityKind.CHECK: (EntityKind.PHASE, EntityKind.ITEM),
}
_BOTH: Final[tuple[Literal["yours", "theirs", "rekey"], ...]] = ("yours", "theirs")


def _entity_id(entity_id: str) -> EntityId:
    return EntityId(UUID(real_id(entity_id)))


def _conflict_id(kind: ConflictKind, subject: str, member: str | None) -> str:
    text = json.dumps([kind.value, subject, member or ""], ensure_ascii=False, separators=(",", ":"))
    return "rc-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _merge3(base: Value, yours: Value, theirs: Value) -> tuple[Value, Side | None] | None:
    """``(value, side it came from)``; the side is ``None`` when both agree; ``None`` on conflict."""
    if same(yours, theirs):
        return yours, None
    if same(yours, base):
        return theirs, "theirs"
    if same(theirs, base):
        return yours, "yours"
    return None


def _form_error(index: int, message: str) -> ValidationFailed:
    issue: JsonObject = {"pointer": f"/resolutions/{index}", "schema_pointer": "", "message": message}
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, message, details={"issues": [issue]})


# ---------------------------------------------------------------------------------------------- merge


class _Merged:
    """Working state of one entity: its merged record (``None`` while it is not in the result)."""

    __slots__ = ("deleted_by", "kept", "open_fields", "record", "taken")

    def __init__(self, record: JsonObject | None) -> None:
        self.record = record
        self.deleted_by: Side | Literal["both"] | None = None
        self.kept = 0
        self.taken = 0
        self.open_fields: set[str] = set()

    def count(self, side: Side | None) -> None:
        if side == "yours":
            self.kept += 1
        elif side == "theirs":
            self.taken += 1


class _Rebase:
    def __init__(
        self, base: SideDoc, yours: SideDoc, theirs: SideDoc, resolutions: Sequence[RebaseResolution]
    ) -> None:
        self.b, self.y, self.t = base, yours, theirs
        self.wanted: dict[str, tuple[int, RebaseResolution]] = {}
        for index, resolution in enumerate(resolutions):
            if resolution.conflict_id in self.wanted:
                raise _form_error(index, "a conflict is resolved once")
            self.wanted[resolution.conflict_id] = (index, resolution)
        self.arisen: dict[str, str] = {}  # conflict_id -> the id-space subject it first arose for
        # (conflict_id, subject) of an open conflict -> its place in its bucket
        self.recorded: dict[tuple[str, str], tuple[list[RebaseConflict], int]] = {}
        self.applied: set[str] = set()
        self.plan: JsonObject = {}
        self.plan_kept = self.plan_taken = 0
        self.entities: dict[EntityKind, dict[str, _Merged]] = {kind: {} for _, kind in ENTITY_ARRAYS}
        self.plan_conflicts: list[RebaseConflict] = []
        self.entity_conflicts: list[RebaseConflict] = []
        self.container_conflicts: list[RebaseConflict] = []
        self.key_conflicts: list[RebaseConflict] = []

    # ------------------------------------------------------------------ resolutions

    def settle(
        self, conflict: RebaseConflict, bucket: list[RebaseConflict], subject: str
    ) -> tuple[int, RebaseResolution] | None:
        """The resolution of ``conflict`` (its shape checked), or ``None`` after recording it as open.

        ``subject`` is what the conflict is about: ``"plan"``, ``"document"`` or the id-space id of an entity.
        Met again for the same subject, it is the same conflict — the presence of a container (§5.10 step 5)
        is checked again for its children (step 7): its resolution applies again, and while open it is
        reported once, in its first place, with what the later visit knows (``children_kept``). A
        ``conflict_id`` that names a conflict of another subject (occurrences of a repeated ``id``) cannot be
        resolved: a resolution would have to guess which entity it means, so it is refused; the draft must be
        fixed.
        """
        ambiguous = self.arisen.setdefault(conflict.conflict_id, subject) != subject
        found = self.wanted.get(conflict.conflict_id)
        if found is None:
            recorded = self.recorded.get((conflict.conflict_id, subject))
            if recorded is not None:
                place, position = recorded
                place[position] = conflict
            else:
                self.recorded[conflict.conflict_id, subject] = (bucket, len(bucket))
                bucket.append(conflict)
            return None
        index, resolution = found
        if ambiguous:
            raise _form_error(
                index, "conflict_id names more than one conflict (a repeated entity id, duplicate_id)"
            )
        if conflict.kind is ConflictKind.KEY_COLLISION:
            fits = resolution.keep is None and isinstance(resolution.new_key, str)
        else:
            fits = resolution.new_key is None and resolution.keep in conflict.resolutions
        if not fits:
            expected = ", ".join(conflict.resolutions) or "none"
            raise _form_error(
                index, f"resolution does not fit a {conflict.kind} conflict (allowed: {expected})"
            )
        self.applied.add(conflict.conflict_id)
        return found

    def check_unknown(self) -> None:
        unknown = sorted(index for cid, (index, _) in self.wanted.items() if cid not in self.arisen)
        if unknown:
            conflict_id = next(c for c, (i, _) in self.wanted.items() if i == unknown[0])
            raise ValidationFailed(
                ErrorCode.INVALID_REFERENCE, "no such rebase conflict", details={"conflict_id": conflict_id}
            )

    # ------------------------------------------------------------------ conflicts

    def _locate(self, kind: EntityKind, entity_id: str) -> tuple[int, JsonObject]:
        for side in (self.y, self.t, self.b):
            found = side.entities[kind].get(entity_id)
            if found is not None:
                return found
        raise AssertionError(entity_id)  # every merged id comes from one of the documents

    def _original(
        self,
        side: SideDoc,
        kind: EntityKind,
        entity_id: str,
        member: str | None,
        group: tuple[str, ...] | None,
    ) -> Value:
        found = side.entities[kind].get(entity_id)
        if group is not None:  # the object of the group members, as merged ({} for an empty base)
            entity = found[1] if found is not None else {}
            return {name: copy.deepcopy(entity[name]) for name in group if name in entity}
        if found is None:
            return ABSENT
        entity = found[1]
        if member is None:
            return copy.deepcopy(entity)
        if member == "key" and kind is EntityKind.CHECK:
            return display_key_of(kind, entity)
        return copy.deepcopy(entity.get(member, ABSENT))

    def entity_conflict(
        self,
        conflict_kind: ConflictKind,
        kind: EntityKind,
        entity_id: str,
        member: str | None = None,
        group: tuple[str, ...] | None = None,
        *,
        colliding: str | None = None,
        children: tuple[EntityId, ...] = (),
    ) -> RebaseConflict:
        index, entity = self._locate(kind, entity_id)
        pointer = f"/{ARRAY_OF[kind]}/{index}" + (f"/{member}" if member else "")
        if conflict_kind is ConflictKind.KEY_COLLISION:
            values: tuple[Value, Value, Value] = (ABSENT, ABSENT, ABSENT)
            resolutions: tuple[Literal["yours", "theirs", "rekey"], ...] = ("rekey",)
        else:
            values = cast(
                "tuple[Value, Value, Value]",
                tuple(
                    self._original(side, kind, entity_id, member, group) for side in (self.b, self.y, self.t)
                ),
            )
            resolutions = _BOTH
        return RebaseConflict(
            conflict_id=_conflict_id(conflict_kind, real_id(entity_id), member),
            kind=conflict_kind,
            entity_id=_entity_id(entity_id),
            entity_kind=kind,
            key=display_key_of(kind, entity),
            field=member,
            pointer=pointer,
            base=values[0],
            yours=values[1],
            theirs=values[2],
            resolutions=resolutions,
            colliding_entity_id=_entity_id(colliding) if colliding is not None else None,
            children_kept=children,
            issues=(),
        )

    # ------------------------------------------------------------------ step 4: plan fields

    def merge_plan(self) -> None:
        for name in PLAN_FIELDS:
            base, yours, theirs = (side.doc.get(name, ABSENT) for side in (self.b, self.y, self.t))
            merged = _merge3(base, yours, theirs)
            if merged is not None:
                value, side = merged
                self.plan_kept += side == "yours"
                self.plan_taken += side == "theirs"
            else:
                conflict = RebaseConflict(
                    conflict_id=_conflict_id(ConflictKind.FIELD, "plan", name),
                    kind=ConflictKind.FIELD,
                    entity_id=None,
                    entity_kind=None,
                    key=None,
                    field=name,
                    pointer=f"/{name}",
                    base=copy.deepcopy(base),
                    yours=copy.deepcopy(yours),
                    theirs=copy.deepcopy(theirs),
                    resolutions=_BOTH,
                    colliding_entity_id=None,
                    children_kept=(),
                    issues=(),
                )
                found = self.settle(conflict, self.plan_conflicts, "plan")
                value = theirs if found is not None and found[1].keep == "theirs" else yours
            if not isinstance(value, Absent):
                self.plan[name] = copy.deepcopy(value)

    # ------------------------------------------------------------------ steps 5-6: presence and fields

    def merge_entities(self) -> None:
        for _, kind in ENTITY_ARRAYS:
            theirs = self.t.records[kind]
            for entity_id in [*theirs, *(i for i in self.y.records[kind] if i not in theirs)]:
                self.entities[kind][entity_id] = self._presence(kind, entity_id)
            for entity_id in self.b.records[kind]:
                if entity_id not in self.entities[kind]:
                    merged = _Merged(None)
                    merged.deleted_by = "both"
                    self.entities[kind][entity_id] = merged

    def _presence(self, kind: EntityKind, entity_id: str) -> _Merged:
        base = self.b.records[kind].get(entity_id)
        yours = self.y.records[kind].get(entity_id)
        theirs = self.t.records[kind].get(entity_id)
        merged = _Merged(None)
        if base is None:
            if yours is not None and theirs is not None:
                merged.record = self._fields(merged, kind, entity_id, {}, yours, theirs)
            else:
                merged.record = copy.deepcopy(yours if yours is not None else theirs)
                merged.count("yours" if yours is not None else "theirs")
        elif yours is not None and theirs is not None:
            merged.record = self._fields(merged, kind, entity_id, base, yours, theirs)
        elif yours is not None:  # current deleted it
            self._one_sided(merged, kind, entity_id, ConflictKind.MODIFY_DELETE, base, yours, "theirs")
        elif theirs is not None:  # the draft deleted it
            self._one_sided(merged, kind, entity_id, ConflictKind.DELETE_MODIFY, base, theirs, "yours")
        return merged

    def _one_sided(
        self,
        merged: _Merged,
        kind: EntityKind,
        entity_id: str,
        conflict_kind: ConflictKind,
        base: JsonObject,
        survivor: JsonObject,
        deleter: Side,
    ) -> None:
        if same(survivor, base):
            merged.deleted_by = deleter
            merged.count(deleter)
            return
        conflict = self.entity_conflict(conflict_kind, kind, entity_id)
        found = self.settle(conflict, self.entity_conflicts, entity_id)
        if found is None:  # open: step 7 meets it again and adds the children it would keep
            merged.deleted_by = deleter
            return
        if found[1].keep == deleter:
            merged.deleted_by = deleter
        else:
            merged.record = copy.deepcopy(survivor)

    def _fields(
        self, merged: _Merged, kind: EntityKind, entity_id: str, base: JsonObject, yours: JsonObject,
        theirs: JsonObject,
    ) -> JsonObject:  # fmt: skip
        record: JsonObject = {}
        groups = _GROUPS.get(kind, ())
        sets = _SETS.get(kind, frozenset())
        done: set[str] = set()
        for name in dict.fromkeys([*theirs, *yours, *base]):
            if name in done:
                continue
            group = next((g for g in groups if name in g), None)
            if group is not None:
                done.update(group)
                values = [{f: r[f] for f in group if f in r} for r in (base, yours, theirs)]
                value = self._unit(merged, kind, entity_id, group[0], group, *values)
                if isinstance(value, dict):
                    record.update(copy.deepcopy(value))
                continue
            done.add(name)
            b, y, t = (r.get(name, ABSENT) for r in (base, yours, theirs))
            if name in sets and not (kind is EntityKind.PHASE and ABSENT in (b, y, t)):
                value = self._set_unit(merged, b, y, t, keep_empty=kind is EntityKind.PHASE)
            else:
                value = self._unit(merged, kind, entity_id, name, None, b, y, t)
            if not isinstance(value, Absent):
                record[name] = copy.deepcopy(value)
        return record

    def _unit(
        self, merged: _Merged, kind: EntityKind, entity_id: str, member: str, group: tuple[str, ...] | None,
        base: Value, yours: Value, theirs: Value,
    ) -> Value:  # fmt: skip
        result = _merge3(base, yours, theirs)
        if result is not None:
            merged.count(result[1])
            return result[0]
        conflict = self.entity_conflict(ConflictKind.FIELD, kind, entity_id, member, group)
        found = self.settle(conflict, self.entity_conflicts, entity_id)
        if found is None:
            merged.open_fields.add(member)
            return yours  # provisional: the document is not produced while the conflict is open
        return theirs if found[1].keep == "theirs" else yours

    @staticmethod
    def _set_unit(merged: _Merged, base: Value, yours: Value, theirs: Value, *, keep_empty: bool) -> Value:
        b, y, t = as_list(base), as_list(yours), as_list(theirs)
        result = set_merge(b, y, t)
        in_base, in_yours, in_theirs = elements(b), elements(y), elements(t)
        if in_yours != in_theirs:  # a side counts when it changed the set, not only its order
            merged.count("yours" if in_yours != in_base else None)
            merged.count("theirs" if in_theirs != in_base else None)
        return result if result or keep_empty else ABSENT

    # ------------------------------------------------------------------ step 7: containers

    def _children(self, container_id: str) -> list[tuple[EntityKind, str]]:
        return [
            (kind, entity_id)
            for _, kind in ENTITY_ARRAYS
            for entity_id, merged in self.entities[kind].items()
            if merged.record is not None and container_of(kind, merged.record) == container_id
        ]

    def _cascade(self, container_id: str) -> None:
        for kind, entity_id in self._children(container_id):
            merged = self.entities[kind][entity_id]
            merged.record, merged.kept, merged.taken = None, 0, 0
            self._cascade(entity_id)

    def guard_containers(self) -> None:
        for kind in _CONTAINERS:
            for entity_id, merged in self.entities[kind].items():
                if merged.record is not None or merged.deleted_by not in ("yours", "theirs"):
                    continue
                children = tuple(_entity_id(i) for _, i in self._children(entity_id))
                if not children:
                    continue
                by_current = merged.deleted_by == "theirs"
                conflict_kind = ConflictKind.MODIFY_DELETE if by_current else ConflictKind.DELETE_MODIFY
                conflict = self.entity_conflict(conflict_kind, kind, entity_id, children=children)
                found = self.settle(conflict, self.container_conflicts, entity_id)
                if found is None:
                    continue
                merged.kept = merged.taken = 0
                survivor: Side = "yours" if by_current else "theirs"
                if found[1].keep == survivor:
                    side = self.y if by_current else self.t
                    merged.record = copy.deepcopy(dict(side.records[kind][entity_id]))
                    merged.deleted_by = None
                else:
                    self._cascade(entity_id)

    # ------------------------------------------------------------------ step 9: keys

    def final_keys(self) -> dict[str, str]:
        """Display keys of the result; an id outside it keeps its key from yours, then theirs, then base."""
        keys = {**self.b.keys, **self.t.keys, **self.y.keys}
        for _, kind in ENTITY_ARRAYS:
            for entity_id, merged in self.entities[kind].items():
                if merged.record is not None:
                    keys[entity_id] = display_key(kind, merged.record, keys)
        return keys

    def guard_keys(self) -> None:
        """Key collisions kind by kind, containers first, so a rekeyed container settles its children's keys.

        An entity whose key is still open (a ``key``/``phase`` field conflict, an unresolved collision of its
        own or of a container its key is built from) takes no part: its final key is not known yet. The
        resolutions of a group are applied before the rest of it is reported, so an entity is reported only
        while another one still holds its key.
        """
        unsettled: set[str] = set()
        for _, kind in ENTITY_ARRAYS:
            keys = self.final_keys()
            holders: dict[str, list[str]] = {}
            taken: set[str] = set()
            for entity_id, merged in self.entities[kind].items():
                if merged.record is None:
                    continue
                taken.add(keys[entity_id])
                container = container_of(kind, merged.record) if kind in SEPARATOR else None
                open_container = isinstance(container, str) and container in unsettled
                if merged.open_fields & {"key", "phase"} or open_container:
                    unsettled.add(entity_id)
                else:
                    holders.setdefault(keys[entity_id], []).append(entity_id)
            for key, group in holders.items():
                if len(group) < 2:
                    continue
                from_theirs = [entity_id for entity_id in group if self.t.keys.get(entity_id) == key]
                drafted = [entity_id for entity_id in group if entity_id not in from_theirs]
                moved: set[str] = set()
                for entity_id in drafted:  # resolutions first: a rekeyed entity leaves the group
                    wanted = _conflict_id(ConflictKind.KEY_COLLISION, real_id(entity_id), "key")
                    if wanted not in self.wanted:
                        continue
                    conflict = self._collision(kind, entity_id, group, from_theirs, moved)
                    index, resolution = cast(
                        "tuple[int, RebaseResolution]", self.settle(conflict, [], entity_id)
                    )
                    new_key, destination = self._checked_key(
                        index, kind, entity_id, key, cast("str", resolution.new_key), taken
                    )
                    taken.add(new_key)
                    moved.add(entity_id)
                    self._rekey(kind, entity_id, new_key, destination)
                for entity_id in drafted:
                    if entity_id in moved or not [g for g in group if g != entity_id and g not in moved]:
                        continue
                    conflict = self._collision(kind, entity_id, group, from_theirs, moved)
                    self.settle(conflict, self.key_conflicts, entity_id)  # no resolution: recorded as open
                    unsettled.add(entity_id)

    def _collision(
        self, kind: EntityKind, entity_id: str, group: list[str], from_theirs: list[str], moved: set[str]
    ) -> RebaseConflict:
        """The ``key_collision`` of ``entity_id``: with current's holder, else another one still there."""
        left = [g for g in group if g != entity_id and g not in moved]
        other = (from_theirs or left or [g for g in group if g != entity_id])[0]
        return self.entity_conflict(ConflictKind.KEY_COLLISION, kind, entity_id, "key", colliding=other)

    def _checked_key(
        self, index: int, kind: EntityKind, entity_id: str, current: str, new_key: str, taken: set[str]
    ) -> tuple[str, str | None]:
        """``new_key`` of the colliding entity (the same key kind, not taken) and its new container id.

        A local ``U<k>`` / ``V<n>`` / material key is completed with the container of the current key, which
        then stays (``None``). A key in another container moves the entity there: that container must be in
        the result under exactly that key. The container is the one the record names, not the prefix of a key
        kept as written (``key_prefix_mismatch``).
        """
        separator = SEPARATOR.get(kind)
        if kind is EntityKind.MATERIAL and not new_key.startswith("material/"):
            new_key = f"material/{new_key}"
        if kind in (EntityKind.UNIT, EntityKind.CHECK) and separator is not None and separator not in new_key:
            new_key = f"{current.rpartition(separator)[0]}{separator}{new_key}"
        if key_kind(new_key) is not key_kind_of(kind):
            raise _form_error(index, f"new_key {new_key!r} is not a {kind} key")
        if new_key in taken:
            raise _form_error(index, f"new_key {new_key!r} is taken")
        if separator is None:
            return new_key, None
        keys = self.final_keys()
        record = cast("JsonObject", self.entities[kind][entity_id].record)
        text = new_key.rpartition(separator)[0]
        if text == ref_text(container_of(kind, record), keys):
            return new_key, None
        found = [
            entity_id
            for container_kind in _CONTAINER_KINDS[kind]
            for entity_id, merged in self.entities[container_kind].items()
            if merged.record is not None and keys[entity_id] == text
        ]
        if len(found) != 1:
            raise _form_error(index, f"new_key {new_key!r} names no single container {text!r} in the result")
        return new_key, found[0]

    def _rekey(self, kind: EntityKind, entity_id: str, new_key: str, container: str | None) -> None:
        record = cast("JsonObject", self.entities[kind][entity_id].record)
        if kind in (EntityKind.UNIT, EntityKind.CHECK):
            old = cast("list[JsonValue]", record["key"])[0]
            record["key"] = [old if container is None else container, new_key.rpartition(SEPARATOR[kind])[2]]
        elif kind is EntityKind.ITEM:
            record["key"] = new_key.rpartition(".")[2]
            if container is not None:
                record["phase"] = container
        elif kind is EntityKind.MATERIAL:
            record["key"] = new_key.removeprefix("material/")
        else:
            record["key"] = new_key

    # ------------------------------------------------------------------ step 8: order

    def order(self, kind: EntityKind) -> list[str]:
        survivors = [i for i, m in self.entities[kind].items() if m.record is not None]
        final = {
            i: canon(container_of(kind, cast("JsonObject", self.entities[kind][i].record))) for i in survivors
        }
        base, yours, theirs = (positions(side, kind) for side in (self.b, self.y, self.t))
        y_ids = list(self.y.records[kind])
        moved = [
            i
            for i in y_ids
            if i in final
            and (
                i not in base[0]
                or (yours[0][i] != base[0][i] and yours[0][i] == final[i])
                or (i in theirs[0] and yours[1][i] != base[1][i] and theirs[1][i] == base[1][i])
            )
        ]
        sequence = [i for i in self.t.records[kind] if i in final and i not in moved]
        for entity_id in moved:
            before = y_ids[: y_ids.index(entity_id)]
            anchor = next(
                (j for j in reversed(before) if j in sequence and final[j] == final[entity_id]), None
            )
            if anchor is not None:
                position = sequence.index(anchor) + 1
            else:
                position = next(
                    (n for n, j in enumerate(sequence) if final[j] == final[entity_id]), len(sequence)
                )
            sequence.insert(position, entity_id)
        for entity_id in survivors:
            if entity_id not in sequence:
                last = [n for n, j in enumerate(sequence) if final[j] == final[entity_id]]
                sequence.insert(last[-1] + 1 if last else len(sequence), entity_id)
        return sequence

    # ------------------------------------------------------------------ step 11: the document

    def document(self) -> JsonObject:
        keys = self.final_keys()
        convert = to_key(keys)
        out: JsonObject = {"schema": self.t.doc.get("schema", SPECIFICATION_URN), **copy.deepcopy(self.plan)}
        for array, kind in ENTITY_ARRAYS:
            entities: list[JsonValue] = []
            for entity_id in self.order(kind):
                record = copy.deepcopy(cast("JsonObject", self.entities[kind][entity_id].record))
                own = keys[entity_id]
                context = None
                if kind is EntityKind.UNIT:
                    context = own.split("/", 1)[0]
                elif kind is EntityKind.CRITERION:
                    context = ref_text(record.get("owner"), keys).split("/", 1)[0]
                rewrite_refs(array, record, context, convert)
                if kind in (EntityKind.ITEM, EntityKind.UNIT):
                    record["key"] = own
                elif kind is EntityKind.CHECK:
                    owner, _, local = own.rpartition(":")
                    record["owner"], record["key"] = owner, local
                entities.append({"id": real_id(entity_id), **record})
            out[array] = entities
        return out

    def counters(self) -> tuple[int, int]:
        merged = [m for kind in self.entities.values() for m in kind.values()]
        return (
            self.plan_taken + sum(m.taken for m in merged),
            self.plan_kept + sum(m.kept for m in merged),
        )

    def conflicts(self) -> tuple[RebaseConflict, ...]:
        return (*self.plan_conflicts, *self.entity_conflicts, *self.container_conflicts, *self.key_conflicts)


def rebase_document(
    base: Mapping[str, JsonValue] | None,
    yours: Mapping[str, JsonValue],
    theirs: Mapping[str, JsonValue],
    resolutions: Sequence[RebaseResolution],
    *,
    schema: SchemaValidator,
) -> RebaseOutcome:
    """Rebase ``yours`` (the draft) made from ``base`` onto ``theirs`` (the current revision), §5.10.

    ``base = None``: the draft was opened before the first publication. A resolution for a conflict that does
    not arise is ``INVALID_REFERENCE``; one of the wrong shape, with an unusable ``new_key`` or for a
    ``conflict_id`` that names several conflicts is ``SCHEMA_INVALID``, and so is a base or a current that
    repeats an entity id (``duplicate_id``; the issues point at ``/base/...`` and ``/theirs/...``). With open
    conflicts ``document`` is ``None`` and the counters describe the attempt.
    """
    base_doc = normalize_document(
        base if base is not None else {"schema": theirs.get("schema", SPECIFICATION_URN)}
    )
    theirs_doc = normalize_document(theirs)
    refuse_repeated_revisions(base_doc, theirs_doc)
    rebase = _Rebase(
        side_doc(base_doc, "b"),
        side_doc(normalize_document(yours), "y"),
        side_doc(theirs_doc, "t"),
        resolutions,
    )
    rebase.merge_plan()
    rebase.merge_entities()
    rebase.guard_containers()
    rebase.guard_keys()
    conflicts = rebase.conflicts()
    document: JsonObject | None = None
    if not conflicts:
        document = normalize_document(rebase.document())
        issues = schema.issues(document)
        if issues:
            conflict = RebaseConflict(
                conflict_id=_conflict_id(ConflictKind.SCHEMA, "document", None),
                kind=ConflictKind.SCHEMA,
                entity_id=None,
                entity_kind=None,
                key=None,
                field=None,
                pointer=None,
                base=ABSENT,
                yours=ABSENT,
                theirs=ABSENT,
                resolutions=(),
                colliding_entity_id=None,
                children_kept=(),
                issues=tuple(
                    {"pointer": i.pointer, "schema_pointer": i.schema_pointer, "message": i.message}
                    for i in issues
                ),
            )
            schema_conflicts: list[RebaseConflict] = []
            rebase.settle(conflict, schema_conflicts, "document")  # no resolution fits a schema conflict
            conflicts, document = tuple(schema_conflicts), None
    rebase.check_unknown()
    taken, kept = rebase.counters()
    return RebaseOutcome(document, conflicts, taken, kept, len(rebase.applied))
