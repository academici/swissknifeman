"""Stage records: "stage started" written before execution (execution §4.7).

At most one record of an attempt is unfinished (``started``, ``context_draft`` or ``running``); repeating
``begin_stage`` with the same ``(stage_id, round_no, input_digest)`` returns that record. Control-plane
stages are created ``completed`` in one transaction, skipped stages are recorded ``skipped``.

``process_identities`` are the durable observed units of the stage (role steps, check runs, Git effects),
keyed by ``ownership.owner.unit_kind/unit_id``; they survive the deletion of the lease. A terminal record
(``interrupted``, ``failed``…) or a cancelled step is history, not a proof that the processes stopped:
only a confirmed reap of every unit is (``os_stop_proven``).
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, NoReturn

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution.domain.workflow.stage_inputs import StageMode

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from skm.kernel.ids import AttemptId, RunId, TaskId
    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.ids import StageRecordId, StepId
    from skm.modules.execution.domain.lease import ProcessIdentity

__all__ = [
    "ACTIVE_STAGE_STATES",
    "AGENT_STAGE_TYPES",
    "CONTROL_PLANE_STAGE_TYPES",
    "STAGE_TRANSITIONS",
    "TERMINAL_STAGE_STATES",
    "StageOutcomeKind",
    "StageRecord",
    "StageState",
    "active_stage",
    "begin_stage_record",
    "complete_stage",
    "control_plane_record",
    "fail_stage",
    "interrupt_stage",
    "mark_runtime_started",
    "os_stop_proven",
    "record_process_identity",
    "skipped_record",
]


class StageState(StrEnum):
    STARTED = "started"
    CONTEXT_DRAFT = "context_draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    SKIPPED = "skipped"


class StageOutcomeKind(StrEnum):
    SUCCESS = "success"
    CHECKS_FAILED = "checks_failed"
    CHECKS_ERROR = "checks_error"
    CHECKS_UNKNOWN = "checks_unknown"
    MANUAL_PENDING = "manual_pending"
    TREE_CHANGED = "tree_changed"
    VERDICT_GREEN = "verdict_green"
    VERDICT_ATTENTION = "verdict_attention"
    VERDICT_RED = "verdict_red"
    QUESTION = "question"
    BLOCKED = "blocked"
    WRITE_SCOPE_VIOLATION = "write_scope_violation"
    RESULT_INVALID = "result_invalid"
    RUNTIME_ERROR = "runtime_error"
    CONFLICT = "conflict"
    APPROVAL_REQUIRED = "approval_required"
    OUTCOME_UNKNOWN = "outcome_unknown"
    HELD = "held"
    ACCEPTED = "accepted"
    NOT_ACCEPTABLE = "not_acceptable"
    CANCELLED = "cancelled"


ACTIVE_STAGE_STATES: Final = frozenset({StageState.STARTED, StageState.CONTEXT_DRAFT, StageState.RUNNING})
TERMINAL_STAGE_STATES: Final = frozenset(
    {StageState.COMPLETED, StageState.FAILED, StageState.INTERRUPTED, StageState.SKIPPED}
)
AGENT_STAGE_TYPES: Final = frozenset({"agent_step", "agent_review", "advisor_consult"})
_BUILTIN_HOST_STAGE_TYPES: Final = frozenset({"prepare_environment", "run_checks", "integrate"})
CONTROL_PLANE_STAGE_TYPES: Final = frozenset(
    {"human_gate", "acceptance_gate", "phase_gate", "plan_acceptance"}
)

_S = StageState
# (source, target); None is "no record yet"
STAGE_TRANSITIONS: Final = frozenset(
    {
        (None, _S.STARTED),  # begin_stage, non-agent
        (None, _S.CONTEXT_DRAFT),  # begin_stage, agent (context draft created)
        (_S.CONTEXT_DRAFT, _S.RUNNING),  # renew_lease(runtime_started) after the final manifest, agent
        (_S.STARTED, _S.RUNNING),  # first heartbeat naming the stage record, non-agent
        *((source, _S.COMPLETED) for source in ACTIVE_STAGE_STATES),
        *((source, _S.FAILED) for source in ACTIVE_STAGE_STATES),
        *((source, _S.INTERRUPTED) for source in ACTIVE_STAGE_STATES),
        (None, _S.SKIPPED),  # advance skipped the stage (skip_when)
        (None, _S.COMPLETED),  # control-plane stage, created and closed by apply_action
    }
)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{2,63}")
_STAGE_ID = re.compile(r"[a-z][a-z0-9_]{0,31}")
_STAGE_TYPE = re.compile(r"[a-z][a-z0-9_]{0,40}")


@dataclass(frozen=True, slots=True)
class StageRecord:
    id: StageRecordId
    attempt_id: AttemptId
    run_id: RunId
    task_id: TaskId
    seq: int
    stage_id: str
    stage_type: str
    round_no: int
    mode: StageMode
    retry_of_id: StageRecordId | None
    state: StageState
    input_digest: str
    outcome_kind: StageOutcomeKind | None
    outcome: Mapping[str, JsonValue] | None
    error_code: str | None
    started_at: datetime
    finished_at: datetime | None
    fencing_token: int
    runtime_started_at: datetime | None
    process_identities: tuple[ProcessIdentity, ...]
    reused_from_step_id: StepId | None

    def __post_init__(self) -> None:
        problems: list[str] = []
        if not _STAGE_ID.fullmatch(self.stage_id) or not _STAGE_TYPE.fullmatch(self.stage_type):
            problems.append("stage_id/stage_type are lower snake identifiers")
        if self.seq < 1 or self.round_no < 1 or self.fencing_token < 0:
            problems.append("seq >= 1, round_no >= 1, fencing_token >= 0")
        if self.retry_of_id is not None and (self.mode is not StageMode.RETRY or self.retry_of_id == self.id):
            problems.append("retry_of_id names another record and needs mode retry")
        if (self.finished_at is not None) != (self.state in TERMINAL_STAGE_STATES):
            problems.append("finished_at is set exactly for a finished stage")
        if self.finished_at is not None and self.finished_at < self.started_at:
            problems.append("finished_at >= started_at")
        if self.state is StageState.COMPLETED and self.outcome_kind is None:
            problems.append("a completed stage has an outcome kind")
        if not _DIGEST.fullmatch(self.input_digest):
            problems.append("input_digest is sha256:<64 hex>")
        if self.error_code is not None and not _ERROR_CODE.fullmatch(self.error_code):
            problems.append("error_code is an UPPER_SNAKE code")
        if self.runtime_started_at is not None and self.runtime_started_at < self.started_at:
            problems.append("runtime_started_at >= started_at")
        if self.reused_from_step_id is not None and (
            self.stage_type != "agent_step"
            or self.state is not StageState.COMPLETED
            or self.fencing_token != 0
            or self.runtime_started_at is not None
        ):
            problems.append("a reused scout result is a completed agent_step without token or runtime start")
        keys = [identity.unit_key for identity in self.process_identities]
        if len(set(keys)) != len(keys):
            problems.append("process identities are keyed by unit")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "stage record invariants violated: " + "; ".join(problems),
                details={"stage_record_id": str(self.id), "violations": list(problems)},
            )


def active_stage(records: Sequence[StageRecord]) -> StageRecord | None:
    """The unfinished record of an attempt; more than one is a broken invariant."""
    active = [record for record in records if record.state in ACTIVE_STAGE_STATES]
    if len(active) > 1:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "an attempt has at most one unfinished stage",
            details={"stage_record_ids": [str(record.id) for record in active]},
        )
    return active[0] if active else None


def begin_stage_record(  # noqa: PLR0913
    existing: Sequence[StageRecord],
    *,
    record_id: StageRecordId,
    attempt_id: AttemptId,
    run_id: RunId,
    task_id: TaskId,
    stage_id: str,
    stage_type: str,
    round_no: int,
    mode: StageMode,
    input_digest: str,
    fencing_token: int,
    now: datetime,
    retry_of_id: StageRecordId | None = None,
    agent: bool | None = None,
) -> StageRecord:
    """``begin_stage``: a ``context_draft`` (agent) or ``started`` (other host) record.

    ``existing`` are the attempt's records. The same unfinished stage with the same input is returned as
    it is (idempotent replay); any other unfinished stage refuses the new one. ``agent`` is derived for the
    built-in types and must be given for a plugin stage type. Control-plane types use
    ``control_plane_record``.
    """
    if stage_type in CONTROL_PLANE_STAGE_TYPES:
        _refuse("a control-plane stage is recorded by control_plane_record", stage_type=stage_type)
    current = active_stage(existing)
    if current is not None:
        if (current.stage_id, current.round_no, current.input_digest) == (stage_id, round_no, input_digest):
            return current
        _refuse("another stage of the attempt is unfinished", stage_record_id=str(current.id))
    is_agent = _is_agent(stage_type, agent)
    return StageRecord(
        id=record_id,
        attempt_id=attempt_id,
        run_id=run_id,
        task_id=task_id,
        seq=_next_seq(existing),
        stage_id=stage_id,
        stage_type=stage_type,
        round_no=round_no,
        mode=mode,
        retry_of_id=retry_of_id,
        state=StageState.CONTEXT_DRAFT if is_agent else StageState.STARTED,
        input_digest=input_digest,
        outcome_kind=None,
        outcome=None,
        error_code=None,
        started_at=now,
        finished_at=None,
        fencing_token=fencing_token,
        runtime_started_at=None,
        process_identities=(),
        reused_from_step_id=None,
    )


def control_plane_record(  # noqa: PLR0913
    existing: Sequence[StageRecord],
    *,
    record_id: StageRecordId,
    attempt_id: AttemptId,
    run_id: RunId,
    task_id: TaskId,
    stage_id: str,
    stage_type: str,
    round_no: int,
    input_digest: str,
    outcome_kind: StageOutcomeKind,
    outcome: Mapping[str, JsonValue] | None,
    now: datetime,
) -> StageRecord:
    """A control-plane stage (``human_gate``, ``acceptance_gate``, ``phase_gate``, ``plan_acceptance``):
    created ``completed`` in the transaction of ``apply_action``, token 0."""
    if stage_type not in CONTROL_PLANE_STAGE_TYPES:
        _refuse("only control-plane stages complete without running", stage_type=stage_type)
    if active_stage(existing) is not None:
        _refuse("another stage of the attempt is unfinished")
    return _closed(
        existing,
        record_id,
        attempt_id,
        run_id,
        task_id,
        stage_id,
        stage_type,
        round_no,
        input_digest,
        now,
        state=StageState.COMPLETED,
        outcome_kind=outcome_kind,
        outcome=outcome,
    )


def skipped_record(  # noqa: PLR0913
    existing: Sequence[StageRecord],
    *,
    record_id: StageRecordId,
    attempt_id: AttemptId,
    run_id: RunId,
    task_id: TaskId,
    stage_id: str,
    stage_type: str,
    round_no: int,
    input_digest: str,
    now: datetime,
) -> StageRecord:
    """``advance`` skipped the stage (``skip_when``): a ``skipped`` record for the history."""
    if active_stage(existing) is not None:
        _refuse("another stage of the attempt is unfinished")
    return _closed(
        existing,
        record_id,
        attempt_id,
        run_id,
        task_id,
        stage_id,
        stage_type,
        round_no,
        input_digest,
        now,
        state=StageState.SKIPPED,
        outcome_kind=None,
        outcome=None,
    )


def mark_runtime_started(record: StageRecord, *, now: datetime) -> StageRecord:
    """``context_draft -> running`` (agent handoff) or ``started -> running`` (first non-agent heartbeat).

    Sets ``runtime_started_at``, the boundary of rule L and of budget settlement; repeating it is a no-op.
    A built-in type has one pre-runtime state; a plugin type keeps the one ``begin_stage_record`` chose
    from its declared ``agent`` flag, so both ``context_draft`` and ``started`` reach ``running``.
    """
    if record.state is StageState.RUNNING:
        return record
    if record.stage_type in AGENT_STAGE_TYPES:
        allowed = frozenset({StageState.CONTEXT_DRAFT})
    elif record.stage_type in _BUILTIN_HOST_STAGE_TYPES:
        allowed = frozenset({StageState.STARTED})
    else:
        allowed = frozenset({StageState.CONTEXT_DRAFT, StageState.STARTED})
    if record.state not in allowed:
        _refuse_change(record, StageState.RUNNING)
    return dataclasses.replace(record, state=StageState.RUNNING, runtime_started_at=now)


def complete_stage(
    record: StageRecord,
    *,
    outcome_kind: StageOutcomeKind,
    outcome: Mapping[str, JsonValue] | None,
    now: datetime,
) -> StageRecord:
    """``record_stage_result`` with any outcome but an infrastructure failure."""
    _require_active(record, StageState.COMPLETED)
    return dataclasses.replace(
        record,
        state=StageState.COMPLETED,
        outcome_kind=StageOutcomeKind(outcome_kind),
        outcome=outcome,
        finished_at=now,
    )


def fail_stage(
    record: StageRecord, *, error_code: str, now: datetime, outcome_kind: StageOutcomeKind | None = None
) -> StageRecord:
    """``result_invalid``/``runtime_error``, ``report_attempt_failure``, timeouts and recovery."""
    _require_active(record, StageState.FAILED)
    return dataclasses.replace(
        record, state=StageState.FAILED, error_code=error_code, outcome_kind=outcome_kind, finished_at=now
    )


def interrupt_stage(record: StageRecord, *, now: datetime) -> StageRecord:
    """``expire_leases`` found the stage unfinished. ``runtime_started_at`` still tells L1 from L2."""
    _require_active(record, StageState.INTERRUPTED)
    return dataclasses.replace(record, state=StageState.INTERRUPTED, error_code="LEASE_LOST", finished_at=now)


def record_process_identity(record: StageRecord, identity: ProcessIdentity) -> StageRecord:
    """Keep the observed identity of one unit of the stage; the first identity of a unit is kept.

    The record may already be finished: identities of processes observed late are still durable facts
    for a later reap. A different identity for an already known unit is refused.
    """
    key = identity.unit_key
    for known in record.process_identities:
        if known.unit_key == key:
            if known == identity:
                return record
            _refuse("a unit of the stage already has another process identity", unit=f"{key[0]}:{key[1]}")
    return dataclasses.replace(record, process_identities=(*record.process_identities, identity))


def os_stop_proven(
    record: StageRecord, *, confirmed_units: frozenset[tuple[str, str]], host_markers_confirmed: bool
) -> bool:
    """Whether every process of the stage is proven stopped (rule L2 reap).

    Needs the host's confirmation that the durable markers of the stage hold no live containment and a
    confirmed empty containment for every recorded unit. The record state is not evidence: an
    ``interrupted``/``failed``/``completed`` record or a cancelled step proves nothing about the OS.
    """
    if not host_markers_confirmed:
        return False
    return all(identity.unit_key in confirmed_units for identity in record.process_identities)


def _closed(  # noqa: PLR0913
    existing: Sequence[StageRecord],
    record_id: StageRecordId,
    attempt_id: AttemptId,
    run_id: RunId,
    task_id: TaskId,
    stage_id: str,
    stage_type: str,
    round_no: int,
    input_digest: str,
    now: datetime,
    *,
    state: StageState,
    outcome_kind: StageOutcomeKind | None,
    outcome: Mapping[str, JsonValue] | None,
) -> StageRecord:
    return StageRecord(
        id=record_id,
        attempt_id=attempt_id,
        run_id=run_id,
        task_id=task_id,
        seq=_next_seq(existing),
        stage_id=stage_id,
        stage_type=stage_type,
        round_no=round_no,
        mode=StageMode.NORMAL,
        retry_of_id=None,
        state=state,
        input_digest=input_digest,
        outcome_kind=outcome_kind,
        outcome=outcome,
        error_code=None,
        started_at=now,
        finished_at=now,
        fencing_token=0,
        runtime_started_at=None,
        process_identities=(),
        reused_from_step_id=None,
    )


def _is_agent(stage_type: str, agent: bool | None) -> bool:
    if stage_type in AGENT_STAGE_TYPES:
        return True
    if stage_type in _BUILTIN_HOST_STAGE_TYPES:
        return False
    if agent is None:
        _refuse("a plugin stage type states whether it runs an agent", stage_type=stage_type)
    return agent


def _next_seq(existing: Sequence[StageRecord]) -> int:
    return max((record.seq for record in existing), default=0) + 1


def _require_active(record: StageRecord, to: StageState) -> None:
    if record.state not in ACTIVE_STAGE_STATES:
        _refuse_change(record, to)


def _refuse_change(record: StageRecord, to: StageState) -> NoReturn:
    raise error_for(
        ErrorCode.INVALID_TRANSITION,
        f"stage record cannot go from {record.state} to {to}",
        details={"stage_record_id": str(record.id), "from": record.state.value, "to": to.value},
    )


def _refuse(message: str, **details: str) -> NoReturn:
    raise error_for(ErrorCode.INVALID_TRANSITION, message, details=dict(details))
