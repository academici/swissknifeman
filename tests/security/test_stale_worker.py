"""Every worker mutation rejects stale fences before recording evidence or outputs."""

from datetime import timedelta
from typing import Any

import pytest

from contracts.execution.test_step_notes import owned_agent
from contracts.execution.test_worker_protocol import worker_claim
from skm.kernel.errors import SkmError
from skm.modules.execution import public as execution
from skm.modules.execution.generated.commands import CancelRun
from skm.modules.execution.ports import OutputRepository, StageRepository
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import side as side


@pytest.mark.parametrize("operation", ["begin", "renew", "result", "release", "failure"])
def test_stale_claim_cannot_mutate_worker_state(side: Any, operation: str) -> None:
    _, _, attempt, claimed, stage, _, _, _, _ = owned_agent(side)
    raw = {**worker_claim(side, claimed), "fencing_token": claimed["fencing_token"] + 1}
    commands = {
        "begin": execution.BeginStage(
            claim=raw, stage_id="execute", round_no=1, input_digest=stage.input_digest
        ),
        "renew": execution.RenewLease(claim=raw),
        "result": execution.RecordStageResult(
            claim=raw,
            stage_record_id=str(stage.id),
            outcome_kind="result_invalid",
            outcome={"error_code": "RESULT_INVALID"},
        ),
        "release": execution.ReleaseAssignment(claim=raw, reason="waiting", retain_environment=True),
        "failure": execution.ReportAttemptFailure(
            claim=raw,
            stage_record_id=str(stage.id),
            error_class="worker_shutdown",
            detail="shutdown",
            worktree_dirty=False,
        ),
    }
    with pytest.raises(SkmError) as caught:
        side.worker1_client.dispatch(commands[operation], idempotency_key=f"stale:{side.new_id()}")
    assert caught.value.code.value == "LEASE_LOST"
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(stage.id).finished_at is None
        assert uow.repo(OutputRepository).latest(attempt.id) is None


def test_context_owner_guard_rejects_expiry_and_cancellation(side: Any) -> None:
    run, _, attempt, claimed, _, step, _, _, _ = owned_agent(side)
    raw = worker_claim(side, claimed)

    def guard() -> None:
        with side.uow() as uow:
            execution.require_current_context_owner(
                uow,
                side.worker1_client._actor,
                f"step:{step.id}",
                assignment_id=step_id(raw["assignment_id"]),
                attempt_id=attempt.id,
                worker_id=side.worker1,
                fencing_token=raw["fencing_token"],
                now=side.clock.now(),
            )

    guard()
    side.clock.advance(timedelta(minutes=5))
    with pytest.raises(SkmError) as caught:
        guard()
    assert caught.value.code.value == "LEASE_LOST"
    side.client.dispatch(CancelRun(run.id, "stop"))
    with pytest.raises(SkmError):
        guard()


def step_id(value: str) -> Any:
    from uuid import UUID

    return UUID(value)
