"""Integration tests for ``GitRunner`` and ``GitRepositoryInspector``."""

from __future__ import annotations

import json
import os
import stat
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from skm.adapters.git.repo_inspect import MARKER_FILENAME, MAX_MARKER_BYTES, GitRepositoryInspector
from skm.adapters.git.runner import (
    GLOBAL_GIT_ARGS,
    GitCommandFailed,
    GitRunner,
    parse_git_version,
    redact_git_text,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, CapabilityUnavailable, NotFound, ValidationFailed
from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.modules.workspace.domain.checkout_marker import CheckoutMarker, marker_for, marker_to_document
from skm.modules.workspace.domain.mount import MountName
from skm.modules.workspace.domain.remote_url import NormalizedRemote
from skm.modules.workspace.ports import MARKER_INVALID
from support.git_repo import init_git_repo

FIXED_NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)


class _FixedClock:
    def now(self) -> datetime:
        return FIXED_NOW


def _sample_marker() -> CheckoutMarker:
    return marker_for(
        instance_id=UUID(int=101),
        workspace_id=WorkspaceId(UUID(int=102)),
        project_id=ProjectId(UUID(int=103)),
        repository_id=RepositoryId(UUID(int=104)),
        mount_name=MountName("main"),
    )


def _write_executable_script(path: Path, body: str) -> Path:
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_git_runner_env_sanitization_and_argv_construction(tmp_path: Path) -> None:
    fake_home, fake_sock = str(tmp_path / "home"), str(tmp_path / "ssh.sock")
    runner = GitRunner(
        base_env={
            "PATH": "/usr/bin:/bin",
            "HOME": fake_home,
            "LANG": "ru_RU.UTF-8",
            "SSH_AUTH_SOCK": fake_sock,
            "SSH_AGENT_PID": "4242",
            "LC_CTYPE": "en_US.UTF-8",
            "GIT_DIR": "/evil/git-dir",
            "GIT_WORK_TREE": "/evil/work-tree",
            "GIT_INDEX_FILE": "/evil/index",
            "GIT_CONFIG_GLOBAL": "/evil/gitconfig",
            "GIT_SSH_COMMAND": "evil-ssh",
            "SECRET_TOKEN": "should-not-leak",
        }
    )
    env = runner.build_environment()
    assert (env["PATH"], env["HOME"], env["LC_CTYPE"]) == ("/usr/bin:/bin", fake_home, "en_US.UTF-8")
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_ASKPASS"] == "/bin/false"
    assert env["SSH_ASKPASS"] == "/bin/false"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["GIT_ATTR_NOSYSTEM"] == "1"
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert (env["LC_ALL"], env["LANG"]) == ("C", "C")
    for forbidden in (
        "SSH_AUTH_SOCK",
        "SSH_AGENT_PID",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_SSH_COMMAND",
        "SECRET_TOKEN",
    ):
        assert forbidden not in env

    ssh_env = runner.build_environment(allow_ssh_agent=True)
    assert (ssh_env["SSH_AUTH_SOCK"], ssh_env["SSH_AGENT_PID"]) == (fake_sock, "4242")

    default_env = GitRunner().build_environment()
    assert default_env["PATH"] == os.pathsep.join(entry for entry in os.get_exec_path() if entry)

    for required_cfg in (
        "protocol.allow=never",
        "protocol.file.allow=never",
        "core.fsmonitor=false",
        "core.hooksPath=/dev/null",
        "credential.helper=",
        "advice.detachedHead=false",
        "gc.auto=0",
        "maintenance.auto=false",
        "core.quotepath=false",
        "commit.gpgsign=false",
        "tag.gpgsign=false",
        "core.autocrlf=false",
        "core.untrackedCache=false",
    ):
        assert required_cfg in GLOBAL_GIT_ARGS

    assert runner.build_argv(tmp_path, ("status", "--short")) == [
        "git",
        *GLOBAL_GIT_ARGS,
        "-C",
        str(tmp_path),
        "status",
        "--short",
    ]


def test_git_runner_version_probe_and_parsing(tmp_path: Path) -> None:
    assert parse_git_version("git version 2.43.0\n") == ((2, 43, 0), "2.43.0")
    assert parse_git_version("git version 2.39.3 (Apple Git-146)\n") == ((2, 39, 3), "2.39.3")
    version = GitRunner().check_version(tmp_path)
    assert (version[0], version[1]) >= (2, 38)

    old_git = _write_executable_script(tmp_path / "old-git", 'echo "git version 2.37.9"')
    with pytest.raises(CapabilityUnavailable) as err:
        GitRunner(git_binary=str(old_git)).check_version(tmp_path)
    assert err.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert err.value.details == {"found": "2.37.9"}


def test_git_runner_missing_binary_timeout_and_nonzero_exit(tmp_path: Path) -> None:
    with pytest.raises(CapabilityUnavailable) as missing_err:
        GitRunner(git_binary=str(tmp_path / "no-such-git")).run(tmp_path, ("status",))
    assert missing_err.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert missing_err.value.details == {"tool": "git"}

    sleep_git = _write_executable_script(tmp_path / "sleep-git", "sleep 5")
    slow_runner = GitRunner(git_binary=str(sleep_git), default_timeout_s=0.1)
    with pytest.raises(BackendUnavailable) as timeout_err:
        slow_runner.run(
            tmp_path,
            (
                "fetch",
                "git+ssh://user:secret_tok@example.com/org/repo.git",
                "user:scp_secret@example.com:org/repo.git",
            ),
        )
    assert timeout_err.value.code is ErrorCode.BACKEND_UNAVAILABLE
    assert timeout_err.value.details["tool"] == "git"
    timeout_serialized = json.dumps(dict(timeout_err.value.details))
    assert "secret_tok" not in timeout_serialized
    assert "scp_secret" not in timeout_serialized

    fail_git = _write_executable_script(
        tmp_path / "fail-git",
        'echo "prefix-'
        + ("x" * 2400)
        + ' ssh+git://user:my_pass@example.com/repo.git user:scp_pw@host.test:org/repo.git" >&2; exit 128',
    )
    fail_runner = GitRunner(git_binary=str(fail_git))
    assert fail_runner.run(tmp_path, ("status",), check=False).exit_code == 128

    with pytest.raises(GitCommandFailed) as cmd_err:
        fail_runner.run(tmp_path, ("push", "https://tok_secret@example.com/repo.git"), check=True)
    assert cmd_err.value.code is ErrorCode.INTERNAL_ERROR
    assert cmd_err.value.exit_code == 128
    assert 1500 < len(cmd_err.value.stderr_tail) <= 2000
    serialized = json.dumps(dict(cmd_err.value.details))
    for secret in ("my_pass", "scp_pw", "tok_secret"):
        assert secret not in serialized
    assert "git@github.com:org/repo.git" in redact_git_text("git@github.com:org/repo.git")


def test_inspector_nonexistent_plain_dir_and_unborn_head(tmp_path: Path) -> None:
    inspector = GitRepositoryInspector(clock=_FixedClock())

    missing_obs = inspector.observe(tmp_path / "does-not-exist")
    assert (missing_obs.exists, missing_obs.toplevel, missing_obs.remotes, missing_obs.head) == (
        False,
        None,
        (),
        None,
    )
    assert (missing_obs.marker, missing_obs.dirty, missing_obs.observed_at) == (None, None, FIXED_NOW)

    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    with pytest.raises(ValidationFailed) as top_err:
        inspector.toplevel(plain_dir)
    assert top_err.value.code is ErrorCode.REPOSITORY_UNSAFE
    assert top_err.value.details.get("reason") == "not_a_repository"

    plain_obs = inspector.observe(plain_dir)
    assert (plain_obs.exists, plain_obs.toplevel, plain_obs.remotes, plain_obs.head, plain_obs.dirty) == (
        True,
        None,
        (),
        None,
        None,
    )

    empty_repo = init_git_repo(tmp_path / "empty-repo")
    empty_obs = inspector.observe(empty_repo.path)
    assert (empty_obs.exists, empty_obs.toplevel, empty_obs.head, empty_obs.remotes, empty_obs.dirty) == (
        True,
        str(empty_repo.path),
        None,
        (),
        False,
    )


def test_inspector_commits_remotes_dirty_subdir_and_worktree(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    sha1 = repo.commit_file("src/app.py", "x = 1\n", "first commit")
    repo.add_remote("upstream", "https://github.com/Example/Upstream.git")
    repo.add_remote("origin", "git@github.com:Example/Service.git")
    repo.add_remote("mirror", "https://github.com/Example/Service")

    inspector = GitRepositoryInspector(runner=repo.runner, clock=_FixedClock())
    assert [name for name, _ in inspector.remote_urls(repo.path)] == ["mirror", "origin", "upstream"]
    expected_remotes = (
        NormalizedRemote("github.com/Example/Service"),
        NormalizedRemote("github.com/Example/Upstream"),
    )
    assert inspector.remotes(repo.path) == expected_remotes

    obs = inspector.observe(repo.path)
    assert (obs.exists, obs.toplevel, obs.head, len(sha1), obs.dirty) == (
        True,
        str(repo.path),
        sha1,
        40,
        False,
    )
    assert obs.remotes == expected_remotes

    sub_obs = inspector.observe(repo.path / "src")
    assert (sub_obs.toplevel, sub_obs.head) == (str(repo.path), sha1)

    (repo.path / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    assert inspector.is_dirty(repo.path) is False
    assert inspector.observe(repo.path).dirty is False
    (repo.path / "untracked.txt").unlink()

    (repo.path / "src/app.py").write_text("x = 2\n", encoding="utf-8")
    assert inspector.is_dirty(repo.path) is True
    assert inspector.observe(repo.path).dirty is True
    sha2 = repo.commit_file("src/app.py", "x = 2\n", "second commit")
    assert (inspector.is_dirty(repo.path), inspector.head(repo.path)) == (False, sha2)

    (repo.path / "staged.txt").write_text("staged\n", encoding="utf-8")
    repo.runner.run(repo.path, ("add", "--", "staged.txt"), check=True)
    assert inspector.is_dirty(repo.path) is True
    repo.runner.run(repo.path, ("reset", "-q", "HEAD", "--", "staged.txt"), check=True)
    (repo.path / "staged.txt").unlink()
    assert inspector.is_dirty(repo.path) is False

    wt_path = repo.add_worktree(tmp_path / "wt-feature", "feature/wt")
    wt_obs = inspector.observe(wt_path)
    assert (wt_obs.exists, wt_obs.toplevel, wt_obs.head, wt_obs.remotes, wt_obs.dirty) == (
        True,
        str(wt_path),
        sha2,
        expected_remotes,
        False,
    )


def test_inspector_branch_exists_and_resolve(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    sha = repo.commit_file()
    repo.create_branch("release/v1")

    inspector = GitRepositoryInspector(runner=repo.runner, clock=_FixedClock())
    assert inspector.branch_exists(repo.path, "main") is True
    assert inspector.branch_exists(repo.path, "release/v1") is True
    assert inspector.branch_exists(repo.path, "missing-branch") is False
    assert inspector.branch_exists(repo.path, "bad..branch") is False
    assert (inspector.resolve(repo.path, "HEAD"), inspector.resolve(repo.path, "release/v1")) == (sha, sha)
    assert inspector.resolve(repo.path, sha) == sha

    with pytest.raises(NotFound) as missing_rev:
        inspector.resolve(repo.path, "nonexistent-ref")
    assert missing_rev.value.code is ErrorCode.NOT_FOUND

    for bad_input in ("-d", "--all", ""):
        with pytest.raises(ValidationFailed) as br_err:
            inspector.branch_exists(repo.path, bad_input)
        assert br_err.value.code is ErrorCode.SCHEMA_INVALID
        with pytest.raises(ValidationFailed) as rev_err:
            inspector.resolve(repo.path, bad_input)
        assert rev_err.value.code is ErrorCode.SCHEMA_INVALID


def test_inspector_marker_lifecycle_and_invalid_marker_diagnostics(tmp_path: Path) -> None:
    assert MARKER_FILENAME == ".skm/project.json"
    repo = init_git_repo(tmp_path / "repo")
    repo.commit_file()
    inspector = GitRepositoryInspector(runner=repo.runner, clock=_FixedClock())
    assert inspector.read_marker(repo.path) is None

    marker = _sample_marker()
    inspector.write_marker(repo.path, marker)
    marker_file = repo.path / MARKER_FILENAME
    assert stat.S_IMODE(os.lstat(marker_file.parent).st_mode) == 0o700
    assert stat.S_IMODE(os.lstat(marker_file).st_mode) == 0o600
    assert inspector.read_marker(repo.path) == marker
    obs_ok = inspector.observe(repo.path)
    assert (obs_ok.marker, obs_ok.dirty, inspector.last_diagnostics) == (marker, False, ())

    marker_file.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValidationFailed) as read_err:
        inspector.read_marker(repo.path)
    assert read_err.value.code is ErrorCode.SCHEMA_INVALID

    obs_bad_json, diags = inspector.observe_with_diagnostics(repo.path)
    assert (obs_bad_json.marker, diags, inspector.last_diagnostics) == (
        None,
        (MARKER_INVALID,),
        (MARKER_INVALID,),
    )

    clean_repo = init_git_repo(tmp_path / "clean-repo")
    clean_repo.commit_file()
    worker_diags: list[tuple[str, ...]] = []
    t = threading.Thread(
        target=lambda: (
            inspector.observe(clean_repo.path),
            worker_diags.append(inspector.last_diagnostics),
        )
    )
    t.start()
    t.join()
    assert worker_diags == [()]
    assert inspector.last_diagnostics == (MARKER_INVALID,)

    bad_doc = {**marker_to_document(marker), "schema": "urn:skm:workspace:checkout-marker:v99"}
    marker_file.write_text(json.dumps(bad_doc), encoding="utf-8")
    assert (inspector.observe(repo.path).marker, inspector.last_diagnostics) == (None, (MARKER_INVALID,))

    marker_file.write_text(" " * (MAX_MARKER_BYTES + 10), encoding="utf-8")
    with pytest.raises(ValidationFailed) as size_err:
        inspector.read_marker(repo.path)
    assert size_err.value.code is ErrorCode.SCHEMA_INVALID
    assert (inspector.observe(repo.path).marker, inspector.last_diagnostics) == (None, (MARKER_INVALID,))
