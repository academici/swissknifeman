"""PostgreSQL ``AcceptanceRepository`` adapter (execution §6; DDL ``0015``, ``0016``)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import (
    acceptance_from_row,
    carry_forward_from_row,
    deviation_from_row,
)
from skm.adapters.postgres.execution.codecs_core import as_uuid
from skm.adapters.postgres.execution.mapping import run
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.stored_payloads import invalid_ref, schema_invalid

if TYPE_CHECKING:
    from skm.kernel.ids import RunId, TaskId
    from skm.kernel.json_types import JsonObject
    from skm.modules.execution.domain.acceptance import AcceptanceDecision
    from skm.modules.execution.domain.carry_forward import CarryForward
    from skm.modules.execution.domain.deviation import DeviationAcceptance

__all__ = ["PostgresAcceptanceRepository"]

_SHA256_RE: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUN_META: Final = "SELECT workspace_id, plan_id, revision_id FROM skm_execution.runs WHERE id = %s"
_INSERT_ACCEPTANCE: Final = """
INSERT INTO skm_execution.acceptance_decisions (
    id, workspace_id, run_id, task_id, attempt_id, output_id,
    decision, clearance, actor_id, basis, decided_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
_DECISIONS_FOR_TASK: Final = """
SELECT * FROM skm_execution.acceptance_decisions
 WHERE task_id = %s
 ORDER BY decided_at ASC, id ASC
"""
_INSERT_DEVIATION: Final = """
INSERT INTO skm_execution.deviation_acceptances (
    id, workspace_id, run_id, task_id, plan_id, revision_id, scope,
    criterion_id, criterion_entity_kind, finding_id, reason, approved_by, approved_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'criterion', %s, %s, %s, %s)
"""
_DEVIATIONS_FOR_TASK: Final = """
SELECT * FROM skm_execution.deviation_acceptances
 WHERE task_id = %s
 ORDER BY approved_at ASC, id ASC
"""
_INSERT_CARRY_FORWARD: Final = """
INSERT INTO skm_execution.result_carry_forwards (
    id, workspace_id, source_run_id, source_task_id, source_attempt_id, source_output_id,
    target_run_id, target_task_id, compatibility_digest, compatibility_inputs,
    decision, approved_by, reason, created_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
_CARRY_FORWARDS_FOR_RUN: Final = """
SELECT * FROM skm_execution.result_carry_forwards
 WHERE target_run_id = %s
 ORDER BY created_at ASC, id ASC
"""


class PostgresAcceptanceRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def add_decision(self, decision: AcceptanceDecision) -> None:
        att_uuid = UUID(str(decision.attempt_id))
        att_col: UUID | None = None if att_uuid == UUID(int=0) else att_uuid
        clearance = decision.basis.clearance.value if decision.decision == "accepted" else None
        b = decision.basis
        basis_doc: JsonObject = {
            "clearance": b.clearance.value,
            "check_execution_ids": [str(x) for x in b.check_execution_ids],
            "review_id": None if b.review_id is None else str(b.review_id),
            "manual_verdict_ids": [str(x) for x in b.manual_verdict_ids],
            "deviation_ids": [str(x) for x in b.deviation_ids],
            "review_debt": b.review_debt,
            "coverage_report": None if b.coverage_report is None else thaw_json(b.coverage_report),
            "carry_forward_id": None if b.carry_forward_id is None else str(b.carry_forward_id),
            "reasons": list(b.reasons),
        }

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    _INSERT_ACCEPTANCE,
                    (
                        decision.id,
                        decision.workspace_id,
                        decision.run_id,
                        decision.task_id,
                        att_col,
                        decision.output_id,
                        decision.decision,
                        clearance,
                        decision.actor_id,
                        to_jsonb(basis_doc),
                        require_aware(decision.decided_at),
                    ),
                )

        run(_op)

    def decisions_for_task(self, task_id: TaskId) -> tuple[AcceptanceDecision, ...]:
        def _op() -> tuple[AcceptanceDecision, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_DECISIONS_FOR_TASK, (task_id,))
                return tuple(acceptance_from_row(r) for r in cur.fetchall())

        return run(_op)

    def add_deviation(self, deviation: DeviationAcceptance) -> None:
        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_RUN_META, (deviation.run_id,))
                rm = cur.fetchone()
                if rm is None:
                    raise invalid_ref("fk_deviation_acceptances__runs_revision", run_id=str(deviation.run_id))
                cur.execute(
                    _INSERT_DEVIATION,
                    (
                        deviation.id,
                        as_uuid(rm["workspace_id"]),
                        deviation.run_id,
                        deviation.task_id,
                        as_uuid(rm["plan_id"]),
                        as_uuid(rm["revision_id"]),
                        deviation.scope,
                        deviation.criterion_id,
                        deviation.finding_id,
                        deviation.reason,
                        deviation.approved_by,
                        require_aware(deviation.approved_at),
                    ),
                )

        run(_op)

    def deviations_for_task(self, task_id: TaskId) -> tuple[DeviationAcceptance, ...]:
        def _op() -> tuple[DeviationAcceptance, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_DEVIATIONS_FOR_TASK, (task_id,))
                return tuple(deviation_from_row(r) for r in cur.fetchall())

        return run(_op)

    def add_carry_forward(self, carry_forward: CarryForward) -> None:
        if carry_forward.source_run_id == carry_forward.target_run_id:
            raise schema_invalid("carry_forward source_run_id must differ from target_run_id")
        if not _SHA256_RE.match(carry_forward.compatibility_digest):
            raise schema_invalid("compatibility_digest must be sha256:<64 hex>", field="compatibility_digest")

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_RUN_META, (carry_forward.target_run_id,))
                rm = cur.fetchone()
                if rm is None:
                    raise invalid_ref(
                        "fk_result_carry_forwards__target_run", run_id=str(carry_forward.target_run_id)
                    )
                cur.execute(
                    _INSERT_CARRY_FORWARD,
                    (
                        carry_forward.id,
                        as_uuid(rm["workspace_id"]),
                        carry_forward.source_run_id,
                        carry_forward.source_task_id,
                        carry_forward.source_attempt_id,
                        carry_forward.source_output_id,
                        carry_forward.target_run_id,
                        carry_forward.target_task_id,
                        carry_forward.compatibility_digest,
                        to_jsonb(thaw_json(carry_forward.compatibility_inputs)),
                        carry_forward.decision,
                        carry_forward.approved_by,
                        carry_forward.reason,
                        require_aware(carry_forward.created_at),
                    ),
                )

        run(_op)

    def carry_forwards_for_run(self, run_id: RunId) -> tuple[CarryForward, ...]:
        def _op() -> tuple[CarryForward, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_CARRY_FORWARDS_FOR_RUN, (run_id,))
                return tuple(carry_forward_from_row(r) for r in cur.fetchall())

        return run(_op)
