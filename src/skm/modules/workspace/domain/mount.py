"""Mounts: the binding of a repository to a project under a mount name (workspace §4.2, §5.3)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Final, override

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed, ValidationFailed
from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId

if TYPE_CHECKING:
    from .project import Project
    from .repository import Repository

__all__ = ["DEFAULT_MOUNT_NAME", "MountName", "MountRole", "ProjectRepository", "attach", "detach"]

# Same language as the ``mount_name`` definition of ``urn:skm:workspace:defs:v1``.
_MOUNT_NAME: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
DEFAULT_MOUNT_NAME: Final = "main"


class MountRole(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    DOCS = "docs"
    INFRA = "infra"


@dataclass(frozen=True, slots=True)
class MountName:
    value: str

    def __post_init__(self) -> None:
        if not _MOUNT_NAME.fullmatch(self.value):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "mount name must match ^[a-z0-9][a-z0-9_-]{0,31}$",
                details={"field": "mount_name", "value": self.value},
            )

    @override
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ProjectRepository:
    workspace_id: WorkspaceId
    project_id: ProjectId
    repository_id: RepositoryId
    mount_name: MountName
    role: MountRole
    attached_at: datetime


def attach(
    project: Project,
    repository: Repository,
    mount_name: MountName,
    role: MountRole,
    existing_mounts: Sequence[ProjectRepository],
    *,
    now: datetime,
) -> ProjectRepository:
    """A repository of the project's workspace, under a name unique in the project, at most one primary."""
    if repository.workspace_id != project.workspace_id:
        raise PreconditionFailed(
            ErrorCode.CHECKOUT_MISMATCH,
            "the repository belongs to another workspace",
            details={"reason": "other_workspace"},
        )
    mounts = [item for item in existing_mounts if item.project_id == project.id]
    if any(item.mount_name == mount_name for item in mounts):
        raise Conflict(
            ErrorCode.ALREADY_EXISTS,
            "the mount name is already used in the project",
            details={"kind": "mount", "mount_name": mount_name.value},
        )
    if role is MountRole.PRIMARY and any(item.role is MountRole.PRIMARY for item in mounts):
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "the project already has a primary mount",
            details={"reason": "primary_exists"},
        )
    return ProjectRepository(
        workspace_id=project.workspace_id,
        project_id=project.id,
        repository_id=repository.id,
        mount_name=mount_name,
        role=role,
        attached_at=now,
    )


def detach(
    existing_mounts: Sequence[ProjectRepository], project_id: ProjectId, mount_name: MountName
) -> ProjectRepository | None:
    """The mount to remove, or ``None`` when the project has no such mount (no event for that)."""
    for item in existing_mounts:
        if item.project_id == project_id and item.mount_name == mount_name:
            return item
    return None
