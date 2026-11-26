"""Workspace entity: the logical area of ownership (workspace §4.2, §4.3, §5.3, §5.4)."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import WorkspaceId

from .slug import Slug

__all__ = [
    "TITLE_MAX",
    "Workspace",
    "WorkspaceState",
    "archive",
    "new_workspace",
    "require_active",
    "valid_title",
]

TITLE_MAX = 200


class WorkspaceState(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class Workspace:
    id: WorkspaceId
    slug: Slug
    title: str
    state: WorkspaceState
    row_version: int
    created_at: datetime


def valid_title(title: str, *, field: str = "title") -> str:
    """Trimmed title of 1..200 characters; shared by the workspace, project and repository constructors."""
    trimmed = title.strip()
    if not 1 <= len(trimmed) <= TITLE_MAX:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"{field} must be 1..{TITLE_MAX} characters",
            details={"field": field},
        )
    return trimmed


def new_workspace(*, workspace_id: WorkspaceId, slug: Slug, title: str, now: datetime) -> Workspace:
    return Workspace(
        id=workspace_id,
        slug=slug,
        title=valid_title(title),
        state=WorkspaceState.ACTIVE,
        row_version=1,
        created_at=now,
    )


def archive(workspace: Workspace) -> Workspace:
    """``active|suspended -> archived``; archived is terminal and a repeated archive is a no-op (no event)."""
    if workspace.state is WorkspaceState.ARCHIVED:
        return workspace
    return replace(workspace, state=WorkspaceState.ARCHIVED, row_version=workspace.row_version + 1)


def require_active(workspace: Workspace) -> None:
    if workspace.state is not WorkspaceState.ACTIVE:
        raise PreconditionFailed(
            ErrorCode.PROJECT_ARCHIVED,
            f"workspace is {workspace.state.value}",
            details={"kind": "workspace", "workspace_id": str(workspace.id), "state": workspace.state.value},
        )
