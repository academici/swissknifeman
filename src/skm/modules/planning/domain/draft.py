"""Draft aggregate: the editable specification document with optimistic ``edit_version`` (planning §4.4).

Every transition checks the state first and the version second: an abandoned draft answers
``DRAFT_NOT_OPEN`` even when the caller's version is also stale.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Final, NewType
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed
from skm.modules.planning.domain.plan import require_editable

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.ids import PlanId, PrincipalId, RevisionId, WorkspaceId
    from skm.kernel.json_types import JsonObject
    from skm.modules.planning.domain.plan import Plan

__all__ = [
    "Draft",
    "DraftId",
    "DraftState",
    "abandon",
    "is_stale",
    "mark_published",
    "open_draft",
    "rebase",
    "require_current_base",
    "require_edit_version",
    "require_in_plan",
    "require_open",
    "save",
]

DraftId = NewType("DraftId", UUID)

FIRST_EDIT_VERSION: Final = 1


class DraftState(StrEnum):
    OPEN = "open"
    PUBLISHED = "published"
    ABANDONED = "abandoned"


@dataclass(frozen=True, slots=True)
class Draft:
    id: DraftId
    plan_id: PlanId
    workspace_id: WorkspaceId
    base_revision_id: RevisionId | None
    edit_version: int
    document: JsonObject
    state: DraftState
    published_revision_id: RevisionId | None
    created_by: PrincipalId
    created_at: datetime
    updated_by: PrincipalId
    updated_at: datetime
    closed_at: datetime | None


def require_in_plan(draft: Draft, plan_id: PlanId) -> None:
    """A draft of another plan is reported as absent: its existence is not disclosed."""
    if draft.plan_id != plan_id:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "draft not found",
            details={"kind": "draft", "ref": str(draft.id)},
        )


def require_open(draft: Draft) -> None:
    if draft.state is not DraftState.OPEN:
        raise PreconditionFailed(
            ErrorCode.DRAFT_NOT_OPEN,
            "the draft is closed",
            details={"draft_id": str(draft.id), "state": draft.state.value},
        )


def require_edit_version(draft: Draft, expected_edit_version: int) -> None:
    if draft.edit_version != expected_edit_version:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            "the draft was changed by another edit",
            details={"expected": expected_edit_version, "actual": draft.edit_version},
        )


def _require_writable(draft: Draft, expected_edit_version: int) -> None:
    require_open(draft)
    require_edit_version(draft, expected_edit_version)


def is_stale(draft: Draft, plan: Plan) -> bool:
    """An open draft whose base is not the plan's current revision (``None`` equals ``None``)."""
    return draft.state is DraftState.OPEN and draft.base_revision_id != plan.current_revision_id


def require_current_base(draft: Draft, plan: Plan) -> None:
    if draft.base_revision_id != plan.current_revision_id:
        raise Conflict(
            ErrorCode.BASE_REVISION_CHANGED,
            "the plan has a newer revision than the draft base",
            details={
                "base_revision_id": None if draft.base_revision_id is None else str(draft.base_revision_id),
                "current_revision_id": (
                    None if plan.current_revision_id is None else str(plan.current_revision_id)
                ),
            },
        )


def open_draft(
    draft_id: DraftId,
    plan: Plan,
    base_revision_id: RevisionId | None,
    document: JsonObject,
    actor: PrincipalId,
    now: datetime,
) -> Draft:
    """The ``max_open`` limit is counted by the handler under the plan lock (siblings are not seen here)."""
    require_editable(plan)
    return Draft(
        id=draft_id,
        plan_id=plan.id,
        workspace_id=plan.workspace_id,
        base_revision_id=base_revision_id,
        edit_version=FIRST_EDIT_VERSION,
        document=copy.deepcopy(document),
        state=DraftState.OPEN,
        published_revision_id=None,
        created_by=actor,
        created_at=now,
        updated_by=actor,
        updated_at=now,
        closed_at=None,
    )


def save(
    draft: Draft,
    document: JsonObject,
    expected_edit_version: int,
    actor: PrincipalId,
    now: datetime,
) -> Draft:
    _require_writable(draft, expected_edit_version)
    return replace(
        draft,
        document=copy.deepcopy(document),
        edit_version=draft.edit_version + 1,
        updated_by=actor,
        updated_at=now,
    )


def rebase(
    draft: Draft,
    document: JsonObject,
    new_base_revision_id: RevisionId | None,
    expected_edit_version: int,
    actor: PrincipalId,
    now: datetime,
) -> Draft:
    _require_writable(draft, expected_edit_version)
    return replace(
        draft,
        document=copy.deepcopy(document),
        base_revision_id=new_base_revision_id,
        edit_version=draft.edit_version + 1,
        updated_by=actor,
        updated_at=now,
    )


def abandon(
    draft: Draft,
    expected_edit_version: int,
    now: datetime,
    *,
    actor: PrincipalId | None = None,
) -> Draft:
    """Close without publishing; the document is untouched, so ``edit_version`` stays."""
    _require_writable(draft, expected_edit_version)
    return replace(
        draft,
        state=DraftState.ABANDONED,
        closed_at=now,
        updated_at=now,
        updated_by=draft.updated_by if actor is None else actor,
    )


def mark_published(
    draft: Draft,
    revision_id: RevisionId,
    now: datetime,
    *,
    actor: PrincipalId | None = None,
) -> Draft:
    """Called by ``publish_revision`` under the draft lock, after the state and version were checked."""
    require_open(draft)
    return replace(
        draft,
        state=DraftState.PUBLISHED,
        published_revision_id=revision_id,
        closed_at=now,
        updated_at=now,
        updated_by=draft.updated_by if actor is None else actor,
    )
