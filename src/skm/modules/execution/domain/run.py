"""Run aggregate and its state machine (execution §4.1, §4.1.1).

Pure transitions: each function returns a new ``Run`` with ``row_version + 1`` or raises. Every change is
one rule of ``RUN_TRANSITIONS``; any other change is ``INVALID_TRANSITION`` and a change of a terminal run
is ``RUN_NOT_ACTIVE``. Repeating a command whose state is already reached (pause of a paused run, resume
of a running one) returns the run unchanged and records no event. Budget, live policy and task
aggregation preconditions belong to the caller; the run never follows a newer revision.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution.domain.events import ExecutionEvent

if TYPE_CHECKING:
    from skm.kernel.ids import (
        FileVersionId,
        PlanId,
        PrincipalId,
        ProjectId,
        ResourceVersionId,
        RevisionId,
        RunId,
        WorkspaceId,
    )
    from skm.modules.execution.domain.ids import ReadinessReportId, ReviewRequestId
    from skm.modules.execution.domain.review_grouping import ReviewGrouping

__all__ = [
    "RUN_TRANSITIONS",
    "TERMINAL_RUN_STATUSES",
    "PauseSource",
    "Run",
    "RunKind",
    "RunStatus",
    "RunTransition",
    "cancel",
    "clear_unmetered",
    "finish",
    "mark_ready",
    "mark_unmetered",
    "pause",
    "resume",
    "run_rule",
    "start",
    "wait",
    "wake",
]

type PauseSource = Literal["system", "owner"]


class RunKind(StrEnum):
    PLAN = "plan"
    ADHOC = "adhoc"
    REVIEW_REQUEST = "review_request"
    READINESS_AUDIT = "readiness_audit"


class RunStatus(StrEnum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_RUN_STATUSES: Final = frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED})
_NOT_STARTED: Final = frozenset({RunStatus.CREATED, RunStatus.READY})
_STOP_CODE_STATUSES: Final = frozenset({RunStatus.WAITING, RunStatus.PAUSED, RunStatus.FAILED})


@dataclass(frozen=True, slots=True)
class RunTransition:
    rule_id: str
    sources: frozenset[RunStatus]
    target: RunStatus
    event: ExecutionEvent | None


_S = RunStatus
_NONTERMINAL: Final = frozenset(RunStatus) - TERMINAL_RUN_STATUSES

RUN_TRANSITIONS: Final[tuple[RunTransition, ...]] = (
    RunTransition("R1", frozenset(), _S.CREATED, ExecutionEvent.RUN_CREATED),
    RunTransition("R2", frozenset({_S.CREATED}), _S.READY, None),
    RunTransition("R3", frozenset({_S.READY}), _S.RUNNING, ExecutionEvent.RUN_STARTED),
    RunTransition("R4", frozenset({_S.RUNNING}), _S.WAITING, ExecutionEvent.RUN_WAITING),
    RunTransition("R5", frozenset({_S.WAITING}), _S.RUNNING, ExecutionEvent.RUN_RESUMED),
    RunTransition("R6", frozenset({_S.RUNNING, _S.WAITING}), _S.PAUSED, ExecutionEvent.RUN_PAUSED),
    RunTransition("R7", frozenset({_S.PAUSED}), _S.RUNNING, ExecutionEvent.RUN_RESUMED),
    RunTransition("R8", frozenset({_S.RUNNING}), _S.SUCCEEDED, ExecutionEvent.RUN_FINISHED),
    RunTransition("R9", frozenset({_S.RUNNING, _S.WAITING}), _S.FAILED, ExecutionEvent.RUN_FINISHED),
    RunTransition("R10", _NONTERMINAL, _S.CANCELLED, ExecutionEvent.RUN_CANCELLED),
)
_BY_ID: Final = {rule.rule_id: rule for rule in RUN_TRANSITIONS}


@dataclass(frozen=True, slots=True)
class Run:
    id: RunId
    workspace_id: WorkspaceId
    project_id: ProjectId
    kind: RunKind
    plan_id: PlanId | None
    revision_id: RevisionId | None
    revision_no: int | None
    status: RunStatus
    requested_by: PrincipalId
    readiness_report_id: ReadinessReportId | None
    audited_report_id: ReadinessReportId | None
    review_request_id: ReviewRequestId | None
    compiler_version: int
    workflow_resource_version_id: ResourceVersionId
    review_grouping: ReviewGrouping
    autopilot: bool
    queued: bool
    pause_reason: str | None
    pause_source: PauseSource | None
    stop_code: str | None
    unmetered_at: datetime | None
    row_version: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    inline_spec_file_version_id: FileVersionId | None = None

    def __post_init__(self) -> None:
        problems = self._spec_problems()
        if self.row_version < 1:
            problems.append("row_version >= 1")
        if (self.kind is RunKind.REVIEW_REQUEST) != (self.review_request_id is not None):
            problems.append("kind = review_request <=> review_request_id is set")
        if (self.kind is RunKind.READINESS_AUDIT) != (self.audited_report_id is not None):
            problems.append("kind = readiness_audit <=> audited_report_id is set")
        if (self.status in TERMINAL_RUN_STATUSES) != (self.finished_at is not None):
            problems.append("terminal status <=> finished_at is set")
        if (self.status not in _NOT_STARTED) != (self.started_at is not None):
            problems.append("started_at is set <=> status not in {created, ready}")
        if (self.status is RunStatus.PAUSED) != (self.pause_source is not None):
            problems.append("status = paused <=> pause_source is set")
        if self.pause_reason is not None and self.status is not RunStatus.PAUSED:
            problems.append("pause_reason only while paused")
        if self.stop_code is not None and self.status not in _STOP_CODE_STATUSES:
            problems.append("stop_code only in waiting, paused or failed")
        if (
            self.finished_at is not None
            and self.started_at is not None
            and self.finished_at < self.started_at
        ):
            problems.append("finished_at >= started_at")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "run invariants violated: " + "; ".join(problems),
                details={"run_id": str(self.id), "violations": list(problems)},
            )

    def _spec_problems(self) -> list[str]:
        problems: list[str] = []
        if self.kind is RunKind.ADHOC:
            if self.plan_id is not None or self.revision_id is not None or self.revision_no is not None:
                problems.append("adhoc run has no plan or revision")
            if self.inline_spec_file_version_id is None:
                problems.append("adhoc run requires an inline spec file version")
            if self.readiness_report_id is not None:
                problems.append("adhoc run has no readiness report")
        else:
            if (
                self.plan_id is None
                or self.revision_id is None
                or self.revision_no is None
                or self.revision_no < 1
            ):
                problems.append("revision-backed run requires a plan and revision with revision_no >= 1")
            if self.inline_spec_file_version_id is not None:
                problems.append("revision-backed run has no inline spec")
        return problems

    def require_revision(self) -> RevisionId:
        if self.revision_id is None:
            raise error_for(ErrorCode.INVALID_TRANSITION, "operation requires a revision-backed run")
        return self.revision_id

    def require_plan(self) -> PlanId:
        if self.plan_id is None:
            raise error_for(ErrorCode.INVALID_TRANSITION, "operation requires a revision-backed run")
        return self.plan_id


def run_rule(source: RunStatus, target: RunStatus) -> RunTransition:
    """The rule of ``RUN_TRANSITIONS`` for ``source -> target``; otherwise the error a command reports."""
    for rule in RUN_TRANSITIONS:
        if source in rule.sources and rule.target is target:
            return rule
    code = ErrorCode.RUN_NOT_ACTIVE if source in TERMINAL_RUN_STATUSES else ErrorCode.INVALID_TRANSITION
    raise error_for(
        code,
        f"run cannot go from {source} to {target}",
        details={"from": source.value, "to": target.value},
    )


def mark_ready(run: Run) -> Run:
    """R2: tasks compiled and the bundle stored (``start_run`` step 7)."""
    return _apply(run, "R2")


def start(run: Run, *, now: datetime) -> Run:
    """R3: the first task becomes ready (``start_run`` step 9); a queued run stops being queued."""
    return _apply(run, "R3", started_at=now, queued=False)


def wait(run: Run, *, stop_code: str | None = None) -> Run:
    """R4: nothing can move and some task waits with a ``WAITING_*`` reason."""
    return _apply(run, "R4", stop_code=stop_code)


def wake(run: Run) -> Run:
    """R5: an answer, verdict, approval or timer unblocked a task; the current stop code is cleared.

    The previous code goes into the ``RunResumed`` payload, taken from the run passed in.
    """
    return _apply(run, "R5", stop_code=None)


def pause(run: Run, *, reason: str, source: PauseSource, stop_code: str | None = None) -> Run:
    """R6. An owner pause carries no stop code; a system pause (budget, breaker, kill switch…) needs one.

    Pausing a paused run is a no-op that keeps the first pause.
    """
    if source == "owner" and stop_code is not None:
        raise error_for(
            ErrorCode.SCHEMA_INVALID, "an owner pause has no stop code", details={"field": "stop_code"}
        )
    if source == "system" and stop_code is None:
        raise error_for(
            ErrorCode.SCHEMA_INVALID, "a system pause names its stop code", details={"field": "stop_code"}
        )
    if run.status is RunStatus.PAUSED:
        return run
    return _apply(run, "R6", pause_reason=reason, pause_source=source, stop_code=stop_code)


def resume(run: Run) -> Run:
    """R7: clears ``stop_code``, ``pause_source`` and ``pause_reason``; resuming a running run is a no-op.

    ``unmetered_at`` stays: only the owner's answer to the unmetered budget escalation clears it.
    """
    if run.status is RunStatus.RUNNING:
        return run
    return _apply(run, "R7", stop_code=None, pause_source=None, pause_reason=None)


def finish(
    run: Run,
    *,
    outcome: Literal[RunStatus.SUCCEEDED, RunStatus.FAILED],
    now: datetime,
    stop_code: str | None = None,
) -> Run:
    """R8 (all tasks accepted or skipped) or R9 (nothing can progress); a success has no stop code."""
    if outcome is RunStatus.SUCCEEDED:
        if stop_code is not None:
            raise error_for(
                ErrorCode.SCHEMA_INVALID, "a succeeded run has no stop code", details={"field": "stop_code"}
            )
        return _apply(run, "R8", finished_at=now, stop_code=None, queued=False)
    return _apply(run, "R9", finished_at=now, stop_code=stop_code, queued=False)


def cancel(run: Run, *, now: datetime) -> Run:
    """R10 from any non-terminal status; the current stop code and pause state are cleared."""
    started = run.started_at if run.started_at is not None else now
    return _apply(
        run,
        "R10",
        finished_at=now,
        started_at=started,
        stop_code=None,
        pause_source=None,
        pause_reason=None,
        queued=False,
    )


def mark_unmetered(run: Run, *, now: datetime) -> Run:
    """Settle with unknown usage under ``unknown_usage_policy = block`` (§5.6): every later reserve fails.

    The first mark is kept.
    """
    if run.status in TERMINAL_RUN_STATUSES:
        run_rule(run.status, run.status)
    if run.unmetered_at is not None:
        return run
    return dataclasses.replace(run, unmetered_at=now, row_version=run.row_version + 1)


def clear_unmetered(run: Run) -> Run:
    """The owner answered ``BLOCKED_BY_BUDGET{reason=unmetered}`` with ``resume_run``/``raise_budget``."""
    if run.unmetered_at is None:
        return run
    return dataclasses.replace(run, unmetered_at=None, row_version=run.row_version + 1)


def _apply(run: Run, rule_id: str, **changes: object) -> Run:
    rule = _BY_ID[rule_id]
    if run.status not in rule.sources:
        found = run_rule(run.status, rule.target)
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            f"{run.status} -> {rule.target} is {found.rule_id}, not {rule_id}",
            details={"from": run.status.value, "to": rule.target.value, "rule": rule_id},
        )
    return dataclasses.replace(run, status=rule.target, row_version=run.row_version + 1, **changes)
