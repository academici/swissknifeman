"""Assignment secrets cannot become worker credentials or move across steps."""

from typing import Any

import pytest

from contracts.execution.harness import PEPPER
from contracts.execution.test_step_notes import owned_agent
from contracts.execution.test_worker_protocol import worker_claim
from skm.kernel.errors import SkmError
from skm.modules.access import public as access
from skm.modules.execution import public as execution
from skm.modules.execution.application._stage_preparation import issue_step_token
from skm.modules.execution.application._worker_protocol import lock_fenced_context
from skm.modules.execution.ports import StepRepository
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import context
from unit.execution.application._support import side as side
from unit.execution.application.test_result_retry import report


@pytest.mark.parametrize("command", ["claim", "result", "seal"])
def test_assignment_token_cannot_invoke_worker_protocol(side: Any, command: str) -> None:
    _, _, _, claimed, stage, step, runtime, _, _ = owned_agent(side)
    raw = worker_claim(side, claimed)
    operations = {
        "claim": execution.ClaimAssignment(
            worker_id=str(side.worker1),
            host_id=str(side.host1),
            workspace_id=str(side.ws),
            offer={
                "capabilities": [],
                "labels": [],
                "environment_kinds": ["git_worktree"],
                "isolation_profiles": [],
            },
        ),
        "result": execution.RecordStageResult(
            claim=raw,
            stage_record_id=str(stage.id),
            outcome_kind="success",
            outcome={"step_id": str(step.id), "role_result": {}},
        ),
        "seal": execution.SealOutput(
            claim=raw,
            stage_record_id=str(stage.id),
            source="executor",
            step_id=str(step.id),
            manifest={
                "algorithm": "skm-output-v2",
                "mounts": [],
                "changed_paths": [],
                "tree_digest": "sha256:" + "1" * 64,
                "outside_write_scope": [],
                "excluded_paths": [],
                "patch_file_version_id": None,
                "diff_stats": {"files": 0, "insertions": 0, "deletions": 0},
                "empty": True,
            },
        ),
    }
    with pytest.raises(SkmError) as caught:
        runtime.dispatch(operations[command], idempotency_key=f"forbidden:{side.new_id()}")
    assert caught.value.code.value == "FORBIDDEN"


def test_terminal_stage_revokes_secret_and_cannot_issue_another_for_same_step(side: Any) -> None:
    run, _, _, claimed, stage, step, runtime, _, secret = owned_agent(side)
    report(side, claimed, stage, step, {})
    with pytest.raises(SkmError):
        runtime.dispatch(
            execution.RecordStepNote(step_id=str(step.id), kind="progress", text="late"),
            idempotency_key=f"note:{side.new_id()}",
        )
    with side.uow() as uow:
        with pytest.raises(SkmError):
            access.authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())
        ctx = context(side, uow, run, actor=side.worker1_client._actor)
        fenced = lock_fenced_context(uow, ctx, worker_claim(side, claimed))
        with pytest.raises(SkmError):
            issue_step_token(uow, ctx, fenced, step, str(access.generate_secret(lambda n: b"Q" * n)))
    with side.uow(readonly=True) as uow:
        assert not uow.repo(StepRepository).notes_for_step(step.id)
