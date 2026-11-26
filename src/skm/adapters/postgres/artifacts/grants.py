"""PostgreSQL grants repositories with local parameterized SQL (artifacts §6, §11).

Connections belong to the surrounding UoW; checked row decoding lives in mapping.py.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Final

import psycopg

from skm.adapters.postgres.artifacts import mapping
from skm.adapters.postgres.jsonb import require_aware
from skm.kernel.ids import FileVersionId, PrincipalId
from skm.modules.artifacts.domain.access_grant import AccessGrant, AccessGrantId, GrantReason

__all__ = ["PostgresAccessGrantRepository"]

_GRANT_COLS: Final = (
    "SELECT id, workspace_id, principal_id, file_version_id, reason, ref, expires_at, created_at, revoked_at "
    "FROM skm_artifacts.access_grants "
)

_GRANT_CLAIM_LOCK: Final = "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"

_GRANT_ACTIVE_CLASH: Final = (
    "SELECT 1 FROM skm_artifacts.access_grants WHERE principal_id = %s AND file_version_id = %s "
    "AND reason = %s AND ref = %s AND revoked_at IS NULL AND expires_at > %s LIMIT 1"
)

_GRANT_INSERT: Final = (
    "INSERT INTO skm_artifacts.access_grants (id, workspace_id, principal_id, file_version_id, reason, ref, "
    "expires_at, created_at, revoked_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (id) DO NOTHING RETURNING id"
)

_GRANT_ACTIVE_FOR: Final = (
    _GRANT_COLS + "WHERE principal_id = %(principal)s AND file_version_id = %(version)s "
    "AND (%(reason)s::text IS NULL OR reason = %(reason)s::text) "
    "AND (%(ref)s::text IS NULL OR ref = %(ref)s::text) "
    "AND revoked_at IS NULL AND expires_at > %(now)s "
    "ORDER BY expires_at DESC, created_at DESC, id DESC LIMIT 1"
)

_GRANT_HELD_CLAIMS: Final = (
    "SELECT DISTINCT file_version_id FROM skm_artifacts.access_grants "
    "WHERE principal_id = %s AND file_version_id = ANY(%s::uuid[]) AND reason = %s AND ref = %s "
    "AND revoked_at IS NULL AND expires_at > %s"
)

_GRANT_REVOKE_BY_REF: Final = (
    "UPDATE skm_artifacts.access_grants SET revoked_at = %s "
    "WHERE reason = %s AND ref = %s AND revoked_at IS NULL"
)

_GRANT_EXTEND_BY_REF: Final = (
    "UPDATE skm_artifacts.access_grants SET expires_at = greatest(expires_at, %s) "
    "WHERE reason = %s AND ref = %s AND revoked_at IS NULL AND expires_at > %s"
)


class PostgresAccessGrantRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add_many(self, grants: Sequence[AccessGrant]) -> None:
        if not grants:
            return
        seen_ids: set[AccessGrantId] = set()
        batch: list[AccessGrant] = []
        for grant in grants:
            require_aware(grant.expires_at)
            require_aware(grant.created_at)
            mapping.opt_aware(grant.revoked_at)
            claim = (grant.principal_id, grant.file_version_id, grant.reason, grant.ref)
            clash = grant.revoked_at is None and any(
                (other.principal_id, other.file_version_id, other.reason, other.ref) == claim
                and other.expires_at > grant.created_at
                for other in batch
            )
            if grant.id in seen_ids or clash:
                raise mapping.exists("access_grant", file_version_id=str(grant.file_version_id))
            seen_ids.add(grant.id)
            batch.append(grant)

        lock_keys = sorted(
            {
                f"{g.principal_id}:{g.file_version_id}:{GrantReason(g.reason).value}:{g.ref}"
                for g in grants
                if g.revoked_at is None
            }
        )

        def write() -> None:
            for key in lock_keys:
                mapping.run(lambda key=key: self._conn.execute(_GRANT_CLAIM_LOCK, (key,)))
            for g in grants:
                r_val = GrantReason(g.reason).value
                if g.revoked_at is None:
                    clash_args = (g.principal_id, g.file_version_id, r_val, g.ref, g.created_at)
                    if mapping.run(
                        lambda a=clash_args: self._conn.execute(_GRANT_ACTIVE_CLASH, a).fetchone()
                    ):
                        raise mapping.exists("access_grant", file_version_id=str(g.file_version_id))
                ins_args = (
                    g.id, g.workspace_id, g.principal_id, g.file_version_id, r_val, g.ref,
                    g.expires_at, g.created_at, g.revoked_at,
                )  # fmt: skip
                if mapping.run(lambda a=ins_args: self._conn.execute(_GRANT_INSERT, a).fetchone()) is None:
                    raise mapping.exists("access_grant", file_version_id=str(g.file_version_id))

        mapping.in_savepoint(self._conn, write)

    def active_for(
        self,
        principal_id: PrincipalId,
        version_id: FileVersionId,
        now: datetime,
        *,
        reason: GrantReason | None = None,
        ref: str | None = None,
    ) -> AccessGrant | None:
        params = {
            "principal": principal_id,
            "version": version_id,
            "reason": None if reason is None else GrantReason(reason).value,
            "ref": ref,
            "now": require_aware(now),
        }
        row = mapping.run(lambda: self._conn.execute(_GRANT_ACTIVE_FOR, params).fetchone())
        return None if row is None else mapping.access_grant_from_row(row)

    def held_claims(
        self,
        principal_id: PrincipalId,
        version_ids: Sequence[FileVersionId],
        now: datetime,
        *,
        reason: GrantReason,
        ref: str,
    ) -> frozenset[FileVersionId]:
        wanted = list(dict.fromkeys(version_ids))
        if not wanted:
            return frozenset()
        params = (principal_id, wanted, GrantReason(reason).value, ref, require_aware(now))
        rows = mapping.run(lambda: self._conn.execute(_GRANT_HELD_CLAIMS, params).fetchall())
        return frozenset(FileVersionId(row[0]) for row in rows)

    def revoke_by_ref(self, reason: GrantReason, ref: str, at: datetime) -> int:
        params = (require_aware(at), GrantReason(reason).value, ref)
        return mapping.run(lambda: self._conn.execute(_GRANT_REVOKE_BY_REF, params)).rowcount

    def extend_by_ref(self, reason: GrantReason, ref: str, expires_at: datetime, now: datetime) -> int:
        params = (require_aware(expires_at), GrantReason(reason).value, ref, require_aware(now))
        return mapping.run(lambda: self._conn.execute(_GRANT_EXTEND_BY_REF, params)).rowcount
