"""Project entity: an area of engineering work inside a workspace (workspace §4.2, §5.4)."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import ProjectId, WorkspaceId

from .slug import Slug
from .workspace import valid_title

__all__ = ["DESCRIPTION_MAX", "Project", "ProjectState", "archive", "new_project", "require_active"]

DESCRIPTION_MAX = 4000


class ProjectState(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class Project:
    id: ProjectId
    workspace_id: WorkspaceId
    slug: Slug
    title: str
    description: str
    state: ProjectState
    row_version: int
    created_at: datetime


def new_project(
    *,
    project_id: ProjectId,
    workspace_id: WorkspaceId,
    slug: Slug,
    title: str,
    description: str,
    now: datetime,
) -> Project:
    """Pure constructor: validation of the title and description lives here, not in the handler."""
    if len(description) > DESCRIPTION_MAX:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"description must be at most {DESCRIPTION_MAX} characters",
            details={"field": "description"},
        )
    return Project(
        id=project_id,
        workspace_id=workspace_id,
        slug=slug,
        title=valid_title(title),
        description=description,
        state=ProjectState.ACTIVE,
        row_version=1,
        created_at=now,
    )


def archive(project: Project) -> Project:
    """``active -> archived``; a repeated archive is a no-op the handler must not record an event for."""
    if project.state is ProjectState.ARCHIVED:
        return project
    return replace(project, state=ProjectState.ARCHIVED, row_version=project.row_version + 1)


def require_active(project: Project) -> None:
    if project.state is not ProjectState.ACTIVE:
        raise PreconditionFailed(
            ErrorCode.PROJECT_ARCHIVED,
            "project is archived",
            details={"kind": "project", "project_id": str(project.id)},
        )
