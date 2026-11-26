from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from skm.kernel.ids import FileVersionId, PrincipalId, WorkspaceId
from skm.modules.artifacts.domain.access_grant import AccessGrant, AccessGrantId, GrantReason, grant_is_active

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WS = WorkspaceId(uuid4())
USER = PrincipalId(uuid4())
VERSION_A = FileVersionId(uuid4())
VERSION_B = FileVersionId(uuid4())


def _grant() -> AccessGrant:
    return AccessGrant(
        AccessGrantId(uuid4()),
        WS,
        USER,
        VERSION_A,
        GrantReason.ASSIGNMENT,
        "a1",
        NOW + timedelta(hours=1),
        NOW,
        None,
    )


def test_active_until_expiry_or_revoke() -> None:
    g = _grant()
    assert grant_is_active(g, NOW)
    assert not grant_is_active(g, g.expires_at)
    assert not grant_is_active(replace(g, revoked_at=NOW), NOW)


def test_grant_names_one_exact_version() -> None:
    # equal digests of two versions never widen a grant: it carries only a version id
    g = _grant()
    assert g.file_version_id == VERSION_A != VERSION_B
