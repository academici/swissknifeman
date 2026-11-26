"""Execution persistence invariants shared by memory and PostgreSQL."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import psycopg
import pytest

from skm.adapters.postgres.uow import PostgresUnitOfWork
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, SkmError, ValidationFailed
from skm.kernel.ids import RunId, ScopeId, TaskId
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.execution.domain.acceptance import AcceptanceBasis, AcceptanceDecision
from skm.modules.execution.domain.assignment import Assignment, AssignmentState
from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension, BudgetReservation
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionRequest,
    DecisionState,
)
from skm.modules.execution.domain.ids import (
    AcceptanceDecisionId,
    BudgetReservationId,
    DecisionRequestId,
    OutputId,
)
from skm.modules.execution.domain.lease import Lease, WorkerClaim, verify_fence
from skm.modules.execution.domain.review import ReviewClearance
from skm.modules.execution.domain.run import RunKind, RunStatus
from skm.modules.execution.domain.step_note import NoteKind, StepNote, Urgency
from skm.modules.execution.domain.task import WORK_KINDS, TaskKind, TaskStatus
from skm.modules.execution.domain.task_graph import EdgeKind, TaskEdge
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AssignmentRepository,
    BudgetRepository,
    DecisionRepository,
    ExecutionQueries,
    OutputRepository,
    RunRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.execution.public import RunBudgetView

from .repository_fixtures import assignment, effect, offer
from .seed_helpers import seed_attempt, seed_output, seed_run, seed_stage, seed_step, seed_task

if TYPE_CHECKING:
    from .harness import ExecSide


def test_adhoc_run_binds_to_its_project_and_owns_executable_tasks(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        if isinstance(uow, PostgresUnitOfWork):
            uow.connection.execute("SET LOCAL ROLE skm_app")
        run = seed_run(exec_side, uow, kind=RunKind.ADHOC, inline_spec_file_version_id=exec_side.fv1)
        task = seed_task(exec_side, uow, run.id, kind=TaskKind.ADHOC, display_key="ADHOC-1")
        plan = seed_run(exec_side, uow)
        uow.commit()
    with exec_side.uow(readonly=True) as uow:
        saved = uow.repo(RunRepository).get(run.id)
        assert saved == run
        assert (saved.plan_id, saved.revision_id, saved.revision_no) == (None, None, None)
        assert saved.inline_spec_file_version_id == exec_side.fv1
        scope = uow.repo(ScopeRegistry).get(ScopeId(run.id))
        assert (scope.kind, scope.workspace_id, scope.parent_id) == (
            ScopeKind.RUN,
            exec_side.ws,
            ScopeId(exec_side.proj),
        )
        assert uow.repo(TaskRepository).get(task.id).kind in WORK_KINDS
    with exec_side.uow() as uow:
        if isinstance(uow, PostgresUnitOfWork):
            uow.connection.execute("SET LOCAL ROLE skm_app")
        with pytest.raises(ValidationFailed) as caught:
            seed_task(exec_side, uow, plan.id, kind=TaskKind.ADHOC, display_key="ADHOC-2")
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_adhoc_run_rejects_a_run_scope_under_plan(exec_side: ExecSide) -> None:
    side = exec_side
    with side.uow() as uow:
        run = seed_run(side, uow, kind=RunKind.ADHOC, inline_spec_file_version_id=side.fv1)
        wrong_scope = RunId(side.new_id())
        uow.repo(ScopeRegistry).create(
            ScopeId(wrong_scope), ScopeKind.RUN, parent=ScopeId(side.plan1), workspace_id=side.ws
        )
        with pytest.raises(ValidationFailed) as caught:
            uow.repo(RunRepository).add(replace(run, id=wrong_scope))
        assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_scoped_foreign_keys_outputs_and_acceptance_are_immutable(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        task = seed_task(exec_side, uow, run.id)
        other = seed_task(exec_side, uow, run.id, display_key="P1.1/U2", position=1)
        att = seed_attempt(exec_side, uow, run.id, task.id)
        foreign_att = seed_attempt(exec_side, uow, run.id, other.id)
        output = seed_output(exec_side, uow, att)
        decision = AcceptanceDecision(
            AcceptanceDecisionId(exec_side.new_id()),
            exec_side.ws,
            run.id,
            task.id,
            att.id,
            output.id,
            "accepted",
            exec_side.owner.principal_id,
            AcceptanceBasis(ReviewClearance.GREEN, (), None, (), (), False, None, None, ()),
            exec_side.clock.now(),
        )
        uow.repo(AcceptanceRepository).add_decision(decision)
        uow.commit()
    for invalid in (
        replace(task, status=TaskStatus.ACCEPTED, accepted_attempt_id=foreign_att.id),
        replace(task, workspace_id=exec_side.ws2),
    ):
        with exec_side.uow() as uow:
            with pytest.raises((Conflict, ValidationFailed)):
                uow.repo(TaskRepository).save(invalid, expected_version=1)
            uow.rollback()
    with exec_side.uow() as uow:
        with pytest.raises(Conflict):
            uow.repo(OutputRepository).add(replace(output, id=OutputId(exec_side.new_id())))
        uow.rollback()
    for revision, workspace in ((exec_side.rev_p2, exec_side.ws), (exec_side.rev1, exec_side.ws2)):
        with exec_side.uow() as uow:
            with pytest.raises(ValidationFailed):
                seed_run(exec_side, uow, rev_id=revision, ws=workspace)
            uow.rollback()
    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(OutputRepository).get(output.id) == output
        assert uow.repo(AcceptanceRepository).decisions_for_task(task.id) == (decision,)
        uow.rollback()
    if exec_side.dsn:
        with psycopg.connect(exec_side.dsn) as conn:
            for query in (
                "UPDATE skm_execution.acceptance_decisions SET decision='accepted' WHERE id=%s",
                "DELETE FROM skm_execution.acceptance_decisions WHERE id=%s",
            ):
                with pytest.raises(psycopg.errors.RestrictViolation):
                    conn.execute(query, (decision.id,))
                conn.rollback()
            cascading = conn.execute(
                "SELECT conname FROM pg_constraint WHERE contype='f' AND confdeltype='c' "
                "AND connamespace='skm_execution'::regnamespace"
            ).fetchall()
            assert cascading == []


def test_budget_atomic_reservation_settlement_overrun_and_replay(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        task = seed_task(exec_side, uow, run.id)
        accounts = (
            BudgetAccount(
                exec_side.new_id(),
                run.id,
                "run",
                None,
                BudgetDimension.TOKENS,
                Decimal(10),
                Decimal(0),
                Decimal(0),
                1,
            ),
            BudgetAccount(
                exec_side.new_id(),
                run.id,
                "task",
                task.id,
                BudgetDimension.TOKENS,
                Decimal(5),
                Decimal(0),
                Decimal(0),
                1,
            ),
        )
        repo = uow.repo(BudgetRepository)
        repo.add_accounts(accounts)
        ids = tuple(a.id for a in accounts)
        assert repo.reserve(ids, Decimal(6)) is False
        assert all(a.reserved == 0 for a in repo.accounts_for(run.id, task.id, BudgetDimension.TOKENS))
        assert repo.reserve(ids, Decimal(5)) is True
        reservation = BudgetReservation(
            BudgetReservationId(exec_side.new_id()),
            ids,
            BudgetDimension.TOKENS,
            None,
            Decimal(5),
            "reserved",
            None,
            exec_side.clock.now(),
            None,
        )
        repo.add_reservation(reservation)
        repo.settle(reservation, Decimal(12))
        repo.settle(reservation, Decimal(99))
        settled = repo.accounts_for(run.id, task.id, BudgetDimension.TOKENS)
        assert [(a.spent, a.reserved) for a in settled] == [(Decimal(12), Decimal(0))] * 2
        assert repo.get_reservation(reservation.id).settled_amount == 12
        assert repo.reserve(ids, Decimal(1)) is False
        uow.commit()
    for values in ({"spent": Decimal(-1)}, {"reserved": Decimal(-1)}, {"limit_value": Decimal(-1)}):
        with pytest.raises(ValueError, match="budget account invariants"):
            replace(accounts[0], **values)


def test_claim_fence_reissue_and_reconcile_binding(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow, status=RunStatus.RUNNING)
        task = seed_task(exec_side, uow, run.id)
        att = seed_attempt(exec_side, uow, run.id, task.id)
        row = assignment(exec_side, uow, att)
        uow.commit()
    with exec_side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        claimed = repo.claim(
            worker=offer(exec_side),
            workspace_ids=frozenset({exec_side.ws}),
            blocked_project_ids=frozenset(),
            now=exec_side.clock.now(),
            ttl=timedelta(seconds=60),
        )
        assert claimed is not None
        leased, lease = claimed
        assert leased.id == row.id
        assert lease.fencing_token == 1
        claim = WorkerClaim(row.id, att.id, exec_side.worker1, 1)
        verify_fence(lease, leased, claim, exec_side.clock.now())
        for bad_claim, now in (
            (replace(claim, fencing_token=2), exec_side.clock.now()),
            (replace(claim, worker_id=exec_side.worker2), exec_side.clock.now()),
            (claim, lease.expires_at),
        ):
            with pytest.raises(Conflict) as exc:
                verify_fence(lease, leased, bad_claim, now)
            assert exc.value.code is ErrorCode.LEASE_LOST
        repo.drop_lease(row.id)
        repo.save(replace(leased, state=AssignmentState.AVAILABLE), expected_version=leased.row_version)
        again = repo.claim(
            worker=offer(exec_side),
            workspace_ids=frozenset({exec_side.ws}),
            blocked_project_ids=frozenset(),
            now=exec_side.clock.now(),
            ttl=timedelta(seconds=60),
        )
        assert again is not None
        assert again[1].fencing_token == 2
        repo.drop_lease(row.id)
        repo.save(replace(again[0], state=AssignmentState.COMPLETED), expected_version=again[0].row_version)
        eff = effect(exec_side, uow, att)
        reconcile = assignment(exec_side, uow, att, effect_id=eff.id)
        uow.commit()
    with exec_side.uow() as uow:
        with pytest.raises(ValidationFailed) as exc:
            uow.repo(AssignmentRepository).save(
                replace(reconcile, reconcile_effect_id=None), expected_version=1
            )
        assert exc.value.code is ErrorCode.FIELD_OWNED
        uow.rollback()
    with exec_side.uow() as uow:
        with pytest.raises(Conflict):
            assignment(exec_side, uow, att, effect_id=eff.id)
        uow.rollback()
    if exec_side.dsn:
        with psycopg.connect(exec_side.dsn) as conn:
            with pytest.raises(psycopg.errors.RestrictViolation):
                conn.execute(
                    "UPDATE skm_execution.assignments SET reconcile_effect_id=NULL WHERE id=%s",
                    (reconcile.id,),
                )
            conn.rollback()
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "UPDATE skm_execution.assignments SET required_host_id=NULL WHERE id=%s", (reconcile.id,)
                )
            conn.rollback()


def test_step_note_limits_and_fencing(exec_side: ExecSide) -> None:
    manifest_id = exec_side.make_final_manifest()
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        task = seed_task(exec_side, uow, run.id)
        att = seed_attempt(exec_side, uow, run.id, task.id)
        stage = seed_stage(exec_side, uow, att)
        step = seed_step(exec_side, uow, att, stage, manifest_id=manifest_id)
        assignment(exec_side, uow, att)
        claimed = uow.repo(AssignmentRepository).claim(
            worker=offer(exec_side),
            workspace_ids=frozenset({exec_side.ws}),
            blocked_project_ids=frozenset(),
            now=exec_side.clock.now(),
            ttl=timedelta(seconds=60),
        )
        assert claimed is not None
        row, lease = claimed
        note = StepNote(
            exec_side.new_id(),
            step.id,
            NoteKind.QUESTION,
            "x" * 20000,
            (),
            "y" * 2000,
            Urgency.BLOCKING,
            exec_side.clock.now(),
        )
        repo = uow.repo(StepRepository)
        repo.add_note(
            note,
            assignment_id=row.id,
            fencing_token=lease.fencing_token,
            created_by=exec_side.owner.principal_id,
        )
        assert repo.notes_for_step(step.id) == (note,)
        uow.commit()
    for bad_note in (
        replace(note, text="x" * 20001),
        replace(note, why_blocked="y" * 2001),
        replace(note, kind=NoteKind.PROGRESS, why_blocked=None),
    ):
        with exec_side.uow() as uow:
            with pytest.raises(ValidationFailed):
                uow.repo(StepRepository).add_note(
                    replace(bad_note, id=exec_side.new_id()),
                    assignment_id=row.id,
                    fencing_token=lease.fencing_token,
                    created_by=exec_side.owner.principal_id,
                )
            uow.rollback()
    with exec_side.uow() as uow:
        with pytest.raises(Conflict) as exc:
            uow.repo(StepRepository).add_note(
                replace(note, id=exec_side.new_id()),
                assignment_id=row.id,
                fencing_token=lease.fencing_token + 1,
                created_by=exec_side.owner.principal_id,
            )
        assert exc.value.code is ErrorCode.LEASE_LOST
        uow.rollback()

    if exec_side.dsn:
        with psycopg.connect(exec_side.dsn) as conn:
            for kind, text, why, urgency, constraint in (
                ("question", "x" * 20001, None, "normal", "ck_step_notes__text"),
                ("question", "body", "y" * 2001, "normal", "ck_step_notes__why"),
                ("progress", "body", None, "blocking", "ck_step_notes__urgency"),
            ):
                with pytest.raises(psycopg.errors.CheckViolation) as pg_exc:
                    conn.execute(
                        "INSERT INTO skm_execution.step_notes "
                        "SELECT %s, workspace_id, run_id, attempt_id, step_id, assignment_id, "
                        "fencing_token, %s, %s, NULL, %s, %s, created_by, created_at "
                        "FROM skm_execution.step_notes WHERE id=%s",
                        (exec_side.new_id(), kind, text, why, urgency, note.id),
                    )
                assert pg_exc.value.diag.constraint_name == constraint
                conn.rollback()


def test_active_seconds_add_the_stages_each_filter_selects(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        first = seed_task(exec_side, uow, run.id)
        second = seed_task(exec_side, uow, run.id, display_key="P1.1/U2", position=1)
        first_attempt = seed_attempt(exec_side, uow, run.id, first.id)
        second_attempt = seed_attempt(exec_side, uow, run.id, second.id)
        first_stage = seed_stage(exec_side, uow, first_attempt)
        seed_stage(exec_side, uow, second_attempt)
        uow.commit()
    now = exec_side.clock.now() + timedelta(seconds=30)
    with exec_side.uow(readonly=True) as uow:
        runs = uow.repo(RunRepository)
        assert runs.active_seconds(run.id, now) == 60.0
        assert runs.active_seconds(run.id, now, task_id=first.id) == 30.0
        assert runs.active_seconds(run.id, now, attempt_id=second_attempt.id) == 30.0
        assert runs.active_seconds(run.id, now, stage_id=first_stage.id) == 30.0
        assert runs.active_seconds(run.id, now, attempt_id=second_attempt.id, stage_id=first_stage.id) == 0.0


def test_expired_leases_come_with_their_assignments_in_expiry_order(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow, status=RunStatus.RUNNING)
        for position in range(3):
            task = seed_task(exec_side, uow, run.id, display_key=f"P1.1/U{position + 1}", position=position)
            assignment(exec_side, uow, seed_attempt(exec_side, uow, run.id, task.id))
        uow.commit()
    with exec_side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        claimed: list[tuple[Assignment, Lease]] = []
        for ago in (200, 300, None):
            pair = repo.claim(
                worker=offer(exec_side),
                workspace_ids=frozenset({exec_side.ws}),
                blocked_project_ids=frozenset(),
                now=exec_side.clock.now(),
                ttl=timedelta(seconds=600),
            )
            assert pair is not None
            row, lease = pair
            if ago is not None:  # expired on either clock: the store bounds `now` by its own
                expires_at = lease.last_heartbeat_at - timedelta(seconds=ago)
                repo.renew(
                    lease,
                    expires_at=expires_at,
                    heartbeat_at=expires_at - timedelta(seconds=1),
                    identity=None,
                )
                renewed = repo.lease(row.id)
                assert renewed is not None
                lease = renewed
            claimed.append((row, lease))
        uow.commit()
    later, soon, (_, live) = claimed
    far = max(exec_side.clock.now(), live.last_heartbeat_at) + timedelta(days=1)
    with exec_side.uow(readonly=True) as uow:
        repo = uow.repo(AssignmentRepository)
        assert repo.expiry_candidates(limit=10) == (soon, later)
        assert repo.expiry_candidates(limit=0) == ()
    with exec_side.uow() as uow:  # the sweep locks the leases it returns
        repo = uow.repo(AssignmentRepository)
        assert repo.expired(far, limit=10) == (soon, later)
        assert repo.expired(far, limit=1) == (soon,)
        assert repo.expired(far, limit=0) == ()
        uow.rollback()


def test_a_task_batch_lands_whole_or_not_at_all(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        first = seed_task(exec_side, uow, run.id)
        uow.commit()
    batch = tuple(
        replace(first, id=TaskId(exec_side.new_id()), display_key=f"P1.1/U{n + 2}", position=n + 1)
        for n in range(3)
    )
    edges = tuple(
        TaskEdge(run.id, dependent.id, prerequisite.id, EdgeKind.BLOCKS, frozenset({"order"}))
        for dependent, prerequisite in zip(batch, (first, *batch), strict=False)
    )
    with exec_side.uow() as uow:
        uow.repo(TaskRepository).add_many(batch, edges)
        uow.commit()
    with exec_side.uow(readonly=True) as uow:
        tasks = uow.repo(TaskRepository)
        assert [t.id for t in tasks.list_for_run(run.id)] == [first.id, *(t.id for t in batch)]
        assert set(tasks.edges_for_run(run.id)) == set(edges)
    late = replace(first, id=TaskId(exec_side.new_id()), display_key="P1.1/U9", position=9)
    dangling = TaskEdge(run.id, late.id, TaskId(exec_side.new_id()), EdgeKind.BLOCKS, frozenset())
    with exec_side.uow() as uow:
        with pytest.raises(SkmError) as exc:
            uow.repo(TaskRepository).add_many((late,), (dangling,))
        assert exc.value.code is ErrorCode.INVALID_REFERENCE
        uow.rollback()
    with exec_side.uow(readonly=True) as uow:
        assert len(uow.repo(TaskRepository).list_for_run(run.id)) == 4


def test_the_expiry_sweep_needs_a_writable_unit_of_work(exec_side: ExecSide) -> None:
    """The sweep locks the leases it returns, which a readonly unit of work cannot do on either store."""
    refused = pytest.raises((RuntimeError, InternalError))  # each store's refusal of a readonly write
    with exec_side.uow(readonly=True) as uow, refused:
        uow.repo(AssignmentRepository).expired(exec_side.clock.now(), limit=10)


def test_the_expiry_sweep_does_not_look_past_the_now_it_is_given(exec_side: ExecSide) -> None:
    """Each store bounds ``now`` by its own clock, never the other way round."""
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow, status=RunStatus.RUNNING)
        task = seed_task(exec_side, uow, run.id)
        assignment(exec_side, uow, seed_attempt(exec_side, uow, run.id, task.id))
        uow.commit()
    with exec_side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        pair = repo.claim(
            worker=offer(exec_side),
            workspace_ids=frozenset({exec_side.ws}),
            blocked_project_ids=frozenset(),
            now=exec_side.clock.now(),
            ttl=timedelta(seconds=600),
        )
        assert pair is not None
        _, lease = pair
        expires_at = lease.last_heartbeat_at - timedelta(seconds=100)
        repo.renew(
            lease, expires_at=expires_at, heartbeat_at=expires_at - timedelta(seconds=1), identity=None
        )
        uow.commit()
    with exec_side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        assert repo.expired(expires_at - timedelta(seconds=1), limit=10) == ()
        assert len(repo.expired(expires_at, limit=10)) == 1
        uow.rollback()


def _accounts_of(exec_side: ExecSide, run_id: RunId, task_id: TaskId) -> list[BudgetAccount]:
    def account(task: TaskId | None, dimension: BudgetDimension) -> BudgetAccount:
        scope = "run" if task is None else "task"
        return BudgetAccount(
            exec_side.new_id(), run_id, scope, task, dimension, Decimal(10), Decimal(0), Decimal(0), 1
        )

    return [
        account(task, dim)
        for task in (None, task_id)
        for dim in (BudgetDimension.USD, BudgetDimension.TOKENS)
    ]


def test_a_limit_is_raised_on_the_one_account_of_its_scope(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        runs = [seed_run(exec_side, uow) for _ in range(2)]
        accounts = [
            account
            for run in runs
            for account in _accounts_of(exec_side, run.id, seed_task(exec_side, uow, run.id).id)
        ]
        uow.repo(BudgetRepository).add_accounts(accounts)
        uow.commit()
    run, task_id = runs[0].id, accounts[2].task_id
    assert task_id is not None
    with exec_side.uow() as uow:
        budgets = uow.repo(BudgetRepository)
        budgets.raise_limit(run, None, BudgetDimension.TOKENS, Decimal(20))
        budgets.raise_limit(run, task_id, BudgetDimension.USD, Decimal(30))
        with pytest.raises(SkmError) as missing:
            budgets.raise_limit(runs[1].id, task_id, BudgetDimension.USD, Decimal(40))
        assert missing.value.code is ErrorCode.NOT_FOUND
        uow.commit()
    with exec_side.uow(readonly=True) as uow:
        view = RunBudgetView.from_json(uow.repo(ExecutionQueries).budget_view(run))
    limits = {(a["scope"], a["task_id"], a["dimension"]): a["limit"] for a in view.accounts}
    assert limits == {
        ("run", None, "usd"): "10",
        ("run", None, "tokens"): "20",
        ("task", str(task_id), "usd"): "30",
        ("task", str(task_id), "tokens"): "10",
    }


def _escalation(exec_side: ExecSide, run_id: RunId, task_id: TaskId, state: DecisionState) -> DecisionRequest:
    return DecisionRequest(
        DecisionRequestId(exec_side.new_id()),
        exec_side.ws,
        run_id,
        task_id,
        DecisionKind.ESCALATION,
        Audience.OWNER,
        None,
        frozenset(),
        None,
        None,
        1,
        {"code": "STALLED", "options": ["resume_run", "fail"]},
        None,
        {},
        state,
        None,
        None,
        exec_side.clock.now(),
    )


def test_decisions_are_counted_per_task_whatever_their_state(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        asked, other = (
            seed_task(exec_side, uow, run.id),
            seed_task(exec_side, uow, run.id, display_key="P1.1/U2"),
        )
        decisions = uow.repo(DecisionRepository)
        for state in (DecisionState.OPEN, DecisionState.ANSWERED, DecisionState.OPEN):
            decisions.add(_escalation(exec_side, run.id, asked.id, state))
        decisions.add(_escalation(exec_side, run.id, other.id, DecisionState.OPEN))
        uow.commit()
    with exec_side.uow(readonly=True) as uow:
        decisions = uow.repo(DecisionRepository)
        assert decisions.count_for_task(asked.id) == 3
        assert decisions.count_for_task(other.id) == 1
        assert decisions.count_for_task(TaskId(exec_side.new_id())) == 0
