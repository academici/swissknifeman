"""Digest of a task contract and the reuse key of a scout (runtimes §4.11 rule 4, execution §5.2).

Both are canonical JSON (sorted keys, no spaces, UTF-8) hashed with SHA-256 as ``sha256:<hex>``. Neither
reads a clock: remaining time, deadlines and other run facts are not part of the contract, so the same
contract under the same effective work policy always has the same digest. Wording of ``guidance`` and
``rules`` is not part of it either.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject, JsonValue

__all__ = ["SCOUT_REUSE_FIELDS", "TASK_CONTRACT_FIELDS", "scout_reuse_key", "task_contract_digest"]

# Fields of the planning entity that make the contract; an absent field reads as ``null``.
TASK_CONTRACT_FIELDS: Final = (
    "goal",
    "instructions",
    "deliverables",
    "outputs",
    "declared_write_scope",
    "criteria",
    "check_specs",
    "review_requirement",
    "declared_work_policy",
)
# Inputs of the scout reuse key (§5.2); the set is closed, a change of any input is a new key.
SCOUT_REUSE_FIELDS: Final = (
    "project_id",
    "task_contract_digest",
    "baseline",
    "scout_profile_resource_version_id",
    "context_policy_digest",
)


def _canonical(document: JsonValue) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(document: JsonValue) -> str:
    return "sha256:" + hashlib.sha256(_canonical(document).encode("utf-8")).hexdigest()


def _as_list(value: JsonValue, name: str) -> list[JsonValue]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _check_spec(spec: JsonValue) -> JsonValue:
    """``(id, kind, definition digest)``: only the digest of the definition enters the contract."""
    if not isinstance(spec, Mapping):
        raise ValueError("a check spec must be an object")
    definition_digest = spec.get("definition_digest")
    if definition_digest is None:
        definition_digest = _digest(spec.get("definition"))
    return {"id": spec.get("id"), "kind": spec.get("kind"), "definition_digest": definition_digest}


def task_contract_digest(entity: JsonObject, work_policy_digest: str) -> str:
    """Digest of ``{goal, instructions, deliverables, outputs, declared_write_scope, criteria, check_specs,
    review_requirement, declared_work_policy, effective_work_policy_digest}`` of the entity.

    ``declared_write_scope`` and ``check_specs`` are sets (their order does not change the contract) and are
    sorted; ``criteria`` and the other lists keep their order. ``None`` write scope (unknown) differs from
    ``[]`` (no writes).
    """
    if not isinstance(entity, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError("the task entity must be an object")
    if not work_policy_digest:
        raise ValueError("the effective work policy digest is part of the contract")
    document: dict[str, JsonValue] = {field: entity.get(field) for field in TASK_CONTRACT_FIELDS}
    scope = document["declared_write_scope"]
    if scope is not None:
        document["declared_write_scope"] = sorted(_as_list(scope, "declared_write_scope"), key=_canonical)
    document["check_specs"] = sorted(
        (_check_spec(spec) for spec in _as_list(document["check_specs"], "check_specs")), key=_canonical
    )
    document["effective_work_policy_digest"] = work_policy_digest
    return _digest(document)


def _baseline_entry(entry: JsonValue) -> list[JsonValue]:
    """``[mount, commit_sha, dirty_patch_digest | null]`` from an object or a three-item list."""
    if isinstance(entry, Mapping):
        return [entry.get("mount"), entry.get("commit_sha"), entry.get("dirty_patch_digest")]
    if isinstance(entry, Sequence) and not isinstance(entry, str) and len(entry) == 3:
        return list(entry)
    raise ValueError(
        "a baseline entry is {mount, commit_sha, dirty_patch_digest} or [mount, commit_sha, digest]"
    )


def scout_reuse_key(inputs: JsonObject) -> str:
    """``sha256`` of ``{project_id, task_contract_digest, baseline, scout_profile_resource_version_id,
    context_policy_digest}``; ``baseline`` lists the environment's
    ``(mount, commit_sha, dirty patch digest | null)`` and is a set.

    A missing or an extra input is an error: a hidden input would make two different scouts share a key.
    """
    names = set(inputs)
    if names != set(SCOUT_REUSE_FIELDS):
        missing, extra = sorted(set(SCOUT_REUSE_FIELDS) - names), sorted(names - set(SCOUT_REUSE_FIELDS))
        raise ValueError(f"scout reuse key inputs differ: missing {missing}, unexpected {extra}")
    document: dict[str, JsonValue] = dict(inputs)
    document["baseline"] = sorted(
        (_baseline_entry(entry) for entry in _as_list(inputs["baseline"], "baseline")), key=_canonical
    )
    return _digest(document)
