"""A committed Begin without final context is safely repeatable and cannot spawn."""

from uuid import UUID

import pytest

from contracts.execution._worker_protocol_support import begin
from fixtures.execution.harness import clean_test_database, pg_session, recovery, test_database
from fixtures.execution.protocol import agent, finalize, handoff
from skm.kernel.errors import SkmError
from skm.modules.context.ports import ContextRepository
from skm.modules.execution.ports import StageRepository, StepRepository
from support.fault_injection import FaultPlan, FaultPoint, FaultyClient, InjectedFault

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = pytest.mark.pg


def test_context_draft_restart_reuses_stage_and_does_not_start_runtime(recovery):
    side = recovery
    case = agent(side)
    first = case.ready
    replay = begin(side, case.claimed, secret=case.secret, key=case.begin_key)
    assert replay["stage_record_id"] == first["stage_record_id"]
    assert replay["step"]["step_id"] == first["step"]["step_id"]
    assert replay["step"]["context"]["draft"] == first["step"]["context"]["draft"]
    with pytest.raises(SkmError) as caught:
        handoff(side, case)
    assert caught.value.code.value == "CONTEXT_NOT_FINALIZED"
    with side.uow(readonly=True) as uow:
        step = uow.repo(StepRepository).get(UUID(first["step"]["step_id"]))
        assert uow.repo(ContextRepository).get(step.context_manifest_id).state.value == "draft"
        assert uow.repo(StageRepository).get(UUID(first["stage_record_id"])).runtime_started_at is None
        assert len(uow.repo(StageRepository).history(case.attempt.id).entries) == 1
    finalize(side, case)
    assert "refusal" not in handoff(side, case)


def test_response_loss_after_begin_commit_replays_same_secret_and_draft(recovery):
    from contracts.execution._worker_protocol_support import make_case, worker_claim
    from fixtures.execution.harness import recovery_claim
    from skm.modules.execution import public as execution

    side = recovery
    _, _, attempt, _ = make_case(side)
    claimed = recovery_claim(side)
    command = execution.BeginStage(
        claim=worker_claim(side, claimed),
        stage_id="prepare",
        round_no=1,
        input_digest=claimed["instruction"]["input_digest"],
    )
    client = FaultyClient(side.worker1_client, FaultPlan({FaultPoint.CLIENT_AFTER_SERVER_COMMIT: 1}))
    key = f"lost-begin:{side.new_id()}"
    with pytest.raises(InjectedFault):
        client.dispatch(command, idempotency_key=key)
    first = client.dispatch(command, idempotency_key=key)
    assert side.worker1_client.dispatch(command, idempotency_key=key) == first
    with side.uow(readonly=True) as uow:
        assert len(uow.repo(StageRepository).history(attempt.id).entries) == 1
