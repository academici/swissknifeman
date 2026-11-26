"""A long-lived process proves a plain checkout's identity once per few seconds, never across a change."""

from __future__ import annotations

from pathlib import Path
from typing import override

import pytest

from skm.adapters.git.repo_inspect import MARKER_FILENAME, GitRepositoryInspector
from skm.bootstrap import checkout_operations
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.workspace.domain.checkout_binding import ObservedCheckout
from support.git_repo import init_git_repo

REMOTE = "github.com/org/skm"


class _CountingInspector(GitRepositoryInspector):
    def __init__(self) -> None:
        super().__init__()
        self.observed = 0

    @override
    def observe(
        self, path: str | Path, *, marker_relpath: str = MARKER_FILENAME, timeout_seconds: float = 60.0
    ) -> ObservedCheckout:
        self.observed += 1
        return super().observe(path, marker_relpath=marker_relpath, timeout_seconds=timeout_seconds)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fresh = type(checkout_operations._PROOFS)(ttl_seconds=3600)
    monkeypatch.setattr(checkout_operations, "_PROOFS", fresh)
    fixture = init_git_repo(tmp_path / "work")
    fixture.commit_file("README.md", "# x\n", message="init")
    fixture.add_remote("origin", "https://github.com/org/skm.git")
    return fixture.path.resolve()


def test_repeated_hooks_prove_the_same_checkout_once(repo: Path) -> None:
    inspector = _CountingInspector()
    for _ in range(5):
        assert checkout_operations._check_identity(inspector, repo, REMOTE) == repo
    assert inspector.observed == 1  # Before: 5, each running four git processes.


def test_a_changed_remote_is_proven_again_at_once(repo: Path) -> None:
    inspector = _CountingInspector()
    checkout_operations._check_identity(inspector, repo, REMOTE)
    init_git_repo(repo).runner.run(
        repo, ("remote", "set-url", "origin", "https://example.test/other.git"), check=True
    )
    with pytest.raises(SkmError) as raised:
        checkout_operations._check_identity(inspector, repo, REMOTE)
    assert raised.value.code is ErrorCode.CHECKOUT_MISMATCH


def test_a_failed_proof_is_never_remembered(repo: Path) -> None:
    inspector = _CountingInspector()
    for _ in range(2):
        with pytest.raises(SkmError):
            checkout_operations._check_identity(inspector, repo, "https://example.test/not-bound.git")
    assert inspector.observed == 2


def test_an_expired_proof_is_repeated(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    short = type(checkout_operations._PROOFS)(ttl_seconds=3.0, clock=lambda: now[0])
    monkeypatch.setattr(checkout_operations, "_PROOFS", short)
    inspector = _CountingInspector()
    checkout_operations._check_identity(inspector, repo, REMOTE)
    now[0] += 2.9
    checkout_operations._check_identity(inspector, repo, REMOTE)
    now[0] += 0.2
    checkout_operations._check_identity(inspector, repo, REMOTE)
    assert inspector.observed == 2


def test_a_worktree_style_git_file_is_always_proven(repo: Path, tmp_path: Path) -> None:
    fixture = init_git_repo(repo)
    branch = tmp_path / "linked"
    linked = fixture.add_worktree(branch, "side").resolve()
    inspector = _CountingInspector()
    for _ in range(3):
        checkout_operations._check_identity(inspector, linked, REMOTE)
    assert inspector.observed == 3


def test_cached_observation_revalidates_the_checkout_trust(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skm.adapters.git import runner

    inspector = _CountingInspector()
    checkout_operations._check_identity(inspector, repo, REMOTE)
    checked: list[Path] = []
    original = runner._validate_dot_git

    def track(root: Path, dot_git: Path) -> None:
        checked.append(root)
        original(root, dot_git)

    monkeypatch.setattr(runner, "_validate_dot_git", track)
    checkout_operations._check_identity(inspector, repo, REMOTE)
    assert repo in checked
    assert inspector.observed == 1


def test_worktree_specific_configuration_is_observed_each_time(repo: Path) -> None:
    (repo / ".git/config.worktree").write_text("# worktree-specific configuration\n")
    inspector = _CountingInspector()
    for _ in range(2):
        checkout_operations._check_identity(inspector, repo, REMOTE)
    assert inspector.observed == 2
