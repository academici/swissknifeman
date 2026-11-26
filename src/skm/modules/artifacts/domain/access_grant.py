"""AccessGrant: a time-boxed right to one exact file version; equal digests share nothing."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType
from uuid import UUID

from skm.kernel.ids import FileVersionId, PrincipalId, WorkspaceId

__all__ = ["AccessGrant", "AccessGrantId", "GrantReason", "grant_is_active"]


class GrantReason(StrEnum):
    ASSIGNMENT = "assignment"
    SHARE = "share"


AccessGrantId = NewType("AccessGrantId", UUID)


@dataclass(frozen=True, slots=True)
class AccessGrant:
    id: AccessGrantId
    workspace_id: WorkspaceId
    principal_id: PrincipalId
    file_version_id: FileVersionId
    reason: GrantReason
    ref: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None


def grant_is_active(grant: AccessGrant, now: datetime) -> bool:
    return grant.revoked_at is None and grant.expires_at > now
