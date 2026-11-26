"""Owner retry pins immutable commits and checks run only in disposable recheck worktrees."""

from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from integration.git.conftest import environment_spec, make_repo, safe_cleanup
from skm.adapters.git.commit import git_vcs
from skm.adapters.git.environments.worktree import WorktreeManager
from skm.modules.execution.domain.assignment import StageInstruction
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.host.checks import CheckResult
from skm.modules.execution.host.stages.base import StageRequest
from skm.modules.execution.host.stages.run_checks import RunChecksStage
from skm.modules.execution.ports import StageDeps


def stub(**kwargs) -> Any:
    return SimpleNamespace(**kwargs)


def setup_checks(tmp_path, *, exit_code=0, retry=False):
    repo = tmp_path / "repo"
    git, sha = make_repo(repo)
    spec = environment_spec(tmp_path / "envs", repo)
    manager: Any = WorktreeManager(git, worktrees_root=spec.root, cleanup_proof=safe_cleanup)
    environment = manager.prepare(spec)
    calls = []

    def run(request, deps):
        calls.append((request.cwd, git.run(request.cwd, ["rev-parse", "HEAD"]).stdout.strip()))
        stdout, stderr = tmp_path / "stdout", tmp_path / "stderr"
        stdout.write_text("check ran")
        stderr.write_text("")
        return CheckResult(exit_code, False, None, False, stdout, stderr, (), 0.1)

    deps = StageDeps(
        stub(),
        environment,
        stub(),
        stub(get=lambda _: stub(run=run)),
        stub(),
        git_vcs(git, state_dir=tmp_path / "state"),
        stub(),
        stub(get=lambda _: 10000),
        stub(),
        stub(),
        stub(),
        stub(),
    )
    raw = {
        "check_execution_id": str(uuid4()),
        "check_spec_id": str(uuid4()),
        "kind": "command",
        "definition": {"argv": ["true"], "cwd": {"mount": "main"}},
        "reused": False,
    }
    instruction = StageInstruction(
        "run_stage",
        stage_id="checks",
        stage_type="run_checks",
        mode=StageMode.RETRY if retry else StageMode.NORMAL,
        round_no=1,
        params={"scope": "rerun_after_integration", "recheck_commits": {"main": sha}},
    )
    request = StageRequest(instruction, {"stage_record_id": str(uuid4()), "checks": [raw]}, None, {})
    stage = RunChecksStage(
        isolation=lambda *args: stub(),
        read_capture=lambda p: p.read_bytes(),
        verify_environment=lambda _: None,
        candidate_marks=lambda *args: pytest.fail("recheck must not reuse output marks"),
        environment_manager=manager,
        current_tips=lambda *args: {"main": sha},
    )
    return SimpleNamespace(
        stage=stage,
        request=request,
        deps=deps,
        calls=calls,
        manager=manager,
        environment=environment,
        git=git,
        repo=repo,
        sha=sha,
    )


def test_owner_approved_retry_runs_on_exact_sha_and_always_cleans_owned_worktree(tmp_path):
    case = setup_checks(tmp_path, retry=True)
    result = case.stage.run(case.request, case.deps)
    assert result.kind.value == "success"
    assert case.calls[0][1] == case.sha
    assert "_recheck" in str(case.calls[0][0])
    assert not case.calls[0][0].exists()
    assert case.environment.mounts["main"].exists()


def test_changed_tip_escalates_without_running_checks_or_substituting_approval(tmp_path):
    case = setup_checks(tmp_path, retry=True)
    case.stage.current_tips = lambda *args: {"main": "f" * 40}
    result = case.stage.run(case.request, case.deps)
    assert result.kind.value == "runtime_error"
    assert result.payload["error_code"] == "INTEGRATION_RECHECK_FAILED"
    assert not case.calls
    assert not (case.manager.root / "_recheck").exists()


@pytest.mark.parametrize("change", ["missing_commits", "reuse", "missing_tip_guard"])
def test_recheck_refuses_missing_approval_reuse_or_unknown_retry_tip(tmp_path, change):
    case = setup_checks(tmp_path, retry=True)
    if change == "missing_commits":
        case.request = replace(
            case.request,
            instruction=replace(case.request.instruction, params={"scope": "rerun_after_integration"}),
        )
    elif change == "reuse":
        case.request.begin["checks"][0]["reused"] = True
    else:
        case.stage.current_tips = None
    assert case.stage.run(case.request, case.deps).payload["error_code"] == "INTEGRATION_RECHECK_FAILED"
    assert not case.calls


def test_red_recheck_is_not_acceptance_and_preserves_original_inputs(tmp_path):
    case = setup_checks(tmp_path, exit_code=1)
    original = dict(case.request.instruction.params)
    result = case.stage.run(case.request, case.deps)
    assert result.kind.value == "checks_failed"
    assert result.payload["error_code"] == "INTEGRATION_RECHECK_FAILED"
    assert case.request.instruction.params == original
    assert case.environment.mounts["main"].exists()
    assert not case.calls[0][0].exists()


def test_owner_can_approve_a_new_sha_without_replacing_it_with_original_candidate(tmp_path):
    from integration.git.test_integration import seal

    case = setup_checks(tmp_path, retry=True)
    (case.repo / "owner-fix").write_text("approved correction\n")
    approved = seal(case.git, case.repo, case.sha, tmp_path / "seal")
    case.request = replace(
        case.request,
        instruction=replace(
            case.request.instruction,
            params={"scope": "rerun_after_integration", "recheck_commits": {"main": approved}},
        ),
    )
    case.stage.current_tips = lambda *args: {"main": approved}
    result = case.stage.run(case.request, case.deps)
    assert result.kind.value == "success"
    assert case.calls[0][1] == approved
    assert approved != case.sha
