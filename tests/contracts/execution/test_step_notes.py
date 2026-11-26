"""Step notes derive their live claim from the assignment token; no lifecycle events."""

from dataclasses import replace
from typing import Any

import pytest

from contracts.execution.harness import PEPPER
from contracts.execution.seed_helpers import seed_stage, seed_step
from contracts.execution.test_worker_protocol import claim, make_case, worker_claim
from skm.kernel.errors import SkmError
from skm.kernel.ports_uow import Surface
from skm.modules.access import public as access
from skm.modules.execution import public as execution
from skm.modules.execution.application._stage_preparation import issue_step_token
from skm.modules.execution.application._worker_protocol import lock_fenced_context
from skm.modules.execution.domain.attempt import consume_stage
from skm.modules.execution.domain.stage_record import StageState
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.ports import AttemptRepository, ExecutionQueries, StepRepository, TaskRepository
from unit.execution.application._support import context


def owned_agent(side: Any) -> Any:
    # The test seeds its own agent stage after claiming a synthetic preparation assignment.
    run, task, attempt, _ = make_case(side, env=True)
    claimed = claim(side)
    sid = side.new_id()
    manifest_id = side.make_final_manifest(step_ref=f"step:{sid}")
    secret = str(access.generate_secret(lambda n: bytes([31]) * n))
    with side.uow() as uow:
        attempt, _ = consume_stage(attempt, continuation_id=attempt.continuation.continuation_id)
        uow.repo(AttemptRepository).save(
            attempt, expected_version=uow.repo(AttemptRepository).version(attempt.id)
        )
        task = replace(
            task,
            status=TaskStatus.EXECUTING,
            required_host_id=side.host1,
            row_version=uow.repo(TaskRepository).get(task.id).row_version + 1,
        )
        uow.repo(TaskRepository).save(task, expected_version=task.row_version - 1)
        stage = seed_stage(side, uow, attempt, state=StageState.CONTEXT_DRAFT)
        step = seed_step(side, uow, attempt, stage, manifest_id=manifest_id, step_id=sid)
        ctx = context(side, uow, run, actor=side.worker1_client._actor)
        fenced = lock_fenced_context(uow, ctx, worker_claim(side, claimed))
        token = issue_step_token(uow, ctx, fenced, step, secret)
        actor = access.authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())
        uow.commit()
    return (
        run,
        task,
        attempt,
        claimed,
        stage,
        step,
        side.app.client(actor=actor, surface=Surface.MCP),
        token,
        secret,
    )


def test_note_appends_once_without_lifecycle_event(exec_side: Any) -> None:
    side = exec_side
    run, _, _, _, _, step, runtime, _, _ = owned_agent(side)
    with side.uow(readonly=True) as uow:
        before = uow.repo(ExecutionQueries).head_run_seq(run.id)
    command = execution.RecordStepNote(step_id=str(step.id), kind="progress", text="Reading pinned input")
    key = f"note:{side.new_id()}"
    first = runtime.dispatch(command, idempotency_key=key)
    assert runtime.dispatch(command, idempotency_key=key) == first
    with side.uow(readonly=True) as uow:
        assert len(uow.repo(StepRepository).notes_for_step(step.id)) == 1
        assert uow.repo(ExecutionQueries).head_run_seq(run.id) == before


def test_note_rejects_foreign_step_and_management_token(exec_side: Any) -> None:
    side = exec_side
    _, _, _, _, _, step, runtime, _, _ = owned_agent(side)
    with pytest.raises(SkmError):
        runtime.dispatch(
            execution.RecordStepNote(step_id=str(side.new_id()), kind="progress", text="foreign"),
            idempotency_key=f"note:{side.new_id()}",
        )
    with pytest.raises(SkmError):
        side.worker1_client.dispatch(
            execution.RecordStepNote(step_id=str(step.id), kind="progress", text="no subprocess binding"),
            idempotency_key=f"note:{side.new_id()}",
        )
    with side.uow(readonly=True) as uow:
        assert not uow.repo(StepRepository).notes_for_step(step.id)
