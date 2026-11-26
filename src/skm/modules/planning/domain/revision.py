"""Immutable revision metadata (planning §4.4).

A revision is only ever created: neither this module nor the repository port has an update, and the database
refuses one (planning I1). A rollback is a new revision that copies an older payload (I9).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.modules.planning.domain.canonical import CANONICALIZATION_VERSION
from skm.modules.planning.domain.compile_graph import COMPILER_VERSION
from skm.modules.planning.domain.plan import require_active

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.ids import PlanId, PrincipalId, RevisionId, WorkspaceId
    from skm.modules.planning.domain.plan import Plan

__all__ = ["SCHEMA_VERSION", "RevisionMeta", "RevisionOrigin", "new_revision_meta"]

SCHEMA_VERSION: Final = 1

_DIGEST: Final = re.compile(r"sha256:[0-9a-f]{64}")
_REASON_MAX: Final = 2000


class RevisionOrigin(StrEnum):
    DRAFT = "draft"
    RESTORE = "restore"
    IMPORT = "import"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class RevisionMeta:
    id: RevisionId
    plan_id: PlanId
    workspace_id: WorkspaceId
    revision_no: int
    parent_revision_id: RevisionId | None
    schema_version: int
    content_digest: str
    canonicalization_version: int
    compiler_version: int
    origin: RevisionOrigin
    restored_from_revision_id: RevisionId | None
    published_by: PrincipalId
    published_at: datetime
    change_reason: str


def new_revision_meta(
    revision_id: RevisionId,
    plan: Plan,
    *,
    content_digest: str,
    origin: RevisionOrigin,
    restored_from: RevisionId | None,
    change_reason: str,
    actor: PrincipalId,
    now: datetime,
) -> RevisionMeta:
    """Metadata of the revision the next publication of ``plan`` writes (``plan.next_revision_no``)."""
    require_active(plan)
    if not _DIGEST.fullmatch(content_digest):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            "content digest is not sha256:<64 hex>",
            details={"reason": "digest_form"},
        )
    if (origin is RevisionOrigin.RESTORE) != (restored_from is not None):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            "restored_from_revision_id is set exactly for the restore origin",
            details={"reason": "restored_from", "origin": origin.value},
        )
    if restored_from is not None and (plan.current_revision_id is None or restored_from == revision_id):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            "a restore copies an older revision of a plan that already has one",
            details={"reason": "restored_from"},
        )
    reason = change_reason.strip()
    if not 1 <= len(reason) <= _REASON_MAX:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"reason must be 1..{_REASON_MAX} characters",
            details={"field": "reason", "reason": "length"},
        )
    return RevisionMeta(
        id=revision_id,
        plan_id=plan.id,
        workspace_id=plan.workspace_id,
        revision_no=plan.next_revision_no,
        parent_revision_id=plan.current_revision_id,
        schema_version=SCHEMA_VERSION,
        content_digest=content_digest,
        canonicalization_version=CANONICALIZATION_VERSION,
        compiler_version=COMPILER_VERSION,
        origin=origin,
        restored_from_revision_id=restored_from,
        published_by=actor,
        published_at=now,
        change_reason=reason,
    )
