"""R3-8 meter and control contracts on memory and PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from typing import Any
from uuid import UUID

import psycopg
import pytest

from contracts.execution.harness import ExecSide
from contracts.execution.repository_fixtures import offer
from contracts.execution.test_step_notes import owned_agent
from contracts.execution.test_worker_protocol import worker_claim
from skm.adapters.postgres.uow import PostgresUnitOfWork
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import RunId, TaskId
from skm.kernel.json_types import JsonObject
from skm.modules.access import public as access
from skm.modules.execution import public as execution
from skm.modules.execution.application.commands import enforce_timeouts
from skm.modules.execution.domain.assignment import AssignmentState, reissue, transition_assignment
from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
from skm.modules.execution.domain.ids import AssignmentId, StepId
from skm.modules.execution.domain.stage_record import mark_runtime_started
from skm.modules.execution.ports import (
    AssignmentRepository,
    BudgetRepository,
    ExecutionQueries,
    RunRepository,
    StageRepository,
    StepRepository,
)
from unit.execution.application._support import context

TOOL_CALLS = BudgetDimension.TOOL_CALLS


def _start(side: ExecSide, *, limit: int | None = None, has_ledger: bool = True) -> Any:
    run, task, attempt, claim, stage, step, *_ = owned_agent(side)
    with side.uow() as uow:
        now = uow.repo(RunRepository).now()
        uow.repo(StageRepository).save(mark_runtime_started(stage, now=now))
        budget = BudgetAccount(
            side.new_id(),
            run.id,
            "run",
            None,
            TOOL_CALLS,
            None if limit is None else Decimal(limit),
            Decimal(0),
            Decimal(0),
            1,
        )
        if has_ledger:
            uow.repo(BudgetRepository).add_accounts((budget,))
        uow.commit()
    return run, task, attempt, claim, stage, step


def _renew(
    side: ExecSide,
    claim: Any,
    stage: Any,
    step: Any,
    calls: list[dict[str, Any]],
    *,
    coverage: str = "partial",
    key: str | None = None,
) -> Any:
    return side.worker1_client.dispatch(
        execution.RenewLease(
            claim=worker_claim(side, claim),
            progress={
                "stage_record_id": str(stage.id),
                "step_id": str(step.id),
                "tool_calls": {"coverage": coverage, "calls": calls},
            },
        ),
        idempotency_key=key or f"tool-calls:{side.new_id()}",
    )


def _ledger(side: ExecSide, run_id: RunId, task_id: TaskId, step_id: StepId) -> tuple[Decimal, list[str]]:
    with side.uow(readonly=True) as uow:
        (account,) = uow.repo(BudgetRepository).accounts_for(run_id, task_id, TOOL_CALLS)
        calls = uow.repo(StepRepository).tool_calls(step_id, limit=100, after="")
        return account.spent, [row.call.call_id for row in calls]


def test_r3_8_tool_calls_charge_once_and_preserve_unknown_duration(exec_side: ExecSide) -> None:
    side = exec_side
    run, task, _, claim, stage, step = _start(side)
    one = {"call_id": "read", "tool": "file_read", "duration_ms": None}
    two = {"call_id": "scan", "duration_ms": 25}
    _renew(side, claim, stage, step, [one, one, two], key="lost-tool-response")
    _renew(side, claim, stage, step, [one, one, two], key="lost-tool-response")
    _renew(side, claim, stage, step, [{**one, "duration_ms": 42}], coverage="complete")
    _renew(side, claim, stage, step, [], coverage="unavailable")
    with pytest.raises(SkmError) as invalid:
        _renew(
            side, claim, stage, step, [{"call_id": "unknown", "duration_ms": None}], coverage="unavailable"
        )
    assert invalid.value.code is ErrorCode.SCHEMA_INVALID
    assert _ledger(side, run.id, task.id, step.id) == (2, ["read", "scan"])
    view: Any = side.client.ask(execution.GetTaskLiveControl(run.id, task.id))
    assert view.active_step_id == step.id
    assert [(call.call_id, call.duration_ms, call.coverage) for call in view.tool_calls] == [
        ("read", None, "partial"),
        ("scan", 25, "partial"),
    ]
    paged: Any = side.client.ask(execution.GetTaskLiveControl(run.id, task.id, step.id, "read"))
    assert [call.call_id for call in paged.tool_calls] == ["scan"]


def test_r3_8_legacy_run_creates_one_meter_when_tool_calls_arrive(exec_side: ExecSide) -> None:
    side = exec_side
    run, task, _, claim, stage, step = _start(side, has_ledger=False)
    calls = [{"call_id": "first", "duration_ms": None}]
    _renew(side, claim, stage, step, calls)
    _renew(side, claim, stage, step, calls)
    assert _ledger(side, run.id, task.id, step.id) == (1, ["first"])


def test_r3_8_old_fence_after_reissue_changes_zero_budget(exec_side: ExecSide) -> None:
    side = exec_side
    run, task, _, claim, stage, step = _start(side)
    _renew(side, claim, stage, step, [{"call_id": "first", "duration_ms": None}], key="old-tool-receipt")
    with side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        old = repo.get(AssignmentId(UUID(claim["assignment_id"])), for_update=True)
        expired = transition_assignment(old, AssignmentState.EXPIRED)
        repo.save(expired, expected_version=old.row_version)
        repo.drop_lease(old.id)
        now = uow.repo(RunRepository).now()
        repo.add(reissue(expired, new_id=AssignmentId(side.new_id()), now=now - timedelta(seconds=1)))
        leased = repo.claim(
            worker=offer(side),
            workspace_ids=frozenset({side.ws}),
            blocked_project_ids=frozenset(),
            now=now,
            ttl=timedelta(minutes=2),
        )
        assert leased is not None
        assert leased[1].fencing_token > claim["fencing_token"]
        uow.commit()
    for call_id, key in [("first", "old-tool-receipt"), ("late", "late-tool-request")]:
        with pytest.raises(SkmError) as stale:
            _renew(side, claim, stage, step, [{"call_id": call_id, "duration_ms": None}], key=key)
        assert stale.value.code is ErrorCode.LEASE_LOST
    assert _ledger(side, run.id, task.id, step.id) == (1, ["first"])


def test_r3_8_tool_charge_and_journal_roll_back_together(
    exec_side: ExecSide, monkeypatch: pytest.MonkeyPatch
) -> None:
    side = exec_side
    run, task, _, claim, stage, step = _start(side)
    with side.uow(readonly=True) as uow:
        adapter = type(uow.repo(BudgetRepository))

    def reject(*_args: object) -> None:
        raise RuntimeError("injected budget write failure")

    calls = [{"call_id": "first", "duration_ms": None}]
    with monkeypatch.context() as patch:
        patch.setattr(adapter, "record_spend", reject)
        with pytest.raises(SkmError) as error:
            _renew(side, claim, stage, step, calls)
    assert error.value.code is ErrorCode.INTERNAL_ERROR
    assert _ledger(side, run.id, task.id, step.id) == (0, [])
    _renew(side, claim, stage, step, calls, coverage="complete")
    assert _ledger(side, run.id, task.id, step.id) == (1, ["first"])


def test_r3_8_budget_alert_and_breaker_at_exact_limit(exec_side: ExecSide) -> None:
    side = exec_side
    run, task, _, claim, stage, step = _start(side, limit=5)
    with side.uow(readonly=True) as uow:
        before = uow.repo(ExecutionQueries).head_run_seq(run.id)
    calls = [{"call_id": str(n), "duration_ms": None} for n in range(4)]
    assert not _renew(side, claim, stage, step, calls)["cancel_requested"]
    assert not _renew(side, claim, stage, step, calls)["cancel_requested"]
    with side.uow(readonly=True) as uow:
        assert uow.repo(ExecutionQueries).head_run_seq(run.id) == before + 1
    assert _renew(side, claim, stage, step, [{"call_id": "4", "duration_ms": None}])["cancel_requested"]
    assert _ledger(side, run.id, task.id, step.id) == (5, ["0", "1", "2", "3", "4"])
    updated: Any = side.client.ask(execution.GetRun(run.id))
    assert (updated.status, updated.stop_code) == ("paused", "BUDGET_EXHAUSTED")
    view: Any = side.client.ask(execution.GetTaskLiveControl(run.id, task.id))
    assert view.cancellation_requested


def test_abort_is_fenced_and_reconciled_by_stage_cancellation(exec_side: ExecSide) -> None:
    side = exec_side
    run, task, _, claim, stage, step = _start(side)
    view: Any = side.client.ask(execution.GetTaskLiveControl(run.id, task.id))
    command = execution.AbortStep(
        run.id, task.id, view.row_version, view.assignment_id, view.fencing_token, step.id, "Operator abort"
    )
    with pytest.raises(SkmError) as denied:
        side.viewer_client.dispatch(command)
    assert denied.value.code is ErrorCode.FORBIDDEN
    with pytest.raises(SkmError) as stale:
        side.client.dispatch(replace(command, expected_fencing_token=claim["fencing_token"] + 1))
    assert stale.value.code is ErrorCode.VERSION_CONFLICT
    first: Any = side.client.dispatch(command, idempotency_key="operator-abort")
    assert first.effective == "cancellation_requested"
    assert side.client.dispatch(command, idempotency_key="operator-abort") == first
    assert _renew(side, claim, stage, step, [], coverage="unavailable")["cancel_requested"]
    with pytest.raises(SkmError) as late:
        side.worker1_client.dispatch(
            execution.RecordStageResult(
                claim=worker_claim(side, claim),
                stage_record_id=str(stage.id),
                outcome_kind="result_invalid",
                outcome={"error_code": "RESULT_INVALID"},
            ),
            idempotency_key="late-aborted-stage",
        )
    assert late.value.code is ErrorCode.LEASE_LOST
    with side.uow() as uow:
        stages = uow.repo(StageRepository)
        requested = stages.get(stage.id)
        assert requested.finished_at is None
        past = (uow.repo(RunRepository).now() - timedelta(seconds=1)).isoformat()
        stages.save(
            replace(
                requested,
                outcome={
                    **(requested.outcome or {}),
                    "timeout_deadline_at": past,
                    "timeout_grace_deadline_at": past,
                },
            )
        )
        uow.commit()
    with side.uow() as uow:
        result = enforce_timeouts.handle(
            enforce_timeouts.EnforceTimeouts(run_id=str(run.id)),
            context(side, uow, run, actor=access.SYSTEM_ACTOR),
            uow,
        )
        assert result["failed"] == 1
        uow.commit()
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id).error_code == "STEP_ABORTED"
        assert uow.repo(AssignmentRepository).lease(AssignmentId(UUID(claim["assignment_id"]))) is None


@pytest.mark.pg
@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_concurrent_distinct_receipts_book_one_call(exec_side: ExecSide) -> None:
    run, task, _, claim, stage, step = _start(exec_side)
    barrier = Barrier(2)

    def report(key: str) -> None:
        barrier.wait(timeout=10)
        _renew(exec_side, claim, stage, step, [{"call_id": "one", "duration_ms": None}], key=key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(report, "call-request-a")
        second = pool.submit(report, "call-request-b")
        first.result(timeout=15)
        second.result(timeout=15)
    assert _ledger(exec_side, run.id, task.id, step.id) == (1, ["one"])


@pytest.mark.pg
@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_journal_acls_are_final_and_append_only(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        assert isinstance(uow, PostgresUnitOfWork)
        with uow.connection.cursor() as cur:
            cur.execute("SET LOCAL ROLE skm_app")
            for table in ("skm_execution.incident_gates", "skm_execution.step_tool_calls"):
                cur.execute(
                    """SELECT array_agg(has_table_privilege(%s, privilege) ORDER BY ordinal)
                       FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE'])
                       WITH ORDINALITY AS permissions(privilege, ordinal)""",
                    (table,),
                )
                row = cur.fetchone()
                assert row is not None
                assert row[0] == [True, True, False, False, False]
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute("DELETE FROM skm_execution.step_tool_calls")


def test_incident_receipts_survive_reopen_and_are_task_scoped(exec_side):
    from skm.modules.execution.application._incident_gate import journal
    from unit.execution.application._support import context

    run, task, *_ = _start(exec_side)
    details: JsonObject = {"branch": "A", "authority": "coordinator", "action": "retry"}
    for _ in range(2):
        with exec_side.uow() as uow:
            uow.repo(RunRepository).get(run.id, for_update=True)
            journal(uow, context(exec_side, uow, run), task.id, "retry", details)
            uow.commit()
    result: Any = exec_side.client.ask(execution.GetTaskLiveControl(run.id, task.id))
    assert len(result.incidents) == 1
    assert result.incidents[0].branch == "A"
    assert result.incidents[0].authority == "coordinator"
