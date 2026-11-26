"""Structural diff between two specification documents by stable entity ``id`` (planning §5.8)."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal

from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.display_keys import key_sort_key
from skm.modules.planning.domain.id_space import container_of, to_id_space
from skm.modules.planning.domain.identity import ENTITY_ARRAYS
from skm.modules.planning.domain.specification import EntityKind

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from skm.kernel.ids import EntityId
    from skm.kernel.json_types import JsonObject, JsonValue

__all__ = [
    "EntityDiff",
    "FieldChange",
    "SpecDiff",
    "diff_specifications",
]

_KIND_RANK: Final[Mapping[EntityKind, int]] = MappingProxyType(
    {kind: idx for idx, (_, kind) in enumerate(ENTITY_ARRAYS)}
)


@dataclass(frozen=True, slots=True)
class FieldChange:
    pointer: str
    op: Literal["add", "remove", "replace"]
    before: JsonValue
    after: JsonValue


@dataclass(frozen=True, slots=True)
class EntityDiff:
    entity_id: EntityId
    entity_kind: EntityKind
    change: Literal["added", "removed", "changed"]
    key_before: str | None
    key_after: str | None
    rekeyed: bool
    moved: bool
    fields: tuple[FieldChange, ...]


@dataclass(frozen=True, slots=True)
class SpecDiff:
    from_digest: str
    to_digest: str
    summary: Mapping[str, int]
    plan_fields: tuple[FieldChange, ...]
    entities: tuple[EntityDiff, ...]


def _escape_pointer(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def _same_value(a: JsonValue, b: JsonValue) -> bool:
    return json.dumps(a, ensure_ascii=False, separators=(",", ":"), sort_keys=True) == json.dumps(
        b, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def _diff_values(
    va_id: JsonValue,
    vb_id: JsonValue,
    va_key: JsonValue,
    vb_key: JsonValue,
    *,
    ptr: str,
) -> list[FieldChange]:
    if (
        isinstance(va_id, dict)
        and isinstance(vb_id, dict)
        and isinstance(va_key, dict)
        and isinstance(vb_key, dict)
    ):
        return _diff_objects(va_id, vb_id, va_key, vb_key, prefix=ptr)
    if (
        isinstance(va_id, list)
        and isinstance(vb_id, list)
        and isinstance(va_key, list)
        and isinstance(vb_key, list)
    ):
        return _diff_lists(va_id, vb_id, va_key, vb_key, prefix=ptr)
    if not _same_value(va_id, vb_id):
        return [
            FieldChange(
                pointer=ptr,
                op="replace",
                before=copy.deepcopy(va_key),
                after=copy.deepcopy(vb_key),
            )
        ]
    return []


def _diff_lists(
    a_id: Sequence[JsonValue],
    b_id: Sequence[JsonValue],
    a_key: Sequence[JsonValue],
    b_key: Sequence[JsonValue],
    *,
    prefix: str,
) -> list[FieldChange]:
    changes: list[FieldChange] = []
    max_len = max(len(a_id), len(b_id))
    for idx in range(max_len):
        ptr = f"{prefix}/{idx}"
        in_a = idx < len(a_id)
        in_b = idx < len(b_id)
        if in_a and not in_b:
            changes.append(
                FieldChange(pointer=ptr, op="remove", before=copy.deepcopy(a_key[idx]), after=None)
            )
        elif not in_a and in_b:
            changes.append(FieldChange(pointer=ptr, op="add", before=None, after=copy.deepcopy(b_key[idx])))
        else:
            changes.extend(_diff_values(a_id[idx], b_id[idx], a_key[idx], b_key[idx], ptr=ptr))
    return changes


def _diff_objects(
    a_id: Mapping[str, JsonValue],
    b_id: Mapping[str, JsonValue],
    a_key: Mapping[str, JsonValue],
    b_key: Mapping[str, JsonValue],
    *,
    prefix: str = "",
    ignore_keys: frozenset[str] = frozenset(),
) -> list[FieldChange]:
    changes: list[FieldChange] = []
    for name in dict.fromkeys([*a_id.keys(), *b_id.keys()]):
        if not prefix and name in ignore_keys:
            continue
        ptr = f"{prefix}/{_escape_pointer(name)}"
        in_a = name in a_id
        in_b = name in b_id
        if in_a and not in_b:
            changes.append(
                FieldChange(pointer=ptr, op="remove", before=copy.deepcopy(a_key[name]), after=None)
            )
        elif not in_a and in_b:
            changes.append(FieldChange(pointer=ptr, op="add", before=None, after=copy.deepcopy(b_key[name])))
        else:
            changes.extend(_diff_values(a_id[name], b_id[name], a_key[name], b_key[name], ptr=ptr))
    return changes


def _stationary_ids(a_shared: Sequence[EntityId], b_shared: Sequence[EntityId]) -> frozenset[EntityId]:
    """Longest common subsequence of shared siblings; tie-breaks keep earlier elements of ``a_shared``."""
    m, n = len(a_shared), len(b_shared)
    if m == 0 or n == 0:
        return frozenset()
    if list(a_shared) == list(b_shared):
        return frozenset(a_shared)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            if a_shared[i] == b_shared[j]:
                dp[i][j] = 1 + dp[i + 1][j + 1]
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    kept: set[EntityId] = set()
    i = j = 0
    while i < m and j < n:
        if a_shared[i] == b_shared[j]:
            kept.add(a_shared[i])
            i += 1
            j += 1
        elif dp[i][j + 1] >= dp[i + 1][j]:
            j += 1
        else:
            i += 1
    return frozenset(kept)


def _canon_container(kind: EntityKind, record: Mapping[str, JsonValue]) -> str:
    return json.dumps(container_of(kind, record), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def diff_specifications(a: JsonObject, b: JsonObject) -> SpecDiff:
    """Compute the structural diff between ``a`` (from) and ``b`` (to) (planning §5.8)."""
    a_space = to_id_space(a)
    b_space = to_id_space(b)
    from_digest = specification_digest(normalize_document(a))
    to_digest = specification_digest(normalize_document(b))

    plan_fields = tuple(
        _diff_objects(
            a_space.plan_fields,
            b_space.plan_fields,
            a_space.key_plan_fields,
            b_space.key_plan_fields,
        )
    )

    entity_diffs: list[EntityDiff] = []
    for _, kind in ENTITY_ARRAYS:
        a_map = a_space.entities[kind]
        b_map = b_space.entities[kind]
        containers = {_canon_container(kind, ent.id_record) for ent in (*a_map.values(), *b_map.values())}
        stationary_set: set[EntityId] = set()
        for c_key in containers:
            a_c = [
                eid
                for eid, ent in a_map.items()
                if eid in b_map
                and _canon_container(kind, ent.id_record) == c_key
                and _canon_container(kind, b_map[eid].id_record) == c_key
            ]
            b_c = [
                eid
                for eid, ent in b_map.items()
                if eid in a_map
                and _canon_container(kind, ent.id_record) == c_key
                and _canon_container(kind, a_map[eid].id_record) == c_key
            ]
            stationary_set.update(_stationary_ids(a_c, b_c))
        stationary = frozenset(stationary_set)

        for eid in dict.fromkeys([*a_map.keys(), *b_map.keys()]):
            a_ent = a_map.get(eid)
            b_ent = b_map.get(eid)
            if a_ent is None and b_ent is not None:
                entity_diffs.append(
                    EntityDiff(
                        entity_id=eid,
                        entity_kind=kind,
                        change="added",
                        key_before=None,
                        key_after=b_ent.display_key,
                        rekeyed=False,
                        moved=False,
                        fields=(),
                    )
                )
            elif a_ent is not None and b_ent is None:
                entity_diffs.append(
                    EntityDiff(
                        entity_id=eid,
                        entity_kind=kind,
                        change="removed",
                        key_before=a_ent.display_key,
                        key_after=None,
                        rekeyed=False,
                        moved=False,
                        fields=(),
                    )
                )
            elif a_ent is not None and b_ent is not None:
                rekeyed = a_ent.display_key != b_ent.display_key
                moved = eid not in stationary
                fields = tuple(
                    _diff_objects(
                        a_ent.id_record,
                        b_ent.id_record,
                        a_ent.key_record,
                        b_ent.key_record,
                        ignore_keys=frozenset({"key"}),
                    )
                )
                if fields or rekeyed or moved:
                    entity_diffs.append(
                        EntityDiff(
                            entity_id=eid,
                            entity_kind=kind,
                            change="changed",
                            key_before=a_ent.display_key,
                            key_after=b_ent.display_key,
                            rekeyed=rekeyed,
                            moved=moved,
                            fields=fields,
                        )
                    )

    entity_diffs.sort(
        key=lambda e: (
            _KIND_RANK[e.entity_kind],
            key_sort_key(e.key_after if e.key_after is not None else (e.key_before or "")),
            str(e.entity_id),
        )
    )
    entities = tuple(entity_diffs)
    summary: dict[str, int] = {
        "added": sum(1 for e in entities if e.change == "added"),
        "removed": sum(1 for e in entities if e.change == "removed"),
        "changed": sum(1 for e in entities if e.change == "changed" and bool(e.fields)),
        "rekeyed": sum(1 for e in entities if e.rekeyed),
        "moved": sum(1 for e in entities if e.moved),
    }
    return SpecDiff(
        from_digest=from_digest,
        to_digest=to_digest,
        summary=MappingProxyType(summary),
        plan_fields=plan_fields,
        entities=entities,
    )
