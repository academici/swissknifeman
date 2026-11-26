"""Environment lifecycle, dirty B preservation, local integration tips, and crash boundaries."""

import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from skm.adapters.git.commit import GitOutputSealer
from skm.adapters.git.environments.existing_checkout import ExistingCheckoutEnvironments
from skm.adapters.git.environments.managed_clone import CloneSource, ManagedCloneEnvironments
from skm.adapters.git.environments.worktree import (
    CleanupProof,
    Prepared,
    WorktreeManager,
    git_worktree_environments,
)
from skm.adapters.git.host_inputs import capture_checkout
from skm.adapters.git.status import tree_entries
from skm.kernel.cancel import CancelSource
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.assignment import StageInstruction
from skm.modules.execution.domain.environment import EnvironmentKind
from skm.modules.execution.domain.ids import StageRecordId
from skm.modules.execution.host.environment import PreparedEnvironment
from skm.modules.execution.host.evidence import EvidenceFile
from skm.modules.execution.host.stages.base import StageRequest
from skm.modules.execution.host.stages.prepare_environment import PrepareEnvironmentStage
from skm.modules.execution.ports import ExecutionEnvironmentManager, StageDeps

from .conftest import AUTHOR, environment_spec, safe_cleanup


def test_worktree_prepare_reopen_recheck_remove(repository, tmp_path):
    root, git, head = repository
    spec = environment_spec(tmp_path / "worktrees", root)
    manager = WorktreeManager(git, worktrees_root=spec.root, cleanup_proof=safe_cleanup)
    env = manager.prepare(spec)
    assert env == manager.prepare(spec)
    assert env == manager.reopen(env.environment_id, env.locator)
    assert env.baseline[0].commit_sha == head
    assert env.baseline[0].clean
    assert git.run(env.mounts["main"], ["branch", "--show-current"]).stdout.strip() == spec.branch + "/main"
    marker = spec.root / f"{spec.attempt_id}.skm-environment.json"
    assert marker.stat().st_mode & 0o777 == 0o600
    recheck = manager.prepare_recheck(
        env.environment_id, stage_record_id=StageRecordId(uuid4()), commit_shas={"main": head}
    )
    assert git.run(recheck.mounts["main"], ["branch", "--show-current"]).stdout.strip() == ""
    manager.discard(recheck, retain=False)
    manager.discard(env, retain=True)
    assert env.mounts["main"].exists()
    manager.discard(env, retain=False)
    assert not Path(env.locator).exists()
    assert manager.remove(env.locator).freed_bytes == 0
    assert (root / "file.txt").read_bytes() == b"initial\nsecond\n"


@pytest.mark.parametrize(
    "proof",
    [CleanupProof(False, True, True), CleanupProof(True, False, True), CleanupProof(True, True, False)],
)
def test_cleanup_requires_all_proofs(repository, tmp_path, proof):
    root, git, _ = repository
    spec = environment_spec(tmp_path / "worktrees", root)
    manager = WorktreeManager(git, worktrees_root=spec.root, cleanup_proof=lambda _: proof)
    env = manager.prepare(spec)
    with pytest.raises(SkmError, match="proof"):
        manager.remove(env.locator)
    assert env.mounts["main"].is_dir()


def test_prepare_never_removes_foreign_directory(repository, tmp_path):
    root, git, _ = repository
    spec = environment_spec(tmp_path / "worktrees", root)
    manager = WorktreeManager(git, worktrees_root=spec.root)
    foreign = spec.root / str(spec.attempt_id)
    foreign.mkdir()
    (foreign / "keep").write_bytes(b"owner bytes")
    with pytest.raises(SkmError):
        manager.prepare(spec)
    assert (foreign / "keep").read_bytes() == b"owner bytes"


def test_prepare_crash_keeps_partial_owned_state(repository, tmp_path, monkeypatch):
    root, git, _ = repository
    spec = environment_spec(tmp_path / "worktrees", root)
    manager = WorktreeManager(git, worktrees_root=spec.root)
    run = git.run

    def crash(cwd, args, **kwargs):
        if args[:2] == ["worktree", "add"]:
            raise OSError("injected crash")
        return run(cwd, args, **kwargs)

    monkeypatch.setattr(git, "run", crash)
    with pytest.raises(OSError, match="injected crash"):
        manager.prepare(spec)
    monkeypatch.setattr(git, "run", run)
    with pytest.raises(SkmError, match="reconciliation"):
        manager.prepare(spec)
    assert (spec.root / f"{spec.attempt_id}.skm-environment.json").is_file()


@pytest.mark.parametrize(("interactive", "exclusive"), [(False, True), (True, False)])
def test_existing_requires_external_exclusivity(repository, tmp_path, interactive, exclusive):
    root, git, head = repository
    spec = environment_spec(tmp_path / "state", root, kind=EnvironmentKind.EXISTING_CHECKOUT)
    manager = ExistingCheckoutEnvironments(
        git, worktrees_root=spec.root, interactive=interactive, exclusive=lambda _: exclusive
    )
    with pytest.raises(SkmError):
        manager.prepare(spec)
    assert git.run(root, ["rev-parse", "HEAD"]).stdout.strip() == head


def test_existing_dirty_baseline_and_output_preserve_user_state(repository, tmp_path):
    root, git, head = repository
    (root / "file.txt").write_bytes(b"user dirty\nsecond\n")
    (root / "untracked").write_bytes(b"user untracked\x00")
    (root / "link").symlink_to("untracked")
    (root / "executable").write_bytes(b"#!/bin/sh\n")
    (root / "executable").chmod(0o755)
    git.run(root, ["add", "--", "file.txt"])
    index = (root / ".git/index").read_bytes()
    branch = git.run_bytes(root, ["symbolic-ref", "HEAD"]).stdout
    spec = environment_spec(tmp_path / "state", root, kind=EnvironmentKind.EXISTING_CHECKOUT)
    manager = ExistingCheckoutEnvironments(
        git, worktrees_root=spec.root, interactive=True, exclusive=lambda _: True, cleanup_proof=safe_cleanup
    )
    prepared = manager.prepare(spec)
    baseline = prepared.baseline[0]
    assert baseline.commit_sha != head
    assert baseline.source_head_sha == head
    entries = tree_entries(git, root, baseline.commit_sha)
    assert entries[b"link"].startswith("120000 ")
    assert entries[b"executable"].startswith("100755 ")
    assert b"untracked" in entries
    assert manager.dirty_patches(prepared)[0][1].read_bytes()
    manager.release_locks(str(spec.attempt_id))  # supervisor restart; protected B marker survives
    restarted = ExistingCheckoutEnvironments(
        git, worktrees_root=spec.root, interactive=True, exclusive=lambda _: True, cleanup_proof=safe_cleanup
    )
    assert restarted.prepare(spec).baseline == prepared.baseline
    (root / "file.txt").write_bytes(b"user dirty\ntask delta\n")
    output = GitOutputSealer(git, state_dir=tmp_path / "snapshots").seal(
        root,
        attempt_id=str(spec.attempt_id),
        output_no=1,
        mount="main",
        repository_id=spec.mounts[0].repository_id,
        baseline=baseline.commit_sha,
        write_scope=["file.txt"],
        binding=capture_checkout(root),
    )
    patch = git.run_bytes(
        root, ["diff", baseline.commit_sha, output.mounts[0].head_commit, "--no-ext-diff", "--no-textconv"]
    ).stdout
    assert b"+task delta" in patch
    assert b"+user dirty" not in patch
    assert len(output.changed_paths) == 1
    assert (root / ".git/index").read_bytes() == index
    assert git.run_bytes(root, ["symbolic-ref", "HEAD"]).stdout == branch
    assert git.run(root, ["rev-parse", "HEAD"]).stdout.strip() == head
    restarted.discard(prepared, retain=False)
    assert (root / "untracked").read_bytes() == b"user untracked\x00"
    assert os.readlink(root / "link") == "untracked"
    assert (root / "file.txt").read_bytes() == b"user dirty\ntask delta\n"


def test_existing_index_changed_after_prepare_rejected_without_rollback(repository, tmp_path):
    root, git, _ = repository
    spec = environment_spec(tmp_path / "state", root, kind=EnvironmentKind.EXISTING_CHECKOUT)
    manager = ExistingCheckoutEnvironments(
        git, worktrees_root=spec.root, interactive=True, exclusive=lambda _: True
    )
    env = manager.prepare(spec)
    (root / "file.txt").write_text("IDE bytes")
    git.run(root, ["add", "--", "file.txt"])
    index = (root / ".git/index").read_bytes()
    with pytest.raises(SkmError, match="index"):
        manager.reopen(env.environment_id, env.locator)
    assert (root / "file.txt").read_text() == "IDE bytes"
    assert (root / ".git/index").read_bytes() == index
    manager.release_locks(str(spec.attempt_id))


def test_managed_clone_preserves_unpublished_local_tip(repository, tmp_path):
    root, git, _ = repository
    spec = environment_spec(tmp_path / "worktrees", root, kind=EnvironmentKind.MANAGED_CLONE)
    pinned = tmp_path / "integration" / "repo"
    source = CloneSource(str(root), pinned, "integration", "main")
    spec = replace(spec, mounts=(replace(spec.mounts[0], checkout_locator=str(pinned)),))
    sources = {str(spec.mounts[0].repository_id): source}
    manager = ManagedCloneEnvironments(
        git,
        worktrees_root=spec.root,
        sources=sources,
        enabled=True,
        allow_file_remote=True,
        cleanup_proof=safe_cleanup,
    )
    first = manager.prepare(spec)
    (pinned / "unpublished").write_text("accepted but not pushed")
    git.run(pinned, ["add", "unpublished"])
    git.run_bytes(pinned, ["commit", "-m", "unpublished"], env=AUTHOR)
    tip = git.run(pinned, ["rev-parse", "HEAD"]).stdout.strip()
    git.run(pinned, ["update-ref", "refs/heads/integration", tip])
    second = replace(spec, attempt_id=uuid4(), branch="unused")
    second = replace(second, branch=f"skm/attempt/{second.attempt_id}")
    next_env = manager.prepare(second)
    assert next_env.baseline[0].commit_sha == tip
    assert (next_env.mounts["main"] / "unpublished").read_text() == "accepted but not pushed"
    manager.discard(next_env, retain=False)
    manager.discard(first, retain=False)
    assert (pinned / "unpublished").is_file()


def test_existing_reopen_takes_lock_and_rejects_second_attempt(repository, tmp_path):
    root, git, _ = repository
    spec = environment_spec(tmp_path / "state", root, kind=EnvironmentKind.EXISTING_CHECKOUT)
    manager = ExistingCheckoutEnvironments(
        git, worktrees_root=spec.root, interactive=True, exclusive=lambda _: True
    )
    env = manager.prepare(spec)
    manager.release_locks(str(spec.attempt_id))
    reopened = ExistingCheckoutEnvironments(
        git, worktrees_root=spec.root, interactive=True, exclusive=lambda _: True
    )
    assert reopened.reopen(env.environment_id, env.locator) == env
    other = ExistingCheckoutEnvironments(
        git, worktrees_root=spec.root, interactive=True, exclusive=lambda _: True
    )
    next_spec = replace(spec, attempt_id=uuid4())
    next_spec = replace(next_spec, branch=f"skm/attempt/{next_spec.attempt_id}")
    with pytest.raises(SkmError, match="in use"):
        other.prepare(next_spec)
    reopened.release_locks(str(spec.attempt_id))


def test_same_bytes_config_inode_swap_rejected_after_prepare(repository, tmp_path):
    root, git, _ = repository
    spec = environment_spec(tmp_path / "state", root)
    manager = WorktreeManager(git, worktrees_root=spec.root, cleanup_proof=safe_cleanup)
    env = manager.prepare(spec)
    config = root / ".git/config"
    replacement = root / ".git/replacement-config"
    replacement.write_bytes(config.read_bytes())
    replacement.replace(config)
    with pytest.raises(SkmError, match="binding"):
        manager.reopen(env.environment_id, env.locator)
    with pytest.raises(SkmError, match="binding"):
        manager.remove(env.locator)


def test_prepare_stage_payload_matches_generated_contract(repository, tmp_path):
    from skm.modules.execution.generated.documents import stage_outcome_prepare_environment_from_json
    from skm.platform.schema.registry import SchemaRegistry

    root, git, _ = repository
    spec = environment_spec(tmp_path / "state", root)
    manager = git_worktree_environments(git, worktrees_root=spec.root)
    stage = PrepareEnvironmentStage(manager, spec=lambda *a: spec, patch_files=lambda _: ())
    outcome = stage.run(
        StageRequest(StageInstruction("run_stage", stage_type="prepare_environment"), {}, None, {}),
        cast("StageDeps", SimpleNamespace(cancel=CancelSource().token)),
    )
    payload = dict(outcome.payload)
    assert stage_outcome_prepare_environment_from_json(payload) == payload
    SchemaRegistry.load_default().require_valid(
        "urn:skm:execution:stage-outcome-prepare-environment:v1", payload
    )
    assert payload["environment_id"]


def test_dirty_prepare_upload_mapping_preserves_baseline_on_replay(repository, tmp_path):
    root, git, head = repository
    (root / "file.txt").write_bytes(b"dirty before task\n")
    spec = environment_spec(tmp_path / "state", root, kind=EnvironmentKind.EXISTING_CHECKOUT)
    manager = ExistingCheckoutEnvironments(
        git, worktrees_root=spec.root, interactive=True, exclusive=lambda _: True
    )
    request = StageRequest(StageInstruction("run_stage", stage_type="prepare_environment"), {}, None, {})
    # This stage only gets cancellation; its environment gateway is wired separately.
    deps = cast("StageDeps", SimpleNamespace(cancel=CancelSource().token))
    gateway = cast("ExecutionEnvironmentManager", manager)
    stage = PrepareEnvironmentStage(gateway, spec=lambda *a: spec, patch_files=lambda _: ())
    with pytest.raises(ValueError, match="attempt-owned patch"):
        stage.run(request, deps)

    def patch_files(environment: PreparedEnvironment) -> tuple[EvidenceFile, ...]:
        assert isinstance(environment, Prepared)
        return tuple(
            EvidenceFile(path, f"attempt:{spec.attempt_id}", "patch", f"{mount}.dirty.patch", "text/x-patch")
            for mount, path in manager.dirty_patches(environment)
        )

    stage = PrepareEnvironmentStage(gateway, spec=lambda *a: spec, patch_files=patch_files)
    first = stage.run(request, deps)
    second = stage.run(request, deps)
    assert first == second
    mounts, baselines = first.payload["mounts"], first.payload["baseline"]
    assert isinstance(mounts, list)
    assert len(mounts) == 1
    assert isinstance(baselines, list)
    assert len(baselines) == 1
    mount, baseline = mounts[0], baselines[0]
    assert isinstance(mount, dict)
    assert isinstance(baseline, dict)
    assert mount["dirty_patch_filename"] == "main.dirty.patch"
    assert mount["environment_locator"] == str(spec.root / str(spec.attempt_id))
    assert baseline["source_head_sha"] == head
    assert baseline["commit_sha"] != head
    assert b"+dirty before task" in first.files[0].path.read_bytes()
    assert git.run(root, ["rev-parse", "HEAD"]).stdout.strip() == head
    assert (root / "file.txt").read_bytes() == b"dirty before task\n"
    manager.release_locks(str(spec.attempt_id))
