"""PostgreSQL pairing storage. Exchange holds the row lock in its caller's UoW."""

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from skm.adapters.postgres.access.repositories import _run  # pyright: ignore[reportPrivateUsage]
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed
from skm.kernel.ids import PrincipalId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.access.domain.pairing import PairingResult, PairingToken
from skm.modules.access.domain.token import TokenId

__all__ = ["PostgresPairingRepository"]


class PostgresPairingRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, pairing: PairingToken) -> None:
        row = _run(
            lambda: self._conn.execute(
                """INSERT INTO skm_access.pairing_tokens
               (id, issuer_id, issuer_token_id, workspace_id, secret_hash, binding, created_at, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id""",
                (
                    pairing.id,
                    pairing.issuer_id,
                    pairing.issuer_token_id,
                    pairing.workspace_id,
                    pairing.secret_hash,
                    Jsonb(pairing.binding),
                    pairing.created_at,
                    pairing.expires_at,
                ),
            ).fetchone()
        )
        if row is None:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "pairing credential already exists")

    def get_for_update(self, pairing_id: UUID) -> PairingToken | None:
        row = _run(
            lambda: self._conn.execute(
                """SELECT issuer_id, issuer_token_id, workspace_id, secret_hash, binding, created_at,
                      expires_at, revoked_at, result_principal_id, result_token_id, result_worker_id
               FROM skm_access.pairing_tokens WHERE id = %s FOR UPDATE""",
                (pairing_id,),
            ).fetchone()
        )
        if row is None:
            return None
        return PairingToken(
            id=pairing_id,
            issuer_id=PrincipalId(row[0]),
            issuer_token_id=None if row[1] is None else TokenId(row[1]),
            workspace_id=WorkspaceId(row[2]),
            secret_hash=cast("bytes", row[3]),
            binding=cast("JsonObject", row[4]),
            created_at=row[5],
            expires_at=row[6],
            revoked_at=row[7],
            result=None if row[8] is None else PairingResult(PrincipalId(row[8]), TokenId(row[9]), row[10]),
        )

    def consume(self, pairing_id: UUID, result: PairingResult, now: datetime) -> None:
        row = _run(
            lambda: self._conn.execute(
                """UPDATE skm_access.pairing_tokens
               SET consumed_at = %s, result_principal_id = %s, result_token_id = %s, result_worker_id = %s
               WHERE id = %s AND consumed_at IS NULL AND revoked_at IS NULL
                 AND expires_at > %s RETURNING id""",
                (now, result.principal_id, result.token_id, result.worker_id, pairing_id, now),
            ).fetchone()
        )
        if row is None:
            raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "pairing credential is unavailable")

    def revoke(self, pairing_id: UUID, now: datetime) -> None:
        _run(
            lambda: self._conn.execute(
                "UPDATE skm_access.pairing_tokens SET revoked_at = %s WHERE id = %s AND revoked_at IS NULL",
                (now, pairing_id),
            )
        )

    def revoke_all(self, now: datetime) -> int:
        rows = _run(
            lambda: self._conn.execute(
                "UPDATE skm_access.pairing_tokens SET revoked_at = %s WHERE revoked_at IS NULL RETURNING id",
                (now,),
            ).fetchall()
        )
        return len(rows)
