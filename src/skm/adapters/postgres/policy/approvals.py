"""PostgreSQL ``ApprovalRepository`` (policy §6, §11; DDL ``0012``): append-only approvals.

``add`` takes the workspace from the intent in the same statement (the composite FK keeps them equal). The
only change ever made to a row is ``mark_used``: ``UPDATE ... WHERE used_at IS NULL``, so two concurrent
admissions spend an approval once; the trigger of the table refuses every other update and any delete.
"""

from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.policy.mapping import Row, damaged, not_found, run
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden
from skm.kernel.ids import PrincipalId, ToolIntentId
from skm.modules.policy.domain.approval import Approval, ApprovalDecision, ApprovalId

__all__ = ["PostgresApprovalRepository"]

_COLUMNS: Final = (
    "SELECT id, intent_id, approver_id, decision, args_digest, single_use, expires_at, used_at, reason, "
    "created_at FROM skm_policy.approvals "
)
_FOR_INTENT: Final = _COLUMNS + "WHERE intent_id = %s ORDER BY created_at, id"
_INSERT: Final = """
INSERT INTO skm_policy.approvals
    (id, workspace_id, intent_id, approver_id, decision, args_digest, single_use, reason, created_at,
     expires_at, used_at)
SELECT %s, workspace_id, id, %s, %s, %s, %s, %s, %s, %s, %s FROM skm_policy.tool_intents WHERE id = %s
ON CONFLICT DO NOTHING RETURNING id
"""
_INTENT_EXISTS: Final = "SELECT 1 FROM skm_policy.tool_intents WHERE id = %s"
_MARK_USED: Final = """
UPDATE skm_policy.approvals SET used_at = %s
 WHERE id = %s AND used_at IS NULL AND decision = 'approve'
RETURNING id
"""


def _approval(row: Row) -> Approval:
    try:
        return Approval(
            id=ApprovalId(cast("UUID", row[0])),
            intent_id=ToolIntentId(cast("UUID", row[1])),
            approver_id=PrincipalId(cast("UUID", row[2])),
            decision=ApprovalDecision(cast("str", row[3])),
            args_digest=cast("str", row[4]),
            single_use=cast("bool", row[5]),
            expires_at=cast("datetime", row[6]),
            used_at=cast("datetime | None", row[7]),
            reason=cast("str", row[8]),
            created_at=cast("datetime", row[9]),
        )
    except (TypeError, ValueError) as exc:
        raise damaged("approvals", row[0], exc) from exc


class PostgresApprovalRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, approval: Approval) -> None:
        params = (
            approval.id,
            approval.approver_id,
            ApprovalDecision(approval.decision).value,
            approval.args_digest,
            approval.single_use,
            approval.reason,
            approval.created_at,
            approval.expires_at,
            approval.used_at,
            approval.intent_id,
        )
        if run(lambda: self._conn.execute(_INSERT, params).fetchone()) is not None:
            return
        if run(lambda: self._conn.execute(_INTENT_EXISTS, (approval.intent_id,)).fetchone()) is None:
            raise not_found("tool_intent", approval.intent_id)
        raise Conflict(ErrorCode.ALREADY_EXISTS, "approval already exists", details={"kind": "approval"})

    def for_intent(self, intent_id: ToolIntentId) -> tuple[Approval, ...]:
        rows = run(lambda: self._conn.execute(_FOR_INTENT, (intent_id,)).fetchall())
        return tuple(_approval(row) for row in rows)

    def mark_used(self, approval_id: ApprovalId, used_at: datetime) -> None:
        if run(lambda: self._conn.execute(_MARK_USED, (used_at, approval_id)).fetchone()) is None:
            raise Forbidden(
                ErrorCode.APPROVAL_MISMATCH,
                "the approval has been used",
                details={"reason": "already_used", "approval_id": str(approval_id)},
            )
