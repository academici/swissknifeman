"""Late evidence and lawful operator uploads against real memory/PostgreSQL bus and persistence."""

import pytest

from contracts.execution._worker_protocol_support import worker_claim
from contracts.execution.test_step_notes import owned_agent
from integration.artifacts.test_upload_flow import add_file_dto
from skm.kernel.errors import SkmError
from skm.modules.execution import public as execution
from skm.modules.execution.generated.commands import CancelRun
from skm.modules.execution.ports import (
    AcceptanceRepository,
    EffectRepository,
    ExecutionQueries,
    OutputRepository,
    StepRepository,
)


def manifest(side):
    from skm.modules.execution.domain.output import OutputMount, output_tree_digest

    raw = {
        "algorithm": "skm-output-v2",
        "mounts": [
            {
                "mount": "repo",
                "repository_id": str(side.repo_id),
                "object_format": "sha1",
                "base_commit": "1" * 40,
                "head_commit": "2" * 40,
                "tree_sha": "3" * 40,
            }
        ],
        "changed_paths": [],
        "outside_write_scope": [],
        "excluded_paths": [],
        "tree_digest": "sha256:" + "1" * 64,
        "patch_file_version_id": None,
        "diff_stats": {"files": 0, "insertions": 0, "deletions": 0},
        "empty": True,
    }
    mount = OutputMount("repo", side.repo_id, "sha1", "1" * 40, "2" * 40, "3" * 40)
    raw["tree_digest"] = output_tree_digest((mount,), ())
    return raw


@pytest.mark.parametrize("seal_first", [False, True])
def test_late_result_after_cancel_cannot_add_observation_approval_or_effect(exec_side, seal_first):
    side = exec_side
    run, task, attempt, claimed, stage, step, _, _, _ = owned_agent(side)
    seal = None
    if seal_first:
        seal = side.worker1_client.dispatch(
            execution.SealOutput(
                claim=worker_claim(side, claimed),
                stage_record_id=str(stage.id),
                step_id=str(step.id),
                source="executor",
                manifest=manifest(side),
            ),
            idempotency_key=f"seal:{side.new_id()}",
        )
    side.client.dispatch(CancelRun(run.id, "cancel before late terminal"))
    with side.uow(readonly=True) as uow:
        before = uow.repo(StepRepository).get(step.id)
        acceptance = uow.repo(AcceptanceRepository).decisions_for_task(task.id)
        effects = uow.repo(EffectRepository).unresolved(limit=100)
    with pytest.raises(SkmError) as caught:
        side.worker1_client.dispatch(
            execution.RecordStageResult(
                claim=worker_claim(side, claimed),
                stage_record_id=str(stage.id),
                outcome_kind="result_invalid",
                outcome={"error_code": "RESULT_INVALID"},
                observations=[{"step_id": str(step.id), "observation": None}],
            ),
            idempotency_key=f"late:{side.new_id()}",
        )
    assert caught.value.code.value == "LEASE_LOST"
    with side.uow(readonly=True) as uow:
        assert uow.repo(StepRepository).get(step.id) == before
        assert uow.repo(AcceptanceRepository).decisions_for_task(task.id) == acceptance
        assert uow.repo(EffectRepository).unresolved(limit=100) == effects
        if seal is not None:
            assert str(uow.repo(OutputRepository).latest(attempt.id).id) == seal["output_id"]


def test_lawful_operator_artifact_upload_does_not_reopen_terminal_step_or_add_history_edge(exec_side):
    side = exec_side
    run, _, _, _, _, step, _, _, _ = owned_agent(side)
    side.client.dispatch(CancelRun(run.id, "operator evidence after termination"))
    with side.uow(readonly=True) as uow:
        terminal = uow.repo(StepRepository).get(step.id)
        cursor = uow.repo(ExecutionQueries).head_run_seq(run.id)
    content = b"operator supplied recovery evidence"
    staged = side.client.upload_blob(side.ws, [content], size=len(content), media_type="text/plain")
    uploaded = side.client.dispatch(
        add_file_dto(side.ws, side.proj, staged), idempotency_key=f"operator:{side.new_id()}"
    )
    assert uploaded.file_version_id is not None
    with side.uow(readonly=True) as uow:
        assert uow.repo(StepRepository).get(step.id) == terminal
        assert uow.repo(ExecutionQueries).head_run_seq(run.id) == cursor
