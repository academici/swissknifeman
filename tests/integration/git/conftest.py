"""Real local Git fixtures: no donor packages or inherited credentials."""

from pathlib import Path
from uuid import uuid4

import pytest

from skm.adapters.git.environments.worktree import CleanupProof
from skm.adapters.git.runner import GitRunner
from skm.kernel.ids import AttemptId, RepositoryId
from skm.modules.execution.domain.environment import EnvironmentKind, attempt_branch
from skm.modules.execution.host.environment import EnvironmentMount, EnvironmentSpec

AUTHOR = {
    "GIT_AUTHOR_NAME": "Test Worker",
    "GIT_AUTHOR_EMAIL": "worker@example.invalid",
    "GIT_COMMITTER_NAME": "Test Worker",
    "GIT_COMMITTER_EMAIL": "worker@example.invalid",
}


def make_repo(root: Path) -> tuple[GitRunner, str]:
    root.mkdir()
    git = GitRunner()
    git.run(root, ["init", "--initial-branch=main"])
    (root / "file.txt").write_bytes(b"initial\nsecond\n")
    git.run(root, ["add", "--", "file.txt"])
    head = git.run_bytes(root, ["commit", "-m", "initial"], env=AUTHOR)
    assert head.exit_code == 0
    return git, git.run(root, ["rev-parse", "HEAD"]).stdout.strip()


def environment_spec(root: Path, repository: Path, *, kind=EnvironmentKind.GIT_WORKTREE, baseline="HEAD"):
    attempt_id = AttemptId(uuid4())
    mount = EnvironmentMount("main", RepositoryId(uuid4()), str(repository), baseline)
    return EnvironmentSpec(attempt_id, kind, (mount,), attempt_branch(attempt_id), root, None, None)


def safe_cleanup(_environment):
    return CleanupProof(True, True, True)


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    git, head = make_repo(root)
    return root, git, head
