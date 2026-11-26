"""Task aggregate and its state machine (execution §4.4, §4.4.1).

``TASK_TRANSITIONS`` is the complete table T1-T31: a status change that no row allows is
``INVALID_TRANSITION`` and a change of a terminal task is ``INVALID_TRANSITION`` too. Each change names
its rule, so the caller records the event of that rule. The status never replaces the history of
attempts, outputs and acceptance: ``accept`` binds the accepted attempt and its own output once, and a
carried-forward acceptance (T31) binds neither.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution.domain.attempt import acceptable
from skm.modules.execution.domain.blocking_reason import BLOCKING_CATALOG
from skm.modules.execution.domain.events import ExecutionEvent

if TYPE_CHECKING:
    from skm.kernel.ids import AttemptId, EntityId, HostId, RunId, TaskId, WorkspaceId
    from skm.modules.execution.domain.attempt import Attempt
    from skm.modules.execution.domain.blocking_reason import BlockingReason
    from skm.modules.execution.domain.carry_forward import CarryForward
    from skm.modules.execution.domain.ids import FindingId, OutputId
    from skm.modules.execution.domain.output import Output

__all__ = [
    "BLOCKING_STATUSES",
    "GATE_KINDS",
    "TASK_TRANSITIONS",
    "TERMINAL_TASK_STATUSES",
    "WORK_KINDS",
    "PathPattern",
    "ReviewMode",
    "Task",
    "TaskKind",
    "TaskOrigin",
    "TaskStatus",
    "TaskTransition",
    "accept",
    "accept_carried_forward",
    "task_rules",
    "transition",
]


class TaskKind(StrEnum):
    ADHOC = "adhoc"
    UNIT = "unit"
    ITEM = "item"
    ITEM_GATE = "item_gate"
    PHASE_GATE = "phase_gate"
    INTEGRATION = "integration"
    FOLLOWUP = "followup"
    GROUP_REVIEW = "group_review"
    PLAN_ACCEPTANCE = "plan_acceptance"
    PLAN_AUDIT = "plan_audit"


class TaskStatus(StrEnum):
    BLOCKED = "blocked"
    READY = "ready"
    ASSIGNED = "assigned"
    EXECUTING = "executing"
    CHECKING = "checking"
    MANUAL_PENDING = "manual_pending"
    REVIEWING = "reviewing"
    REWORK_REQUIRED = "rework_required"
    AWAITING_DECISION = "awaiting_decision"
    INTEGRATING = "integrating"
    ACCEPTED = "accepted"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    SKIPPED = "skipped"


class ReviewMode(StrEnum):
    REQUIRED = "required"
    SELF = "self"
    WAIVED = "waived"


@dataclass(frozen=True, slots=True)
class TaskOrigin:
    source_task_id: TaskId | None
    finding_ids: tuple[FindingId, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class PathPattern:
    mount: str
    pattern: str


TERMINAL_TASK_STATUSES: Final = frozenset(
    {TaskStatus.ACCEPTED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.SUPERSEDED, TaskStatus.SKIPPED}
)
# statuses that exist only because of a wait: the reason must be stated
BLOCKING_STATUSES: Final = frozenset(
    {TaskStatus.BLOCKED, TaskStatus.MANUAL_PENDING, TaskStatus.AWAITING_DECISION}
)
_NO_REASON: Final = frozenset(
    {TaskStatus.ACCEPTED, TaskStatus.CANCELLED, TaskStatus.SUPERSEDED, TaskStatus.SKIPPED}
)
_SYNTHETIC_WITH_ORIGIN: Final = frozenset({TaskKind.INTEGRATION, TaskKind.FOLLOWUP, TaskKind.GROUP_REVIEW})


@dataclass(frozen=True, slots=True)
class Task:
    id: TaskId
    run_id: RunId
    workspace_id: WorkspaceId
    kind: TaskKind
    spec_entity_id: EntityId | None
    display_key: str
    origin: TaskOrigin | None
    position: int
    status: TaskStatus
    work_kind: str
    review_mode: ReviewMode
    review_profile: str | None
    declared_write_scope: tuple[PathPattern, ...] | None
    required_host_id: HostId | None
    current_attempt_id: AttemptId | None
    accepted_attempt_id: AttemptId | None
    accepted_output_id: OutputId | None
    check_fix_rounds: int
    review_rounds: int
    attempt_count: int
    blocking_reason: BlockingReason | None
    row_version: int

    @property
    def granted_write_scope(self) -> tuple[PathPattern, ...]:
        """Paths the task may write. An undeclared (``None``) scope grants no writes, like an empty one."""
        return self.declared_write_scope or ()

    def __post_init__(self) -> None:
        problems: list[str] = []
        spec_backed = self.kind in {TaskKind.UNIT, TaskKind.ITEM, TaskKind.ITEM_GATE, TaskKind.PHASE_GATE}
        if spec_backed != (self.spec_entity_id is not None):
            problems.append("spec_entity_id is set exactly for unit, item, item_gate and phase_gate")
        adhoc_key = (
            re.fullmatch(r"ADHOC-[0-9]+", self.display_key) is not None
            if self.kind is TaskKind.ADHOC
            else not self.display_key.startswith("ADHOC-")
        )
        if not adhoc_key:
            problems.append("only adhoc tasks use a key of the form ADHOC-<number>")
        if (self.kind in _SYNTHETIC_WITH_ORIGIN) != (self.origin is not None):
            problems.append("origin is set exactly for integration, followup and group_review")
        if min(self.position, self.check_fix_rounds, self.review_rounds, self.attempt_count) < 0:
            problems.append("position and counters are >= 0")
        if self.row_version < 1:
            problems.append("row_version >= 1")
        if self.accepted_output_id is not None and self.accepted_attempt_id is None:
            problems.append("an accepted output belongs to the accepted attempt")
        if self.accepted_attempt_id is not None and self.status is not TaskStatus.ACCEPTED:
            problems.append("accepted_attempt_id only on an accepted task")
        if self.kind in GATE_KINDS and self.declared_write_scope != ():
            problems.append("gate tasks declare an empty write scope")
        reason = self.blocking_reason
        if reason is not None:
            if reason.task_id != self.id:
                problems.append("blocking_reason belongs to this task")
            if self.status in _NO_REASON:
                problems.append(f"a {self.status} task has no blocking reason")
            elif (
                self.status is not TaskStatus.FAILED
                and self.status not in BLOCKING_CATALOG[reason.code].task_statuses
            ):
                problems.append(f"{reason.code} is not a reason of a {self.status} task")
        elif self.status in BLOCKING_STATUSES:
            problems.append(f"a {self.status} task states its blocking reason")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "task invariants violated: " + "; ".join(problems),
                details={"task_id": str(self.id), "violations": list(problems)},
            )


WORK_KINDS = frozenset(
    (TaskKind.ADHOC, TaskKind.UNIT, TaskKind.ITEM, TaskKind.INTEGRATION, TaskKind.FOLLOWUP)
)
GATE_KINDS = frozenset(TaskKind) - WORK_KINDS


@dataclass(frozen=True, slots=True)
class TaskTransition:
    rule_id: str
    sources: frozenset[TaskStatus]
    targets: frozenset[TaskStatus]
    events: tuple[ExecutionEvent, ...]


_T = TaskStatus
_E = ExecutionEvent
_NONTERMINAL: Final = frozenset(TaskStatus) - TERMINAL_TASK_STATUSES


def _rule(
    rule_id: str,
    sources: TaskStatus | frozenset[TaskStatus],
    targets: TaskStatus | frozenset[TaskStatus],
    *events: ExecutionEvent,
) -> TaskTransition:
    def _set(value: TaskStatus | frozenset[TaskStatus]) -> frozenset[TaskStatus]:
        return value if isinstance(value, frozenset) else frozenset({value})

    return TaskTransition(rule_id, _set(sources), _set(targets), events)


TASK_TRANSITIONS: Final[tuple[TaskTransition, ...]] = (
    _rule("T1", _T.BLOCKED, _T.READY, _E.TASK_READY),
    _rule("T1m", _T.READY, _T.BLOCKED, _E.TASK_WAIT_CHANGED),
    _rule("T2", _T.READY, _T.ASSIGNED, _E.TASK_ASSIGNED),
    _rule("T3", _T.ASSIGNED, _T.EXECUTING, _E.ATTEMPT_STARTED),
    # LeaseExpired on expiry; TaskReady{reason=pause} when a pause released the pre-stage assignment
    _rule("T4", _T.ASSIGNED, _T.READY, _E.LEASE_EXPIRED, _E.TASK_READY),
    _rule("T5", _T.EXECUTING, _T.CHECKING),
    _rule("T6", _T.EXECUTING, _T.EXECUTING, _E.STAGE_COMPLETED),
    _rule("T7", _T.CHECKING, _T.MANUAL_PENDING, _E.DECISION_REQUESTED),
    _rule("T8", _T.CHECKING, _T.REWORK_REQUIRED, _E.TASK_REWORK_REQUIRED),
    _rule("T9", _T.CHECKING, _T.REVIEWING),
    _rule("T9f", _T.REVIEWING, _T.CHECKING),
    _rule("T10", _T.CHECKING, _T.INTEGRATING, _E.ACCEPTANCE_DECIDED),
    _rule(
        "T11",
        _T.MANUAL_PENDING,
        frozenset({_T.REVIEWING, _T.INTEGRATING, _T.REWORK_REQUIRED}),
        _E.MANUAL_VERDICT_RECORDED,
    ),
    _rule("T12", _T.REVIEWING, _T.REWORK_REQUIRED, _E.TASK_REWORK_REQUIRED),
    _rule("T13", _T.REVIEWING, _T.INTEGRATING, _E.ACCEPTANCE_DECIDED),
    _rule("T14", _T.REVIEWING, _T.AWAITING_DECISION, _E.DECISION_REQUESTED),
    _rule("T15", _T.REWORK_REQUIRED, _T.EXECUTING),
    _rule("T16", _T.REWORK_REQUIRED, _T.READY, _E.ATTEMPT_OWNERSHIP_LOST),
    _rule(
        "T17",
        _NONTERMINAL - {_T.BLOCKED, _T.AWAITING_DECISION},
        _T.AWAITING_DECISION,
        _E.DECISION_REQUESTED,
    ),
    _rule(
        "T18",
        _T.AWAITING_DECISION,
        frozenset({_T.EXECUTING, _T.READY, _T.FAILED, _T.SKIPPED}),
        _E.DECISION_ANSWERED,
    ),
    _rule("T19", _T.INTEGRATING, _T.ACCEPTED, _E.INTEGRATION_COMPLETED, _E.TASK_ACCEPTED),
    _rule("T20", _T.INTEGRATING, _T.INTEGRATING, _E.STAGE_COMPLETED, _E.INTEGRATION_COMPLETED),
    _rule("T21", _T.INTEGRATING, _T.ACCEPTED, _E.INTEGRATION_COMPLETED, _E.TASK_ACCEPTED),
    _rule(
        "T22",
        frozenset({_T.EXECUTING, _T.CHECKING, _T.REVIEWING, _T.REWORK_REQUIRED}),
        _T.READY,
        _E.ATTEMPT_OWNERSHIP_LOST,
    ),
    # L3 handoff: the current attempt lost ownership; no new attempt, charge or admission yet
    _rule("T22a", _NONTERMINAL - {_T.READY}, _T.READY, _E.ATTEMPT_OWNERSHIP_LOST, _E.TASK_READY),
    _rule("T23", _NONTERMINAL, _T.FAILED, _E.TASK_FAILED),
    _rule("T24", _NONTERMINAL, _T.CANCELLED),
    _rule("T25", frozenset({_T.BLOCKED, _T.READY, _T.AWAITING_DECISION}), _T.SKIPPED, _E.TASK_SKIPPED),
    _rule(
        "T27",
        frozenset({_T.REWORK_REQUIRED, _T.CHECKING, _T.REVIEWING}),
        _T.AWAITING_DECISION,
        _E.DECISION_REQUESTED,
    ),
    _rule("T28", frozenset({_T.CHECKING, _T.REVIEWING, _T.INTEGRATING}), _T.BLOCKED, _E.FOLLOWUPS_CREATED),
    _rule("T29", _T.BLOCKED, _T.READY, _E.TASK_READY),
    _rule(
        "T30",
        frozenset({_T.READY, _T.ASSIGNED, _T.INTEGRATING}),
        _T.AWAITING_DECISION,
        _E.DECISION_REQUESTED,
    ),
    _rule("T31", frozenset({_T.ASSIGNED, _T.EXECUTING}), _T.ACCEPTED, _E.TASK_ACCEPTED),
)
_BY_ID: Final = {rule.rule_id: rule for rule in TASK_TRANSITIONS}
# rules that end in ``accepted`` go through ``accept``/``accept_carried_forward``
_ACCEPT_RULES: Final = frozenset({"T19", "T21"})


def task_rules(source: TaskStatus, target: TaskStatus) -> tuple[TaskTransition, ...]:
    """Every rule that allows ``source -> target`` (empty when the change is invalid)."""
    return tuple(rule for rule in TASK_TRANSITIONS if source in rule.sources and target in rule.targets)


def transition(
    task: Task,
    to: TaskStatus,
    *,
    rule: str,
    blocking: BlockingReason | None = None,
) -> Task:
    """Apply rule ``rule`` (``"T1"`` …) moving ``task`` to ``to``.

    ``blocking`` is the reason of the new status: required for ``blocked``, ``manual_pending`` and
    ``awaiting_decision``, optional for the waits inside working statuses, refused for the terminal
    statuses. Entering ``accepted`` needs ``accept``/``accept_carried_forward`` so the accepted attempt
    and output are bound with it.
    """
    to = TaskStatus(to)
    found = _BY_ID.get(rule)
    if found is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, f"unknown task rule {rule}", details={"rule": rule})
    if to is TaskStatus.ACCEPTED:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "a task becomes accepted only through accept() or accept_carried_forward()",
            details={"rule": rule, "task_id": str(task.id)},
        )
    _check_rule(task, to, found)
    return dataclasses.replace(task, status=to, blocking_reason=blocking, row_version=task.row_version + 1)


def accept(task: Task, *, rule: str, attempt: Attempt | None, output: Output | None) -> Task:
    """T19/T21: the task becomes terminal ``accepted`` and records ``TaskAccepted`` (K3).

    The attempt is the task's own current attempt, never one that lost ownership or was abandoned (A1);
    the output is exactly the attempt's current output (A2, ``OUTPUT_NOT_CURRENT``): neither an earlier
    output of the attempt nor ``None`` while the attempt has one. A gate accepted without changes may have
    no output. An accepted output is never replaced: a terminal task cannot be accepted again.
    """
    found = _BY_ID.get(rule)
    if found is None or rule not in _ACCEPT_RULES:
        raise error_for(
            ErrorCode.INVALID_TRANSITION, f"{rule} does not accept a task", details={"rule": rule}
        )
    _check_rule(task, TaskStatus.ACCEPTED, found)
    if attempt is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "an integrated task is accepted with its attempt")
    if attempt.task_id != task.id or attempt.id != task.current_attempt_id:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "only the task's current attempt can be accepted",
            details={"task_id": str(task.id), "attempt_id": str(attempt.id)},
        )
    if not acceptable(attempt):
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            f"an attempt in state {attempt.state} is never accepted",
            details={"attempt_id": str(attempt.id), "state": attempt.state.value},
        )
    if output is not None and (output.attempt_id != attempt.id or output.task_id != task.id):
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "the accepted output belongs to the accepted attempt",
            details={"output_id": str(output.id), "attempt_id": str(attempt.id)},
        )
    output_id = None if output is None else output.id
    if output_id != attempt.current_output_id:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "the accepted output is the attempt's current output",
            details={
                "reason": "OUTPUT_NOT_CURRENT",
                "attempt_id": str(attempt.id),
                "output_id": None if output_id is None else str(output_id),
                "current_output_id": None
                if attempt.current_output_id is None
                else str(attempt.current_output_id),
            },
        )
    return dataclasses.replace(
        task,
        status=TaskStatus.ACCEPTED,
        accepted_attempt_id=attempt.id,
        accepted_output_id=None if output is None else output.id,
        blocking_reason=None,
        row_version=task.row_version + 1,
    )


def accept_carried_forward(task: Task, carry: CarryForward) -> Task:
    """T31: an accepted carry-forward decision for this task; no attempt or output of this run is bound.

    The source task and its acceptance stay historical facts of the source run.
    """
    _check_rule(task, TaskStatus.ACCEPTED, _BY_ID["T31"])
    if carry.target_task_id != task.id or carry.target_run_id != task.run_id or carry.decision != "accepted":
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "carry-forward accepts only its own target task with an accepted decision",
            details={"task_id": str(task.id), "carry_forward_id": str(carry.id)},
        )
    return dataclasses.replace(
        task,
        status=TaskStatus.ACCEPTED,
        accepted_attempt_id=None,
        accepted_output_id=None,
        blocking_reason=None,
        row_version=task.row_version + 1,
    )


def _check_rule(task: Task, to: TaskStatus, rule: TaskTransition) -> None:
    if task.status not in rule.sources or to not in rule.targets:
        allowed = [found.rule_id for found in task_rules(task.status, to)]
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            f"task cannot go from {task.status} to {to} by {rule.rule_id}",
            details={
                "task_id": str(task.id),
                "from": task.status.value,
                "to": to.value,
                "rule": rule.rule_id,
                "allowed_rules": list(allowed),
            },
        )
