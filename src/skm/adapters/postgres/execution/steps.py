"""PostgreSQL repository for attempt steps and step notes (DDL ``0014``, ``0026``)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import step_from_row, step_note_from_row
from skm.adapters.postgres.execution.mapping import (
    opt_aware,
    opt_jsonb,
    process_identity_to_json,
    require_unchanged,
    run,
    usage_to_json,
    validate_step_payloads,
)
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import AttemptId, PrincipalId, ProjectId, TaskId
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.ids import AssignmentId, StageRecordId, StepId
from skm.modules.execution.domain.lease import ProcessIdentity
from skm.modules.execution.domain.live_control import IncidentGate, ToolCall, ToolCallObservation
from skm.modules.execution.domain.step import AttemptStep, RoleId, StepState
from skm.modules.execution.domain.step_note import NoteKind, StepNote
from skm.modules.execution.domain.stored_payloads import (
    invalid_ref,
    invalid_transition,
    not_found,
    validate_step_note,
)
from skm.modules.runtimes.public import UsageReport

__all__ = ["PostgresStepRepository"]

_STEP_OWNED: Final = (
    "attempt_id",
    "stage_record_id",
    "parent_step_id",
    "seq",
    "role",
    "purpose",
    "runtime_id",
    "model",
    "effort",
    "operation",
    "route_source",
    "route_reason",
    "context_manifest_id",
    "session_mode",
    "session_fingerprint_digest",
    "started_at",
)


def _fingerprint_to_json(step: AttemptStep) -> dict[str, object]:
    fp = step.session_fingerprint
    return {
        "runtime_id": fp.runtime_id,
        "project_id": str(fp.project_id),
        "environment_id": str(fp.environment_id),
        "role": fp.role.value,
        "attempt_id": str(fp.attempt_id),
        "instruction_digest": fp.instruction_digest,
        "authority_digest": fp.authority_digest,
        "route": {"runtime_id": fp.route.runtime_id, "model": fp.route.model, "effort": fp.route.effort},
        "last_validated_output_id": (
            None if fp.last_validated_output_id is None else str(fp.last_validated_output_id)
        ),
    }


class PostgresStepRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, step: AttemptStep) -> None:
        validate_step_payloads(step, None)
        u_doc = usage_to_json(step.usage)

        def _ins() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT workspace_id FROM skm_execution.attempts WHERE id = %s",
                    (UUID(str(step.attempt_id)),),
                )
                arow = cur.fetchone()
                if arow is None:
                    raise invalid_ref("fk_attempt_steps__attempt_stages", attempt_id=str(step.attempt_id))
                cur.execute(
                    """
                    INSERT INTO skm_execution.attempt_steps (
                        id, attempt_id, stage_record_id, workspace_id, parent_step_id, seq,
                        role, purpose, runtime_id, model, effort, operation, admission,
                        route_source, route_reason, context_manifest_id,
                        session_mode, session_ref, session_fingerprint,
                        session_fingerprint_digest, fresh_reason,
                        state, result, raw_result_file_version_id, repairs, schema_errors,
                        usage, usage_status, usage_so_far, process_identity, activity,
                        route_snapshot, runtime_observation, reuse_key,
                        transcript_file_version_id, last_progress_at, error_code, started_at, finished_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        UUID(str(step.id)),
                        UUID(str(step.attempt_id)),
                        UUID(str(step.stage_record_id)),
                        arow[0],
                        None if step.parent_step_id is None else UUID(str(step.parent_step_id)),
                        step.seq,
                        step.role.value,
                        step.purpose.value,
                        step.runtime_id,
                        step.model,
                        step.effort,
                        step.operation,
                        to_jsonb(thaw_json(step.admission)),
                        step.route_source,
                        step.route_reason,
                        UUID(str(step.context_manifest_id)),
                        step.session_mode,
                        step.session_ref,
                        to_jsonb(_fingerprint_to_json(step)),
                        step.session_fingerprint_digest,
                        step.fresh_reason,
                        step.state.value,
                        opt_jsonb(step.result),
                        (
                            None
                            if step.raw_result_file_version_id is None
                            else UUID(str(step.raw_result_file_version_id))
                        ),
                        to_jsonb(list(step.repairs)),
                        to_jsonb([thaw_json(e) for e in step.schema_errors]),
                        opt_jsonb(u_doc),
                        None if step.usage is None else step.usage.status.value,
                        opt_jsonb(usage_to_json(step.usage_so_far)),
                        opt_jsonb(process_identity_to_json(step.process_identity)),
                        opt_jsonb(step.activity),
                        opt_jsonb(step.route_snapshot),
                        opt_jsonb(step.runtime_observation),
                        step.reuse_key,
                        (
                            None
                            if step.transcript_file_version_id is None
                            else UUID(str(step.transcript_file_version_id))
                        ),
                        opt_aware(step.last_progress_at),
                        step.error_code,
                        require_aware(step.started_at),
                        opt_aware(step.finished_at),
                    ),
                )

        run(_ins)

    def save(self, step: AttemptStep) -> None:
        def _upd() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM skm_execution.attempt_steps WHERE id = %s FOR UPDATE",
                    (UUID(str(step.id)),),
                )
                row = cur.fetchone()
                if row is None:
                    raise not_found("step", step.id)
                current = step_from_row(row)
                require_unchanged("step", current, step, _STEP_OWNED)
                validate_step_payloads(step, current)
                u_doc = usage_to_json(step.usage)
                cur.execute(
                    """
                    UPDATE skm_execution.attempt_steps
                       SET session_ref = %s, fresh_reason = %s, state = %s, result = %s,
                           raw_result_file_version_id = %s, repairs = %s, schema_errors = %s,
                           usage = %s, usage_status = %s, usage_so_far = %s,
                           process_identity = %s, activity = %s,
                           route_snapshot = %s, runtime_observation = %s, reuse_key = %s,
                           transcript_file_version_id = %s, last_progress_at = %s,
                           error_code = %s, finished_at = %s
                     WHERE id = %s
                    """,
                    (
                        step.session_ref,
                        step.fresh_reason,
                        step.state.value,
                        opt_jsonb(step.result),
                        (
                            None
                            if step.raw_result_file_version_id is None
                            else UUID(str(step.raw_result_file_version_id))
                        ),
                        to_jsonb(list(step.repairs)),
                        to_jsonb([thaw_json(e) for e in step.schema_errors]),
                        opt_jsonb(u_doc),
                        None if step.usage is None else step.usage.status.value,
                        opt_jsonb(usage_to_json(step.usage_so_far)),
                        opt_jsonb(process_identity_to_json(step.process_identity)),
                        opt_jsonb(step.activity),
                        opt_jsonb(step.route_snapshot),
                        opt_jsonb(step.runtime_observation),
                        step.reuse_key,
                        (
                            None
                            if step.transcript_file_version_id is None
                            else UUID(str(step.transcript_file_version_id))
                        ),
                        opt_aware(step.last_progress_at),
                        step.error_code,
                        opt_aware(step.finished_at),
                        UUID(str(step.id)),
                    ),
                )

        run(_upd)

    def get(self, step_id: StepId) -> AttemptStep:
        def _q() -> AttemptStep:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM skm_execution.attempt_steps WHERE id = %s", (UUID(str(step_id)),))
                row = cur.fetchone()
            if row is None:
                raise not_found("step", step_id)
            return step_from_row(row)

        return run(_q)

    def for_stage(self, stage_record_id: StageRecordId) -> tuple[AttemptStep, ...]:
        def _q() -> tuple[AttemptStep, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM skm_execution.attempt_steps WHERE stage_record_id = %s ORDER BY seq ASC",
                    (UUID(str(stage_record_id)),),
                )
                return tuple(step_from_row(r) for r in cur.fetchall())

        return run(_q)

    def last_for_role(self, attempt_id: AttemptId, role: RoleId) -> AttemptStep | None:
        def _q() -> AttemptStep | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM skm_execution.attempt_steps
                     WHERE attempt_id = %s AND role = %s
                     ORDER BY seq DESC
                     LIMIT 1
                    """,
                    (UUID(str(attempt_id)), role.value),
                )
                row = cur.fetchone()
            return None if row is None else step_from_row(row)

        return run(_q)

    def first_writing(self, attempt_id: AttemptId) -> AttemptStep | None:
        def _q() -> AttemptStep | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT stp.*
                      FROM skm_execution.attempt_steps stp
                      JOIN skm_execution.attempt_stages stg ON stg.id = stp.stage_record_id
                     WHERE stp.attempt_id = %s AND stp.role = 'executor'
                     ORDER BY stg.seq ASC, stp.seq ASC
                     LIMIT 1
                    """,
                    (UUID(str(attempt_id)),),
                )
                row = cur.fetchone()
            return None if row is None else step_from_row(row)

        return run(_q)

    def touch_progress(
        self,
        step_id: StepId,
        at: datetime,
        *,
        usage_so_far: UsageReport | None,
        identity: ProcessIdentity | None,
    ) -> None:
        def _upd() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM skm_execution.attempt_steps WHERE id = %s FOR UPDATE",
                    (UUID(str(step_id)),),
                )
                row = cur.fetchone()
                if row is None:
                    raise not_found("step", step_id)
                cur_step = step_from_row(row)
                if cur_step.state is not StepState.STARTED:
                    raise invalid_transition("touch_progress requires a started step", step_id=str(step_id))
                eff_u = usage_so_far if usage_so_far is not None else cur_step.usage_so_far
                eff_id = identity if identity is not None else cur_step.process_identity
                cur.execute(
                    """
                    UPDATE skm_execution.attempt_steps
                       SET last_progress_at = %s, usage_so_far = %s, process_identity = %s
                     WHERE id = %s
                    """,
                    (
                        require_aware(at),
                        opt_jsonb(usage_to_json(eff_u)),
                        opt_jsonb(process_identity_to_json(eff_id)),
                        UUID(str(step_id)),
                    ),
                )

        run(_upd)

    def find_reusable_scout(self, project_id: ProjectId, reuse_key: str) -> AttemptStep | None:
        def _q() -> AttemptStep | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT stp.*
                      FROM skm_execution.attempt_steps stp
                      JOIN skm_execution.attempts att ON att.id = stp.attempt_id
                      JOIN skm_execution.runs r ON r.id = att.run_id
                     WHERE r.project_id = %s
                       AND stp.role = 'scout'
                       AND stp.state = 'succeeded'
                       AND stp.reuse_key = %s
                     ORDER BY stp.finished_at DESC NULLS LAST, stp.id DESC
                     LIMIT 1
                    """,
                    (UUID(str(project_id)), reuse_key),
                )
                row = cur.fetchone()
            return None if row is None else step_from_row(row)

        return run(_q)

    def add_note(
        self,
        note: StepNote,
        *,
        assignment_id: AssignmentId,
        fencing_token: int,
        created_by: PrincipalId,
    ) -> None:
        validate_step_note(note)
        rec_at = require_aware(note.recorded_at)

        def _ins() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT att.workspace_id, att.run_id, att.id
                      FROM skm_execution.attempt_steps stp
                      JOIN skm_execution.attempts att ON att.id = stp.attempt_id
                     WHERE stp.id = %s
                    """,
                    (UUID(str(note.step_id)),),
                )
                srow = cur.fetchone()
                if srow is None:
                    raise not_found("step", note.step_id)
                ws_id, run_id, att_id = srow
                cur.execute(
                    """
                    SELECT 1
                      FROM skm_execution.assignments a
                      JOIN skm_execution.assignment_leases l ON l.assignment_id = a.id
                     WHERE a.id = %s
                       AND a.attempt_id = %s
                       AND a.state = 'leased'
                       AND l.fencing_token = %s
                       AND l.expires_at > %s
                    """,
                    (UUID(str(assignment_id)), att_id, fencing_token, rec_at),
                )
                if cur.fetchone() is None:
                    raise Conflict(
                        ErrorCode.LEASE_LOST,
                        "step note requires a live lease matching assignment and fencing token",
                        details={"assignment_id": str(assignment_id), "fencing_token": fencing_token},
                    )
                opts = (
                    to_jsonb([thaw_json(o) for o in note.options])
                    if note.kind is NoteKind.QUESTION and note.options
                    else None
                )
                urg = note.urgency.value if note.kind is NoteKind.QUESTION else None
                cur.execute(
                    """
                    INSERT INTO skm_execution.step_notes (
                        id, workspace_id, run_id, attempt_id, step_id,
                        assignment_id, fencing_token, kind, text, options,
                        why_blocked, urgency, created_by, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        note.id,
                        ws_id,
                        run_id,
                        att_id,
                        UUID(str(note.step_id)),
                        UUID(str(assignment_id)),
                        fencing_token,
                        note.kind.value,
                        note.text,
                        opts,
                        note.why_blocked if note.kind is NoteKind.QUESTION else None,
                        urg,
                        UUID(str(created_by)),
                        rec_at,
                    ),
                )

        run(_ins)

    def add_tool_calls(self, calls: Sequence[ToolCallObservation]) -> int:
        def _op() -> int:
            with self._conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO skm_execution.step_tool_calls
                       (step_id, call_id, tool, duration_ms, coverage, fencing_token, recorded_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (step_id, call_id) DO NOTHING""",
                    [
                        (
                            e.step_id,
                            e.call.call_id,
                            e.call.tool,
                            e.call.duration_ms,
                            e.coverage,
                            e.fencing_token,
                            e.recorded_at,
                        )
                        for e in calls
                    ],
                )
                return cur.rowcount

        return run(_op)

    def tool_calls(self, step_id: StepId, *, after: str, limit: int) -> tuple[ToolCallObservation, ...]:
        def _op() -> tuple[ToolCallObservation, ...]:
            with self._conn.cursor() as cur:
                cur.execute(
                    """SELECT call_id, tool, duration_ms, coverage, fencing_token, recorded_at
                       FROM skm_execution.step_tool_calls
                       WHERE step_id = %s AND call_id > %s
                       ORDER BY call_id LIMIT %s""",
                    (step_id, after, limit),
                )
                return tuple(
                    ToolCallObservation(step_id, ToolCall(call_id, tool, duration), coverage, fence, at)
                    for call_id, tool, duration, coverage, fence, at in cur.fetchall()
                )

        return run(_op)

    def live_controls(self, task_id: TaskId) -> JsonObject:
        def _op() -> JsonObject:
            with self._conn.cursor() as cur:
                cur.execute("SELECT live_controls FROM skm_execution.run_tasks WHERE id = %s", (task_id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("task", task_id)
                return cast("JsonObject", row[0])

        return run(_op)

    def save_live_controls(self, task_id: TaskId, pending: JsonObject) -> None:
        def _op() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    "UPDATE skm_execution.run_tasks SET live_controls = %s WHERE id = %s",
                    (to_jsonb(pending), task_id),
                )

        run(_op)

    def incident_gates(self, task_id: TaskId) -> tuple[IncidentGate, ...]:
        def _op() -> tuple[IncidentGate, ...]:
            with self._conn.cursor() as cur:
                cur.execute(
                    """SELECT id, task_id, stop_after, fencing_token, kind, actor_id,
                              reason, details, created_at
                       FROM skm_execution.incident_gates WHERE task_id = %s ORDER BY created_at, id""",
                    (task_id,),
                )
                return tuple(IncidentGate(*row) for row in cur.fetchall())

        return run(_op)

    def add_incident_gate(self, gate: IncidentGate) -> None:
        def _op() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO skm_execution.incident_gates
                       (id, task_id, stop_after, fencing_token, kind, actor_id, reason, details, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        gate.id,
                        gate.task_id,
                        gate.stop_after,
                        gate.fencing_token,
                        gate.kind,
                        gate.actor_id,
                        gate.reason,
                        to_jsonb(gate.details),
                        gate.created_at,
                    ),
                )

        run(_op)

    def notes_for_step(self, step_id: StepId) -> tuple[StepNote, ...]:
        def _q() -> tuple[StepNote, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM skm_execution.step_notes "
                    "WHERE step_id = %s ORDER BY created_at ASC, id ASC",
                    (UUID(str(step_id)),),
                )
                return tuple(step_note_from_row(r) for r in cur.fetchall())

        return run(_q)
