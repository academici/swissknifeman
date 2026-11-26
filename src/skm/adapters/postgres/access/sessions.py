"""PostgreSQL web session storage over ``skm_access.web_sessions`` (0006)."""

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.access.repositories import _run  # pyright: ignore[reportPrivateUsage]
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import PrincipalId
from skm.modules.access.domain.session import WebSession

__all__ = ["PostgresWebSessionRepository"]


class PostgresWebSessionRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, session: WebSession) -> None:
        row = _run(
            lambda: self._conn.execute(
                """INSERT INTO skm_access.web_sessions
                   (id, principal_id, secret_hash, created_at, expires_at, revoked_at)
                   VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id""",
                (
                    session.id,
                    session.principal_id,
                    session.secret_hash,
                    session.created_at,
                    session.expires_at,
                    session.revoked_at,
                ),
            ).fetchone()
        )
        if row is None:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "web session already exists")

    def get(self, session_id: UUID) -> WebSession | None:
        row = _run(
            lambda: self._conn.execute(
                """SELECT id, principal_id, secret_hash, created_at, expires_at, revoked_at
                   FROM skm_access.web_sessions WHERE id = %s""",
                (session_id,),
            ).fetchone()
        )
        if row is None:
            return None
        return WebSession(
            id=cast("UUID", row[0]),
            principal_id=PrincipalId(cast("UUID", row[1])),
            secret_hash=bytes(cast("bytes", row[2])),
            created_at=cast("datetime", row[3]),
            expires_at=cast("datetime", row[4]),
            revoked_at=cast("datetime | None", row[5]),
        )

    def find_by_hash(self, secret_hash: bytes) -> WebSession | None:
        row = _run(
            lambda: self._conn.execute(
                """SELECT id, principal_id, secret_hash, created_at, expires_at, revoked_at
                   FROM skm_access.web_sessions WHERE secret_hash = %s""",
                (secret_hash,),
            ).fetchone()
        )
        if row is None:
            return None
        return WebSession(
            id=cast("UUID", row[0]),
            principal_id=PrincipalId(cast("UUID", row[1])),
            secret_hash=bytes(cast("bytes", row[2])),
            created_at=cast("datetime", row[3]),
            expires_at=cast("datetime", row[4]),
            revoked_at=cast("datetime | None", row[5]),
        )

    def revoke(self, session_id: UUID, now: datetime) -> bool:
        row = _run(
            lambda: self._conn.execute(
                """UPDATE skm_access.web_sessions SET revoked_at = %s
                   WHERE id = %s AND revoked_at IS NULL RETURNING id""",
                (now, session_id),
            ).fetchone()
        )
        return row is not None

    def revoke_for_principal(self, principal_id: PrincipalId, now: datetime) -> int:
        rows = _run(
            lambda: self._conn.execute(
                """UPDATE skm_access.web_sessions SET revoked_at = %s
                   WHERE principal_id = %s AND revoked_at IS NULL RETURNING id""",
                (now, principal_id),
            ).fetchall()
        )
        return len(rows)

    def revoke_all(self, now: datetime) -> int:
        rows = _run(
            lambda: self._conn.execute(
                """UPDATE skm_access.web_sessions SET revoked_at = %s
                   WHERE revoked_at IS NULL RETURNING id""",
                (now,),
            ).fetchall()
        )
        return len(rows)
