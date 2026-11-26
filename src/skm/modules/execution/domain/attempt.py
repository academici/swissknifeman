"""Attempt, its state machine and the durable continuation cursor (execution §4.6, §4.6.1).

An attempt is one try of a task in one environment. Its outputs are an append-only sequence; the current
one is ``current_output_id`` and never replaces an earlier output (§4.11). Attempts that lost ownership
or were abandoned are never accepted (A1).

``Attempt.continuation`` is a server-private cursor, not a command queue: ``None`` (no cursor, or an
unknown legacy state that is never reconstructed from history), an ``advance`` cursor of trusted triggers
not yet applied by the evaluator, or a ``stage`` cursor holding an already selected and applied semantic
``RunStage`` template. Selecting a stage is not an admission and does not start the attempt (T3 happens
at ``begin_stage``). A terminal attempt state clears the cursor in the same transition.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal, NoReturn, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.ids import StageRecordId
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode

if TYPE_CHECKING:
    from skm.kernel.ids import AttemptId, HostId, RunId, TaskId, WorkerId, WorkspaceId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.execution.domain.ids import EnvironmentId, OutputId
    from skm.modules.execution.domain.output import Output
    from skm.modules.execution.domain.session import RouteRef

__all__ = [
    "ATTEMPT_TRANSITIONS",
    "CONTINUATION_MAX_BYTES",
    "CONTROL_PLANE_STAGE_TYPES",
    "MAX_TRIGGERS",
    "TERMINAL_ATTEMPT_STATES",
    "TRIGGER_KINDS",
    "AdvanceContinuation",
    "Attempt",
    "AttemptEndReason",
    "AttemptState",
    "AttemptTransition",
    "ContinuationCause",
    "DeferredTrigger",
    "EntityRef",
    "PendingContinuation",
    "SelectedStage",
    "StageContinuation",
    "acceptable",
    "bind_executor_route",
    "consume_stage",
    "continuation_to_json",
    "defer_trigger",
    "record_output",
    "select_stage",
    "settle_advance",
    "transition_attempt",
]

CONTINUATION_MAX_BYTES: Final = 65536
MAX_TRIGGERS: Final = 128
_MAX_PARAMS: Final = 128
# control-plane stages run inside apply_action and are never queued as a host continuation
CONTROL_PLANE_STAGE_TYPES: Final = frozenset(
    {"acceptance_gate", "phase_gate", "plan_acceptance", "human_gate"}
)
TRIGGER_KINDS: Final = frozenset(
    {
        "manual_start",
        "dependency_satisfied",
        "stage_outcome",
        "check_failed",
        "review_findings",
        "retry",
        "lease_recovery",
        "operator_resume",
        "reconfigure",
        "observation",
        "run_start",
        "followup",
        "integration",
        "wait_changed",
        "monitor",
        "policy_resolved",
        "carry_forward",
        "cancel",
        "timeout",
        "timer",
        "subscription",
        "restart",
        "skip",
        "decision_answered",
        "manual_verdict",
    }
)
_REF_KINDS: Final = frozenset(
    {
        "run",
        "task",
        "attempt",
        "stage",
        "step",
        "output",
        "check",
        "review",
        "decision_request",
        "decision",
        "effect",
        "recovery",
        "fix_brief",
        "finding",
        "reconfiguration",
    }
)
_STAGE_ID = re.compile(r"[a-z][a-z0-9_]{0,31}")
_STAGE_TYPE = re.compile(r"[a-z][a-z0-9_]{0,40}")
_ADVANCE_RULE = re.compile(r"[A-Z][A-Za-z0-9_]{0,31}")
_REASON_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
_COMMAND_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")


class AttemptState(StrEnum):
    PREPARING = "preparing"
    RUNNING = "running"
    WAITING = "waiting"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    OWNERSHIP_LOST = "ownership_lost"
    ABANDONED = "abandoned"


class AttemptEndReason(StrEnum):
    ACCEPTED = "ACCEPTED"
    LEASE_LOST = "LEASE_LOST"
    RESTARTED = "RESTARTED"
    RETRY_NEW_ATTEMPT = "RETRY_NEW_ATTEMPT"
    RECOVERY_NEW_ATTEMPT = "RECOVERY_NEW_ATTEMPT"
    OWNER_DECISION = "OWNER_DECISION"
    GATE_REREVIEW = "GATE_REREVIEW"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


TERMINAL_ATTEMPT_STATES: Final = frozenset(
    {AttemptState.COMPLETED, AttemptState.OWNERSHIP_LOST, AttemptState.ABANDONED}
)
_NEVER_ACCEPTED: Final = frozenset({AttemptState.OWNERSHIP_LOST, AttemptState.ABANDONED})


# ---------------------------------------------------------------- continuation (§4.6.1)


@dataclass(frozen=True, slots=True)
class EntityRef:
    kind: str
    id: UUID

    def __post_init__(self) -> None:
        if self.kind not in _REF_KINDS:
            _invalid("cause.refs", f"unknown entity ref kind {self.kind!r}")


@dataclass(frozen=True, slots=True)
class ContinuationCause:
    """The authoritative cause of a cursor (``urn:skm:execution:execution-history:v1#/$defs/cause``).

    Observations never authorize lifecycle: ``trigger_kind = observation`` is refused here.
    """

    trigger_kind: str
    advance_rule: str | None
    reason_codes: tuple[str, ...] = ()
    refs: tuple[EntityRef, ...] = ()
    command_id: str | None = None
    source_event_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.trigger_kind not in TRIGGER_KINDS:
            _invalid("cause.trigger_kind", f"unknown trigger kind {self.trigger_kind!r}")
        if self.trigger_kind == "observation":
            _invalid("cause.trigger_kind", "an observation is not a trusted continuation trigger")
        if self.advance_rule is not None and not _ADVANCE_RULE.fullmatch(self.advance_rule):
            _invalid("cause.advance_rule", "advance_rule is a rule id such as D6g")
        if len(self.reason_codes) > 32 or not all(_REASON_CODE.fullmatch(code) for code in self.reason_codes):
            _invalid("cause.reason_codes", "at most 32 UPPER_SNAKE reason codes")
        if len(self.refs) > 200:
            _invalid("cause.refs", "at most 200 refs")
        if self.command_id is not None and not _COMMAND_ID.fullmatch(self.command_id):
            _invalid("cause.command_id", "invalid command id")


@dataclass(frozen=True, slots=True)
class DeferredTrigger:
    """A committed trusted transition not yet applied by the evaluator; ``advance_rule`` is still null."""

    source_event_id: UUID
    cause: ContinuationCause

    def __post_init__(self) -> None:
        if self.cause.advance_rule is not None:
            _invalid("triggers.cause.advance_rule", "a deferred trigger has not fired an advance rule yet")
        if self.cause.source_event_id not in (None, self.source_event_id):
            _invalid("triggers.cause.source_event_id", "cause.source_event_id equals the trigger's event")


@dataclass(frozen=True, slots=True)
class SelectedStage:
    """The normalized semantic ``RunStage`` template; never config digests, tokens or host locators."""

    stage_id: str
    stage_type: str
    mode: StageMode
    round_no: int
    params: Mapping[str, JsonValue]
    not_before: datetime | None
    route_override: RouteRef | None
    feedback_refs: FeedbackRefs
    input_output_id: OutputId | None
    retry_of_id: StageRecordId | None

    def __post_init__(self) -> None:
        if not _STAGE_ID.fullmatch(self.stage_id):
            _invalid("stage.stage_id", "invalid stage id")
        if not _STAGE_TYPE.fullmatch(self.stage_type):
            _invalid("stage.stage_type", "invalid stage type")
        if self.stage_type in CONTROL_PLANE_STAGE_TYPES:
            _invalid("stage.stage_type", "a control-plane stage is never a host continuation")
        if self.round_no < 1:
            _invalid("stage.round_no", "round_no >= 1")
        if len(self.params) > _MAX_PARAMS:
            _invalid("stage.params", f"at most {_MAX_PARAMS} params")
        if self.retry_of_id is not None and self.mode is not StageMode.RETRY:
            _invalid("stage.retry_of_id", "retry_of_id only with mode retry")
        answers = self.feedback_refs.answer_request_ids
        if len(answers) > MAX_TRIGGERS or len(set(answers)) != len(answers):
            _invalid("stage.feedback_refs.answer_request_ids", "at most 128 distinct answer requests")
        # a deep immutable copy: a caller keeps no handle that could change the template after its size check
        object.__setattr__(self, "params", _freeze(self.params, "stage.params"))


@dataclass(frozen=True, slots=True)
class StageContinuation:
    schema_version: Literal[1]
    continuation_id: UUID
    kind: Literal["stage"]
    cause: ContinuationCause
    stage: SelectedStage

    def __post_init__(self) -> None:
        _check_header(self.schema_version, self.kind, "stage")
        _check_size(self)


@dataclass(frozen=True, slots=True)
class AdvanceContinuation:
    schema_version: Literal[1]
    continuation_id: UUID
    kind: Literal["advance"]
    triggers: tuple[DeferredTrigger, ...]

    def __post_init__(self) -> None:
        _check_header(self.schema_version, self.kind, "advance")
        if not 1 <= len(self.triggers) <= MAX_TRIGGERS:
            _invalid("triggers", f"an advance cursor holds 1..{MAX_TRIGGERS} triggers")
        events = [trigger.source_event_id for trigger in self.triggers]
        if len(set(events)) != len(events):
            _invalid("triggers", "trigger source events are distinct")
        _check_size(self)


type PendingContinuation = StageContinuation | AdvanceContinuation


# ---------------------------------------------------------------- attempt


@dataclass(frozen=True, slots=True)
class Attempt:
    id: AttemptId
    run_id: RunId
    task_id: TaskId
    workspace_id: WorkspaceId
    attempt_no: int
    state: AttemptState
    worker_id: WorkerId | None
    host_id: HostId | None
    environment_id: EnvironmentId | None
    current_output_id: OutputId | None
    executor_route: RouteRef | None
    continuation: PendingContinuation | None
    started_at: datetime
    finished_at: datetime | None
    end_reason: str | None

    def __post_init__(self) -> None:
        problems: list[str] = []
        terminal = self.state in TERMINAL_ATTEMPT_STATES
        if self.attempt_no < 1:
            problems.append("attempt_no >= 1")
        if terminal != (self.finished_at is not None):
            problems.append("finished_at is set exactly in completed, ownership_lost and abandoned")
        if (self.end_reason is not None) != (self.finished_at is not None):
            problems.append("end_reason is set exactly when finished")
        if self.end_reason is not None and self.end_reason not in AttemptEndReason.__members__:
            problems.append(f"unknown end_reason {self.end_reason}")
        if self.finished_at is not None and self.finished_at < self.started_at:
            problems.append("finished_at >= started_at")
        if terminal and self.continuation is not None:
            problems.append("a terminal attempt has no continuation cursor")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "attempt invariants violated: " + "; ".join(problems),
                details={"attempt_id": str(self.id), "violations": list(problems)},
            )


@dataclass(frozen=True, slots=True)
class AttemptTransition:
    sources: frozenset[AttemptState]
    target: AttemptState
    trigger: str


_A = AttemptState

ATTEMPT_TRANSITIONS: Final[tuple[AttemptTransition, ...]] = (
    AttemptTransition(
        frozenset(), _A.PREPARING, "schedule_ready_tasks creates the attempt with its assignment"
    ),
    AttemptTransition(frozenset({_A.PREPARING}), _A.RUNNING, "prepare_environment succeeded"),
    AttemptTransition(
        frozenset({_A.RUNNING}), _A.WAITING, "manual/decision wait, paused release or rule L1/L2 expiry"
    ),
    AttemptTransition(
        frozenset({_A.WAITING}), _A.RUNNING, "a new assignment of the same attempt was claimed"
    ),
    AttemptTransition(frozenset({_A.RUNNING}), _A.SUBMITTED, "begin_stage(integrate)"),
    AttemptTransition(frozenset({_A.SUBMITTED}), _A.COMPLETED, "task accepted after integration"),
    AttemptTransition(
        frozenset({_A.PREPARING, _A.RUNNING, _A.WAITING, _A.SUBMITTED}), _A.OWNERSHIP_LOST, "rule L3"
    ),
    AttemptTransition(
        frozenset({_A.PREPARING, _A.RUNNING, _A.WAITING}),
        _A.ABANDONED,
        "restart, NewAttempt, recovery, cancel_run or carry_forward_result",
    ),
    AttemptTransition(
        frozenset({_A.RUNNING, _A.WAITING}),
        _A.COMPLETED,
        "task failed/skipped or gate accepted without changes",
    ),
)


def acceptable(attempt: Attempt) -> bool:
    """A1: results of attempts that lost ownership or were abandoned are never accepted."""
    return attempt.state not in _NEVER_ACCEPTED


def transition_attempt(
    attempt: Attempt,
    to: AttemptState,
    *,
    now: datetime | None = None,
    end_reason: AttemptEndReason | None = None,
) -> Attempt:
    """Apply one row of ``ATTEMPT_TRANSITIONS``; anything else is ``INVALID_TRANSITION``.

    A terminal state needs ``now`` and ``end_reason`` and clears the continuation in the same change (the
    same UPDATE, SQL ``ck_attempts__continuation``). Non-terminal changes keep the cursor: an expiry or a
    pause between stages must not lose a selected stage or unapplied triggers.
    """
    to = AttemptState(to)
    if not any(attempt.state in rule.sources and rule.target is to for rule in ATTEMPT_TRANSITIONS):
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            f"attempt cannot go from {attempt.state} to {to}",
            details={"attempt_id": str(attempt.id), "from": attempt.state.value, "to": to.value},
        )
    if to in TERMINAL_ATTEMPT_STATES:
        if now is None or end_reason is None:
            raise error_for(
                ErrorCode.SCHEMA_INVALID, "a finished attempt records when and why", details={"to": to.value}
            )
        return dataclasses.replace(
            attempt,
            state=to,
            finished_at=now,
            end_reason=AttemptEndReason(end_reason).value,
            continuation=None,
        )
    if end_reason is not None:
        _invalid("end_reason", "only a finished attempt has an end reason")
    return dataclasses.replace(attempt, state=to)


def record_output(attempt: Attempt, output: Output, *, previous: Output | None) -> Attempt:
    """Seal ``output`` as the attempt's newest output; earlier outputs stay as they were.

    ``previous`` is the attempt's current output (``None`` before the first seal); the new output follows
    it with ``seq + 1``. A finished attempt seals nothing.
    """
    if attempt.state in TERMINAL_ATTEMPT_STATES:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "a finished attempt seals no output",
            details={"attempt_id": str(attempt.id), "state": attempt.state.value},
        )
    if (
        output.attempt_id != attempt.id
        or output.task_id != attempt.task_id
        or output.run_id != attempt.run_id
    ):
        _invalid("output.attempt_id", "the output belongs to this attempt")
    current = None if previous is None else previous.id
    if current != attempt.current_output_id:
        _invalid("previous", "previous is the attempt's current output")
    expected = 1 if previous is None else previous.seq + 1
    if output.seq != expected:
        _invalid("output.seq", f"the next output of the attempt has seq {expected}")
    return dataclasses.replace(attempt, current_output_id=output.id)


def bind_executor_route(attempt: Attempt, route: RouteRef) -> Attempt:
    """Record the executor route of the attempt once; a later route change binds only its own step."""
    if attempt.executor_route is not None:
        return attempt
    return dataclasses.replace(attempt, executor_route=route)


def defer_trigger(attempt: Attempt, trigger: DeferredTrigger, *, continuation_id: UUID) -> Attempt:
    """Append a committed trusted trigger to the advance cursor (created when there is none).

    Repeating the same source event is a no-op. A selected stage cannot absorb a new trigger
    (``INVALID_TRANSITION``, reason ``continuation_already_selected``) and a full cursor refuses it
    before any change: no trigger is lost and nothing is applied partially. ``continuation_id`` is the
    fresh identity of the replaced cursor.
    """
    _require_active(attempt)
    current = attempt.continuation
    if isinstance(current, StageContinuation):
        _refuse(attempt, "continuation_already_selected")
    triggers: tuple[DeferredTrigger, ...] = () if current is None else current.triggers
    if any(found.source_event_id == trigger.source_event_id for found in triggers):
        return attempt
    if len(triggers) >= MAX_TRIGGERS:
        _refuse(attempt, "continuation_full")
    cursor = AdvanceContinuation(1, continuation_id, "advance", (*triggers, trigger))
    return dataclasses.replace(attempt, continuation=cursor)


def select_stage(
    attempt: Attempt, *, cause: ContinuationCause, stage: SelectedStage, continuation_id: UUID
) -> Attempt:
    """Replace the cursor with the stage the evaluator selected and already applied.

    This is not an admission: the attempt state and task status do not change here (T3 is ``begin_stage``).
    A stage that is already selected is never selected again (counters must not repeat).
    """
    _require_active(attempt)
    if isinstance(attempt.continuation, StageContinuation):
        _refuse(attempt, "continuation_already_selected")
    cursor = StageContinuation(1, continuation_id, "stage", cause, stage)
    return dataclasses.replace(attempt, continuation=cursor)


def settle_advance(attempt: Attempt) -> Attempt:
    """The evaluator applied the triggers and the result is a wait or terminal action: no cursor."""
    _require_active(attempt)
    if not isinstance(attempt.continuation, AdvanceContinuation):
        _refuse(attempt, "no_pending_triggers")
    return dataclasses.replace(attempt, continuation=None)


def consume_stage(attempt: Attempt, *, continuation_id: UUID) -> tuple[Attempt, SelectedStage]:
    """``begin_stage`` takes the selected stage atomically with creating its StageRecord.

    ``continuation_id`` must be the one the instruction was materialized from; a refused begin consumes
    nothing because it never calls this.
    """
    _require_active(attempt)
    cursor = attempt.continuation
    if not isinstance(cursor, StageContinuation):
        _refuse(attempt, "no_selected_stage")
    if cursor.continuation_id != continuation_id:
        _refuse(attempt, "continuation_changed")
    return dataclasses.replace(attempt, continuation=None), cursor.stage


def continuation_to_json(cursor: PendingContinuation) -> JsonObject:
    """The stored form (``urn:skm:execution:pending-continuation:v1``)."""
    if isinstance(cursor, AdvanceContinuation):
        return {
            "schema_version": 1,
            "continuation_id": str(cursor.continuation_id),
            "kind": "advance",
            "triggers": [
                {"source_event_id": str(trigger.source_event_id), "cause": _cause_json(trigger.cause)}
                for trigger in cursor.triggers
            ],
        }
    stage = cursor.stage
    feedback = stage.feedback_refs
    route = stage.route_override
    return {
        "schema_version": 1,
        "continuation_id": str(cursor.continuation_id),
        "kind": "stage",
        "cause": _cause_json(cursor.cause),
        "stage": {
            "stage_id": stage.stage_id,
            "stage_type": stage.stage_type,
            "mode": stage.mode.value,
            "round_no": stage.round_no,
            "params": thaw_json(stage.params),
            "not_before": None
            if stage.not_before is None
            else stage.not_before.isoformat().replace("+00:00", "Z"),
            "route_override": None
            if route is None
            else {"runtime_id": route.runtime_id, "model": route.model, "effort": route.effort},
            "feedback_refs": {
                "fix_brief_id": _optional_id(feedback.fix_brief_id),
                "schema_errors_step_id": _optional_id(feedback.schema_errors_step_id),
                "answer_request_ids": [str(found) for found in feedback.answer_request_ids],
                "advice_step_id": _optional_id(feedback.advice_step_id),
                "interrupted_stage_record_id": _optional_id(feedback.interrupted_stage_record_id),
            },
            "input_output_id": _optional_id(stage.input_output_id),
            "retry_of_id": _optional_id(stage.retry_of_id),
        },
    }


def _cause_json(cause: ContinuationCause) -> JsonObject:
    document: JsonObject = {
        "trigger_kind": cause.trigger_kind,
        "advance_rule": cause.advance_rule,
        "reason_codes": list(cause.reason_codes),
        "refs": [{"kind": ref.kind, "id": str(ref.id)} for ref in cause.refs],
    }
    if cause.command_id is not None:
        document["command_id"] = cause.command_id
    if cause.source_event_id is not None:
        document["source_event_id"] = str(cause.source_event_id)
    return document


def _optional_id(value: UUID | None) -> str | None:
    return None if value is None else str(value)


def _freeze(value: object, field: str) -> Mapping[str, JsonValue]:
    frozen = _freeze_value(value, field)
    if not isinstance(frozen, MappingProxyType):
        _invalid(field, "params is an object")
    return cast("Mapping[str, JsonValue]", frozen)


def _freeze_value(value: object, field: str) -> object:
    """Objects become read-only mappings and arrays tuples, recursively; anything else is not JSON."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _invalid(field, "a non-finite number is not JSON")
        return value
    if isinstance(value, Mapping):
        items = cast("Mapping[object, object]", value)
        if not all(isinstance(key, str) for key in items):
            _invalid(field, "object keys are strings")
        return MappingProxyType(
            {str(key): _freeze_value(item, f"{field}.{key}") for key, item in items.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item, f"{field}[]") for item in cast("Sequence[object]", value))
    raise error_for(
        ErrorCode.SCHEMA_INVALID, f"{type(value).__name__} is not a JSON value", details={"field": field}
    )


def _check_header(version: int, kind: str, expected: str) -> None:
    if version != 1:
        _invalid("schema_version", "continuation schema_version is 1")
    if kind != expected:
        _invalid("kind", f"kind is {expected}")


def _check_size(cursor: PendingContinuation) -> None:
    text = json.dumps(continuation_to_json(cursor), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(text.encode("utf-8")) > CONTINUATION_MAX_BYTES:
        _invalid("continuation", f"a continuation cursor is at most {CONTINUATION_MAX_BYTES} bytes")


def _require_active(attempt: Attempt) -> None:
    if attempt.state in TERMINAL_ATTEMPT_STATES:
        _refuse(attempt, "attempt_finished")


def _refuse(attempt: Attempt, reason: str) -> NoReturn:
    raise error_for(
        ErrorCode.INVALID_TRANSITION,
        f"continuation of attempt {attempt.id}: {reason}",
        details={"attempt_id": str(attempt.id), "reason": reason},
    )


def _invalid(field: str, message: str) -> NoReturn:
    raise error_for(ErrorCode.SCHEMA_INVALID, message, details={"field": field})
