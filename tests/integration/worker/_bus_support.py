"""Admitted stage fixtures; all results, prompts and continuations use the real bus."""

import atexit
import functools
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from contracts.context.harness import UNIT_ID, default_work_policy
from contracts.execution._worker_protocol_support import claim, make_case
from contracts.execution.seed_helpers import seed_stage, seed_step
from skm.adapters.git.runner import GitRunner
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.context import public as context
from skm.modules.context.domain.request import (
    ContextRequest,
    ExecutionBlocks,
    PermissionsSummary,
    RunParams,
    RuntimeTarget,
    StepPurpose,
)
from skm.modules.execution.domain.attempt import AttemptState, consume_stage
from skm.modules.execution.domain.environment import (
    BaselineEntry,
    EnvironmentKind,
    EnvironmentState,
    ExecutionEnvironment,
    attempt_branch,
)
from skm.modules.execution.domain.stage_record import StageState
from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.domain.task import PathPattern, ReviewMode, Task, TaskKind, TaskStatus
from skm.modules.execution.ports import (
    AttemptRepository,
    EnvironmentRepository,
    StageRepository,
    TaskRepository,
)
from skm.platform.config.store import ConfigStore, ScopeTree


def required_task(side, uow, run_id):
    # Seed immutable review_mode at creation, just as publication would do.
    task = Task(
        id=side.new_id(),
        run_id=run_id,
        workspace_id=side.ws,
        kind=TaskKind.UNIT,
        spec_entity_id=UNIT_ID,
        display_key="P1.1/U1",
        origin=None,
        position=0,
        status=TaskStatus.READY,
        work_kind="code",
        review_mode=ReviewMode.REQUIRED,
        review_profile=None,
        declared_write_scope=(PathPattern("repo", "src/**"),),
        required_host_id=None,
        current_attempt_id=None,
        accepted_attempt_id=None,
        accepted_output_id=None,
        check_fix_rounds=0,
        review_rounds=0,
        attempt_count=0,
        blocking_reason=None,
        row_version=1,
    )
    uow.repo(TaskRepository).add_many((task,), ())
    return task


@functools.lru_cache(maxsize=1)
def _baseline_template() -> tuple[Path, str]:
    tpl = Path(tempfile.mkdtemp(prefix="skm-bus-tpl-"))
    atexit.register(shutil.rmtree, tpl, ignore_errors=True)
    (tpl / "src").mkdir()
    (tpl / "src/app.py").write_text("answer = 0\n")
    (tpl / "AGENTS.md").write_text("HOST-INSTRUCTIONS: check the real answer.\n")
    git = GitRunner()
    git.run(tpl, ["init", "--initial-branch=main"])
    git.run(tpl, ["add", "."])
    git.run_bytes(
        tpl,
        ["commit", "-m", "baseline"],
        env={
            "GIT_AUTHOR_NAME": "Worker test",
            "GIT_AUTHOR_EMAIL": "worker@example.invalid",
            "GIT_COMMITTER_NAME": "Worker test",
            "GIT_COMMITTER_EMAIL": "worker@example.invalid",
        },
    )
    baseline = git.run(tpl, ["rev-parse", "HEAD"]).stdout.strip()
    return tpl, baseline


def bus_case(side, root):
    tpl, baseline = _baseline_template()
    shutil.copytree(tpl, root)
    git = GitRunner()
    with patch("contracts.execution._worker_protocol_support.seed_task", required_task):
        run, task, attempt, _ = make_case(
            side, stage_id="execute", stage_type="agent_step", params={"role": "executor"}
        )
    with side.uow() as uow:
        env = ExecutionEnvironment(
            side.new_id(),
            attempt.id,
            side.host1,
            EnvironmentKind.GIT_WORKTREE,
            (BaselineEntry("repo", side.repo_id, baseline, baseline, None),),
            attempt_branch(attempt.id),
            str(root),
            EnvironmentState.READY,
            side.clock.now(),
            None,
            None,
        )
        uow.repo(EnvironmentRepository).upsert(env)
        repo = uow.repo(AttemptRepository)
        attempt = replace(repo.get(attempt.id), environment_id=env.id, state=AttemptState.RUNNING)
        repo.save(attempt, expected_version=repo.version(attempt.id))
        uow.commit()
    claimed = claim_seeded_stage(side)
    return SimpleNamespace(
        side=side,
        root=root,
        git=git,
        baseline=baseline,
        run=run,
        task=task,
        attempt=attempt,
        claimed=claimed,
        environment=env,
    )


def claim_seeded_stage(side):
    # This fixture supplies admitted steps itself, so no host runtime installation is required.
    with patch(
        "skm.modules.execution.application.commands.claim_assignment.stage_route_available", return_value=True
    ):
        claimed = claim(side)
    assert "assignment_id" in claimed, claimed
    return claimed


def context_draft(side, step_id, stage_id):
    owner = f"step:{step_id}"
    with side.uow() as uow:
        cfg = side.app.config.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.PLAN, ScopeId(side.plan1))
        )
        request = ContextRequest(
            side.ws,
            side.proj,
            side.plan1,
            side.rev1,
            UNIT_ID,
            "skm",
            StepPurpose("executor", stage_id, str(step_id), 1, 1),
            side.workflow_rv_id,
            RuntimeTarget(
                "codex_cli",
                "gpt-5",
                128000,
                frozenset(),
                frozenset(),
                (),
                "plan",
                "execute",
                "isolated",
                (),
                frozenset(),
                (),
            ),
            PermissionsSummary(("repo:src/**",), ("repo:**",), ("pytest",), (), "none", (), ()),
            RunParams("run_1", "default", 1, 1, None, "none", "json", "en", ()),
            ExecutionBlocks(default_work_policy(), (), None, None, None, (), None, (), ()),
            None,
            "medium",
            (),
            None,
        )
        draft = context.assemble_draft(uow, side.app.gateways, request, config=cfg, owner_ref=owner)
        uow.commit()
    return draft


def admitted_stage(case, role=None, *, real_draft=False, admission=None):
    """Seed admission only, leaving the saved workflow continuation and all result handling real."""
    side = case.side
    with side.uow(readonly=True) as uow:
        attempt = uow.repo(AttemptRepository).get(case.attempt.id)
        selected = attempt.continuation.stage
    step_id = side.new_id() if role else None
    draft = context_draft(side, step_id, selected.stage_id) if real_draft else None
    manifest_id = (
        (draft.manifest_id if draft else side.make_final_manifest(step_ref=f"step:{step_id}"))
        if role
        else None
    )
    with side.uow() as uow:
        repo = uow.repo(AttemptRepository)
        attempt = repo.get(attempt.id)
        active, _ = consume_stage(attempt, continuation_id=attempt.continuation.continuation_id)
        repo.save(active, expected_version=repo.version(active.id))
        repo = uow.repo(TaskRepository)
        task = repo.get(case.task.id)
        repo.save(
            replace(
                task,
                status=TaskStatus.EXECUTING,
                required_host_id=side.host1,
                row_version=task.row_version + 1,
            ),
            expected_version=task.row_version,
        )
        seq = len(uow.repo(StageRepository).history(active.id).entries) + 1
        stage = seed_stage(
            side,
            uow,
            active,
            seq=seq,
            stage_id=selected.stage_id,
            stage_type=selected.stage_type,
            round_no=selected.round_no,
            state=StageState.CONTEXT_DRAFT if role else StageState.RUNNING,
        )
        step = None
        if role:
            assert manifest_id is not None
            step = seed_step(
                side,
                uow,
                active,
                stage,
                manifest_id=manifest_id,
                step_id=step_id,
                seq=seq,
                role=RoleId(role),
                admission=admission,
            )
        uow.commit()
    return stage, step, draft
