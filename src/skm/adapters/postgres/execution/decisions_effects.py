"""PostgreSQL adapters for ``DecisionRepository`` and ``EffectRepository`` (execution §6; DDL ``0016``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import (
    decision_answer_from_row,
    decision_record_from_row,
    decision_request_from_row,
    effect_from_row,
)
from skm.adapters.postgres.execution.codecs_core import as_uuid
from skm.adapters.postgres.execution.mapping import opt_aware, opt_jsonb, require_unchanged, run
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.decision_request import DecisionKind, DecisionRequest, DecisionState
from skm.modules.execution.domain.external_effect import EffectState
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.stored_payloads import (
    already_exists,
    field_owned,
    invalid_ref,
    not_found,
    schema_invalid,
)

if TYPE_CHECKING:
    from skm.kernel.ids import ProjectId, TaskId
    from skm.modules.execution.domain.decision_record import DecisionRecord
    from skm.modules.execution.domain.decision_request import DecisionAnswer
    from skm.modules.execution.domain.external_effect import ExternalEffect
    from skm.modules.execution.domain.ids import DecisionRequestId, ExternalEffectId

__all__ = [
    "PostgresDecisionRepository",
    "PostgresEffectRepository",
]

_DECISION_OWNED: Final = ("workspace_id", "run_id", "task_id", "kind", "created_at")
_EFFECT_OWNED: Final = (
    "workspace_id",
    "run_id",
    "attempt_id",
    "task_id",
    "kind",
    "intent_id",
    "request_digest",
    "created_at",
)

_STEP_ATTEMPT: Final = "SELECT attempt_id FROM skm_execution.attempt_steps WHERE id = %s"
_STAGE_ATTEMPT: Final = "SELECT attempt_id FROM skm_execution.attempt_stages WHERE id = %s"
_GET_DECISION: Final = """
SELECT dr.*, da.id AS answer_id
  FROM skm_execution.decision_requests dr
  LEFT JOIN skm_execution.decision_answers da
    ON da.request_id = dr.id AND da.request_revision = dr.revision
 WHERE dr.id = %s
"""
_LOCK_DECISION: Final = """
SELECT dr.*, da.id AS answer_id
  FROM skm_execution.decision_requests dr
  LEFT JOIN skm_execution.decision_answers da
    ON da.request_id = dr.id AND da.request_revision = dr.revision
 WHERE dr.id = %s
   FOR UPDATE OF dr
"""
_INSERT_DECISION: Final = """
INSERT INTO skm_execution.decision_requests (
    id, workspace_id, run_id, task_id, kind, audience, category, gate_categories,
    question_key, question_digest, revision, payload, attempt_id, stage_record_id,
    asked_by_step_id, input_part_digest, blocking, state, stale_answer, deadline_at,
    row_version, created_at, updated_at
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    1, %s, %s
)
"""
_UPDATE_DECISION: Final = """
UPDATE skm_execution.decision_requests
   SET audience = %s, category = %s, gate_categories = %s, question_key = %s,
       question_digest = %s, revision = %s, payload = %s, attempt_id = %s,
       stage_record_id = %s, asked_by_step_id = %s, input_part_digest = %s,
       blocking = %s, state = %s, stale_answer = %s, deadline_at = %s,
       row_version = row_version + 1, updated_at = clock_timestamp()
 WHERE id = %s
"""
_OPEN_DECISIONS_FOR_TASK: Final = """
SELECT dr.*, da.id AS answer_id
  FROM skm_execution.decision_requests dr
  LEFT JOIN skm_execution.decision_answers da
    ON da.request_id = dr.id AND da.request_revision = dr.revision
 WHERE dr.task_id = %s AND dr.state = 'open'
 ORDER BY dr.created_at ASC, dr.id ASC
"""
_DECISION_META: Final = "SELECT workspace_id, revision FROM skm_execution.decision_requests WHERE id = %s"
_INSERT_ANSWER: Final = """
INSERT INTO skm_execution.decision_answers (
    id, request_id, workspace_id, request_revision, answered_by_kind,
    answered_by_principal_id, answered_by_attempt_id, answered_by_step_id,
    value, authority, answered_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
_ANSWERS_FOR_REQUEST: Final = """
SELECT * FROM skm_execution.decision_answers
 WHERE request_id = %s
 ORDER BY request_revision ASC, answered_at ASC, id ASC
"""
_FIND_REUSABLE_RECORD: Final = """
SELECT * FROM skm_execution.decision_records
 WHERE project_id = %s AND question_key = %s AND question_input_digest = %s AND status = 'applied'
 ORDER BY created_at DESC, id DESC
 LIMIT 1
"""
_INSERT_RECORD: Final = """
INSERT INTO skm_execution.decision_records (
    id, workspace_id, project_id, run_id, task_id, request_id, category,
    gate_categories, authority, status, selected_option, value, rationale,
    evidence_refs, assumptions, requires_owner, question_key, question_input_digest,
    created_at, superseded_at
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, CASE WHEN %s = 'superseded' THEN %s ELSE NULL END
)
"""
_SUPERSEDE_RECORDS: Final = """
UPDATE skm_execution.decision_records
   SET status = 'superseded', superseded_at = clock_timestamp()
 WHERE project_id = %s AND question_key = %s AND status = 'applied'
"""
# Narrowed to the task's run so the (run_id, state) index serves it; no index leads with task_id alone.
_COUNT_DECISIONS_FOR_TASK: Final = """
SELECT count(*) AS cnt FROM skm_execution.decision_requests
 WHERE run_id = (SELECT t.run_id FROM skm_execution.run_tasks t WHERE t.id = %s) AND task_id = %s
"""

_EFFECT_DUP_CHECK: Final = """
SELECT 1 FROM skm_execution.external_effects
 WHERE run_id = %s AND kind = %s AND request_digest = %s
"""
_INSERT_EFFECT: Final = """
INSERT INTO skm_execution.external_effects (
    id, workspace_id, run_id, task_id, attempt_id, kind, intent_id,
    request_digest, request, state, receipt, row_version, created_at, updated_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
"""
_GET_EFFECT: Final = "SELECT * FROM skm_execution.external_effects WHERE id = %s"
_LOCK_EFFECT: Final = "SELECT * FROM skm_execution.external_effects WHERE id = %s FOR UPDATE"
_UPDATE_EFFECT: Final = """
UPDATE skm_execution.external_effects
   SET state = %s, receipt = %s, updated_at = %s, row_version = row_version + 1
 WHERE id = %s
"""
_UNRESOLVED_EFFECTS: Final = """
SELECT * FROM skm_execution.external_effects
 WHERE state IN ('intended', 'executing', 'outcome_unknown')
 ORDER BY updated_at ASC, id ASC
 LIMIT %s
"""


def _parse_opt_uuid(raw: object, field: str) -> UUID | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise schema_invalid(f"{field} must be a UUID string", field=field)
    try:
        return UUID(raw)
    except ValueError:
        raise schema_invalid(f"{field} must be a valid UUID", field=field) from None


def _decision_cols(
    cur: psycopg.Cursor[Any], req: DecisionRequest
) -> tuple[JsonObject, UUID | None, UUID | None, str | None, bool]:
    payload_doc = cast("dict[str, JsonValue]", thaw_json(req.payload))
    if isinstance(oid := req.binding.get("output_id"), str):
        payload_doc["_binding_output_id"] = oid
    att_id = _parse_opt_uuid(req.binding.get("attempt_id"), "binding.attempt_id")
    stg_id = _parse_opt_uuid(req.binding.get("stage_record_id"), "binding.stage_record_id")
    if att_id is None and req.asked_by_step_id is not None:
        cur.execute(_STEP_ATTEMPT, (req.asked_by_step_id,))
        sr = cur.fetchone()
        if sr is None:
            raise invalid_ref("fk_decision_requests__attempt_steps", step_id=str(req.asked_by_step_id))
        att_id = as_uuid(sr["attempt_id"])
    if att_id is None and stg_id is not None:
        cur.execute(_STAGE_ATTEMPT, (stg_id,))
        gr = cur.fetchone()
        if gr is None:
            raise invalid_ref("fk_decision_requests__attempt_stages", stage_record_id=str(stg_id))
        att_id = as_uuid(gr["attempt_id"])
    raw_in = req.binding.get("input_part_digest")
    in_digest = str(raw_in) if isinstance(raw_in, str) else None
    if isinstance(b := req.payload.get("blocking"), bool):
        blocking = b
    elif req.kind is DecisionKind.QUESTION:
        blocking = req.payload.get("urgency") == "blocking"
    else:
        blocking = req.state is not DecisionState.ASSUMED
    return payload_doc, att_id, stg_id, in_digest, blocking


def _sql_question_digest(raw: str | None) -> str | None:
    if raw is None or raw.startswith("sha256:") or len(raw) != 64:
        return raw
    return f"sha256:{raw}"


class PostgresDecisionRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def add(self, request: DecisionRequest) -> None:
        created = require_aware(request.created_at)

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                payload_doc, att_id, stg_id, in_digest, blocking = _decision_cols(cur, request)
                cur.execute(
                    _INSERT_DECISION,
                    (
                        request.id,
                        request.workspace_id,
                        request.run_id,
                        request.task_id,
                        request.kind.value,
                        request.audience.value,
                        None if request.category is None else request.category.value,
                        sorted(request.gate_categories),
                        request.question_key,
                        _sql_question_digest(request.question_digest),
                        request.revision,
                        to_jsonb(payload_doc),
                        att_id,
                        stg_id,
                        request.asked_by_step_id,
                        in_digest,
                        blocking,
                        request.state.value,
                        opt_jsonb(request.stale_answer),
                        opt_aware(request.deadline_at),
                        created,
                        created,
                    ),
                )

        run(_op)

    def get(self, request_id: DecisionRequestId, *, for_update: bool = False) -> DecisionRequest:
        def _op() -> DecisionRequest:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if for_update:
                    cur.execute(_LOCK_DECISION, (request_id,))
                else:
                    cur.execute(_GET_DECISION, (request_id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("decision_request", request_id)
                return decision_request_from_row(row)

        return run(_op)

    def save(self, request: DecisionRequest) -> None:
        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_LOCK_DECISION, (request.id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("decision_request", request.id)
                require_unchanged(
                    "decision_request", decision_request_from_row(row), request, _DECISION_OWNED
                )
                payload_doc, att_id, stg_id, in_digest, blocking = _decision_cols(cur, request)
                cur.execute(
                    _UPDATE_DECISION,
                    (
                        request.audience.value,
                        None if request.category is None else request.category.value,
                        sorted(request.gate_categories),
                        request.question_key,
                        _sql_question_digest(request.question_digest),
                        request.revision,
                        to_jsonb(payload_doc),
                        att_id,
                        stg_id,
                        request.asked_by_step_id,
                        in_digest,
                        blocking,
                        request.state.value,
                        opt_jsonb(request.stale_answer),
                        opt_aware(request.deadline_at),
                        request.id,
                    ),
                )

        run(_op)

    def open_for_task(self, task_id: TaskId) -> tuple[DecisionRequest, ...]:
        def _op() -> tuple[DecisionRequest, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_OPEN_DECISIONS_FOR_TASK, (task_id,))
                return tuple(decision_request_from_row(r) for r in cur.fetchall())

        return run(_op)

    def add_answer(self, answer: DecisionAnswer) -> None:
        by_kind = answer.answered_by.get("kind")
        if not isinstance(by_kind, str):
            raise schema_invalid("answered_by.kind is required", field="answered_by")
        prin_id = _parse_opt_uuid(answer.answered_by.get("principal_id"), "answered_by.principal_id")
        step_id = _parse_opt_uuid(answer.answered_by.get("step_id"), "answered_by.step_id")
        auth_doc: JsonObject = {
            "mode": answer.authority.mode,
            "gate_categories": list(answer.authority.gate_categories),
            "confidence": answer.authority.confidence,
        }

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_DECISION_META, (answer.request_id,))
                rm = cur.fetchone()
                if rm is None:
                    raise invalid_ref(
                        "fk_decision_answers__decision_requests", request_id=str(answer.request_id)
                    )
                att_id: UUID | None = None
                if step_id is not None:
                    cur.execute(_STEP_ATTEMPT, (step_id,))
                    sr = cur.fetchone()
                    if sr is None:
                        raise invalid_ref("fk_decision_answers__attempt_steps", step_id=str(step_id))
                    att_id = as_uuid(sr["attempt_id"])
                cur.execute(
                    _INSERT_ANSWER,
                    (
                        answer.id,
                        answer.request_id,
                        as_uuid(rm["workspace_id"]),
                        int(rm["revision"]),
                        by_kind,
                        prin_id,
                        att_id,
                        step_id,
                        to_jsonb(thaw_json(answer.value)),
                        to_jsonb(auth_doc),
                        require_aware(answer.answered_at),
                    ),
                )

        run(_op)

    def answers_for(self, request_id: DecisionRequestId) -> tuple[DecisionAnswer, ...]:
        def _op() -> tuple[DecisionAnswer, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_ANSWERS_FOR_REQUEST, (request_id,))
                return tuple(decision_answer_from_row(r) for r in cur.fetchall())

        return run(_op)

    def find_reusable(
        self, project_id: ProjectId, question_key: str, question_digest: str
    ) -> DecisionRecord | None:
        def _op() -> DecisionRecord | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_FIND_REUSABLE_RECORD, (project_id, question_key, question_digest))
                row = cur.fetchone()
                return None if row is None else decision_record_from_row(row)

        return run(_op)

    def add_record(self, record: DecisionRecord) -> None:
        created = require_aware(record.created_at)

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    _INSERT_RECORD,
                    (
                        record.id,
                        record.workspace_id,
                        record.project_id,
                        record.run_id,
                        record.task_id,
                        record.request_id,
                        record.category.value,
                        list(record.gate_categories),
                        record.authority,
                        record.status,
                        record.selected_option,
                        to_jsonb(thaw_json(record.value)),
                        record.rationale,
                        to_jsonb(list(record.evidence_refs)),
                        to_jsonb(list(record.assumptions)),
                        record.requires_owner,
                        record.question_key,
                        record.question_input_digest,
                        created,
                        record.status,
                        created,
                    ),
                )

        run(_op)

    def supersede_records(self, project_id: ProjectId, question_key: str) -> int:
        def _op() -> int:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_SUPERSEDE_RECORDS, (project_id, question_key))
                return cur.rowcount

        return run(_op)

    def count_for_task(self, task_id: TaskId) -> int:
        def _op() -> int:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_COUNT_DECISIONS_FOR_TASK, (task_id, task_id))
                row = cur.fetchone()
                return 0 if row is None else int(row["cnt"])

        return run(_op)


class PostgresEffectRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def add(self, effect: ExternalEffect) -> None:
        if effect.state is EffectState.SUCCEEDED and effect.receipt is None:
            raise schema_invalid("succeeded external_effect requires receipt", field="receipt")

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_EFFECT_DUP_CHECK, (effect.run_id, effect.kind.value, effect.request_digest))
                if cur.fetchone() is not None:
                    raise already_exists(
                        "uq_external_effects__run_id_kind_request_digest",
                        run_id=str(effect.run_id),
                        kind=effect.kind.value,
                        request_digest=effect.request_digest,
                    )
                cur.execute(
                    _INSERT_EFFECT,
                    (
                        effect.id,
                        effect.workspace_id,
                        effect.run_id,
                        effect.task_id,
                        effect.attempt_id,
                        effect.kind.value,
                        effect.intent_id,
                        effect.request_digest,
                        to_jsonb(thaw_json(effect.request)),
                        effect.state.value,
                        opt_jsonb(effect.receipt),
                        require_aware(effect.created_at),
                        require_aware(effect.updated_at),
                    ),
                )

        run(_op)

    def get(self, effect_id: ExternalEffectId, *, for_update: bool = False) -> ExternalEffect:
        def _op() -> ExternalEffect:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if for_update:
                    cur.execute(_LOCK_EFFECT, (effect_id,))
                else:
                    cur.execute(_GET_EFFECT, (effect_id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("external_effect", effect_id)
                return effect_from_row(row)

        return run(_op)

    def save(self, effect: ExternalEffect) -> None:
        if effect.state is EffectState.SUCCEEDED and effect.receipt is None:
            raise schema_invalid("succeeded external_effect requires receipt", field="receipt")

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_LOCK_EFFECT, (effect.id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("external_effect", effect.id)
                cur_eff = effect_from_row(row)
                require_unchanged("external_effect", cur_eff, effect, _EFFECT_OWNED)
                if thaw_json(effect.request) != thaw_json(cur_eff.request):
                    raise field_owned("external_effect", "request")
                if cur_eff.receipt is not None and thaw_json(effect.receipt) != thaw_json(cur_eff.receipt):
                    raise field_owned("external_effect", "receipt")
                cur.execute(
                    _UPDATE_EFFECT,
                    (
                        effect.state.value,
                        opt_jsonb(effect.receipt),
                        require_aware(effect.updated_at),
                        effect.id,
                    ),
                )

        run(_op)

    def unresolved(self, *, limit: int) -> tuple[ExternalEffect, ...]:
        def _op() -> tuple[ExternalEffect, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_UNRESOLVED_EFFECTS, (limit,))
                return tuple(effect_from_row(r) for r in cur.fetchall())

        return run(_op)
