"""Execution environments of attempts (execution §4.10).

One environment per attempt on one host. The baseline records, per mount, the commit the attempt starts
from and the source ``HEAD``; a clean environment has ``source_head_sha == commit_sha`` and no dirty patch,
an ``existing_checkout`` with local changes starts from a synthetic baseline commit whose parent is
``HEAD`` and keeps the dirty bytes as separate evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.ids import AttemptId, FileVersionId, HostId, RepositoryId
    from skm.modules.execution.domain.ids import EnvironmentId

__all__ = [
    "BaselineEntry",
    "EnvironmentKind",
    "EnvironmentState",
    "ExecutionEnvironment",
    "attempt_branch",
]


class EnvironmentKind(StrEnum):
    GIT_WORKTREE = "git_worktree"
    EXISTING_CHECKOUT = "existing_checkout"
    MANAGED_CLONE = "managed_clone"


class EnvironmentState(StrEnum):
    PREPARING = "preparing"
    READY = "ready"
    DISCARDED = "discarded"
    RETAINED = "retained"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class BaselineEntry:
    mount: str
    repository_id: RepositoryId
    commit_sha: str
    source_head_sha: str
    dirty_patch_file_version_id: FileVersionId | None

    @property
    def clean(self) -> bool:
        return self.dirty_patch_file_version_id is None and self.commit_sha == self.source_head_sha


@dataclass(frozen=True, slots=True)
class ExecutionEnvironment:
    id: EnvironmentId
    attempt_id: AttemptId
    host_id: HostId
    kind: EnvironmentKind
    baseline: tuple[BaselineEntry, ...]
    branch: str
    local_locator: str
    state: EnvironmentState
    created_at: datetime
    discarded_at: datetime | None
    removed_at: datetime | None

    def __post_init__(self) -> None:
        problems: list[str] = []
        if self.branch != attempt_branch(self.attempt_id):
            problems.append("the branch of an attempt is skm/attempt/<attempt_id>")
        mounts = [entry.mount for entry in self.baseline]
        if len(set(mounts)) != len(mounts):
            problems.append("one baseline entry per mount")
        if self.kind is not EnvironmentKind.EXISTING_CHECKOUT and not all(
            entry.clean for entry in self.baseline
        ):
            problems.append("only an existing checkout starts from a dirty snapshot")
        if (self.state is EnvironmentState.REMOVED) != (self.removed_at is not None):
            problems.append("removed_at is set exactly for a removed environment")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "environment invariants violated: " + "; ".join(problems),
                details={"environment_id": str(self.id), "violations": list(problems)},
            )


def attempt_branch(attempt_id: AttemptId) -> str:
    """The attempt's branch ``skm/attempt/<attempt_id>``."""
    return f"skm/attempt/{attempt_id}"
