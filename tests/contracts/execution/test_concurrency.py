"""PostgreSQL claim/sweeper exclusion and budget contention with real connections."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from threading import Event
from typing import TYPE_CHECKING, Any

import psycopg
import pytest

from skm.adapters.postgres.execution.assignments import PostgresAssignmentRepository
from skm.adapters.postgres.execution.budgets import PostgresBudgetRepository
from skm.adapters.postgres.execution.decisions_effects import PostgresEffectRepository
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
from skm.modules.execution.domain.ids import ExternalEffectId
from skm.modules.execution.ports import AssignmentRepository, BudgetRepository, EffectRepository

from .repository_fixtures import assignment, effect, offer
from .seed_helpers import seed_attempt, seed_run, seed_task

if TYPE_CHECKING:
    from skm.modules.execution.domain.external_effect import ExternalEffect

    from .harness import ExecSide


def test_reservation_contention_cannot_overspend_limit(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        account = BudgetAccount(
            exec_side.new_id(),
            run.id,
            "run",
            None,
            BudgetDimension.TOKENS,
            Decimal(10),
            Decimal(0),
            Decimal(0),
            1,
        )
        uow.repo(BudgetRepository).add_accounts((account,))
        uow.commit()
    dsn = exec_side.dsn
    if dsn:
        started = Event()

        def contend() -> bool:
            with psycopg.connect(dsn or "", options="-c statement_timeout=5000") as conn:
                started.set()
                return PostgresBudgetRepository(conn).reserve((account.id,), Decimal(7))

        with psycopg.connect(dsn) as conn, ThreadPoolExecutor(max_workers=1) as pool:
            assert PostgresBudgetRepository(conn).reserve((account.id,), Decimal(7)) is True
            pending = pool.submit(contend)
            assert started.wait(5)
            conn.commit()
            assert pending.result(timeout=10) is False
    else:
        with exec_side.uow() as uow:
            repo = uow.repo(BudgetRepository)
            assert repo.reserve((account.id,), Decimal(7)) is True
            assert repo.reserve((account.id,), Decimal(7)) is False
            uow.commit()
    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(BudgetRepository).accounts_for(run.id, None, BudgetDimension.TOKENS)[0].reserved == 7
        uow.rollback()


def test_claim_and_sweeper_skip_rows_locked_by_other_transaction(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        task = seed_task(exec_side, uow, run.id)
        att = seed_attempt(exec_side, uow, run.id, task.id)
        row = assignment(exec_side, uow, att)
        uow.commit()
    dsn = exec_side.dsn
    claim_args: dict[str, Any] = {
        "worker": offer(exec_side),
        "workspace_ids": frozenset({exec_side.ws}),
        "blocked_project_ids": frozenset(),
        "now": exec_side.clock.now(),
        "ttl": timedelta(seconds=1),
    }
    if exec_side.dsn:
        with (
            psycopg.connect(exec_side.dsn) as first,
            psycopg.connect(dsn or "", options="-c statement_timeout=5000") as second,
        ):
            first.execute("SELECT id FROM skm_execution.assignments WHERE id=%s FOR UPDATE", (row.id,))
            assert PostgresAssignmentRepository(second).claim(**claim_args) is None
            second.rollback()
            first.rollback()
    with exec_side.uow() as uow:
        claimed = uow.repo(AssignmentRepository).claim(**claim_args)
        assert claimed is not None
        assert claimed[0].id == row.id
        assert uow.repo(AssignmentRepository).claim(**claim_args) is None
        uow.commit()
    exec_side.clock.advance(timedelta(seconds=2))
    expired_at = exec_side.clock.now()
    if exec_side.dsn:
        with (
            psycopg.connect(exec_side.dsn) as first,
            psycopg.connect(dsn or "", options="-c statement_timeout=5000") as second,
        ):
            first.execute(
                "UPDATE skm_execution.assignment_leases "
                "SET expires_at=clock_timestamp()-interval '1 second', "
                "last_heartbeat_at=clock_timestamp()-interval '2 seconds' WHERE assignment_id=%s",
                (row.id,),
            )
            first.commit()
            clock_row = first.execute("SELECT clock_timestamp()").fetchone()
            assert clock_row is not None
            expired_at = clock_row[0]
            first_rows = PostgresAssignmentRepository(first).expired(expired_at, limit=10)
            assert [a.id for a, _ in first_rows] == [row.id]
            assert PostgresAssignmentRepository(second).expired(expired_at, limit=10) == ()
            second.rollback()
            first.rollback()
    with exec_side.uow() as uow:
        assert [a.id for a, _ in uow.repo(AssignmentRepository).expired(expired_at, limit=10)] == [row.id]
        uow.rollback()


def test_concurrent_records_of_one_effect_request_leave_one_row(exec_side: ExecSide) -> None:
    """Both writers pass the duplicate pre-check before either commits; the unique constraint decides."""
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        att = seed_attempt(exec_side, uow, run.id, seed_task(exec_side, uow, run.id).id)
        uow.commit()
    with exec_side.uow() as uow:  # only the row is wanted here; each writer below stores its own
        first = effect(exec_side, uow, att)
        uow.rollback()
    second: ExternalEffect = replace(first, id=ExternalEffectId(exec_side.new_id()))
    dsn = exec_side.dsn
    if dsn:
        pids: list[int] = []

        def contend() -> None:
            with psycopg.connect(dsn or "", options="-c statement_timeout=5000") as conn:
                pids.append(conn.info.backend_pid)
                PostgresEffectRepository(conn).add(second)

        with (
            psycopg.connect(dsn) as conn,
            psycopg.connect(dsn, autocommit=True) as watch,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            PostgresEffectRepository(conn).add(first)
            pending = pool.submit(contend)
            deadline = time.monotonic() + 5
            while not pending.done() and time.monotonic() < deadline:  # until its insert waits on ours
                waiting = watch.execute(
                    "SELECT 1 FROM pg_stat_activity WHERE pid = ANY(%s) AND wait_event_type = 'Lock'", (pids,)
                ).fetchone()
                if waiting is not None:
                    break
                time.sleep(0.02)
            conn.commit()
            with pytest.raises(SkmError) as refused:
                pending.result(timeout=10)
    else:
        with exec_side.uow() as uow:
            uow.repo(EffectRepository).add(first)
            with pytest.raises(SkmError) as refused:
                uow.repo(EffectRepository).add(second)
            uow.commit()
    assert (refused.value.code, refused.value.details["constraint"]) == (
        ErrorCode.ALREADY_EXISTS,
        "uq_external_effects__run_id_kind_request_digest",
    )


def test_revision_start_lock_serializes_audit_visibility(exec_side: ExecSide) -> None:
    from skm.adapters.postgres.execution.runs_tasks import PostgresRunRepository
    from skm.modules.execution.domain.run import RunKind
    from skm.modules.execution.ports import ReadinessRepository, RunRepository

    from .event_helpers import make_readiness

    report = make_readiness(exec_side, rev_id=exec_side.rev1)
    with exec_side.uow() as audit:
        runs = audit.repo(RunRepository)
        runs.lock_revision_start(exec_side.rev1, audit=True)
        audit.repo(ReadinessRepository).add(report)
        seed_run(exec_side, audit, kind=RunKind.READINESS_AUDIT, audited_report_id=report.id)
        if exec_side.dsn:
            with psycopg.connect(exec_side.dsn, options="-c lock_timeout=500") as conn:
                contender = PostgresRunRepository(conn)
                contender.lock_revision_start(exec_side.rev2)
                assert not contender.has_active_readiness_audit(exec_side.rev1)
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    contender.lock_revision_start(exec_side.rev1)
                conn.rollback()
        audit.commit()
    with exec_side.uow() as start:
        runs = start.repo(RunRepository)
        runs.lock_revision_start(exec_side.rev1)
        assert runs.has_active_readiness_audit(exec_side.rev1)
        assert not runs.has_active_readiness_audit(exec_side.rev2)
