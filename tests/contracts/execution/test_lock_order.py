"""Lease scan locks are released before K5 ownership locks and terminal writes."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import psycopg
import pytest

from contracts.execution._worker_protocol_support import begin, claim, make_case, worker_claim
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.errors import SkmError
from skm.modules.execution import public as execution
from skm.modules.execution.application.commands import expire_leases
from skm.modules.execution.domain.assignment import AssignmentState
from skm.modules.execution.generated.commands import CancelRun
from skm.modules.execution.ports import AssignmentRepository, ExecutionQueries, RunRepository, StageRepository
from unit.execution.application._support import context, set_setting

SYSTEM = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")


def sweep(side):
    with side.uow() as uow:
        result = expire_leases.handle(expire_leases.ExpireLeases(), context(side, uow, actor=SYSTEM), uow)
        uow.commit()
        return result


def expire_now(side, assignment):
    if side.dsn:
        with psycopg.connect(side.dsn) as conn:
            conn.execute(
                "UPDATE skm_execution.assignment_leases "
                "SET expires_at=clock_timestamp()-interval '1 second', "
                "last_heartbeat_at=clock_timestamp()-interval '2 seconds' WHERE assignment_id=%s",
                (assignment.id,),
            )
            row = conn.execute("SELECT clock_timestamp()").fetchone()
            assert row is not None
            (now,) = row
        side.clock.advance(now - side.clock.now() + timedelta(seconds=1))
    else:
        side.clock.advance(timedelta(seconds=121))


def test_two_sweepers_preserve_one_terminal_winner(exec_side):
    _, _, _, assignment = make_case(exec_side)
    old = claim(exec_side)
    expire_now(exec_side, assignment)
    if exec_side.dsn:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: sweep(exec_side), range(2)))
    else:
        results = [sweep(exec_side), sweep(exec_side)]
    assert sum(r["expired"] for r in results) == 1
    with exec_side.uow(readonly=True) as uow:
        repo = uow.repo(AssignmentRepository)
        assert repo.get(assignment.id).state is AssignmentState.EXPIRED
        assert repo.lease(assignment.id) is None
        rows = repo.for_attempt(assignment.attempt_id)
        assert sum(a.state is AssignmentState.AVAILABLE for a in rows) == 1
    with pytest.raises(SkmError) as caught:
        exec_side.worker1_client.dispatch(
            execution.RenewLease(claim=worker_claim(exec_side, old)),
            idempotency_key=f"late:{exec_side.new_id()}",
        )
    assert caught.value.code.value == "LEASE_LOST"


def test_sweepers_and_cancel_take_run_before_assignment_without_deadlock(exec_side):
    run, _, _, assignment = make_case(exec_side)
    owned = claim(exec_side)
    started = begin(exec_side, owned)
    expire_now(exec_side, assignment)

    def late_result():
        with pytest.raises(SkmError) as caught:
            exec_side.worker1_client.dispatch(
                execution.RecordStageResult(
                    claim=worker_claim(exec_side, owned),
                    stage_record_id=started["stage_record_id"],
                    outcome_kind="success",
                    outcome={},
                ),
                idempotency_key=f"late-result:{exec_side.new_id()}",
            )
        assert caught.value.code.value == "LEASE_LOST"
        return "fenced"

    def cancel():
        return exec_side.client.dispatch(
            CancelRun(run.id, "concurrent cancel"),
            idempotency_key=f"cancel:{exec_side.new_id()}",
        )

    if exec_side.dsn:
        with ThreadPoolExecutor(max_workers=4) as pool:
            pending = [
                pool.submit(sweep, exec_side),
                pool.submit(sweep, exec_side),
                pool.submit(cancel),
                pool.submit(late_result),
            ]
            results = [f.result(timeout=15) for f in pending]
        assert len(results) == 4
    else:
        sweep(exec_side)
        late_result()
        cancel()
        sweep(exec_side)
    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).get(run.id).status.value == "cancelled"
        assert uow.repo(AssignmentRepository).lease(assignment.id) is None
        record = uow.repo(StageRepository).get(UUID(started["stage_record_id"]))
        assert record.state.value in {"interrupted", "failed"}
        queries = uow.repo(ExecutionQueries)
        history = queries.run_events(run.id, 0, queries.head_run_seq(run.id), 100)
        assert sum(e["event_type"] == "urn:skm:execution:event:stage-completed:v1" for e in history) == 1


def test_locked_candidate_is_rechecked_after_a_renewal(exec_side):
    _, _, _, assignment = make_case(exec_side)
    claim(exec_side)
    with exec_side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        observed = repo.get(assignment.id)
        lease = repo.lease(assignment.id)
        # Candidate metadata is stale after a renewal; fresh locked state wins.
        repo.renew(
            lease,
            expires_at=lease.expires_at + timedelta(seconds=300),
            heartbeat_at=lease.last_heartbeat_at,
            identity=lease.process_identity,
        )
        fenced = expire_leases.lock_ownership(uow, observed)
        assert not expire_leases.expired_after_locks(uow, fenced)
        assert repo.lease(assignment.id).expires_at == lease.expires_at + timedelta(seconds=300)
        uow.commit()


def test_run_skip_locked_and_server_clock_ignore_caller_utc(exec_side):
    run, _, _, _ = make_case(exec_side)
    if exec_side.dsn:
        from skm.adapters.postgres.execution.runs_tasks import PostgresRunRepository

        with psycopg.connect(exec_side.dsn) as first, psycopg.connect(exec_side.dsn) as second:
            first.execute("SELECT id FROM skm_execution.runs WHERE id=%s FOR UPDATE", (run.id,))
            assert PostgresRunRepository(second).lock_active((run.id,)) == ()
            row = second.execute("SELECT clock_timestamp()").fetchone()
            assert row is not None
            (server,) = row
            sampled = PostgresRunRepository(second).now()
            assert 0 <= (sampled - server).total_seconds() < 5
            second.rollback()
    with exec_side.uow() as uow:
        repo = uow.repo(RunRepository)
        assert [r.id for r in repo.lock_active((run.id,))] == [run.id]
        assert repo.now().tzinfo is not None
        uow.rollback()


def test_expiry_candidate_scan_holds_no_lease_lock(exec_side):
    _, _, _, assignment = make_case(exec_side)
    claim(exec_side)
    expire_now(exec_side, assignment)
    if exec_side.dsn:
        from skm.adapters.postgres.execution.assignments import PostgresAssignmentRepository

        with psycopg.connect(exec_side.dsn) as first, psycopg.connect(exec_side.dsn) as second:
            assert PostgresAssignmentRepository(first).expiry_candidates(limit=1)[0][0].id == assignment.id
            row = second.execute(
                "SELECT assignment_id FROM skm_execution.assignment_leases "
                "WHERE assignment_id=%s FOR UPDATE NOWAIT",
                (assignment.id,),
            ).fetchone()
            assert row == (assignment.id,)
            second.rollback()
            first.rollback()
    with exec_side.uow() as uow:
        assert uow.repo(AssignmentRepository).expiry_candidates(limit=1)[0][0].id == assignment.id
        uow.rollback()


def test_post_lock_renewal_wins_against_stale_expiry_hint(exec_side):
    _, _, _, assignment = make_case(exec_side)
    claim(exec_side)
    with exec_side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        lease = repo.lease(assignment.id)
        repo.renew(
            lease,
            expires_at=lease.expires_at + timedelta(seconds=500),
            heartbeat_at=lease.last_heartbeat_at,
            identity=lease.process_identity,
        )
        fenced = expire_leases.lock_ownership(uow, repo.get(assignment.id))
        assert not expire_leases.expired_after_locks(uow, fenced)
        assert fenced.now <= fenced.lease.expires_at
        uow.commit()


def test_timeout_uses_post_lock_db_time_and_stored_server_origin(exec_side):
    from skm.modules.execution.application.commands import enforce_timeouts
    from skm.modules.execution.ports import StageRepository

    run, _, _, _ = make_case(exec_side)
    owned = claim(exec_side)
    started = begin(exec_side, owned)
    stage_id = UUID(started["stage_record_id"])
    if exec_side.dsn:
        with psycopg.connect(exec_side.dsn) as conn:
            conn.execute(
                "UPDATE skm_execution.attempt_stages "
                "SET started_at=clock_timestamp()-interval '901 seconds' WHERE id=%s",
                (stage_id,),
            )
        exec_side.clock.advance(timedelta(days=-30))
    else:
        exec_side.clock.advance(timedelta(seconds=901))
    with exec_side.uow() as uow:
        ctx = context(exec_side, uow, run, actor=SYSTEM)
        result = enforce_timeouts.handle(enforce_timeouts.EnforceTimeouts(run_id=str(run.id)), ctx, uow)
        assert result["cancel_requested"] == 1
        stage = uow.repo(StageRepository).get(stage_id)
        deadline = stage.outcome["timeout_deadline_at"]
        from datetime import datetime

        assert abs((datetime.fromisoformat(deadline) - stage.started_at).total_seconds() - 900) < 0.01
        assert uow.repo(RunRepository).get(run.id).status.value == "running"
        uow.commit()


def _owned_runtime(side):
    from skm.modules.execution.domain.lease import ProcessIdentity
    from skm.modules.execution.domain.stage_record import record_process_identity
    from skm.modules.execution.ports import StageRepository
    from unit.execution.application.test_background_commands import running_case

    run, task, attempt, assignment, stage, step = running_case(side)
    with side.uow() as uow:
        if side.dsn:
            server_now = uow.repo(RunRepository).now()
            uow.connection.execute(
                "UPDATE skm_execution.attempt_stages SET started_at=%s, runtime_started_at=%s WHERE id=%s",
                (server_now, server_now, stage.id),
            )
        stage = uow.repo(StageRepository).get(stage.id)
        owner = {
            "host_id": str(side.host1),
            "worker_id": str(side.worker1),
            "attempt_id": str(attempt.id),
            "stage_record_id": str(stage.id),
            "unit_kind": "step",
            "unit_id": str(step.id),
            "owner_nonce": "contract-owned-reap-nonce",
            "identity_dir": "/owned/contract-step",
        }
        ownership = {"kind": "cgroup", "ref": "/skm/contract-step", "owner": owner}
        identity = ProcessIdentity(
            123, 123, stage.started_at, ownership, boot_id="boot-contract", start_ticks=100
        )
        uow.repo(StageRepository).save(record_process_identity(stage, identity))
        uow.commit()
    proof = {
        "dead": True,
        "stage_record_id": str(stage.id),
        "unit_kind": "step",
        "unit_id": str(step.id),
        "identity": {
            "pid": 123,
            "pgid": 123,
            "started_at": stage.started_at.isoformat(),
            "ownership": ownership,
            "boot_id": "boot-contract",
            "start_ticks": 100,
        },
    }
    return run, task, attempt, assignment, stage, proof


def test_l2_reap_consumes_advance_once_and_preserves_terminal_stage(exec_side):
    from copy import deepcopy

    from skm.modules.execution.application.apply_action import process_pending
    from skm.modules.execution.ports import AttemptRepository, StageRepository, TaskRepository

    run, task, attempt, assignment, stage, proof = _owned_runtime(exec_side)
    expire_now(exec_side, assignment)
    assert sweep(exec_side)["expired"] == 1
    with exec_side.uow() as uow:
        repo = uow.repo(AttemptRepository)
        cursor = repo.get(attempt.id).continuation
        assert cursor.kind == "advance"
        assert process_pending(uow, context(exec_side, uow, run, actor=SYSTEM), attempt.id) == "deferred"
        assert repo.get(attempt.id).continuation == cursor
        terminal = uow.repo(StageRepository).get(stage.id)
        assert not uow.repo(StageRepository).reap_confirmed(stage.id)
        uow.commit()
    forged = deepcopy(proof)
    forged["identity"]["start_ticks"] += 1

    def reap(report):
        return exec_side.worker1_client.dispatch(
            execution.ClaimAssignment(
                worker_id=str(exec_side.worker1),
                host_id=str(exec_side.host1),
                workspace_id=str(exec_side.ws),
                offer={
                    "capabilities": ["codex_cli"],
                    "labels": ["linux"],
                    "environment_kinds": ["git_worktree"],
                    "isolation_profiles": ["landlock"],
                },
                reaped_steps=[report],
            ),
            idempotency_key=f"reap:{exec_side.new_id()}",
        )

    assert reap(forged)["outcome"] == "nothing_to_claim"
    claimed = reap(proof)
    assert claimed["attempt_id"] == str(attempt.id)
    assert claimed["assignment_id"] != str(assignment.id)
    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id) == terminal
        assert uow.repo(StageRepository).reap_confirmed(stage.id)
        assert uow.repo(TaskRepository).get(task.id).blocking_reason is None
        assert uow.repo(TaskRepository).get(task.id).attempt_count == 1
        current = uow.repo(AttemptRepository).get(attempt.id)
        assert current.continuation.kind == "stage"
        assert current.continuation.cause.advance_rule == "L2b"
        assert current.continuation.stage.mode.value == "retry"


def test_timeout_cancel_requested_is_delivered_without_pausing_run(exec_side):
    from skm.modules.execution.application.commands import enforce_timeouts
    from skm.modules.execution.ports import AttemptRepository, StageRepository

    run, _, attempt, assignment, stage, _ = _owned_runtime(exec_side)
    with exec_side.uow() as uow:
        assignments = uow.repo(AssignmentRepository)
        lease = assignments.lease(assignment.id)
        assignments.renew(
            lease,
            expires_at=lease.expires_at + timedelta(hours=1),
            heartbeat_at=lease.last_heartbeat_at,
            identity=lease.process_identity,
        )
        if exec_side.dsn:
            uow.connection.execute(
                "WITH sample AS (SELECT clock_timestamp()-interval '1801 seconds' AS at) "
                "UPDATE skm_execution.attempt_stages SET started_at=sample.at, "
                "runtime_started_at=sample.at FROM sample WHERE id=%s",
                (stage.id,),
            )
        uow.commit()
    if not exec_side.dsn:
        exec_side.clock.advance(timedelta(seconds=1801))

    def enforce():
        with exec_side.uow() as uow:
            result = enforce_timeouts.handle(
                enforce_timeouts.EnforceTimeouts(run_id=str(run.id)),
                context(exec_side, uow, run, actor=SYSTEM),
                uow,
            )
            uow.commit()
            return result

    assert enforce()["cancel_requested"] == 1
    raw = {
        "assignment_id": str(assignment.id),
        "attempt_id": str(attempt.id),
        "worker_id": str(exec_side.worker1),
        "fencing_token": 1,
    }
    renewed = exec_side.worker1_client.dispatch(
        execution.RenewLease(claim=raw), idempotency_key=f"cancel-signal:{exec_side.new_id()}"
    )
    assert renewed["cancel_requested"] is True
    set_setting(exec_side, "execution.supervisor.grace_seconds", 600)
    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).get(run.id).status.value == "running"
    if exec_side.dsn:
        with psycopg.connect(exec_side.dsn) as conn:
            conn.execute(
                "UPDATE skm_execution.attempt_stages SET outcome=outcome || jsonb_build_object("
                "'timeout_requested_at', clock_timestamp()-interval '61 seconds', "
                "'timeout_grace_deadline_at', clock_timestamp()-interval '1 second') "
                "WHERE id=%s",
                (stage.id,),
            )
    else:
        exec_side.clock.advance(timedelta(seconds=61))
    assert enforce()["failed"] == 1
    assert enforce()["failed"] == 0
    with exec_side.uow(readonly=True) as uow:
        closed = uow.repo(StageRepository).get(stage.id)
        assert closed.state.value == "failed"
        assert closed.error_code == "RUNTIME_TIMEOUT"
        assert uow.repo(AttemptRepository).get(attempt.id).continuation.kind == "advance"
        assert uow.repo(AssignmentRepository).lease(assignment.id) is None
