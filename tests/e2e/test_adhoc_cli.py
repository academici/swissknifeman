"""Exercise the new command lines against a fully composed embedded control plane."""

import json
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from contracts.execution.harness import ExecSide
from e2e.test_execution_cli import invoke, result
from skm.kernel.ids import RunId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import PrincipalRepository
from skm.modules.access.public import SYSTEM_ACTOR, Role, grant_initial_membership
from skm.modules.execution.application._state import load_state
from skm.modules.execution.application.commands.schedule_ready_tasks import ScheduleReadyTasks
from skm.modules.execution.ports import AttemptRepository, TaskRepository
from support.adhoc import adhoc_side as adhoc_side
from support.adhoc import workflow
from support.seed import SEED


def test_exec_and_pipe_pin_default_and_supplied_workflows(adhoc_side: ExecSide, tmp_path: Path) -> None:
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(workflow()))
    custom = result(adhoc_side, "pipe", str(path), "Check the docs.")
    default = result(adhoc_side, "exec", "Check the build metadata.")
    # Changing the source file after admission leaves the persisted workflow intact.
    path.write_text("{}")
    custom_id = RunId(UUID(custom["run_id"]))
    with adhoc_side.uow() as uow:
        now = adhoc_side.clock.now()
        uow.repo(PrincipalRepository).add(
            new_principal(
                principal_id=SYSTEM_ACTOR.principal_id,
                kind=SYSTEM_ACTOR.kind,
                display_name="system",
                created_by=None,
                now=now,
            )
        )
        grant_initial_membership(
            uow,
            scope_id=SEED.instance_id,
            principal_id=SYSTEM_ACTOR.principal_id,
            role=Role.OWNER,
            now=now,
        )
        uow.commit()
    scheduler = adhoc_side.app.client(actor=SYSTEM_ACTOR, surface=Surface.BACKGROUND)
    scheduler.dispatch(ScheduleReadyTasks.from_json({"run_ids": [str(custom_id)], "limit": 1}))
    with adhoc_side.uow(readonly=True) as uow:
        for started, expected in ((default, "adhoc-default"), (custom, "standalone-pipe")):
            (task,) = uow.repo(TaskRepository).list_for_run(RunId(UUID(started["run_id"])))
            _, pinned = load_state(uow, task.id)
            assert pinned.id == expected
            assert task.display_key == "ADHOC-1"
        (custom_task,) = uow.repo(TaskRepository).list_for_run(custom_id)
        assert custom_task.current_attempt_id is not None
        attempt = uow.repo(AttemptRepository).get(custom_task.current_attempt_id)
        assert attempt.continuation is not None
        assert attempt.continuation.kind == "stage"
        assert attempt.continuation.stage.stage_id == "setup"


def test_pipe_accepts_stdin_and_rejects_unknown_stage(
    adhoc_side: ExecSide, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from io import StringIO

    monkeypatch.setattr("sys.stdin", StringIO(json.dumps(workflow())))
    assert result(adhoc_side, "pipe", "-", "Check the docs.")["task_count"] == 1
    path = tmp_path / "bad.json"
    document = workflow()
    cast("list[JsonObject]", document["stage"])[1]["type"] = "shell"
    path.write_text(json.dumps(document))
    code, out, _ = invoke(adhoc_side, "pipe", str(path), "Check the docs.")
    assert code != 0
    assert json.loads(out)["error"]["code"] == "SCHEMA_INVALID"


def test_route_pick_and_context_commands(adhoc_side: ExecSide) -> None:
    picked = result(adhoc_side, "route", "pick", "executor")
    assert picked == result(adhoc_side, "runtime", "route", "executor")
    draft = result(
        adhoc_side,
        "context",
        "assemble",
        "--runtime",
        "codex_cli",
        "--model",
        "gpt-5",
        "--context-window",
        "32000",
    )
    identity = draft["manifest_id"]
    assert result(adhoc_side, "context", "explain", identity)["state"] == "draft"
    assert result(adhoc_side, "context", "diff", identity, identity)["counts"]["changed"] == 0
    step = str(adhoc_side.new_id())
    adhoc_side.make_final_manifest(step_ref=f"step:{step}")
    assert result(adhoc_side, "context", "explain", step, "--step")["state"] == "final"
    assert "counts" in result(adhoc_side, "context", "diff", identity, step, "--step")
