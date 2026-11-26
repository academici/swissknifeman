"""Task state machine T1-T31 (execution §4.4.1)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from itertools import product
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.attempt import (
    Attempt,
    AttemptEndReason,
    AttemptState,
    ContinuationCause,
    DeferredTrigger,
    SelectedStage,
    select_stage,
    transition_attempt,
)
from skm.modules.execution.domain.blocking_reason import BlockingCode, BlockingReason, blocking_reason
from skm.modules.execution.domain.carry_forward import CarryForward
from skm.modules.execution.domain.events import ExecutionEvent
from skm.modules.execution.domain.output import (
    DiffStats,
    Output,
    OutputManifest,
    OutputMount,
    OutputSource,
    manifest_digest,
)
from skm.modules.execution.domain.task import (
    BLOCKING_STATUSES,
    TASK_TRANSITIONS,
    TERMINAL_TASK_STATUSES,
    ReviewMode,
    Task,
    TaskKind,
    TaskStatus,
    accept,
    accept_carried_forward,
    task_rules,
    transition,
)
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
TASK_ID: Any = UUID(int=100)
ATTEMPT_ID: Any = UUID(int=200)
ID = str(UUID(int=999))


def uid(n: int) -> Any:
    return UUID(int=n)


REASONS: dict[TaskStatus, tuple[BlockingCode, dict[str, Any]]] = {
    TaskStatus.BLOCKED: (BlockingCode.BLOCKED_BY_DEPENDENCY, {"prerequisite_task_ids": [ID]}),
    TaskStatus.MANUAL_PENDING: (
        BlockingCode.WAITING_MANUAL_CHECK,
        {"check_execution_id": ID, "check_key": "P1.1:V1"},
    ),
    TaskStatus.AWAITING_DECISION: (
        BlockingCode.WAITING_OWNER,
        {"decision_request_id": ID, "stop_code": "NOT_ACCEPTABLE"},
    ),
}


def reason_for(status: TaskStatus, task_id: Any = TASK_ID) -> BlockingReason | None:
    if status not in REASONS:
        return None
    code, refs = REASONS[status]
    return blocking_reason(code, task_id=task_id, refs=refs, now=NOW, message=f"{status}")


def make_task(status: TaskStatus = TaskStatus.BLOCKED, **changes: Any) -> Task:
    values: dict[str, Any] = {
        "id": TASK_ID,
        "run_id": uid(1),
        "workspace_id": uid(2),
        "kind": TaskKind.UNIT,
        "spec_entity_id": uid(3),
        "display_key": "P1.1/U1",
        "origin": None,
        "position": 0,
        "status": status,
        "work_kind": "code",
        "review_mode": ReviewMode.SELF,
        "review_profile": None,
        "declared_write_scope": None,
        "required_host_id": None,
        "current_attempt_id": ATTEMPT_ID,
        "accepted_attempt_id": None,
        "accepted_output_id": None,
        "check_fix_rounds": 0,
        "review_rounds": 0,
        "attempt_count": 1,
        "blocking_reason": reason_for(status),
        "row_version": 1,
    }
    values.update(changes)
    return Task(**values)


def make_attempt(state: AttemptState = AttemptState.SUBMITTED, **changes: Any) -> Attempt:
    terminal = state in {AttemptState.COMPLETED, AttemptState.OWNERSHIP_LOST, AttemptState.ABANDONED}
    values: dict[str, Any] = {
        "id": ATTEMPT_ID,
        "run_id": uid(1),
        "task_id": TASK_ID,
        "workspace_id": uid(2),
        "attempt_no": 1,
        "state": state,
        "worker_id": uid(4),
        "host_id": uid(5),
        "environment_id": uid(6),
        "current_output_id": None,
        "executor_route": None,
        "continuation": None,
        "started_at": NOW,
        "finished_at": NOW if terminal else None,
        "end_reason": "LEASE_LOST" if terminal else None,
    }
    values.update(changes)
    return Attempt(**values)


def make_output(attempt_id: Any = ATTEMPT_ID, task_id: Any = TASK_ID, output_id: Any = None) -> Output:
    manifest = OutputManifest(
        algorithm="skm-output-v2",
        mounts=(OutputMount("app", uid(7), "sha1", "a" * 40, "b" * 40, "c" * 40),),
        changed_paths=(),
        tree_digest="sha256:" + "d" * 64,
        outside_write_scope=(),
        excluded_paths=(),
        patch_file_version_id=None,
        diff_stats=DiffStats(0, 0, 0),
        empty=True,
    )
    return Output(
        id=output_id or uid(300),
        attempt_id=attempt_id,
        task_id=task_id,
        run_id=uid(1),
        seq=1,
        source=OutputSource.RANGE,
        manifest=manifest,
        manifest_digest=manifest_digest(manifest),
        sealed_at=NOW,
        produced_by_step_id=None,
    )


def move(task: Task, to: TaskStatus, rule: str) -> Task:
    return transition(task, to, rule=rule, blocking=reason_for(to, task.id))


# --- completeness ----------------------------------------------------------------------------------------


def test_status_set_is_complete() -> None:
    assert {status.value for status in TaskStatus} == {
        "blocked", "ready", "assigned", "executing", "checking", "manual_pending", "reviewing",
        "rework_required", "awaiting_decision", "integrating", "accepted", "failed", "cancelled",
        "superseded", "skipped",
    }  # fmt: skip
    assert {
        TaskStatus.ACCEPTED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.SUPERSEDED,
        TaskStatus.SKIPPED,
    } == TERMINAL_TASK_STATUSES  # fmt: skip
    assert [rule.rule_id for rule in TASK_TRANSITIONS] == [
        "T1", "T1m", *(f"T{n}" for n in range(2, 10)), "T9f", *(f"T{n}" for n in range(10, 23)),
        "T22a", "T23", "T24", "T25",
        *(f"T{n}" for n in range(27, 32)),
    ]  # fmt: skip


@pytest.mark.parametrize(("source", "target"), list(product(TaskStatus, TaskStatus)), ids=lambda s: s.value)
def test_every_pair_is_a_rule_or_invalid_transition(source: TaskStatus, target: TaskStatus) -> None:
    rules = task_rules(source, target)
    task = make_task(source)
    if not rules:
        with pytest.raises(SkmError) as caught:
            transition(task, target, rule="T23", blocking=reason_for(target))
        assert caught.value.code is ErrorCode.INVALID_TRANSITION
        return
    assert source not in TERMINAL_TASK_STATUSES
    if target is TaskStatus.ACCEPTED:
        return  # covered by the acceptance tests below
    for rule in rules:
        moved = move(task, target, rule.rule_id)
        assert moved.status is target
        assert moved.row_version == task.row_version + 1


CASES = [
    (rule.rule_id, source, target)
    for rule in TASK_TRANSITIONS
    for source in sorted(rule.sources)
    for target in sorted(rule.targets)
    if target is not TaskStatus.ACCEPTED
]


@pytest.mark.parametrize(("rule", "source", "target"), CASES, ids=str)
def test_each_row_of_the_table(rule: str, source: TaskStatus, target: TaskStatus) -> None:
    assert move(make_task(source), target, rule).status is target


def test_a_rule_is_checked_against_its_own_row() -> None:
    with pytest.raises(SkmError) as caught:
        move(make_task(TaskStatus.BLOCKED), TaskStatus.READY, "T2")
    assert caught.value.code is ErrorCode.INVALID_TRANSITION
    assert caught.value.details["allowed_rules"] == ["T1", "T22a", "T29"]
    with pytest.raises(SkmError, match="unknown task rule"):
        move(make_task(TaskStatus.BLOCKED), TaskStatus.READY, "T99")


def test_t30_escalates_ready_assigned_and_integrating_tasks() -> None:
    for source in (TaskStatus.READY, TaskStatus.ASSIGNED, TaskStatus.INTEGRATING):
        escalated = move(make_task(source), TaskStatus.AWAITING_DECISION, "T30")
        assert escalated.blocking_reason is not None
        assert escalated.blocking_reason.code is BlockingCode.WAITING_OWNER
    with pytest.raises(SkmError):
        move(make_task(TaskStatus.EXECUTING), TaskStatus.AWAITING_DECISION, "T30")


@pytest.mark.parametrize("terminal", sorted(TERMINAL_TASK_STATUSES))
def test_terminal_tasks_never_change(terminal: TaskStatus) -> None:
    accepted = {"accepted_attempt_id": ATTEMPT_ID} if terminal is TaskStatus.ACCEPTED else {}
    task = make_task(terminal, **accepted)
    for target in TaskStatus:
        assert task_rules(terminal, target) == ()
        with pytest.raises(SkmError):
            transition(task, target, rule="T23", blocking=reason_for(target))


# --- events (K3) ----------------------------------------------------------------------------------------


def test_task_accepted_only_on_entering_accepted() -> None:
    for rule in TASK_TRANSITIONS:
        if ExecutionEvent.TASK_ACCEPTED in rule.events:
            assert rule.targets == {TaskStatus.ACCEPTED}, rule.rule_id
        if rule.targets == {TaskStatus.ACCEPTED}:
            assert ExecutionEvent.TASK_ACCEPTED in rule.events
    assert {rule.rule_id for rule in TASK_TRANSITIONS if TaskStatus.ACCEPTED in rule.targets} == {
        "T19",
        "T21",
        "T31",
    }


def test_acceptance_is_decided_before_integration() -> None:
    deciding = {rule.rule_id for rule in TASK_TRANSITIONS if ExecutionEvent.ACCEPTANCE_DECIDED in rule.events}
    assert deciding == {"T10", "T13"}
    for rule_id in deciding:
        rule = next(found for found in TASK_TRANSITIONS if found.rule_id == rule_id)
        assert rule.targets == {TaskStatus.INTEGRATING}
    decided = move(make_task(TaskStatus.REVIEWING), TaskStatus.INTEGRATING, "T13")
    assert decided.status is TaskStatus.INTEGRATING
    assert decided.accepted_attempt_id is None
    assert decided.accepted_output_id is None


# --- acceptance and the accepted output --------------------------------------------------------------------


def test_accept_binds_the_current_attempt_and_its_own_output() -> None:
    output = make_output()
    accepted = accept(
        make_task(TaskStatus.INTEGRATING),
        rule="T19",
        attempt=make_attempt(current_output_id=output.id),
        output=output,
    )
    assert (accepted.status, accepted.accepted_attempt_id, accepted.accepted_output_id) == (
        TaskStatus.ACCEPTED,
        ATTEMPT_ID,
        output.id,
    )
    assert accepted.blocking_reason is None
    gate = accept(make_task(TaskStatus.INTEGRATING), rule="T21", attempt=make_attempt(), output=None)
    assert gate.accepted_output_id is None


def test_accept_refuses_foreign_lost_or_mismatched_results() -> None:
    task = make_task(TaskStatus.INTEGRATING)
    other_attempt = make_attempt(id=uid(201))
    with pytest.raises(SkmError, match="current attempt"):
        accept(task, rule="T19", attempt=other_attempt, output=None)
    foreign_task = make_attempt(task_id=uid(101))
    with pytest.raises(SkmError, match="current attempt"):
        accept(task, rule="T19", attempt=foreign_task, output=None)
    for state in (AttemptState.OWNERSHIP_LOST, AttemptState.ABANDONED):
        with pytest.raises(SkmError, match="never accepted"):
            accept(task, rule="T19", attempt=make_attempt(state), output=None)
    with pytest.raises(SkmError, match="belongs to the accepted attempt"):
        accept(task, rule="T19", attempt=make_attempt(), output=make_output(attempt_id=uid(201)))
    with pytest.raises(SkmError, match="belongs to the accepted attempt"):
        accept(task, rule="T19", attempt=make_attempt(), output=make_output(task_id=uid(101)))
    with pytest.raises(SkmError, match="does not accept"):
        accept(task, rule="T13", attempt=make_attempt(), output=None)
    with pytest.raises(SkmError, match="accept"):
        transition(task, TaskStatus.ACCEPTED, rule="T19")


def test_accept_binds_only_the_current_output_of_the_attempt() -> None:
    # A2: an earlier output of the same attempt, or no output while the attempt has one, is not current
    task = make_task(TaskStatus.INTEGRATING)
    attempt = make_attempt(current_output_id=uid(301))
    for output in (make_output(), None):
        with pytest.raises(SkmError, match="current output") as caught:
            accept(task, rule="T19", attempt=attempt, output=output)
        assert caught.value.code is ErrorCode.INVALID_TRANSITION
        assert caught.value.details["reason"] == "OUTPUT_NOT_CURRENT"
    with pytest.raises(SkmError, match="current output"):
        accept(task, rule="T19", attempt=make_attempt(), output=make_output())
    accepted = accept(task, rule="T19", attempt=attempt, output=make_output(output_id=uid(301)))
    assert accepted.accepted_output_id == uid(301)


def test_an_accepted_output_is_never_replaced() -> None:
    first = accept(
        make_task(TaskStatus.INTEGRATING),
        rule="T19",
        attempt=make_attempt(current_output_id=uid(300)),
        output=make_output(),
    )
    with pytest.raises(SkmError) as caught:
        accept(
            first,
            rule="T19",
            attempt=make_attempt(current_output_id=uid(301)),
            output=make_output(output_id=uid(301)),
        )
    assert caught.value.code is ErrorCode.INVALID_TRANSITION
    assert first.accepted_output_id == uid(300)


def carry(**changes: Any) -> CarryForward:
    values: dict[str, Any] = {
        "id": uid(400),
        "source_run_id": uid(41),
        "source_task_id": uid(42),
        "source_attempt_id": uid(43),
        "source_output_id": uid(44),
        "target_run_id": uid(1),
        "target_task_id": TASK_ID,
        "compatibility_digest": "sha256:" + "e" * 64,
        "compatibility_inputs": {},
        "decision": "accepted",
        "approved_by": uid(45),
        "reason": "same evidence",
        "created_at": NOW,
    }
    values.update(changes)
    return CarryForward(**values)


@pytest.mark.parametrize("source", [TaskStatus.ASSIGNED, TaskStatus.EXECUTING])
def test_t31_carry_forward_binds_no_attempt_or_output_of_this_run(source: TaskStatus) -> None:
    accepted = accept_carried_forward(make_task(source), carry())
    assert (accepted.status, accepted.accepted_attempt_id, accepted.accepted_output_id) == (
        TaskStatus.ACCEPTED,
        None,
        None,
    )
    with pytest.raises(SkmError):
        accept_carried_forward(make_task(source), carry(decision="rejected"))
    with pytest.raises(SkmError):
        accept_carried_forward(make_task(source), carry(target_task_id=uid(101)))
    with pytest.raises(SkmError):
        accept_carried_forward(make_task(TaskStatus.READY), carry())


# --- blocking reasons and counters ----------------------------------------------------------------------


def test_waiting_statuses_state_their_reason() -> None:
    for status in BLOCKING_STATUSES:
        with pytest.raises(SkmError, match="states its blocking reason"):
            make_task(status, blocking_reason=None)
    with pytest.raises(SkmError, match="not a reason of"):
        make_task(TaskStatus.BLOCKED, blocking_reason=reason_for(TaskStatus.MANUAL_PENDING))
    with pytest.raises(SkmError, match="belongs to this task"):
        make_task(TaskStatus.BLOCKED, blocking_reason=reason_for(TaskStatus.BLOCKED, uid(101)))
    with pytest.raises(SkmError):
        transition(make_task(TaskStatus.CHECKING), TaskStatus.MANUAL_PENDING, rule="T7")
    ready = move(make_task(TaskStatus.BLOCKED), TaskStatus.READY, "T1")
    assert ready.blocking_reason is None


def test_manual_pending_does_not_spend_rework_rounds() -> None:
    checking = make_task(TaskStatus.CHECKING, check_fix_rounds=1, review_rounds=1)
    pending = move(checking, TaskStatus.MANUAL_PENDING, "T7")
    passed = move(pending, TaskStatus.REVIEWING, "T11")
    assert (pending.check_fix_rounds, passed.check_fix_rounds, passed.review_rounds) == (1, 1, 1)


def test_gate_tasks_declare_no_write_scope() -> None:
    gate = {"kind": TaskKind.ITEM_GATE, "display_key": "P1.1#gate", "review_mode": ReviewMode.REQUIRED}
    assert make_task(**gate, declared_write_scope=()).declared_write_scope == ()
    with pytest.raises(SkmError, match="empty write scope"):
        make_task(**gate, declared_write_scope=None)


def test_spec_and_origin_identity_by_kind() -> None:
    with pytest.raises(SkmError, match="spec_entity_id"):
        make_task(spec_entity_id=None)
    with pytest.raises(SkmError, match="origin"):
        make_task(kind=TaskKind.FOLLOWUP, spec_entity_id=None, display_key="FU-1")


# --- continuation and the task status (§4.6.1) ------------------------------------------------------------


def stage() -> SelectedStage:
    return SelectedStage(
        stage_id="prepare",
        stage_type="prepare_environment",
        mode=StageMode.NORMAL,
        round_no=1,
        params={},
        not_before=None,
        route_override=None,
        feedback_refs=FeedbackRefs(),
        input_output_id=None,
        retry_of_id=None,
    )


def test_t4_pause_before_the_first_stage_keeps_the_preparing_attempt_and_its_cursor() -> None:
    attempt = select_stage(
        make_attempt(AttemptState.PREPARING),
        cause=ContinuationCause("run_start", "A1"),
        stage=stage(),
        continuation_id=uid(500),
    )
    task = make_task(TaskStatus.ASSIGNED)
    released = move(task, TaskStatus.READY, "T4")
    assert released.status is TaskStatus.READY
    assert released.current_attempt_id == attempt.id
    assert attempt.state is AttemptState.PREPARING
    assert attempt.continuation is not None
    assert attempt.continuation.kind == "stage"


def test_selecting_a_stage_is_not_an_admission() -> None:
    task = make_task(TaskStatus.ASSIGNED)
    attempt = make_attempt(AttemptState.PREPARING)
    selected = select_stage(
        attempt, cause=ContinuationCause("run_start", "A1"), stage=stage(), continuation_id=uid(500)
    )
    assert selected.state is AttemptState.PREPARING
    assert task.status is TaskStatus.ASSIGNED
    executing = move(task, TaskStatus.EXECUTING, "T3")  # only begin_stage applies T3
    assert executing.status is TaskStatus.EXECUTING


def test_a_terminal_attempt_clears_its_cursor_in_the_same_transition() -> None:
    attempt = select_stage(
        make_attempt(AttemptState.RUNNING),
        cause=ContinuationCause("stage_outcome", "D1"),
        stage=stage(),
        continuation_id=uid(500),
    )
    abandoned = transition_attempt(
        attempt, AttemptState.ABANDONED, now=NOW + timedelta(1), end_reason=AttemptEndReason.CANCELLED
    )
    assert abandoned.continuation is None
    assert dataclasses.replace(attempt).continuation is not None


def test_an_observation_never_becomes_a_trusted_trigger() -> None:
    with pytest.raises(SkmError, match="observation"):
        DeferredTrigger(uid(600), ContinuationCause("observation", None))
