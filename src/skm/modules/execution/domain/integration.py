"""Pure integration planning; output history and acceptance remain immutable."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.output import matches_path

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from skm.kernel.ids import AttemptId, HostId, RepositoryId, RunId, WorkspaceId
    from skm.modules.execution.domain.ids import IntegrationSlotId
    from skm.modules.execution.domain.output import ChangedPath, Output


class IntegrationStrategy(StrEnum):
    SQUASH = "squash"
    REBASE = "rebase"
    MERGE = "merge"


class CommitMode(StrEnum):
    FINAL_ONLY = "final_only"
    IMPLEMENTATION_AND_FIXES = "implementation_and_fixes"
    PER_STAGE_ATTRIBUTED = "per_stage_attributed"


@dataclass(frozen=True, slots=True)
class IntegrationSlot:
    id: IntegrationSlotId
    workspace_id: WorkspaceId
    repository_id: RepositoryId
    target_branch: str
    holder_attempt_id: AttemptId | None
    fencing_token: int
    expires_at: datetime | None
    writer_host_id: HostId
    row_version: int


@dataclass(frozen=True, slots=True)
class IntegrationHost:
    run_id: RunId
    repository_id: RepositoryId
    host_id: HostId
    pinned_at: datetime


REQUIRED_TRAILERS: Final = (
    ("SKM-Run", "run_id"),
    ("SKM-Plan", "plan_id"),
    ("SKM-Revision", "revision_no"),
    ("SKM-Task", "task_key"),
    ("SKM-Attempt", "attempt_id"),
    ("SKM-Output", "output_id"),
    ("SKM-Effect", "effect_id"),
)
_IDENTITY_TRAILERS: Final = (
    ("SKM-Review", "review_id"),
    ("SKM-Findings", "findings"),
    ("SKM-Output-No", "output_no"),
    ("SKM-Review-Round", "review_round"),
    ("Task-Spec-Ref", "task_spec_ref"),
    ("Task-Spec-Digest", "task_spec_digest"),
    ("Plan", "plan"),
    ("Plan-Ref", "plan_ref"),
)
_PRODUCER_TRAILERS: Final = (
    ("Plan-Role", "plan_role"),
    ("Plan-Actor", "plan_actor"),
    ("Executed-By", "executed_by"),
    ("Executor-Session", "executor_session"),
)
_REVIEWER_TRAILERS: Final = (
    ("Reviewed-By", "reviewed_by"),
    ("Reviewer-Session", "reviewer_session"),
)
OPTIONAL_TRAILERS: Final = (*_IDENTITY_TRAILERS, *_PRODUCER_TRAILERS, *_REVIEWER_TRAILERS)
TRAILER_NAMES: Final = frozenset(name.lower() for name, _ in (*REQUIRED_TRAILERS, *OPTIONAL_TRAILERS))
REPEATABLE_TRAILERS: Final = frozenset(
    {
        "SKM-Findings",
        "Plan-Role",
        "Plan-Actor",
        "Executed-By",
        "Executor-Session",
        "Reviewed-By",
        "Reviewer-Session",
    }
)
_UUID: Final = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
TASK_SPEC_REF: Final = re.compile(
    rf"skm:(?:revision:{_UUID}#entity:{_UUID}|file-version:{_UUID}|task:{_UUID})"
)
TASK_SPEC_DIGEST: Final = re.compile(r"sha256:[0-9a-f]{64}")
FINDING_KEY: Final = re.compile(r"fk-[0-9a-f]{16}")
SESSION_REF: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}")


def _render_trailers(
    inputs: dict[str, JsonValue], keys: tuple[tuple[str, str], ...]
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for trailer, key in keys:
        value = inputs.get(key)
        if value is None:
            if (trailer, key) in REQUIRED_TRAILERS:
                raise ValueError(f"missing integration identity: {key}")
            continue
        if isinstance(value, list) and trailer not in REPEATABLE_TRAILERS:
            raise ValueError(f"invalid integration trailer: {trailer}")
        for item in value if isinstance(value, list) else [value]:
            if type(item) not in (str, int):
                raise ValueError(f"invalid integration trailer: {trailer}")
            text = str(item)
            if not text or text != text.strip() or not text.isprintable():
                raise ValueError(f"invalid integration trailer: {trailer}")
            if trailer == "SKM-Findings" and FINDING_KEY.fullmatch(text) is None:
                raise ValueError(f"invalid integration trailer: {trailer}")
            if trailer in {"Executor-Session", "Reviewer-Session"} and SESSION_REF.fullmatch(text) is None:
                raise ValueError(f"invalid integration trailer: {trailer}")
            result.append((trailer, text))
    return result


def commit_trailers(inputs: JsonObject) -> tuple[tuple[str, str], ...]:
    task_ref, task_digest = inputs.get("task_spec_ref"), inputs.get("task_spec_digest")
    if (task_ref is not None or task_digest is not None) and (
        not isinstance(task_ref, str)
        or TASK_SPEC_REF.fullmatch(task_ref) is None
        or not isinstance(task_digest, str)
        or TASK_SPEC_DIGEST.fullmatch(task_digest) is None
    ):
        raise ValueError("invalid task specification trailers")
    result = _render_trailers(inputs, (*REQUIRED_TRAILERS, *_IDENTITY_TRAILERS))
    result.extend(_render_trailers(inputs, _PRODUCER_TRAILERS))
    producers = inputs.get("producers", [])
    if not isinstance(producers, list):
        raise ValueError("integration producers must be an ordered list")
    for producer in producers:
        if not isinstance(producer, dict):
            raise ValueError("invalid integration producer")
        result.extend(_render_trailers(producer, _PRODUCER_TRAILERS))
    result.extend(_render_trailers(inputs, _REVIEWER_TRAILERS))
    return tuple(result)


def commit_plan(outputs: Sequence[Output], mode: CommitMode) -> JsonObject:
    if not outputs or len({o.id for o in outputs}) != len(outputs):
        raise ValueError("integration requires unique accepted-attempt outputs")
    ordered = sorted(outputs, key=lambda o: o.seq)
    if len({(o.attempt_id, o.task_id, o.run_id) for o in ordered}) != 1:
        raise ValueError("outputs must belong to one accepted attempt")
    if len({o.seq for o in ordered}) != len(ordered):
        raise ValueError("output sequence must be unique")
    selected = ordered[-1:] if mode is CommitMode.FINAL_ONLY else ordered
    return {
        "mode": mode.value,
        "output_ids": [str(o.id) for o in selected],
        "output_digests": [o.manifest_digest for o in selected],
    }


def excluded_paths(paths: Sequence[ChangedPath], patterns: Sequence[str]) -> tuple[ChangedPath, ...]:
    return tuple(
        p
        for p in paths
        if any(
            matches_path(p.path, pattern) or (p.old_path is not None and matches_path(p.old_path, pattern))
            for pattern in patterns
        )
    )


def validate_mode(strategy: IntegrationStrategy, mode: CommitMode) -> None:
    if strategy is IntegrationStrategy.SQUASH and mode is not CommitMode.FINAL_ONLY:
        raise error_for(ErrorCode.CONFIG_INVALID, f"{mode.value} requires rebase or merge")
