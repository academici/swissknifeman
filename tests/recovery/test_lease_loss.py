"""L1 and L3 recovery through PostgreSQL and the registered control-plane commands."""

from dataclasses import replace
from uuid import UUID

import psycopg
import pytest

from contracts.execution._worker_protocol_support import begin, make_case, worker_claim
from contracts.execution.seed_helpers import seed_output
from fixtures.execution.harness import (
    clean_test_database,
    expire,
    pg_session,
    recovery,
    recovery_claim,
    system_dispatch,
    test_database,
)
from fixtures.execution.protocol import agent, dispatch_result, finalize, handoff
from skm.kernel.errors import SkmError
from skm.modules.execution import public as execution
from skm.modules.execution.ports import AttemptRepository, OutputRepository, StageRepository, TaskRepository

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = pytest.mark.pg


@pytest.mark.parametrize("draft", [False, True])
def test_l1_expiry_preserves_cursor_outputs_and_attempt_charge(recovery, draft):
    side = recovery
    if draft:
        case = agent(side)
        task, attempt, old = case.task, case.attempt, case.claimed
    else:
        _run, task, attempt, _ = make_case(side)
        old = recovery_claim(side)
    with side.uow() as uow:
        output = seed_output(side, uow, attempt)
        current = uow.repo(AttemptRepository).get(attempt.id)
        uow.repo(AttemptRepository).save(
            replace(current, current_output_id=output.id),
            expected_version=uow.repo(AttemptRepository).version(attempt.id),
        )
        uow.commit()
    assert expire(side)["expired"] == 1
    assert system_dispatch(side, "expire_leases")["expired"] == 0
    fresh = recovery_claim(side)
    assert fresh["attempt_id"] == old["attempt_id"]
    assert fresh["assignment_id"] != old["assignment_id"]
    with pytest.raises(SkmError) as caught:
        side.worker1_client.dispatch(
            execution.RenewLease(claim=worker_claim(side, old)), idempotency_key=f"late:{side.new_id()}"
        )
    assert caught.value.code.value == "LEASE_LOST"
    with side.uow(readonly=True) as uow:
        saved = uow.repo(AttemptRepository).get(attempt.id)
        assert saved.current_output_id == output.id
        assert uow.repo(OutputRepository).get(output.id) == output
        assert uow.repo(TaskRepository).get(task.id).attempt_count == 1
        assert saved.continuation is not None
        if draft:
            assert saved.continuation.cause.advance_rule == "L1"
        else:
            assert saved.continuation == attempt.continuation
    if not draft:
        assert begin(side, fresh)["outcome"] == "ready"


def test_unconfirmed_active_runtime_becomes_ownership_lost_after_reap_barrier(recovery):
    side = recovery
    case = agent(side)
    finalize(side, case)
    handoff(side, case)
    expire(side)
    assert recovery_claim(side) == {"outcome": "nothing_to_claim"}
    with side.uow(readonly=True) as uow:
        saved = uow.repo(TaskRepository).get(case.task.id)
        assert saved.blocking_reason.code.value == "RECOVERING"
        assert uow.repo(StageRepository).get(UUID(case.ready["stage_record_id"])).finished_at
    with psycopg.connect(side.dsn) as conn:
        # Age the server-owned recovery deadline, not a guessed OS-cleanup bit.
        conn.execute(
            "UPDATE skm_execution.run_tasks SET blocking_reason = "
            "jsonb_set(blocking_reason, '{next_check_at}', "
            "to_jsonb((clock_timestamp()-interval '1 second')::text)) WHERE id=%s",
            (case.task.id,),
        )
    system_dispatch(side, "schedule_ready_tasks")
    with side.uow(readonly=True) as uow:
        assert uow.repo(AttemptRepository).get(case.attempt.id).state.value == "ownership_lost"
    with pytest.raises(SkmError):
        dispatch_result(side, case.claimed, case.ready)
