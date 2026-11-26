"""Test helpers for creating and manipulating temporary local Git repositories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skm.adapters.git.runner import GitRunner

__all__ = ["GitRepoFixture", "add_remote", "add_worktree", "commit_file", "create_branch", "init_git_repo"]

_COMMIT_IDENTITY_ARGS: tuple[str, ...] = (
    "-c",
    "user.name=SKM Test",
    "-c",
    "user.email=test@example.test",
    "-c",
    "commit.gpgsign=false",
)


@dataclass(frozen=True, slots=True)
class GitRepoFixture:
    """Wrapper around a temporary Git repository for integration and security tests."""

    path: Path
    runner: GitRunner

    def commit_file(
        self, rel_path: str = "README.md", content: str = "initial\n", message: str = "initial commit"
    ) -> str:
        return commit_file(self.path, rel_path=rel_path, content=content, message=message, runner=self.runner)

    def add_remote(self, name: str, url: str) -> None:
        add_remote(self.path, name=name, url=url, runner=self.runner)

    def create_branch(self, branch: str, *, start_point: str = "HEAD") -> None:
        create_branch(self.path, branch=branch, start_point=start_point, runner=self.runner)

    def add_worktree(self, target: Path, branch: str) -> Path:
        return add_worktree(self.path, target=target, branch=branch, runner=self.runner)


def init_git_repo(
    path: Path, *, initial_branch: str = "main", runner: GitRunner | None = None
) -> GitRepoFixture:
    """Initialize a new Git repository at ``path``."""
    path.mkdir(parents=True, exist_ok=True)
    git = runner if runner is not None else GitRunner()
    git.run(path, ("init", "--initial-branch", initial_branch), check=True)
    return GitRepoFixture(path=path, runner=git)


def commit_file(
    repo_path: Path,
    *,
    rel_path: str = "README.md",
    content: str = "hello\n",
    message: str = "commit file",
    runner: GitRunner | None = None,
) -> str:
    """Write ``rel_path`` in ``repo_path``, stage it, commit it, and return the commit SHA."""
    git = runner if runner is not None else GitRunner()
    file_path = repo_path / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    git.run(repo_path, ("add", "--", rel_path), check=True)
    git.run(repo_path, (*_COMMIT_IDENTITY_ARGS, "commit", "-m", message), check=True)
    res = git.run(repo_path, ("rev-parse", "--verify", "HEAD"), check=True)
    return res.stdout.strip().lower()


def add_remote(repo_path: Path, *, name: str, url: str, runner: GitRunner | None = None) -> None:
    """Add a named remote to ``repo_path``."""
    git = runner if runner is not None else GitRunner()
    git.run(repo_path, ("remote", "add", name, url), check=True)


def create_branch(
    repo_path: Path, *, branch: str, start_point: str = "HEAD", runner: GitRunner | None = None
) -> None:
    """Create a branch in ``repo_path`` without switching HEAD."""
    git = runner if runner is not None else GitRunner()
    git.run(repo_path, ("branch", branch, start_point), check=True)


def add_worktree(repo_path: Path, *, target: Path, branch: str, runner: GitRunner | None = None) -> Path:
    """Create a linked Git worktree at ``target`` on a new branch ``branch``."""
    git = runner if runner is not None else GitRunner()
    git.run(repo_path, ("worktree", "add", "-b", branch, str(target)), check=True)
    return target
