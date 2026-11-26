"""Attempt steps: one role invocation through a runtime inside a stage (execution §4.8).

A step is history identity. Its ``route_snapshot`` pins the trusted requested/resolved route and the
immutable installation evidence at ``begin_stage``; a later route change creates a new step and never
rewrites an earlier step, attempt or output binding. ``runtime_observation`` stays a neutral nullable
mapping here, and an observation never authorizes a lifecycle change.
"""

from __future__ import annotations

import copy
import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from datetime import datetime
    from typing import Literal

    from skm.kernel.ids import AttemptId, ContextManifestId, FileVersionId
    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.ids import StageRecordId, StepId
    from skm.modules.execution.domain.lease import ProcessIdentity
    from skm.modules.execution.domain.session import SessionFingerprint
    from skm.modules.runtimes.public import UsageReport


class RoleId(StrEnum):
    SCOUT = "scout"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    TRIAGER = "triager"
    ADVISOR = "advisor"
    RESEARCHER = "researcher"
    REGISTRAR = "registrar"


class StepPurpose(StrEnum):
    PRIMARY = "primary"
    RESULT_RETRY = "result_retry"
    TRIAGE_REVERIFY = "triage_reverify"
    CONSILIUM_MEMBER = "consilium_member"
    CONSILIUM_CRITIC = "consilium_critic"


class StepState(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AttemptStep:
    id: StepId
    attempt_id: AttemptId
    stage_record_id: StageRecordId
    parent_step_id: StepId | None
    seq: int
    role: RoleId
    purpose: StepPurpose
    runtime_id: str
    model: str
    effort: str | None
    operation: str
    admission: Mapping[str, JsonValue]
    route_source: str
    route_reason: str
    context_manifest_id: ContextManifestId
    session_mode: Literal["new", "resume"]
    session_ref: str | None
    session_fingerprint: SessionFingerprint
    session_fingerprint_digest: str
    fresh_reason: str | None
    state: StepState
    result: Mapping[str, JsonValue] | None
    raw_result_file_version_id: FileVersionId | None
    repairs: tuple[str, ...]
    schema_errors: tuple[JsonObject, ...]
    usage: UsageReport | None
    usage_so_far: UsageReport | None
    process_identity: ProcessIdentity | None
    activity: Mapping[str, JsonValue] | None
    route_snapshot: Mapping[str, JsonValue] | None
    runtime_observation: Mapping[str, JsonValue] | None
    reuse_key: str | None
    transcript_file_version_id: FileVersionId | None
    last_progress_at: datetime | None
    error_code: str | None
    started_at: datetime
    finished_at: datetime | None

    def __post_init__(self) -> None:
        problems: list[str] = []
        if self.seq < 1:
            problems.append("seq >= 1")
        if self.parent_step_id is not None and self.parent_step_id == self.id:
            problems.append("a step is not its own parent")
        if (self.finished_at is not None) != (self.state is not StepState.STARTED):
            problems.append("finished_at is set exactly for a finished step")
        if self.finished_at is not None and self.finished_at < self.started_at:
            problems.append("finished_at >= started_at")
        if self.result is not None and self.state is not StepState.SUCCEEDED:
            problems.append("only a succeeded step has a result")
        if self.reuse_key is not None and self.role is not RoleId.SCOUT:
            problems.append("only a scout step has a reuse key")
        if self.fresh_reason is not None and self.session_mode != "new":
            problems.append("fresh_reason belongs to a new session")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "step invariants violated: " + "; ".join(problems),
                details={"step_id": str(self.id), "violations": list(problems)},
            )
        for name in _FROZEN_MAPPINGS:
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _freeze(value))


_FROZEN_MAPPINGS: Final = ("admission", "result", "activity", "route_snapshot", "runtime_observation")


def is_output_author(step: AttemptStep, output_producer: StepId | None) -> bool:
    return step.id == output_producer or (step.role is RoleId.EXECUTOR and step.state is StepState.SUCCEEDED)


def _freeze(value: object) -> object:
    """A deep immutable copy: objects become read-only mappings and arrays tuples at every level."""
    if isinstance(value, Mapping):
        items = cast("Mapping[object, object]", value)
        return MappingProxyType({key: _freeze(item) for key, item in items.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in cast("Sequence[object]", value))
    return copy.deepcopy(value)


def finish_step(
    step: AttemptStep,
    *,
    state: StepState,
    now: datetime,
    result: Mapping[str, JsonValue] | None = None,
    error_code: str | None = None,
) -> AttemptStep:
    """``started -> succeeded | failed | cancelled``; a finished step never changes again.

    The route snapshot and the observation of the step stay as recorded.
    """
    if step.state is not StepState.STARTED or state is StepState.STARTED:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            f"step cannot go from {step.state} to {state}",
            details={"step_id": str(step.id), "from": step.state.value, "to": StepState(state).value},
        )
    return dataclasses.replace(step, state=state, finished_at=now, result=result, error_code=error_code)
