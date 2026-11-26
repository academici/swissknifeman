"""Run state machine (execution §4.1, §4.1.1)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from itertools import product
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.execution.domain import run as runs
from skm.modules.execution.domain.events import ExecutionEvent
from skm.modules.execution.domain.review_grouping import ReviewGrouping
from skm.modules.execution.domain.run import (
    RUN_TRANSITIONS,
    TERMINAL_RUN_STATUSES,
    Run,
    RunKind,
    RunStatus,
    run_rule,
)

T0 = datetime(2026, 10, 25, 11, 40, tzinfo=UTC)
T1 = T0 + timedelta(minutes=5)


def uid(n: int) -> Any:
    return UUID(int=n)


def make_run(status: RunStatus = RunStatus.CREATED, **changes: Any) -> Run:
    started = status not in {RunStatus.CREATED, RunStatus.READY}
    values: dict[str, Any] = {
        "id": uid(1),
        "workspace_id": uid(2),
        "project_id": uid(3),
        "kind": RunKind.PLAN,
        "plan_id": uid(4),
        "revision_id": uid(5),
        "revision_no": 1,
        "status": status,
        "requested_by": uid(6),
        "readiness_report_id": uid(7),
        "audited_report_id": None,
        "review_request_id": None,
        "compiler_version": 1,
        "workflow_resource_version_id": uid(8),
        "review_grouping": ReviewGrouping("none", (), "medium", "single task"),
        "autopilot": False,
        "queued": False,
        "pause_reason": "owner pause" if status is RunStatus.PAUSED else None,
        "pause_source": "owner" if status is RunStatus.PAUSED else None,
        "stop_code": None,
        "unmetered_at": None,
        "row_version": 1,
        "created_at": T0,
        "started_at": T0 if started else None,
        "finished_at": T1 if status in TERMINAL_RUN_STATUSES else None,
    }
    values.update(changes)
    return Run(**values)


# --- the table ----------------------------------------------------------------------------------------

ALLOWED = {(source, rule.target): rule.rule_id for rule in RUN_TRANSITIONS for source in rule.sources}


def test_table_has_every_rule_once() -> None:
    assert [rule.rule_id for rule in RUN_TRANSITIONS] == [f"R{n}" for n in range(1, 11)]
    assert next(rule for rule in RUN_TRANSITIONS if rule.rule_id == "R1").sources == frozenset()
    assert (
        next(rule for rule in RUN_TRANSITIONS if rule.rule_id == "R10").sources
        == frozenset(RunStatus) - TERMINAL_RUN_STATUSES
    )


@pytest.mark.parametrize(("source", "target"), list(product(RunStatus, RunStatus)), ids=lambda s: s.value)
def test_every_pair_is_a_rule_or_an_error(source: RunStatus, target: RunStatus) -> None:
    if (source, target) in ALLOWED:
        assert run_rule(source, target).rule_id == ALLOWED[(source, target)]
        return
    with pytest.raises(SkmError) as caught:
        run_rule(source, target)
    expected = ErrorCode.RUN_NOT_ACTIVE if source in TERMINAL_RUN_STATUSES else ErrorCode.INVALID_TRANSITION
    assert caught.value.code is expected


def test_events_of_the_rules() -> None:
    events = {rule.rule_id: rule.event for rule in RUN_TRANSITIONS}
    assert events == {
        "R1": ExecutionEvent.RUN_CREATED,
        "R2": None,
        "R3": ExecutionEvent.RUN_STARTED,
        "R4": ExecutionEvent.RUN_WAITING,
        "R5": ExecutionEvent.RUN_RESUMED,
        "R6": ExecutionEvent.RUN_PAUSED,
        "R7": ExecutionEvent.RUN_RESUMED,
        "R8": ExecutionEvent.RUN_FINISHED,
        "R9": ExecutionEvent.RUN_FINISHED,
        "R10": ExecutionEvent.RUN_CANCELLED,
    }


# --- each command ----------------------------------------------------------------------------------------


def test_r2_r3_start_a_created_run() -> None:
    ready = runs.mark_ready(make_run(queued=True))
    assert ready.status is RunStatus.READY
    assert ready.row_version == 2
    running = runs.start(ready, now=T1)
    assert (running.status, running.started_at, running.queued, running.row_version) == (
        RunStatus.RUNNING,
        T1,
        False,
        3,
    )


def test_r4_r5_wait_and_wake_clear_the_current_stop_code() -> None:
    waiting = runs.wait(make_run(RunStatus.RUNNING), stop_code="ITEM_BLOCKED")
    assert (waiting.status, waiting.stop_code) == (RunStatus.WAITING, "ITEM_BLOCKED")
    woken = runs.wake(waiting)
    assert (woken.status, woken.stop_code) == (RunStatus.RUNNING, None)


@pytest.mark.parametrize("source", [RunStatus.RUNNING, RunStatus.WAITING])
def test_r6_owner_and_system_pause(source: RunStatus) -> None:
    owner = runs.pause(make_run(source), reason="lunch", source="owner")
    assert (owner.status, owner.pause_source, owner.stop_code, owner.pause_reason) == (
        RunStatus.PAUSED,
        "owner",
        None,
        "lunch",
    )
    system = runs.pause(make_run(source), reason="budget", source="system", stop_code="BUDGET_EXHAUSTED")
    assert (system.pause_source, system.stop_code) == ("system", "BUDGET_EXHAUSTED")
    with pytest.raises(SkmError, match="owner pause has no stop code"):
        runs.pause(make_run(source), reason="x", source="owner", stop_code="BUDGET_EXHAUSTED")
    with pytest.raises(SkmError, match="names its stop code"):
        runs.pause(make_run(source), reason="x", source="system")


def test_r7_resume_clears_pause_state_but_not_unmetered() -> None:
    paused = runs.pause(
        runs.mark_unmetered(make_run(RunStatus.RUNNING), now=T1),
        reason="breaker",
        source="system",
        stop_code="RECOVERY_CIRCUIT_OPEN",
    )
    resumed = runs.resume(paused)
    assert (resumed.status, resumed.stop_code, resumed.pause_source, resumed.pause_reason) == (
        RunStatus.RUNNING,
        None,
        None,
        None,
    )
    assert resumed.unmetered_at == T1
    assert runs.clear_unmetered(resumed).unmetered_at is None


def test_repeating_a_reached_state_is_a_noop_without_a_new_version() -> None:
    paused = runs.pause(make_run(RunStatus.RUNNING), reason="first", source="owner")
    again = runs.pause(paused, reason="second", source="owner")
    assert again is paused
    running = make_run(RunStatus.RUNNING)
    assert runs.resume(running) is running
    unmetered = runs.mark_unmetered(running, now=T0)
    assert runs.mark_unmetered(unmetered, now=T1).unmetered_at == T0


def test_r8_r9_finish() -> None:
    succeeded = runs.finish(make_run(RunStatus.RUNNING), outcome=RunStatus.SUCCEEDED, now=T1)
    assert (succeeded.status, succeeded.finished_at, succeeded.stop_code) == (RunStatus.SUCCEEDED, T1, None)
    failed = runs.finish(
        make_run(RunStatus.WAITING), outcome=RunStatus.FAILED, now=T1, stop_code="ITEM_BLOCKED"
    )
    assert (failed.status, failed.stop_code) == (RunStatus.FAILED, "ITEM_BLOCKED")
    with pytest.raises(SkmError) as caught:
        runs.finish(make_run(RunStatus.WAITING), outcome=RunStatus.SUCCEEDED, now=T1)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION


@pytest.mark.parametrize("source", sorted(frozenset(RunStatus) - TERMINAL_RUN_STATUSES))
def test_r10_cancel_from_any_nonterminal_status(source: RunStatus) -> None:
    run = make_run(source)
    if source is RunStatus.PAUSED:
        run = dataclasses.replace(run, pause_source="system", stop_code="BUDGET_EXHAUSTED")
    cancelled = runs.cancel(run, now=T1)
    assert (cancelled.status, cancelled.finished_at, cancelled.stop_code, cancelled.pause_source) == (
        RunStatus.CANCELLED,
        T1,
        None,
        None,
    )
    assert cancelled.started_at is not None


@pytest.mark.parametrize("terminal", sorted(TERMINAL_RUN_STATUSES))
def test_terminal_runs_never_change(terminal: RunStatus) -> None:
    run = make_run(terminal)
    commands = [
        lambda: runs.mark_ready(run),
        lambda: runs.start(run, now=T1),
        lambda: runs.wait(run),
        lambda: runs.wake(run),
        lambda: runs.pause(run, reason="x", source="owner"),
        lambda: runs.resume(run),
        lambda: runs.finish(run, outcome=RunStatus.FAILED, now=T1),
        lambda: runs.cancel(run, now=T1),
        lambda: runs.mark_unmetered(run, now=T1),
    ]
    for command in commands:
        with pytest.raises(SkmError) as caught:
            command()
        assert caught.value.code is ErrorCode.RUN_NOT_ACTIVE


def test_out_of_order_commands_are_invalid_transitions() -> None:
    for command in (
        lambda: runs.start(make_run(), now=T1),
        lambda: runs.wake(make_run(RunStatus.RUNNING)),
        lambda: runs.wait(make_run(RunStatus.READY)),
        lambda: runs.pause(make_run(RunStatus.READY), reason="x", source="owner"),
        lambda: runs.resume(make_run(RunStatus.WAITING)),
    ):
        with pytest.raises(SkmError) as caught:
            command()
        assert caught.value.code is ErrorCode.INVALID_TRANSITION


# --- invariants --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "violation"),
    [
        ({"kind": RunKind.REVIEW_REQUEST}, "review_request_id"),
        ({"review_request_id": uid(9)}, "review_request_id"),
        ({"kind": RunKind.READINESS_AUDIT}, "audited_report_id"),
        ({"audited_report_id": uid(9)}, "audited_report_id"),
        ({"stop_code": "BUDGET_EXHAUSTED"}, "stop_code"),
        ({"pause_source": "owner"}, "pause_source"),
        ({"finished_at": T1}, "finished_at"),
        ({"started_at": T0}, "started_at"),
        ({"revision_no": 0}, "revision_no"),
    ],
)
def test_invariants_of_a_created_run(changes: dict[str, Any], violation: str) -> None:
    with pytest.raises(SkmError, match=violation) as caught:
        make_run(**changes)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_kind_identities_hold_together() -> None:
    assert make_run(kind=RunKind.REVIEW_REQUEST, review_request_id=uid(9)).review_request_id == uid(9)
    assert make_run(kind=RunKind.READINESS_AUDIT, audited_report_id=uid(9)).audited_report_id == uid(9)
    with pytest.raises(SkmError, match="pause_source"):
        make_run(RunStatus.PAUSED, pause_source=None)
    assert make_run(RunStatus.FAILED, stop_code="ITEM_BLOCKED").stop_code == "ITEM_BLOCKED"
    with pytest.raises(SkmError, match="stop_code"):
        make_run(RunStatus.SUCCEEDED, stop_code="ITEM_BLOCKED")


def test_the_revision_of_a_run_never_changes() -> None:
    run = make_run()
    moved = runs.cancel(runs.start(runs.mark_ready(run), now=T1), now=T1)
    assert (moved.revision_id, moved.revision_no, moved.plan_id) == (
        run.revision_id,
        run.revision_no,
        run.plan_id,
    )
