"""Detached, exact-SHA rechecks for all environment kinds; user trees remain untouched."""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from integration.git.conftest import environment_spec, safe_cleanup
from integration.git.test_integration import make_case, prepare, publish, seal
from skm.adapters.git.environments.existing_checkout import ExistingCheckoutEnvironments
from skm.adapters.git.environments.managed_clone import CloneSource, ManagedCloneEnvironments
from skm.adapters.git.environments.worktree import CleanupProof, WorktreeManager
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.environment import EnvironmentKind
from skm.modules.execution.domain.ids import StageRecordId


def prepare_environment(tmp_path, repository, kind):
    repo, git, _ = repository
    root = tmp_path / "environments"
    if kind == "existing_checkout":
        manager = ExistingCheckoutEnvironments(
            git, worktrees_root=root, exclusive=lambda _: True, interactive=True, cleanup_proof=safe_cleanup
        )
    elif kind == "managed_clone":
        spec = environment_spec(root, tmp_path / "canonical", kind=EnvironmentKind.MANAGED_CLONE)
        source = CloneSource(str(repo), Path(spec.mounts[0].checkout_locator), "integration", "main")
        manager = ManagedCloneEnvironments(
            git,
            worktrees_root=root,
            sources={str(spec.mounts[0].repository_id): source},
            enabled=True,
            clone_depth=0,
            allow_file_remote=True,
            cleanup_proof=safe_cleanup,
        )
        return manager, manager.prepare(spec)
    else:
        manager = WorktreeManager(git, worktrees_root=root, cleanup_proof=safe_cleanup)
    spec = environment_spec(root, repo, kind=EnvironmentKind(kind))
    return manager, manager.prepare(spec)


@pytest.mark.parametrize("kind", ["git_worktree", "existing_checkout", "managed_clone"])
def test_exact_detached_recheck_preserves_original_tree_index_and_refs(repository, tmp_path, kind):
    repo, git, head = repository
    (repo / "file.txt").write_bytes(b"staged user bytes\n")
    git.run(repo, ["add", "file.txt"])
    (repo / "file.txt").write_bytes(b"unstaged user bytes\n")
    (repo / "untracked").write_bytes(b"user untracked bytes\n")
    index = (repo / ".git/index").read_bytes()
    original_head = git.run(repo, ["rev-parse", "HEAD"]).stdout
    manager, environment = prepare_environment(tmp_path, repository, kind)
    refs = git.run(repo, ["show-ref"]).stdout
    stage = StageRecordId(uuid4())
    checked = manager.prepare_recheck(
        environment.environment_id, stage_record_id=stage, commit_shas={"main": head}
    )
    assert "_recheck" in checked.locator
    assert git.run(checked.mounts["main"], ["rev-parse", "HEAD"]).stdout.strip() == head
    assert git.run(checked.mounts["main"], ["symbolic-ref", "-q", "HEAD"], check=False).exit_code == 1
    assert (checked.mounts["main"] / "file.txt").read_bytes() == b"initial\nsecond\n"
    assert (
        manager.prepare_recheck(environment.environment_id, stage_record_id=stage, commit_shas={"main": head})
        == checked
    )
    manager.discard(checked, retain=False)
    assert not Path(checked.locator).exists()
    assert (repo / "file.txt").read_bytes() == b"unstaged user bytes\n"
    assert (repo / "untracked").read_bytes() == b"user untracked bytes\n"
    assert (repo / ".git/index").read_bytes() == index
    assert git.run(repo, ["rev-parse", "HEAD"]).stdout == original_head
    assert git.run(repo, ["show-ref"]).stdout == refs
    manager.discard(environment, retain=False)


def test_recheck_requires_exact_sha_and_preserves_foreign_directory(repository, tmp_path):
    manager, environment = prepare_environment(tmp_path, repository, "git_worktree")
    with pytest.raises(ValueError, match="exact object IDs"):
        manager.prepare_recheck(
            environment.environment_id, stage_record_id=StageRecordId(uuid4()), commit_shas={"main": "HEAD"}
        )
    stage = StageRecordId(uuid4())
    foreign = manager.root / "_recheck" / str(Path(environment.locator).name) / str(stage)
    foreign.mkdir(parents=True)
    (foreign / "owner.txt").write_text("keep")
    with pytest.raises(SkmError):
        manager.prepare_recheck(
            environment.environment_id, stage_record_id=stage, commit_shas={"main": repository[2]}
        )
    assert (foreign / "owner.txt").read_text() == "keep"


def test_recheck_cleanup_waits_for_reap_and_retains_diagnostics(repository, tmp_path):
    manager, environment = prepare_environment(tmp_path, repository, "git_worktree")
    checked = manager.prepare_recheck(
        environment.environment_id,
        stage_record_id=StageRecordId(uuid4()),
        commit_shas={"main": repository[2]},
    )
    diagnostic = checked.mounts["main"] / "diagnostic"
    diagnostic.write_bytes(b"failed check detail")
    manager.cleanup_proof = lambda _: CleanupProof(True, False, True)
    with pytest.raises(SkmError):
        manager.discard(checked, retain=False)
    assert diagnostic.read_bytes() == b"failed check detail"


def test_managed_clone_restart_uses_local_tip_and_fetch_does_not_reset_it(tmp_path):
    case = make_case(tmp_path)
    request = prepare(case)
    publish(case, request)
    clone_root = tmp_path / "attempts"
    spec = environment_spec(clone_root, case.repo, kind=EnvironmentKind.MANAGED_CLONE)
    source = CloneSource(str(case.repo), case.repo, "integration", "main")
    args = {
        "worktrees_root": clone_root,
        "sources": {str(spec.mounts[0].repository_id): source},
        "enabled": True,
        "clone_depth": 0,
        "allow_file_remote": True,
        "cleanup_proof": safe_cleanup,
    }
    manager = ManagedCloneEnvironments(case.git, **args)
    environment = manager.prepare(spec)
    assert environment.baseline[0].commit_sha == request.after_sha
    restarted = ManagedCloneEnvironments(case.git, **args)
    tips = restarted.fetch_remote(str(spec.mounts[0].repository_id))
    assert tips == {
        "remote_tip": case.before,
        "local_integration_tip": request.after_sha,
        "last_pushed_tip": None,
    }
    assert restarted.reopen(environment.environment_id, environment.locator) == environment
    # A new attempt gets the same unpublished local history, never the stale remote baseline.
    next_spec = environment_spec(clone_root, case.repo, kind=EnvironmentKind.MANAGED_CLONE)
    next_spec = replace(next_spec, mounts=spec.mounts)
    following = restarted.prepare(next_spec)
    assert following.baseline[0].commit_sha == request.after_sha
    # A projected/owner-approved commit created after prepare exists only in the canonical clone.
    (case.repo / "owner-correction").write_text("approved recheck input\n")
    approved = seal(case.git, case.repo, request.after_sha, tmp_path / "snapshots")
    assert case.git.run(environment.mounts["main"], ["cat-file", "-e", approved], check=False).exit_code != 0
    checked = restarted.prepare_recheck(
        environment.environment_id, stage_record_id=StageRecordId(uuid4()), commit_shas={"main": approved}
    )
    assert case.git.run(checked.mounts["main"], ["rev-parse", "HEAD"]).stdout.strip() == approved
    restarted.discard(checked, retain=False)


def test_recheck_cleanup_does_not_prune_unowned_worktree_registrations(repository, tmp_path):
    import shutil

    repo, git, head = repository
    manager, environment = prepare_environment(tmp_path, repository, "git_worktree")
    foreign = tmp_path / "foreign"
    git.run(repo, ["worktree", "add", "--detach", str(foreign), head])
    shutil.rmtree(foreign)
    checked = manager.prepare_recheck(
        environment.environment_id, stage_record_id=StageRecordId(uuid4()), commit_shas={"main": head}
    )
    manager.discard(checked, retain=False)
    assert str(foreign) in git.run(repo, ["worktree", "list", "--porcelain"]).stdout
