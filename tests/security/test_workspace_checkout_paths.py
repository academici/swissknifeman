"""Security boundary tests for workspace checkout inspection and marker paths."""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from skm.adapters.git.repo_inspect import MARKER_FILENAME, GitRepositoryInspector
from skm.adapters.git.runner import MAX_GITFILE_BYTES, GitRunner
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.modules.workspace.domain.checkout_marker import CheckoutMarker, marker_for
from skm.modules.workspace.domain.mount import MountName
from support.git_repo import init_git_repo

FIXED_NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


class _FixedClock:
    def now(self) -> datetime:
        return FIXED_NOW


def _sample_marker() -> CheckoutMarker:
    return marker_for(
        instance_id=UUID(int=1),
        workspace_id=WorkspaceId(UUID(int=2)),
        project_id=ProjectId(UUID(int=3)),
        repository_id=RepositoryId(UUID(int=4)),
        mount_name=MountName("main"),
    )


def _NeverSpawnInspector(sentinel_file: Path) -> GitRepositoryInspector:
    """Return an inspector whose git binary writes ``sentinel_file`` if ever spawned."""
    script = sentinel_file.with_name("forbidden-git.sh")
    script.write_text(f"#!/bin/sh\necho spawned > {sentinel_file}\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    return GitRepositoryInspector(runner=GitRunner(git_binary=str(script)), clock=_FixedClock())


def test_symlinked_checkout_root_and_ancestor_rejected_before_spawning_git(tmp_path: Path) -> None:
    real_repo = init_git_repo(tmp_path / "real-repo")
    real_repo.commit_file("dir/file.txt", "ok\n")
    sentinel = tmp_path / "spawned.flag"
    inspector = _NeverSpawnInspector(sentinel)

    symlink_root = tmp_path / "symlink-repo"
    symlink_root.symlink_to(real_repo.path, target_is_directory=True)
    dangling = tmp_path / "dangling-link"
    dangling.symlink_to(tmp_path / "missing-target")

    for target in (symlink_root, symlink_root / "dir", dangling):
        with pytest.raises(ValidationFailed) as err:
            inspector.observe(target)
        assert err.value.code is ErrorCode.REPOSITORY_UNSAFE
        assert not sentinel.exists()


def test_symlinked_dot_git_and_metadata_entries_rejected_before_spawning_git(tmp_path: Path) -> None:
    sentinel = tmp_path / "spawned.flag"
    inspector = _NeverSpawnInspector(sentinel)

    external_git = tmp_path / "external-git"
    external_git.mkdir()
    repo_symlink_git = tmp_path / "repo-symlink-git"
    repo_symlink_git.mkdir()
    (repo_symlink_git / ".git").symlink_to(external_git, target_is_directory=True)

    with pytest.raises(ValidationFailed) as err_git:
        inspector.observe(repo_symlink_git)
    assert err_git.value.code is ErrorCode.REPOSITORY_UNSAFE
    assert not sentinel.exists()

    for entry_name in ("config", "HEAD", "hooks"):
        repo = init_git_repo(tmp_path / f"repo-{entry_name}")
        target_entry = repo.path / ".git" / entry_name
        if target_entry.is_dir():
            shutil.rmtree(target_entry)
        elif target_entry.exists():
            target_entry.unlink()
        outside = tmp_path / f"outside-{entry_name}"
        outside.write_text("fake\n", encoding="utf-8")
        target_entry.symlink_to(outside)

        with pytest.raises(ValidationFailed) as err_entry:
            inspector.observe(repo.path)
        assert err_entry.value.code is ErrorCode.REPOSITORY_UNSAFE
        assert not sentinel.exists()

    repo_hook_link = init_git_repo(tmp_path / "repo-hook-script-link")
    evil_hook = tmp_path / "evil-hook.sh"
    evil_hook.write_text("#!/bin/sh\n", encoding="utf-8")
    (repo_hook_link.path / ".git" / "hooks" / "post-checkout").symlink_to(evil_hook)
    with pytest.raises(ValidationFailed) as err_hook:
        inspector.observe(repo_hook_link.path)
    assert err_hook.value.code is ErrorCode.REPOSITORY_UNSAFE
    assert not sentinel.exists()


def test_unsafe_gitfile_pointers_commondir_and_alternates_rejected_before_spawning_git(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "spawned.flag"
    inspector = _NeverSpawnInspector(sentinel)

    real_gitdir = init_git_repo(tmp_path / "backing-repo").path / ".git"
    link_gitdir = tmp_path / "link-gitdir"
    link_gitdir.symlink_to(real_gitdir, target_is_directory=True)

    wt_gitdir = tmp_path / "custom-wt-gitdir"
    wt_gitdir.mkdir()
    (wt_gitdir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (wt_gitdir / "commondir").write_text(f"{link_gitdir}\n", encoding="utf-8")

    cases = {
        "oversized": "gitdir: " + ("a" * MAX_GITFILE_BYTES) + "\n",
        "malformed": "not-a-gitdir-pointer\n",
        "missing": f"gitdir: {tmp_path / 'absent-gitdir'}\n",
        "symlink-gitdir": f"gitdir: {link_gitdir}\n",
        "symlink-commondir": f"gitdir: {wt_gitdir}\n",
    }
    for name, gitfile_text in cases.items():
        candidate_repo = tmp_path / f"case-{name}"
        candidate_repo.mkdir()
        (candidate_repo / ".git").write_text(gitfile_text, encoding="utf-8")
        with pytest.raises(ValidationFailed) as err:
            inspector.observe(candidate_repo)
        assert err.value.code is ErrorCode.REPOSITORY_UNSAFE
        assert not sentinel.exists()

    dir_commondir_repo = init_git_repo(tmp_path / "dir-commondir-repo")
    (dir_commondir_repo.path / ".git" / "commondir").write_text(f"{link_gitdir}\n", encoding="utf-8")
    with pytest.raises(ValidationFailed) as commondir_err:
        inspector.observe(dir_commondir_repo.path)
    assert commondir_err.value.code is ErrorCode.REPOSITORY_UNSAFE
    assert not sentinel.exists()

    alt_repo = init_git_repo(tmp_path / "alternates-repo")
    (alt_repo.path / ".git" / "objects" / "info" / "alternates").write_text(
        str(real_gitdir / "objects") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationFailed) as alt_err:
        inspector.observe(alt_repo.path)
    assert alt_err.value.code is ErrorCode.REPOSITORY_UNSAFE
    assert not sentinel.exists()


def test_ownership_uid_mismatch_rejected_before_spawning_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_git_repo(tmp_path / "owned-repo")
    sentinel = tmp_path / "spawned.flag"
    inspector = _NeverSpawnInspector(sentinel)

    monkeypatch.setattr(os, "geteuid", lambda: os.getuid() + 999)
    with pytest.raises(ValidationFailed) as err:
        inspector.observe(repo.path)
    assert err.value.code is ErrorCode.REPOSITORY_UNSAFE
    assert not sentinel.exists()


def test_symlinked_checkout_marker_intermediate_components_and_path_escape_rejected(
    tmp_path: Path,
) -> None:
    repo = init_git_repo(tmp_path / "repo")
    repo.commit_file()
    inspector = GitRepositoryInspector(runner=repo.runner, clock=_FixedClock())

    victim_file = tmp_path / "victim.json"
    victim_file.write_text('{"preserve": true}\n', encoding="utf-8")
    marker_target = repo.path / MARKER_FILENAME
    marker_target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    marker_target.symlink_to(victim_file)

    with pytest.raises(ValidationFailed) as read_err:
        inspector.read_marker(repo.path)
    assert read_err.value.code is ErrorCode.REPOSITORY_UNSAFE

    with pytest.raises(ValidationFailed) as obs_err:
        inspector.observe(repo.path)
    assert obs_err.value.code is ErrorCode.REPOSITORY_UNSAFE

    with pytest.raises(ValidationFailed) as write_err:
        inspector.write_marker(repo.path, _sample_marker())
    assert write_err.value.code is ErrorCode.REPOSITORY_UNSAFE
    assert json.loads(victim_file.read_text(encoding="utf-8")) == {"preserve": True}

    shutil.rmtree(marker_target.parent)
    outside_dir = tmp_path / "outside-skm"
    outside_dir.mkdir()
    (repo.path / ".skm").symlink_to(outside_dir, target_is_directory=True)
    for op in (
        lambda: inspector.read_marker(repo.path),
        lambda: inspector.observe(repo.path),
        lambda: inspector.write_marker(repo.path, _sample_marker()),
    ):
        with pytest.raises(ValidationFailed) as sym_dir_err:
            op()
        assert sym_dir_err.value.code is ErrorCode.REPOSITORY_UNSAFE

    (repo.path / ".skm").unlink()
    (repo.path / ".skm").write_text("not-a-directory\n", encoding="utf-8")
    for op in (
        lambda: inspector.read_marker(repo.path),
        lambda: inspector.observe(repo.path),
        lambda: inspector.write_marker(repo.path, _sample_marker()),
    ):
        with pytest.raises(ValidationFailed) as file_dir_err:
            op()
        assert file_dir_err.value.code is ErrorCode.REPOSITORY_UNSAFE
    (repo.path / ".skm").unlink()

    for escape_rel in (
        "../victim.json",
        "/etc/passwd",
        "a/../../victim.json",
        "missing_dir/../.skm/project.json",
        ".skm/./project.json",
        ".skm//project.json",
        ".",
        "",
    ):
        with pytest.raises(ValidationFailed) as esc_write_err:
            inspector.write_marker(repo.path, marker=_sample_marker(), marker_relpath=escape_rel)
        assert esc_write_err.value.code is ErrorCode.REPOSITORY_UNSAFE
        with pytest.raises(ValidationFailed) as esc_read_err:
            inspector.read_marker(repo.path, marker_relpath=escape_rel)
        assert esc_read_err.value.code is ErrorCode.REPOSITORY_UNSAFE
        with pytest.raises(ValidationFailed) as esc_obs_err:
            inspector.observe(repo.path, marker_relpath=escape_rel)
        assert esc_obs_err.value.code is ErrorCode.REPOSITORY_UNSAFE


def test_remote_credentials_stripped_and_never_leaked(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "cred-repo")
    repo.commit_file()
    secret = "ghp_SuperSecretTokenValue1234567890"
    repo.add_remote("origin", f"https://oauth2:{secret}@github.com/example/private-repo.git")
    repo.add_remote("ssh_plus", f"git+ssh://user:{secret}@gitlab.com/example/other-repo.git")
    repo.add_remote("scp_cred", f"deploy:{secret}@gitea.example.com:example/scp-repo.git")
    repo.add_remote("local", "/srv/git/local-only")

    inspector = GitRepositoryInspector(runner=repo.runner, clock=_FixedClock())
    raw_urls = inspector.remote_urls(repo.path)
    assert ("origin", "https://github.com/example/private-repo.git") in raw_urls
    assert ("ssh_plus", "git+ssh://gitlab.com/example/other-repo.git") in raw_urls
    assert ("scp_cred", "gitea.example.com:example/scp-repo.git") in raw_urls
    assert secret not in json.dumps(raw_urls)

    remotes = inspector.remotes(repo.path)
    assert [r.value for r in remotes] == [
        "github.com/example/private-repo",
        "gitea.example.com/example/scp-repo",
        "gitlab.com/example/other-repo",
    ]
    assert secret not in str(remotes)

    obs = inspector.observe(repo.path)
    assert obs.remotes == remotes
    assert secret not in str(obs)
