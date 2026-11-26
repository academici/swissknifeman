"""Worker management and assignment credentials have separate scope boundaries (S4/S5/S23)."""

from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import uuid5

import pytest

from contracts.context.harness import UNIT_ID
from contracts.execution.harness import ExecSide
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.seed_helpers import seed_attempt, seed_run, seed_stage, seed_step, seed_task
from contracts.execution.test_step_notes import owned_agent
from integration.api.test_worker_protocol import (
    CLAIM_PATH,
    WORKER_CAPABILITIES,
    bearer,
    claim_body,
    worker_api,
)
from integration.api.test_worker_protocol import worker_side as worker_side
from security.api.harness import BASE, TestClient
from security.test_blob_access import assert_private_output, denial_checks
from skm.kernel.ids import EntityId, WorkerId
from skm.modules.execution.domain.assignment import Assignment, AssignmentState, WorkerRequirements
from skm.modules.execution.domain.environment import EnvironmentKind
from skm.modules.execution.domain.ids import AssignmentId, StepId
from skm.modules.execution.domain.run import Run
from skm.modules.execution.domain.step import AttemptStep, StepState
from skm.modules.execution.domain.task import Task
from skm.modules.execution.ports import AssignmentRepository, StepRepository, TaskRepository
from skm.modules.workspace import public as workspace
from skm.modules.workspace.generated.documents import WorkerCapabilities
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

SCHEMAS = ("access", "workspace", "execution", "artifacts")
FOREIGN_RESULT = "private-same-workspace-step-result-4293"


def foreign_run_step(side: ExecSide) -> tuple[Run, Task, AttemptStep]:
    step_id = StepId(side.new_id())
    manifest = side.make_final_manifest(step_ref=f"step:{step_id}")
    with side.uow() as uow:
        run = seed_run(side, uow)
        task = seed_task(side, uow, run.id)
        attempt = seed_attempt(side, uow, run.id, task.id)
        stage = seed_stage(side, uow, attempt)
        step = seed_step(
            side,
            uow,
            attempt,
            stage,
            manifest_id=manifest,
            step_id=step_id,
            state=StepState.SUCCEEDED,
            result={"summary": FOREIGN_RESULT},
        )
        uow.commit()
    return run, task, step


def test_worker_cannot_claim_queued_work_in_foreign_project(
    worker_side: tuple[ExecSide, dict[str, str], dict[str, str]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    side, worker, owner = worker_side
    foreign = replace(side, ws=side.ws2, proj=side.proj2, plan1=side.plan2_ws2, rev1=side.rev_ws2)
    registered = cast(
        "workspace.RegisterWorkerResult",
        side.client.dispatch(
            workspace.RegisterWorker(
                side.ws2, side.host2, "foreign worker", WorkerCapabilities.from_json(WORKER_CAPABILITIES)
            )
        ),
    )
    foreign_worker_id = WorkerId(registered.worker_id)
    with side.uow() as uow:
        run = seed_run(foreign, uow)
        task = seed_task(foreign, uow, run.id, spec_entity_id=EntityId(uuid5(foreign.plan1, str(UNIT_ID))))
        attempt = seed_attempt(foreign, uow, run.id, task.id, worker_id=foreign_worker_id, host_id=side.host2)
        uow.repo(TaskRepository).save(
            replace(task, current_attempt_id=attempt.id, attempt_count=1, row_version=2), expected_version=1
        )
        assignment = Assignment(
            AssignmentId(side.new_id()),
            run.id,
            task.id,
            attempt.id,
            side.ws2,
            AssignmentState.AVAILABLE,
            side.clock.now(),
            WorkerRequirements(frozenset(), None, frozenset(), EnvironmentKind.GIT_WORKTREE, frozenset()),
            0,
            0,
            None,
            None,
            None,
            side.clock.now(),
            1,
        )
        uow.repo(AssignmentRepository).add(assignment)
        uow.commit()
    with side.uow(readonly=True) as uow:
        before = uow.repo(AssignmentRepository).get(assignment.id)

    with TestClient(worker_api(side), base_url=BASE) as api:
        for index, changes in enumerate(
            (
                {"workspace_id": str(side.ws2)},
                {
                    "workspace_id": str(side.ws2),
                    "host_id": str(side.host2),
                    "worker_id": str(foreign_worker_id),
                },
            )
        ):
            with denial_checks(
                side.app,
                tmp_path,
                dsn=side.dsn,
                schemas=SCHEMAS,
                capsys=capsys,
                private=(
                    str(assignment.id),
                    str(attempt.id),
                    str(run.id),
                    worker["Authorization"][7:],
                    owner["Authorization"][7:],
                ),
                audit=("execution.claim_assignment",),
            ) as check:
                response = api.post(
                    CLAIM_PATH,
                    json=claim_body(side, **changes),
                    headers={**worker, "Idempotency-Key": f"claim-{index}"},
                )
                check((response.text, response.headers))
            assert response.status_code in {403, 404}
            assert response.json()["code"] in {"FORBIDDEN", "NOT_FOUND"}
    with side.uow(readonly=True) as uow:
        assert uow.repo(AssignmentRepository).get(assignment.id) == before
        assert uow.repo(AssignmentRepository).lease(assignment.id) is None


def test_assignment_token_cannot_note_other_steps_or_read_other_runs(
    worker_side: tuple[ExecSide, dict[str, str], dict[str, str]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    side, worker, owner = worker_side
    run, _, attempt, _, stage, step, _, _, secret = owned_agent(side)
    sibling_id = StepId(side.new_id())
    manifest = side.make_final_manifest(step_ref=f"step:{sibling_id}")
    with side.uow() as uow:
        sibling = seed_step(side, uow, attempt, stage, manifest_id=manifest, step_id=sibling_id, seq=2)
        uow.commit()
    same_workspace, _, other_step = foreign_run_step(side)
    assert same_workspace.id != run.id
    assert same_workspace.workspace_id == run.workspace_id
    foreign = replace(side, ws=side.ws2, proj=side.proj2, plan1=side.plan2_ws2, rev1=side.rev_ws2)
    with side.uow() as uow:
        other_run = seed_run(foreign, uow)
        uow.commit()

    note = {"kind": "progress", "text": "private-cross-step-marker-5427"}
    headers = bearer(secret)
    markers = (
        note["text"],
        FOREIGN_RESULT,
        "Secret Plan",
        secret,
        worker["Authorization"][7:],
        owner["Authorization"][7:],
    )
    other_step_path = f"/api/v1/steps/{other_step.id}"
    with TestClient(worker_api(side), base_url=BASE) as api:
        own = api.get(f"/api/v1/runs/{run.id}", headers=headers)
        assert own.is_success, own.text
        assert api.get(f"/api/v1/steps/{step.id}", headers=headers).is_success
        owner_view = api.get(other_step_path, headers=owner)
        assert owner_view.is_success
        assert owner_view.json()["result"]["summary"] == FOREIGN_RESULT
        # The route binds both IDs to the assignment grant before dispatching the command.
        for target_run, target_step in (
            (run, sibling),
            (run, other_step),
            (same_workspace, other_step),
            (other_run, step),
        ):
            with denial_checks(
                side.app,
                tmp_path,
                dsn=side.dsn,
                schemas=SCHEMAS,
                capsys=capsys,
                private=markers,
            ) as check:
                denied = api.post(
                    f"/api/v1/runs/{target_run.id}/steps/{target_step.id}/notes",
                    json=note,
                    headers={**headers, "Idempotency-Key": f"note-{target_step.id}"},
                )
                check((denied.text, denied.headers))
            assert denied.status_code in {403, 404}
            assert denied.json()["code"] in {"FORBIDDEN", "NOT_FOUND"}
            assert "note_id" not in denied.json()
        for path, action in (
            (f"/api/v1/runs/{other_run.id}", "execution.get_run"),
            (f"/api/v1/runs/{same_workspace.id}", "execution.get_run"),
            (other_step_path, "execution.get_step"),
        ):
            with denial_checks(
                side.app,
                tmp_path,
                dsn=side.dsn,
                schemas=SCHEMAS,
                capsys=capsys,
                private=markers,
                audit=(action,),
            ) as check:
                denied = api.get(path, headers=headers)
                check((denied.text, denied.headers))
            assert denied.status_code in {403, 404}
            problem = denied.json()
            assert problem["code"] in {"FORBIDDEN", "NOT_FOUND"}
            assert problem.pop("instance") == path
            assert_private_output(problem, str(same_workspace.id), str(other_step.id))
    with side.uow(readonly=True) as uow:
        for item in (step, sibling, other_step):
            assert not uow.repo(StepRepository).notes_for_step(item.id)
