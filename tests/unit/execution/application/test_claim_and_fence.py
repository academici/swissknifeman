"""Worker identity, workspace scope, receipt and capabilities boundaries."""

from datetime import timedelta
from typing import Any

import pytest

from contracts.execution.harness import exec_side as exec_side
from contracts.execution.test_worker_protocol import begin, claim, make_case, worker_claim
from skm.kernel.errors import SkmError
from skm.modules.execution import public as execution
from skm.modules.execution.ports import AssignmentRepository, AttemptRepository, StageRepository
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import side as side


def test_nothing_to_claim_is_waiting_and_never_cached_in_idempotency_store(side: Any) -> None:
    from skm.application_bus.middleware import is_waiting
    from skm.modules.workspace import public as workspace

    side.worker1_client.dispatch(workspace.RecordWorkerHeartbeat(side.worker1, None))
    key = f"longpoll:{side.new_id()}"
    empty = claim(side, key=key)
    assert empty["outcome"] == "nothing_to_claim"
    assert is_waiting(empty)

    _, _, attempt, assignment = make_case(side)
    claimed = claim(side, key=key)
    assert claimed["assignment_id"] == str(assignment.id)
    assert claimed["attempt_id"] == str(attempt.id)
    assert not is_waiting(claimed)
    assert claim(side, key=key) == claimed
    with side.uow(readonly=True) as uow:
        assert uow.repo(AssignmentRepository).get(assignment.id).last_fencing_token == 1


def test_claim_receipt_replays_one_fence(side: Any) -> None:
    _, _, attempt, assignment = make_case(side)
    key = f"claim:{side.new_id()}"
    first = claim(side, key=key)
    assert claim(side, key=key) == first
    with side.uow(readonly=True) as uow:
        row = uow.repo(AssignmentRepository).get(assignment.id)
        assert row.last_fencing_token == 1
        assert uow.repo(AttemptRepository).get(attempt.id).continuation is not None


@pytest.mark.parametrize("field", ["worker_id", "host_id", "workspace_id"])
def test_claim_rejects_foreign_worker_registration(side: Any, field: str) -> None:
    make_case(side)
    raw = execution.ClaimAssignment(
        worker_id=str(side.worker1),
        host_id=str(side.host1),
        workspace_id=str(side.ws),
        offer={
            "capabilities": ["codex_cli"],
            "labels": ["linux"],
            "environment_kinds": ["git_worktree"],
            "isolation_profiles": ["landlock"],
        },
    )
    raw[field] = str(side.new_id())
    with pytest.raises(SkmError):
        side.worker1_client.dispatch(raw, idempotency_key=f"foreign:{side.new_id()}")


def test_expired_lease_cannot_begin_or_renew(side: Any) -> None:
    _, _, attempt, _ = make_case(side)
    claimed = claim(side)
    side.clock.advance(timedelta(hours=1))
    with pytest.raises(SkmError) as caught:
        begin(side, claimed)
    assert caught.value.code.value == "LEASE_LOST"
    with pytest.raises(SkmError) as caught:
        side.worker1_client.dispatch(
            execution.RenewLease(claim=worker_claim(side, claimed)), idempotency_key=f"renew:{side.new_id()}"
        )
    assert caught.value.code.value == "LEASE_LOST"
    with side.uow(readonly=True) as uow:
        assert not uow.repo(StageRepository).history(attempt.id).entries


def test_retry_later_reissue_increments_fence_and_old_claim_cannot_begin(side: Any) -> None:
    _, _, attempt, _ = make_case(side)
    old = claim(side)
    side.worker1_client.dispatch(
        execution.ReleaseAssignment(
            claim=worker_claim(side, old), reason="retry_later", retain_environment=True
        ),
        idempotency_key=f"release:{side.new_id()}",
    )
    side.clock.advance(timedelta(seconds=6))
    current = claim(side)
    assert current["fencing_token"] > old["fencing_token"]
    assert current["attempt_id"] == str(attempt.id)
    with pytest.raises(SkmError) as caught:
        begin(side, old)
    assert caught.value.code.value == "LEASE_LOST"
    assert begin(side, current)["outcome"] == "ready"


def test_parallel_ceiling_is_checked_before_any_candidate_lease(exec_side: Any, monkeypatch: Any) -> None:
    from dataclasses import replace

    from contracts.execution.seed_helpers import seed_attempt, seed_task
    from skm.modules.execution.application.commands import claim_assignment
    from skm.modules.execution.domain.attempt import ContinuationCause, select_stage
    from skm.modules.execution.domain.task import TaskKind
    from skm.modules.execution.ports import TaskRepository
    from unit.execution.application._support import set_setting

    side = exec_side
    set_setting(side, "execution.parallel.max_units", 1)
    run, _, first_attempt, first_assignment = make_case(side)
    first = claim(side)
    with side.uow() as uow:
        task = seed_task(side, uow, run.id, kind=TaskKind.FOLLOWUP, display_key="FU-2")
        attempt = seed_attempt(side, uow, run.id, task.id)
        repo = uow.repo(AttemptRepository)
        attempt = select_stage(
            attempt,
            cause=ContinuationCause("run_start", "A1"),
            stage=first_attempt.continuation.stage,
            continuation_id=side.new_id(),
        )
        repo.save(attempt, expected_version=repo.version(attempt.id))
        uow.repo(TaskRepository).save(
            replace(task, current_attempt_id=attempt.id, attempt_count=1, row_version=2), expected_version=1
        )
        assignment = replace(first_assignment, id=side.new_id(), task_id=task.id, attempt_id=attempt.id)
        uow.repo(AssignmentRepository).add(assignment)
        uow.commit()
    calls = []
    original = claim_assignment.require_future_admission

    def before_lease(uow, ctx, run, task, values):
        rows = uow.repo(AssignmentRepository).for_attempt(task.current_attempt_id)
        assert all(a.state.value == "available" for a in rows)
        assert all(uow.repo(AssignmentRepository).lease(a.id) is None for a in rows)
        calls.append(task.id)
        return original(uow, ctx, run, task, values)

    monkeypatch.setattr(claim_assignment, "require_future_admission", before_lease)
    assert claim(side)["outcome"] == "nothing_to_claim"
    assert calls == [task.id]
    with side.uow(readonly=True) as uow:
        assert uow.repo(AssignmentRepository).get(assignment.id).last_fencing_token == 0
        assert uow.repo(AssignmentRepository).lease(assignment.id) is None
        assert (
            uow.repo(AssignmentRepository).lease(first_assignment.id).fencing_token == first["fencing_token"]
        )
        assert uow.repo(TaskRepository).get(task.id).status.value == "ready"


def test_claim_of_a_task_with_an_undeclared_write_scope_grants_no_writes(side: Any) -> None:
    from dataclasses import replace

    from skm.modules.execution.ports import TaskRepository

    _, task, _, assignment = make_case(side)
    with side.uow() as uow:
        current = uow.repo(TaskRepository).get(task.id)
        uow.repo(TaskRepository).save(
            replace(current, declared_write_scope=None, row_version=current.row_version + 1),
            expected_version=current.row_version,
        )
        uow.commit()
    claimed = claim(side)
    assert claimed["assignment_id"] == str(assignment.id)
    assert claimed["task"]["declared_write_scope"] == []
    assert begin(side, claimed)["stage_record_id"]
