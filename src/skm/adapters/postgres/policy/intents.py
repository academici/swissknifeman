"""PostgreSQL ``ToolIntentRepository`` (policy §6, §11; DDL ``0012``): explicit SQL, mapping next to it.

``add`` runs ``ON CONFLICT DO NOTHING``: a taken id or an open intent of the same ``(scope, kind, digest)``
(the partial unique index) is ``ALREADY_EXISTS`` and the transaction goes on. ``get_for_update`` and ``save``
lock the row; ``save`` compares ``row_version`` and writes the state, the denial, the receipt and the version
only (``ValueError`` on any other change). ``expired`` locks what it returns and skips rows another
transaction holds. Pages ascend by ``(created_at, id)``.
"""

from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.jsonb import to_jsonb
from skm.adapters.postgres.pagination import page_of, query_digest
from skm.adapters.postgres.policy.mapping import (
    Row,
    damaged,
    ensure_kept,
    keyset,
    not_found,
    run,
    time_key,
    version_conflict,
)
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import PrincipalId, ScopeId, ToolIntentId, WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.kernel.pagination import Page, validate_page_limit
from skm.modules.policy.domain.tool_intent import EffectKind, IntentState, RiskClass, ToolIntent
from skm.platform.system_clock import SystemClock

__all__ = ["PostgresToolIntentRepository"]

_COLUMNS: Final = (
    "SELECT t.id, t.workspace_id, t.scope_id, t.subject_ref, t.actor_id, t.kind, t.normalized_args, "
    "t.args_digest, t.risk, t.reason, t.state, t.denied_reason, t.created_at, t.expires_at, t.row_version, "
    "t.receipt FROM skm_policy.tool_intents t "
)
_GET: Final = _COLUMNS + "WHERE t.id = %s"
_LOCKED: Final = _GET + " FOR UPDATE"
_ACTIVE: Final = _COLUMNS + (
    "WHERE t.scope_id = %s AND t.kind = %s AND t.args_digest = %s "
    "AND t.state IN ('proposed', 'approved', 'executing')"
)
_INSERT: Final = """
INSERT INTO skm_policy.tool_intents
    (id, workspace_id, scope_id, subject_ref, actor_id, kind, normalized_args, args_digest, risk, reason,
     state, denied_reason, receipt, row_version, created_at, updated_at, expires_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING RETURNING id
"""
_UPDATE: Final = """
UPDATE skm_policy.tool_intents
   SET state = %s, denied_reason = %s, receipt = %s, row_version = %s, updated_at = greatest(updated_at, %s)
 WHERE id = %s
"""
_LIST: Final = (
    _COLUMNS
    + """
 WHERE t.workspace_id = %(workspace)s
   AND (%(scope)s::uuid IS NULL OR t.scope_id = %(scope)s::uuid)
   AND (%(state)s::text IS NULL OR t.state = %(state)s::text)
   AND (%(at)s::timestamptz IS NULL OR (t.created_at, t.id) > (%(at)s::timestamptz, %(id)s::uuid))
 ORDER BY t.created_at, t.id
 LIMIT %(limit)s
"""
)
_EXPIRED: Final = """
SELECT t.id, t.workspace_id, t.scope_id, t.subject_ref, t.actor_id, t.kind, t.normalized_args,
       t.args_digest, t.risk, t.reason, t.state, t.denied_reason, t.created_at, t.expires_at, t.row_version,
       t.receipt
  FROM skm_policy.tool_intents t
 WHERE (t.state = 'proposed' AND t.expires_at <= %(now)s)
    OR (t.state = 'approved' AND NOT EXISTS (
            SELECT 1 FROM skm_policy.approvals a
             WHERE a.intent_id = t.id AND a.decision = 'approve' AND a.expires_at > %(now)s))
 ORDER BY t.expires_at, t.id
 LIMIT %(limit)s
 FOR UPDATE OF t SKIP LOCKED
"""
_KEPT: Final = (
    "workspace_id",
    "scope_id",
    "subject_ref",
    "actor_id",
    "kind",
    "normalized_args",
    "args_digest",
    "risk",
    "reason",
    "created_at",
    "expires_at",
)


def _intent(row: Row) -> ToolIntent:
    try:
        return ToolIntent(
            id=ToolIntentId(cast("UUID", row[0])),
            workspace_id=WorkspaceId(cast("UUID", row[1])),
            scope_id=ScopeId(cast("UUID", row[2])),
            subject_ref=cast("str", row[3]),
            actor_id=PrincipalId(cast("UUID", row[4])),
            kind=EffectKind(cast("str", row[5])),
            normalized_args=cast("dict[str, JsonValue]", row[6]),
            args_digest=cast("str", row[7]),
            risk=RiskClass(cast("str", row[8])),
            reason=cast("str", row[9]),
            state=IntentState(cast("str", row[10])),
            denied_reason=cast("str | None", row[11]),
            created_at=cast("datetime", row[12]),
            expires_at=cast("datetime", row[13]),
            row_version=cast("int", row[14]),
            receipt=cast("dict[str, JsonValue] | None", row[15]),
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise damaged("tool_intents", row[0], exc) from exc


class PostgresToolIntentRepository:
    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def get(self, intent_id: ToolIntentId) -> ToolIntent:
        row = run(lambda: self._conn.execute(_GET, (intent_id,)).fetchone())
        if row is None:
            raise not_found("tool_intent", intent_id)
        return _intent(row)

    def get_for_update(self, intent_id: ToolIntentId) -> ToolIntent:
        row = run(lambda: self._conn.execute(_LOCKED, (intent_id,)).fetchone())
        if row is None:
            raise not_found("tool_intent", intent_id)
        return _intent(row)

    def add(self, intent: ToolIntent) -> None:
        params = (
            intent.id,
            intent.workspace_id,
            intent.scope_id,
            intent.subject_ref,
            intent.actor_id,
            EffectKind(intent.kind).value,
            to_jsonb(dict(intent.normalized_args)),
            intent.args_digest,
            RiskClass(intent.risk).value,
            intent.reason,
            IntentState(intent.state).value,
            intent.denied_reason,
            None if intent.receipt is None else to_jsonb(dict(intent.receipt)),
            intent.row_version,
            intent.created_at,
            intent.created_at,
            intent.expires_at,
        )
        if run(lambda: self._conn.execute(_INSERT, params).fetchone()) is None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS, "tool intent already exists", details={"kind": "tool_intent"}
            )

    def save(self, intent: ToolIntent, *, expected_version: int) -> None:
        row = run(lambda: self._conn.execute(_LOCKED, (intent.id,)).fetchone())
        if row is None:
            raise not_found("tool_intent", intent.id)
        current = _intent(row)
        if current.row_version != expected_version:
            raise version_conflict("tool_intent", expected_version, current.row_version)
        ensure_kept("tool intent", current, intent, _KEPT)
        params = (
            IntentState(intent.state).value,
            intent.denied_reason,
            None if intent.receipt is None else to_jsonb(dict(intent.receipt)),
            intent.row_version,
            self._clock.now(),
            intent.id,
        )
        run(lambda: self._conn.execute(_UPDATE, params))

    def find_active(self, scope_id: ScopeId, kind: EffectKind, args_digest: str) -> ToolIntent | None:
        row = run(
            lambda: self._conn.execute(_ACTIVE, (scope_id, EffectKind(kind).value, args_digest)).fetchone()
        )
        return None if row is None else _intent(row)

    def list(
        self,
        *,
        workspace_id: WorkspaceId,
        scope_id: ScopeId | None,
        state: IntentState | None,
        after: str | None,
        limit: int,
    ) -> Page[ToolIntent]:
        limit = validate_page_limit(limit)
        state_value = None if state is None else IntentState(state).value
        digest = query_digest(
            {
                "kind": "policy_intents",
                "workspace_id": str(workspace_id),
                "scope_id": None if scope_id is None else str(scope_id),
                "state": state_value,
            }
        )
        at, start = keyset(after, digest, time_key)
        params = {
            "workspace": workspace_id,
            "scope": scope_id,
            "state": state_value,
            "at": at,
            "id": start,
            "limit": limit + 1,
        }
        rows = run(lambda: self._conn.execute(_LIST, params).fetchall())
        return page_of(
            [_intent(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda item: (item.created_at.isoformat(), str(item.id)),
        )

    def expired(self, now: datetime, *, limit: int) -> tuple[ToolIntent, ...]:
        rows = run(lambda: self._conn.execute(_EXPIRED, {"now": now, "limit": limit}).fetchall())
        return tuple(_intent(row) for row in rows)
