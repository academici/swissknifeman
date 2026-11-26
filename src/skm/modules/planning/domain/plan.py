"""Plan aggregate: stable identity, lifecycle and revision counters (planning §4.4)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import ProjectId, WorkspaceId

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from skm.kernel.ids import PlanId, PrincipalId, RevisionId

__all__ = [
    "Plan",
    "PlanLifecycle",
    "PlanPurpose",
    "archive",
    "new_plan",
    "record_publication",
    "require_active",
    "require_editable",
]

_TITLE_MAX = 300


class PlanLifecycle(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class PlanPurpose(StrEnum):
    STANDARD = "standard"
    REVIEW_REQUESTS = "review_requests"


@dataclass(frozen=True, slots=True)
class Plan:
    id: PlanId
    workspace_id: WorkspaceId
    project_id: ProjectId
    alias: str
    purpose: PlanPurpose
    title: str
    lifecycle: PlanLifecycle
    current_revision_id: RevisionId | None
    next_revision_no: int
    row_version: int
    created_by: PrincipalId
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class _ProjectRef(Protocol):
    """The part of the workspace ``ProjectView`` the aggregate needs; domain does not import workspace."""

    @property
    def workspace_id(self) -> UUID: ...
    @property
    def project_id(self) -> UUID: ...


def _valid_title(title: str) -> str:
    trimmed = title.strip()
    if not 1 <= len(trimmed) <= _TITLE_MAX:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"title must be 1..{_TITLE_MAX} characters",
            details={"field": "title", "reason": "length"},
        )
    return trimmed


def new_plan(
    plan_id: PlanId,
    project: _ProjectRef,
    alias: str,
    title: str,
    actor: PrincipalId,
    now: datetime,
    *,
    purpose: PlanPurpose = PlanPurpose.STANDARD,
) -> Plan:
    """A plan before its first revision: ``next_revision_no = 1``, ``row_version = 1``, no current one."""
    return Plan(
        id=plan_id,
        workspace_id=WorkspaceId(project.workspace_id),
        project_id=ProjectId(project.project_id),
        alias=alias,
        purpose=purpose,
        title=_valid_title(title),
        lifecycle=PlanLifecycle.ACTIVE,
        current_revision_id=None,
        next_revision_no=1,
        row_version=1,
        created_by=actor,
        created_at=now,
        updated_at=now,
        archived_at=None,
    )


def require_active(plan: Plan) -> None:
    if plan.lifecycle is PlanLifecycle.ARCHIVED:
        raise PreconditionFailed(
            ErrorCode.PLAN_ARCHIVED,
            "the plan is archived",
            details={"plan_id": str(plan.id)},
        )


def require_editable(plan: Plan) -> None:
    """Active and not the system plan: drafts, archive, restore and import never touch ``review_requests``."""
    require_active(plan)
    if plan.purpose is PlanPurpose.REVIEW_REQUESTS:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "the review-requests plan is changed only by the review-request facade",
            details={"reason": "system_plan", "plan_id": str(plan.id)},
        )


def archive(plan: Plan, now: datetime) -> Plan:
    """Archive; an archived plan is returned as is (``result is plan``: the caller writes no events)."""
    if plan.lifecycle is PlanLifecycle.ARCHIVED:
        return plan
    return replace(
        plan,
        lifecycle=PlanLifecycle.ARCHIVED,
        archived_at=now,
        updated_at=now,
        row_version=plan.row_version + 1,
    )


def record_publication(plan: Plan, revision_id: RevisionId, title: str, now: datetime) -> Plan:
    """Point the plan at the revision it just received and take the next revision number.

    The title is the exact title of the revision's specification (§4.4): it is not stripped here, so the plan
    shows what the revision stores.
    """
    require_active(plan)
    return replace(
        plan,
        current_revision_id=revision_id,
        title=title,
        next_revision_no=plan.next_revision_no + 1,
        updated_at=now,
        row_version=plan.row_version + 1,
    )
