"""Oldest eligible claim and single ownership winner on memory and real PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest

from contracts.execution._worker_protocol_support import claim, make_case
from skm.modules.execution.domain.assignment import AssignmentState
from skm.modules.execution.ports import AssignmentRepository, TaskRepository


def test_two_workers_claim_a_saved_assignment_exactly_once(exec_side):
    _, _, _, assignment = make_case(exec_side)
    if exec_side.dsn:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: claim(exec_side), range(2)))
    else:
        results = [claim(exec_side), claim(exec_side)]
    winners = [r for r in results if r.get("assignment_id")]
    assert len(winners) == 1
    assert winners[0]["assignment_id"] == str(assignment.id)
    assert sum(r.get("outcome") == "nothing_to_claim" for r in results) == 1
    with exec_side.uow(readonly=True) as uow:
        row = uow.repo(AssignmentRepository).get(assignment.id)
        lease = uow.repo(AssignmentRepository).lease(row.id)
        assert row.state is AssignmentState.LEASED
        assert lease.fencing_token == row.last_fencing_token == 1


def test_oldest_run_wins_despite_younger_run_flood(exec_side):
    older_run, _, _, older_assignment = make_case(exec_side)
    exec_side.clock.advance(timedelta(seconds=1))
    younger = [make_case(exec_side) for _ in range(5)]
    result = claim(exec_side)
    assert result["assignment_id"] == str(older_assignment.id)
    assert result["run_id"] == str(older_run.id)
    for _, _, _, assignment in younger:
        with exec_side.uow(readonly=True) as uow:
            assert uow.repo(AssignmentRepository).get(assignment.id).state is AssignmentState.AVAILABLE


def test_ineligible_host_and_future_backoff_are_skipped_before_limit(exec_side):
    first = make_case(exec_side)
    second = make_case(exec_side)
    _, _, _, eligible = make_case(exec_side)
    with exec_side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        row = repo.get(first[3].id)
        repo.save(
            replace(row, requirements=replace(row.requirements, required_host_id=exec_side.host2)),
            expected_version=row.row_version,
        )
        row = repo.get(second[3].id)
        repo.save(
            replace(row, available_at=exec_side.clock.now() + timedelta(days=10)),
            expected_version=row.row_version,
        )
        uow.commit()
    result = claim(exec_side)
    assert result["assignment_id"] == str(eligible.id)


def test_fresh_claim_rechecks_live_distinct_capacity_under_run_lock(exec_side):
    run, task, _, first = make_case(exec_side)
    from contracts.execution.repository_fixtures import assignment
    from contracts.execution.seed_helpers import seed_attempt, seed_task
    from skm.modules.execution.domain.attempt import AttemptState
    from skm.modules.execution.ports import AttemptRepository

    with exec_side.uow() as uow:
        owner = uow.repo(AttemptRepository).get(first.attempt_id)
        for index in range(3):
            other = seed_task(
                exec_side,
                uow,
                run.id,
                display_key=f"P1.1/U{index + 2}",
                spec_entity_id=None,
                kind=task.kind.FOLLOWUP,
                position=index + 1,
            )
            att = seed_attempt(
                exec_side,
                uow,
                run.id,
                other.id,
                state=AttemptState.PREPARING,
                continuation=owner.continuation,
            )
            repo = uow.repo(TaskRepository)
            repo.save(
                replace(other, current_attempt_id=att.id, attempt_count=1, row_version=other.row_version + 1),
                expected_version=other.row_version,
            )
            assignment(exec_side, uow, att)
        uow.commit()
    winners = [claim(exec_side) for _ in range(4)]
    assert sum(bool(r.get("assignment_id")) for r in winners) == 2


def test_target_host_pin_survives_release_and_expiry_between_runs(exec_side):
    from skm.kernel.errors import SkmError
    from skm.modules.execution.ports import IntegrationSlotRepository

    first = make_case(exec_side)
    second = make_case(exec_side)
    with exec_side.uow() as uow:
        slots = uow.repo(IntegrationSlotRepository)
        assert slots.pin_target_host(exec_side.repo_id, "main", exec_side.host1, exec_side.clock.now()) == (
            exec_side.host1,
            True,
        )
        acquired = slots.acquire(
            exec_side.repo_id,
            "main",
            first[2].id,
            exec_side.host1,
            exec_side.clock.now(),
            exec_side.clock.now() + timedelta(days=1),
        )
        slots.release(acquired.id, first[2].id, acquired.fencing_token)
        assert slots.target_hosts(((exec_side.repo_id, "main"),)) == {
            (exec_side.repo_id, "main"): exec_side.host1
        }
        expiring = slots.acquire(
            exec_side.repo_id,
            "main",
            first[2].id,
            exec_side.host1,
            exec_side.clock.now(),
            exec_side.clock.now() + timedelta(seconds=1),
        )
        assert expiring is not None
        exec_side.clock.advance(timedelta(seconds=2))
        later = exec_side.clock.now()
        assert (
            slots.acquire(
                exec_side.repo_id, "main", second[2].id, exec_side.host1, later, later + timedelta(days=1)
            )
            is not None
        )
        with pytest.raises(SkmError) as caught:
            slots.acquire(
                exec_side.repo_id,
                "main",
                second[2].id,
                exec_side.host2,
                exec_side.clock.now(),
                exec_side.clock.now() + timedelta(days=1),
            )
        assert caught.value.code.value == "INTEGRATION_HOST_MISMATCH"
        uow.commit()


def test_oldest_started_run_precedes_younger_task_position(exec_side):
    from contracts.execution.repository_fixtures import assignment as seed_assignment
    from skm.modules.execution.ports import AttemptRepository

    older, _, task = scheduler_pair(exec_side, position=10)
    with exec_side.uow() as uow:
        current = uow.repo(TaskRepository).get(task.id)
        attempt = uow.repo(AttemptRepository).get(current.current_attempt_id)
        assignment = seed_assignment(exec_side, uow, attempt)
        uow.repo(AssignmentRepository).save(
            replace(assignment, priority=10), expected_version=assignment.row_version
        )
        uow.commit()
    exec_side.clock.advance(timedelta(seconds=1))
    younger, _, _, _ = make_case(exec_side)
    winner = claim(exec_side)
    assert older.started_at < younger.started_at
    assert task.position == 10
    assert winner["run_id"] == str(older.id)
    assert winner["assignment_id"] == str(assignment.id)


def scheduler_pair(side, *, position=1):
    from contracts.execution.seed_helpers import seed_attempt, seed_task
    from skm.modules.execution.domain.attempt import AttemptState
    from skm.modules.execution.domain.task import PathPattern, TaskKind
    from unit.execution.application.test_background_commands import cancel_available

    run, first, owner, assignment = make_case(side)
    cancel_available(side, assignment)
    with side.uow() as uow:
        tasks = uow.repo(TaskRepository)
        first = replace(
            first,
            declared_write_scope=(PathPattern("repo", "src/first/**"),),
            row_version=first.row_version + 1,
        )
        tasks.save(first, expected_version=first.row_version - 1)
        second = seed_task(
            side, uow, run.id, display_key="P1.1/U2", kind=TaskKind.FOLLOWUP, position=position
        )
        attempt = seed_attempt(
            side, uow, run.id, second.id, state=AttemptState.PREPARING, continuation=owner.continuation
        )
        tasks.save(
            replace(
                second,
                current_attempt_id=attempt.id,
                attempt_count=1,
                declared_write_scope=(PathPattern("repo", "src/second/**"),),
                row_version=second.row_version + 1,
            ),
            expected_version=second.row_version,
        )
        uow.commit()
    return run, first, second


@pytest.mark.parametrize("limit", [1, 10])
def test_scheduler_skips_budget_refusal_before_limit_and_capacity(exec_side, limit):
    from decimal import Decimal

    from skm.modules.execution.application.commands import schedule_ready_tasks
    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
    from skm.modules.execution.ports import BudgetRepository
    from unit.execution.application._support import set_setting
    from unit.execution.application.test_background_commands import execute

    run, denied, eligible = scheduler_pair(exec_side)
    set_setting(exec_side, "execution.parallel.max_units", 1)
    with exec_side.uow() as uow:
        account = BudgetAccount(
            exec_side.new_id(),
            run.id,
            "task",
            denied.id,
            BudgetDimension.TOKENS,
            Decimal(1),
            Decimal(1),
            Decimal(0),
            1,
        )
        uow.repo(BudgetRepository).add_accounts((account,))
        uow.commit()
    result = execute(exec_side, schedule_ready_tasks, {"run_ids": [str(run.id)], "limit": limit})
    assert [a["task_id"] for a in result["scheduled"]] == [str(eligible.id)]
    with exec_side.uow(readonly=True) as uow:
        assert all(
            a.state is not AssignmentState.AVAILABLE
            for a in uow.repo(AssignmentRepository).for_attempt(denied.current_attempt_id)
        )
        assert uow.repo(TaskRepository).get(denied.id).attempt_count == 1


def test_scheduler_tick_limit_never_splits_a_required_batch(exec_side):
    from skm.modules.execution.application.commands import schedule_ready_tasks
    from skm.modules.execution.domain.task_graph import EdgeKind, TaskEdge
    from unit.execution.application.test_background_commands import execute

    run, first, second = scheduler_pair(exec_side)
    with exec_side.uow() as uow:
        uow.repo(TaskRepository).add_many(
            (), (TaskEdge(run.id, second.id, first.id, EdgeKind.BATCH, frozenset()),)
        )
        uow.commit()
    assert execute(exec_side, schedule_ready_tasks, {"run_ids": [str(run.id)], "limit": 1})["scheduled"] == []
    result = execute(exec_side, schedule_ready_tasks, {"run_ids": [str(run.id)], "limit": 2})
    assert {a["task_id"] for a in result["scheduled"]} == {str(first.id), str(second.id)}


@pytest.mark.parametrize("foreign_writer", [False, True])
def test_scheduler_checkout_continuation_excludes_only_its_own_environment(exec_side, foreign_writer):
    from skm.modules.execution.application.commands import schedule_ready_tasks
    from skm.modules.execution.ports import EnvironmentRepository
    from unit.execution.application._support import set_setting
    from unit.execution.application.test_background_commands import cancel_available, execute

    set_setting(exec_side, "execution.environment.kind", "existing_checkout")
    run, task, attempt, assignment = make_case(exec_side)
    owner = make_case(exec_side)[2] if foreign_writer else attempt
    cancel_available(exec_side, assignment)
    with exec_side.uow() as uow:
        environments = uow.repo(EnvironmentRepository)
        seed_existing_checkout(exec_side, uow, owner)
        assert environments.busy_existing_checkout_repos(run.project_id) == frozenset({exec_side.repo_id})
        uow.commit()
    result = execute(exec_side, schedule_ready_tasks, {"run_ids": [str(run.id)], "limit": 1})
    assert [a["task_id"] for a in result["scheduled"]] == ([] if foreign_writer else [str(task.id)])


def seed_existing_checkout(side, uow, owner):
    from skm.modules.execution.domain.environment import (
        BaselineEntry,
        EnvironmentKind,
        EnvironmentState,
        ExecutionEnvironment,
        attempt_branch,
    )
    from skm.modules.execution.ports import AttemptRepository, EnvironmentRepository

    env = ExecutionEnvironment(
        side.new_id(),
        owner.id,
        side.host1,
        EnvironmentKind.EXISTING_CHECKOUT,
        (BaselineEntry("repo", side.repo_id, "1" * 40, "1" * 40, None),),
        attempt_branch(owner.id),
        f"/owned/{owner.id}",
        EnvironmentState.READY,
        side.clock.now(),
        None,
        None,
    )
    environments, attempts = uow.repo(EnvironmentRepository), uow.repo(AttemptRepository)
    environments.upsert(env)
    attempts.save(replace(owner, environment_id=env.id), expected_version=attempts.version(owner.id))
    assert environments.for_attempt(owner.id).kind is EnvironmentKind.EXISTING_CHECKOUT
    return env


def test_l3_g4_cannot_reuse_a_lost_attempts_busy_checkout(exec_side):
    from skm.modules.execution.application._primitives import server_context
    from skm.modules.execution.application.commands import expire_leases, schedule_ready_tasks
    from skm.modules.execution.domain.attempt import AttemptState
    from skm.modules.execution.domain.environment import EnvironmentState
    from skm.modules.execution.domain.task import TaskStatus
    from skm.modules.execution.ports import AttemptRepository, EnvironmentRepository, RunRepository
    from unit.execution.application._support import context, set_setting
    from unit.execution.application.test_background_commands import SYSTEM, execute

    set_setting(exec_side, "execution.environment.kind", "existing_checkout")
    run, task, lost, _ = make_case(exec_side)
    with exec_side.uow() as uow:
        env = seed_existing_checkout(exec_side, uow, lost)
        lost = uow.repo(AttemptRepository).get(lost.id)
        expire_leases.handoff_lost(
            uow,
            server_context(context(exec_side, uow, run, actor=SYSTEM), uow),
            run,
            task,
            lost,
        )
        assert uow.repo(AttemptRepository).get(lost.id).state is AttemptState.OWNERSHIP_LOST
        assert uow.repo(TaskRepository).get(task.id).current_attempt_id == lost.id
        uow.commit()
    payload = {"run_ids": [str(run.id)], "limit": 1}
    for _ in range(2):
        assert execute(exec_side, schedule_ready_tasks, payload)["scheduled"] == []
        with exec_side.uow(readonly=True) as uow:
            current = uow.repo(TaskRepository).get(task.id)
            assert current.current_attempt_id is None  # G4 ran; the constructor must still wait for K13.
            assert current.status is TaskStatus.READY
            assert current.attempt_count == 1
            attempts = uow.repo(AttemptRepository).list_for_task(task.id)
            assert [a.id for a in attempts] == [lost.id]
            assert attempts[0].continuation is None
            assert attempts[0].state is AttemptState.OWNERSHIP_LOST
            assert all(
                a.state not in {AssignmentState.AVAILABLE, AssignmentState.LEASED}
                for a in uow.repo(AssignmentRepository).for_attempt(lost.id)
            )
            assert uow.repo(EnvironmentRepository).busy_existing_checkout_repos(run.project_id)
    with exec_side.uow() as uow:
        now = uow.repo(RunRepository).now()
        uow.repo(EnvironmentRepository).upsert(
            replace(env, state=EnvironmentState.REMOVED, discarded_at=now, removed_at=now)
        )
        assert not uow.repo(EnvironmentRepository).busy_existing_checkout_repos(run.project_id)
        uow.commit()
    result = execute(exec_side, schedule_ready_tasks, payload)
    assert [a["task_id"] for a in result["scheduled"]] == [str(task.id)]
    with exec_side.uow(readonly=True) as uow:
        current = uow.repo(TaskRepository).get(task.id)
        assert current.attempt_count == 2
        assert current.current_attempt_id != lost.id
        attempts = uow.repo(AttemptRepository).list_for_task(task.id)
        assert len(attempts) == 2
        assert attempts[1].state is AttemptState.PREPARING
        assert attempts[1].continuation.cause.advance_rule == "A1"
