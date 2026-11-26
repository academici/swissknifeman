"""Fenced worker protocol against real memory and PostgreSQL units of work."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier
from typing import Any, cast
from uuid import UUID

import pytest

from contracts.execution._worker_protocol_support import begin as begin
from contracts.execution._worker_protocol_support import claim as claim
from contracts.execution._worker_protocol_support import make_case as make_case
from contracts.execution._worker_protocol_support import worker_claim as worker_claim
from contracts.execution.harness import PEPPER, ExecSide
from contracts.execution.harness import exec_side as exec_side
from fakes.entropy import DeterministicEntropy
from skm.kernel.errors import SkmError
from skm.kernel.ids import WorkerId
from skm.kernel.ports_uow import Surface
from skm.modules.access import public as access
from skm.modules.execution import public as execution
from skm.modules.execution.application._worker_protocol import instruction
from skm.modules.execution.domain.output import OutputMount, output_tree_digest
from skm.modules.execution.domain.run import RunKind
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    ExecutionQueries,
    StageRepository,
)
from skm.modules.workspace import public as workspace
from skm.modules.workspace.application.views import capabilities_document
from skm.modules.workspace.ports import WorkerRepository
from unit.execution.application._support import context


def test_claim_materializes_without_consuming_then_begin_consumes_once(exec_side: Any) -> None:
    side = exec_side
    _, _, attempt, _ = make_case(side)
    claimed = claim(side)
    with side.uow(readonly=True) as uow:
        saved = uow.repo(AttemptRepository).get(attempt.id)
        assert saved.continuation is not None
        assert instruction(uow, saved)["input_digest"] == claimed["instruction"]["input_digest"]
    key = f"begin:{side.new_id()}"
    ready = begin(side, claimed, key=key)
    replay = begin(side, claimed, key=key)
    assert ready == replay
    with side.uow(readonly=True) as uow:
        assert uow.repo(AttemptRepository).get(attempt.id).continuation is None
        assert len(uow.repo(StageRepository).history(attempt.id).entries) == 1


def test_worker_claim_can_use_its_first_paired_credential(exec_side: ExecSide) -> None:
    side = exec_side
    _, _, _, available = make_case(side)
    pairing_id = side.new_id()
    now = side.clock.now()
    with side.uow() as uow:
        caps = uow.repo(WorkerRepository).get(side.worker1).capabilities
        registration = workspace.RegisterWorker(side.ws, side.host1, "paired", capabilities_document(caps))
        proof = access.issue_pairing_token(
            uow,
            issuer=side.owner,
            workspace_id=side.ws,
            pairing_id=pairing_id,
            now=now,
            expires_at=now + timedelta(minutes=5),
            entropy=DeterministicEntropy().bytes,
            pepper=PEPPER,
            worker_registration=registration.to_json(),
        )
        uow.commit()
    system = side.app.client(actor=access.SYSTEM_ACTOR, surface=Surface.WORKER)
    exchange = workspace.ExchangePairingToken(side.ws, pairing_id, proof)
    start = Barrier(2)

    def claim_pairing(key: str) -> workspace.ExchangePairingTokenResult:
        start.wait(timeout=5)
        return cast("workspace.ExchangePairingTokenResult", system.dispatch(exchange, idempotency_key=key))

    with ThreadPoolExecutor(max_workers=2) as callers:
        results = tuple(callers.map(claim_pairing, ("worker-first-pair-a", "worker-first-pair-b")))
    result, retry = sorted(results, key=lambda item: item.token_secret is None)
    assert retry.token_secret is None
    assert retry.worker_id == result.worker_id
    assert retry.token_id == result.token_id
    assert result.worker_id is not None
    assert result.token_secret is not None
    with side.uow(readonly=True) as uow:
        worker = access.authenticate_token(uow, result.token_secret, pepper=PEPPER, now=now)
    client = side.app.client(actor=worker, surface=Surface.WORKER)
    client.dispatch(workspace.RecordWorkerHeartbeat(result.worker_id, None))
    assert claim(replace(side, worker1_client=client, worker1=WorkerId(result.worker_id)))[
        "assignment_id"
    ] == str(available.id)


def test_claim_adhoc_assignment_has_null_revision(exec_side: Any) -> None:
    run, task, _, _ = make_case(exec_side, kind=RunKind.ADHOC)
    claimed = claim(exec_side)
    assert claimed["run_id"] == str(run.id)
    assert claimed["task_id"] == str(task.id)
    assert claimed["task"]["revision_id"] is None
    assert claimed["task"]["entity_id"] is None


def test_stale_fence_and_forged_template_leave_no_stage(exec_side: Any) -> None:
    side = exec_side
    _, _, attempt, _ = make_case(side)
    claimed = claim(side)
    for field, value in (("fencing_token", claimed["fencing_token"] + 1), ("attempt_id", str(side.new_id()))):
        raw = {**worker_claim(side, claimed), field: value}
        with pytest.raises(SkmError) as caught:
            side.worker1_client.dispatch(
                execution.BeginStage(
                    claim=raw,
                    stage_id="prepare",
                    round_no=1,
                    input_digest=claimed["instruction"]["input_digest"],
                ),
                idempotency_key=f"stale:{side.new_id()}",
            )
        assert caught.value.code.value == "LEASE_LOST"
    forged = {**claimed, "instruction": {**claimed["instruction"], "input_digest": "sha256:" + "0" * 64}}
    with pytest.raises(SkmError, match=r"template|digest"):
        begin(side, forged)
    with side.uow(readonly=True) as uow:
        assert not uow.repo(StageRepository).history(attempt.id).entries
        assert uow.repo(AttemptRepository).get(attempt.id).continuation is not None


@pytest.mark.pg
@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_expired_claim_and_late_result_compete_for_one_current_fence(
    exec_side: Any, monkeypatch: Any
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from threading import Event, current_thread

    from skm.adapters.postgres.execution.assignments import PostgresAssignmentRepository
    from skm.adapters.postgres.execution.runs_tasks import PostgresRunRepository
    from skm.modules.execution.domain.assignment import AssignmentState, reissue, transition_assignment
    from skm.modules.execution.domain.attempt import ContinuationCause, select_stage
    from skm.modules.execution.domain.stage_record import interrupt_stage
    from skm.modules.execution.ports import AcceptanceRepository, OutputRepository, RunRepository

    side = exec_side
    run, task, initial, assignment = make_case(side)
    old = claim(side)
    ready = begin(side, old)
    with side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        saved = repo.get(assignment.id)
        expired = transition_assignment(saved, AssignmentState.EXPIRED)
        repo.save(expired, expected_version=saved.row_version)
        clock = uow.connection.execute("SELECT clock_timestamp()").fetchone()[0]
        uow.connection.execute(
            "UPDATE skm_execution.assignment_leases SET last_heartbeat_at=%s, expires_at=%s "
            "WHERE assignment_id=%s",
            (clock - timedelta(seconds=2), clock - timedelta(seconds=1), assignment.id),
        )
        stage = uow.repo(StageRepository).get(UUID(ready["stage_record_id"]))
        uow.repo(StageRepository).save(interrupt_stage(stage, now=clock))
        attempt = uow.repo(AttemptRepository).get(initial.id)
        uow.repo(AttemptRepository).save(
            select_stage(
                attempt,
                cause=ContinuationCause("lease_recovery", "L1"),
                stage=initial.continuation.stage,
                continuation_id=side.new_id(),
            ),
            expected_version=uow.repo(AttemptRepository).version(attempt.id),
        )
        successor = reissue(expired, new_id=side.new_id(), now=clock, available_at=side.clock.now())
        repo.add(successor)
        uow.commit()
    entered_claim, entered_result = Event(), Event()
    original_claim = PostgresAssignmentRepository._try_claim_candidate
    original_get = PostgresRunRepository.get

    def claim_waiter(self, *args, **kwargs):
        entered_claim.set()
        return original_claim(self, *args, **kwargs)

    def result_waiter(self, identity, *, for_update=False):
        if for_update and current_thread().name.startswith("late-result"):
            entered_result.set()
        return original_get(self, identity, for_update=for_update)

    monkeypatch.setattr(PostgresAssignmentRepository, "_try_claim_candidate", claim_waiter)
    monkeypatch.setattr(PostgresRunRepository, "get", result_waiter)

    def late_result():
        try:
            side.worker1_client.dispatch(
                execution.RecordStageResult(
                    claim=worker_claim(side, old),
                    stage_record_id=ready["stage_record_id"],
                    outcome_kind="runtime_error",
                    outcome={"error_code": "RUNTIME_TRANSPORT"},
                ),
                idempotency_key=f"late:{side.new_id()}",
            )
        except SkmError as exc:
            return exc.code.value
        return "unexpected success"

    with (
        side.uow() as holder,
        ThreadPoolExecutor(max_workers=1) as claims,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="late-result") as results,
    ):
        holder.repo(RunRepository).get(run.id, for_update=True)
        claimant, result = claims.submit(claim, side), results.submit(late_result)
        assert entered_claim.wait(10)
        assert entered_result.wait(10)
        holder.commit()
        new = claimant.result(timeout=20)
        assert result.result(timeout=20) == "LEASE_LOST"
    assert new["assignment_id"] == str(successor.id)
    assert new["fencing_token"] > old["fencing_token"]
    with side.uow(readonly=True) as uow:
        assert uow.repo(AssignmentRepository).lease(successor.id).fencing_token == new["fencing_token"]
        assert len(uow.repo(StageRepository).history(initial.id).entries) == 1
        assert uow.repo(OutputRepository).latest(initial.id) is None
        assert not uow.repo(AcceptanceRepository).decisions_for_task(task.id)
        assert not uow.repo(ExecutionQueries).attempt_view(initial.id)["effects"]


@pytest.mark.pg
@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
@pytest.mark.parametrize("started_stage", [False, True])
def test_begin_and_reconfigure_serialize_and_cannot_mix_bindings(
    exec_side: Any, monkeypatch: Any, started_stage: bool
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, current_thread

    from skm.adapters.postgres.execution.runs_tasks import PostgresRunRepository
    from skm.modules.execution.generated.commands import PauseRun, ReconfigureRun, ResumeRun
    from skm.modules.execution.ports import BundleRepository, RunRepository

    side = exec_side
    run, _, attempt, _ = make_case(side)
    claimed = claim(side)
    if started_stage:
        begin(side, claimed)
    side.client.dispatch(PauseRun(run.id, "checkpoint race"))
    with side.uow(readonly=True) as uow:
        version = uow.repo(RunRepository).get(run.id).row_version
    entered = {name: Event() for name in ("begin-racer", "checkpoint-racer")}
    original = PostgresRunRepository.get

    def observed(self, identity, *, for_update=False):
        if for_update:
            for prefix, barrier in entered.items():
                if current_thread().name.startswith(prefix):
                    barrier.set()
        return original(self, identity, for_update=for_update)

    monkeypatch.setattr(PostgresRunRepository, "get", observed)
    command = ReconfigureRun(run.id, version, {"execution.parallel.max_units": 1}, "new parallel ceiling")

    def checkpoint():
        try:
            side.client.dispatch(command)
        except SkmError as exc:
            return exc.code.value
        return "unexpected success"

    with (
        side.uow() as holder,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="begin-racer") as worker,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="checkpoint-racer") as control,
    ):
        holder.repo(RunRepository).get(run.id, for_update=True)
        beginning, applying = worker.submit(begin, side, claimed), control.submit(checkpoint)
        assert all(barrier.wait(10) for barrier in entered.values())
        holder.commit()
        assert beginning.result(timeout=20)["outcome"] == "refused"
        assert applying.result(timeout=20) == "INVALID_TRANSITION"
    with side.uow(readonly=True) as uow:
        assert len(uow.repo(StageRepository).history(attempt.id).entries) == int(started_stage)
        assert not uow.repo(BundleRepository).reconfigurations(run.id)
    if started_stage:
        return  # The already admitted stage must finish before a checkpoint can apply.
    side.worker1_client.dispatch(
        execution.ReleaseAssignment(
            claim=worker_claim(side, claimed), reason="paused", retain_environment=True
        ),
        idempotency_key=f"release:{side.new_id()}",
    )
    changed = side.client.dispatch(command)
    side.client.dispatch(ResumeRun(run.id))
    current = claim(side)
    assert current["instruction"]["input_digest"] != claimed["instruction"]["input_digest"]
    with pytest.raises(SkmError):
        begin(side, {**current, "instruction": claimed["instruction"]})
    assert begin(side, current)["outcome"] == "ready"
    with side.uow(readonly=True) as uow:
        assert str(uow.repo(BundleRepository).reconfigurations(run.id)[0].id) == str(
            changed.reconfiguration_id
        )


@pytest.mark.pg
@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
@pytest.mark.parametrize("operation", ["result", "renew", "guard"])
def test_waiting_command_checks_fresh_database_expiry(
    exec_side: Any, monkeypatch: Any, operation: str
) -> None:
    """The waiter's transaction now precedes expiry; clock_timestamp after the lock does not."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from threading import Event, current_thread

    import psycopg

    from contracts.execution.test_step_notes import owned_agent
    from skm.adapters.postgres.execution.runs_tasks import PostgresRunRepository
    from skm.modules.execution.ports import RunRepository

    side = exec_side
    run, _, attempt, claimed, stage, step, _, _, _ = owned_agent(side)
    entered = Event()
    transaction_time: list[Any] = []
    original = PostgresRunRepository.get

    def observed_get(self, run_id, *, for_update=False):
        if for_update and current_thread().name.startswith("fenced-waiter"):
            transaction_time.append(self._conn.execute("SELECT transaction_timestamp()").fetchone()[0])
            entered.set()
        return original(self, run_id, for_update=for_update)

    monkeypatch.setattr(PostgresRunRepository, "get", observed_get)

    def waiting() -> str:
        try:
            if operation == "guard":
                with side.uow() as uow:
                    execution.require_current_context_owner(
                        uow,
                        side.worker1_client._actor,
                        f"step:{step.id}",
                        assignment_id=UUID(claimed["assignment_id"]),
                        attempt_id=attempt.id,
                        worker_id=side.worker1,
                        fencing_token=claimed["fencing_token"],
                        now=side.clock.now(),
                    )
            elif operation == "renew":
                side.worker1_client.dispatch(
                    execution.RenewLease(
                        claim=worker_claim(side, claimed),
                        progress={
                            "stage_record_id": str(stage.id),
                            "step_id": str(step.id),
                            "phase": "runtime_started",
                        },
                    ),
                    idempotency_key=f"wait:{side.new_id()}",
                )
            else:
                side.worker1_client.dispatch(
                    execution.RecordStageResult(
                        claim=worker_claim(side, claimed),
                        stage_record_id=str(stage.id),
                        outcome_kind="result_invalid",
                        outcome={"error_code": "RESULT_INVALID"},
                    ),
                    idempotency_key=f"wait:{side.new_id()}",
                )
        except SkmError as exc:
            return exc.code.value
        return "unexpected success"

    with side.uow() as holder, ThreadPoolExecutor(max_workers=1, thread_name_prefix="fenced-waiter") as pool:
        holder.repo(RunRepository).get(run.id, for_update=True)
        pending = pool.submit(waiting)
        assert entered.wait(10)
        expiry = transaction_time[0] + timedelta(microseconds=1)
        with psycopg.connect(side.dsn) as conn:
            conn.execute(
                "UPDATE skm_execution.assignment_leases "
                "SET last_heartbeat_at=%s, expires_at=%s WHERE assignment_id=%s",
                (expiry - timedelta(seconds=1), expiry, UUID(claimed["assignment_id"])),
            )
            clock_row = conn.execute("SELECT clock_timestamp()").fetchone()
            assert clock_row is not None
            assert clock_row[0] > expiry
        holder.commit()
        assert pending.result(timeout=15) == "LEASE_LOST"
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id).finished_at is None


@pytest.mark.pg
@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_parallel_reserves_and_repeat_settlement_cannot_double_spend(exec_side: Any) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from decimal import Decimal
    from threading import Barrier

    import psycopg

    from skm.adapters.postgres.execution.budgets import PostgresBudgetRepository
    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension, BudgetReservation
    from skm.modules.execution.ports import BudgetRepository

    side = exec_side
    run, task, _, _ = make_case(side)
    with side.uow() as uow:
        account = BudgetAccount(
            side.new_id(), run.id, "run", None, BudgetDimension.TOKENS, Decimal(10), Decimal(0), Decimal(0), 1
        )
        uow.repo(BudgetRepository).add_accounts((account,))
        uow.commit()
    barrier = Barrier(2)

    def reserve() -> bool:
        with psycopg.connect(side.dsn) as conn:
            barrier.wait(timeout=10)
            return PostgresBudgetRepository(conn).reserve((account.id,), Decimal(7))

    with ThreadPoolExecutor(max_workers=2) as pool:
        one, two = pool.submit(reserve), pool.submit(reserve)
        assert sorted((one.result(timeout=15), two.result(timeout=15))) == [False, True]
    with side.uow() as uow:
        reservation = BudgetReservation(
            side.new_id(),
            (account.id,),
            BudgetDimension.TOKENS,
            None,
            Decimal(7),
            "reserved",
            None,
            side.clock.now(),
            None,
        )
        repo = uow.repo(BudgetRepository)
        repo.add_reservation(reservation)
        repo.settle(reservation, Decimal(4))
        repo.settle(reservation, Decimal(4))
        uow.commit()
    with side.uow(readonly=True) as uow:
        saved = uow.repo(BudgetRepository).accounts_for(run.id, task.id, BudgetDimension.TOKENS)[0]
        assert saved.spent == 4
        assert saved.reserved == 0


@pytest.mark.pg
@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
@pytest.mark.parametrize(("seal_first", "failure_first"), [(False, False), (True, False), (True, True)])
def test_cancel_result_and_failure_settlement_are_serialized(
    exec_side: Any, monkeypatch: Any, seal_first: bool, failure_first: bool
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from decimal import Decimal
    from threading import Event, current_thread

    from contracts.execution.test_step_notes import owned_agent
    from skm.adapters.postgres.execution.runs_tasks import PostgresRunRepository
    from skm.modules.execution.application.commands.cancel_run import handle as cancel
    from skm.modules.execution.application.commands.report_attempt_failure import handle as failure
    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension, BudgetReservation
    from skm.modules.execution.domain.stage_record import mark_runtime_started
    from skm.modules.execution.generated.commands import CancelRun
    from skm.modules.execution.ports import (
        AcceptanceRepository,
        BudgetRepository,
        OutputRepository,
        RunRepository,
    )

    side = exec_side
    run, task, attempt, claimed, stage, step, _, _, _ = owned_agent(side)
    with side.uow() as uow:
        account = BudgetAccount(
            side.new_id(),
            run.id,
            "run",
            None,
            BudgetDimension.TOKENS,
            Decimal(100),
            Decimal(0),
            Decimal(0),
            1,
        )
        budget = uow.repo(BudgetRepository)
        budget.add_accounts((account,))
        assert budget.reserve((account.id,), Decimal(10))
        reservation = BudgetReservation(
            side.new_id(),
            (account.id,),
            BudgetDimension.TOKENS,
            step.id,
            Decimal(10),
            "reserved",
            None,
            side.clock.now(),
            None,
        )
        budget.add_reservation(reservation)
        uow.repo(StageRepository).save(mark_runtime_started(stage, now=side.clock.now()))
        uow.commit()
    if seal_first:
        mount = OutputMount("repo", side.repo_id, "sha1", "1" * 40, "2" * 40, "3" * 40)
        side.worker1_client.dispatch(
            execution.SealOutput(
                claim=worker_claim(side, claimed),
                stage_record_id=str(stage.id),
                step_id=str(step.id),
                source="executor",
                manifest={
                    "algorithm": "skm-output-v2",
                    "mounts": [
                        {
                            "mount": mount.mount,
                            "repository_id": str(mount.repository_id),
                            "object_format": mount.object_format,
                            "base_commit": mount.base_commit,
                            "head_commit": mount.head_commit,
                            "tree_sha": mount.tree_sha,
                        }
                    ],
                    "changed_paths": [],
                    "outside_write_scope": [],
                    "excluded_paths": [],
                    "tree_digest": output_tree_digest((mount,), ()),
                    "patch_file_version_id": None,
                    "diff_stats": {"files": 0, "insertions": 0, "deletions": 0},
                    "empty": True,
                },
            ),
            idempotency_key=f"seal:{side.new_id()}",
        )
    entered = Event()
    original = PostgresRunRepository.get

    def observed(self, identity, *, for_update=False):
        if for_update and current_thread().name.startswith("cancel-waiter"):
            entered.set()
        return original(self, identity, for_update=for_update)

    monkeypatch.setattr(PostgresRunRepository, "get", observed)

    def waiting() -> str:
        try:
            if failure_first:
                return side.client.dispatch(CancelRun(run.id, "cancel after failure")).status
            side.worker1_client.dispatch(
                execution.RecordStageResult(
                    claim=worker_claim(side, claimed),
                    stage_record_id=str(stage.id),
                    outcome_kind="result_invalid",
                    outcome={"error_code": "RESULT_INVALID"},
                ),
                idempotency_key=f"result:{side.new_id()}",
            )
        except SkmError as exc:
            return exc.code.value
        return "unexpected success"

    with side.uow() as holder, ThreadPoolExecutor(max_workers=1, thread_name_prefix="cancel-waiter") as pool:
        holder.repo(RunRepository).get(run.id, for_update=True)
        pending = pool.submit(waiting)
        assert entered.wait(10)
        if failure_first:
            command = execution.ReportAttemptFailure(
                claim=worker_claim(side, claimed),
                stage_record_id=str(stage.id),
                error_class="timeout",
                detail="runtime stopped",
                worktree_dirty=False,
                usage={
                    "input_tokens": 3,
                    "output_tokens": 1,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 0,
                    "cost_usd_micros": 0,
                    "status": "reported",
                    "source": "stream:result",
                    "subagents": {"used": False, "disclosed": True},
                },
            )
            failure(command, context(side, holder, run, actor=side.worker1_client._actor), holder)
        else:
            cancel(CancelRun(run.id, "cancel before result"), context(side, holder, run), holder)
        holder.commit()
        assert pending.result(timeout=20) == ("cancelled" if failure_first else "LEASE_LOST")
    with side.uow(readonly=True) as uow:
        budget = uow.repo(BudgetRepository)
        saved = budget.accounts_for(run.id, task.id, BudgetDimension.TOKENS)[0]
        assert saved.reserved == 0
        assert saved.spent == (4 if failure_first else 10)
        assert not budget.open_for_steps((step.id,))
        assert not uow.repo(AcceptanceRepository).decisions_for_task(task.id)
        assert (uow.repo(OutputRepository).latest(attempt.id) is not None) is seal_first


@pytest.mark.pg
@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_worker_guard_samples_db_clock_after_run_lock_with_skewed_host(exec_side, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from threading import Event

    import psycopg

    from skm.adapters.postgres.execution.runs_tasks import PostgresRunRepository
    from skm.modules.execution.application._worker_protocol import lock_fenced_context

    side = exec_side
    run, _, _, assignment = make_case(side)
    claimed = claim(side)
    side.clock.advance(timedelta(days=-30))
    reached = Event()
    original = PostgresRunRepository.get

    def waiting_get(self, run_id, *, for_update=False):
        if for_update and run_id == run.id:
            reached.set()
        return original(self, run_id, for_update=for_update)

    monkeypatch.setattr(PostgresRunRepository, "get", waiting_get)

    def guard():
        with side.uow() as uow:
            fenced = lock_fenced_context(
                uow, context(side, uow, run), worker_claim(side, claimed), owner_guard=True
            )
            uow.commit()
            return fenced.now

    with psycopg.connect(side.dsn) as holder, ThreadPoolExecutor(max_workers=1) as pool:
        holder.execute("SELECT id FROM skm_execution.runs WHERE id=%s FOR UPDATE", (run.id,))
        pending = pool.submit(guard)
        assert reached.wait(5)
        holder.execute(
            "UPDATE skm_execution.assignment_leases "
            "SET last_heartbeat_at=clock_timestamp()-interval '30 seconds', "
            "expires_at=clock_timestamp()+interval '120 seconds' WHERE assignment_id=%s",
            (assignment.id,),
        )
        clock_row = holder.execute("SELECT clock_timestamp()").fetchone()
        assert clock_row is not None
        lower = clock_row[0]
        holder.commit()
        sampled = pending.result(timeout=10)
    assert sampled >= lower
    assert sampled > side.clock.now() + timedelta(days=1)
