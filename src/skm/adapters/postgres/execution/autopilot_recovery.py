"""PostgreSQL adapters for autopilot, recovery, and evidence binding repositories."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import autopilot_from_row, recovery_from_row
from skm.adapters.postgres.execution.codecs_core import as_uuid
from skm.adapters.postgres.execution.mapping import opt_aware, require_unchanged, run
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.kernel.ids import FileVersionId, ProjectId
from skm.modules.artifacts.public import BindingRole
from skm.modules.execution.domain.autopilot import AutopilotState, AutopilotStateKind
from skm.modules.execution.domain.contracts import EvidenceOwnerKind
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.stored_payloads import (
    EVIDENCE_BINDING_ROLES,
    already_exists,
    check_binding_role,
    invalid_ref,
    invalid_transition,
    not_found,
    schema_invalid,
    version_conflict,
)

if TYPE_CHECKING:
    from skm.kernel.ids import RunId
    from skm.modules.execution.domain.ids import RecoveryRecordId, StageRecordId, StepId
    from skm.modules.execution.domain.recovery import RecoveryRecord

__all__ = [
    "PostgresAutopilotRepository",
    "PostgresEvidenceBindingRepository",
    "PostgresRecoveryRepository",
]

_RECOVERY_OWNED: Final = ("run_id", "task_id", "attempt_id", "stage_record_id", "step_id", "trigger")
_RUN_PROJ: Final = "SELECT project_id FROM skm_execution.runs WHERE id = %s"
_ATTEMPT_WS: Final = "SELECT workspace_id FROM skm_execution.attempts WHERE id = %s"
_OUTPUT_ATTEMPT_WS: Final = "SELECT attempt_id, workspace_id FROM skm_execution.attempt_outputs WHERE id = %s"
_CHECK_WS: Final = "SELECT workspace_id FROM skm_execution.check_executions WHERE id = %s"
_REVIEW_WS: Final = "SELECT workspace_id FROM skm_execution.reviews WHERE id = %s"

_GET_AUTOPILOT: Final = "SELECT * FROM skm_execution.autopilot_states WHERE project_id = %s"
_LOCK_AUTOPILOT: Final = "SELECT * FROM skm_execution.autopilot_states WHERE project_id = %s FOR UPDATE"
_INSERT_AUTOPILOT: Final = """
INSERT INTO skm_execution.autopilot_states (
    project_id, workspace_id, state, emergency, current_run_id, session_started_at,
    counters, session_limits, stop_code, stop_detail, updated_by, updated_at, row_version
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
ON CONFLICT (project_id) DO NOTHING
RETURNING row_version
"""
_UPDATE_AUTOPILOT: Final = """
UPDATE skm_execution.autopilot_states
   SET state = %s, emergency = %s, current_run_id = %s, session_started_at = %s,
       counters = %s, session_limits = %s, stop_code = %s, stop_detail = %s,
       updated_by = %s, updated_at = %s, row_version = %s
 WHERE project_id = %s
"""
_ENABLED_AUTOPILOT: Final = """
SELECT project_id FROM skm_execution.autopilot_states
 WHERE state IN ('running', 'paused', 'draining')
 ORDER BY updated_at ASC, project_id ASC
 LIMIT %s
"""
_EMERGENCY_AUTOPILOT: Final = """
SELECT project_id FROM skm_execution.autopilot_states WHERE emergency ORDER BY project_id ASC
"""

_INSERT_RECOVERY: Final = """
INSERT INTO skm_execution.run_recoveries (
    id, run_id, task_id, attempt_id, stage_record_id, step_id, workspace_id,
    trigger, steps_done, snapshot_file_version_id, outcome, reason_codes, at, finished_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
_GET_RECOVERY: Final = "SELECT * FROM skm_execution.run_recoveries WHERE id = %s"
_LOCK_RECOVERY: Final = "SELECT * FROM skm_execution.run_recoveries WHERE id = %s FOR UPDATE"
_UPDATE_RECOVERY: Final = """
UPDATE skm_execution.run_recoveries
   SET steps_done = %s, snapshot_file_version_id = %s, outcome = %s,
       reason_codes = %s, at = %s, finished_at = %s
 WHERE id = %s
"""
_OPEN_RECOVERY_FOR_STAGE: Final = """
SELECT * FROM skm_execution.run_recoveries
 WHERE stage_record_id = %s AND outcome IS NULL
 ORDER BY at DESC, id DESC
 LIMIT 1
"""
_COUNT_RECOVERIES_SINCE: Final = """
SELECT count(*) AS cnt
  FROM skm_execution.run_recoveries
 WHERE run_id = %s
   AND at >= %s
   AND (cardinality(%s::text[]) = 0 OR outcome = ANY(%s::text[]))
"""

_INSERT_ATTEMPT_BINDING: Final = """
INSERT INTO skm_execution.attempt_file_bindings (
    attempt_id, workspace_id, file_version_id, role, step_id, created_at
) VALUES (%s, %s, %s, %s, %s, clock_timestamp())
ON CONFLICT (attempt_id, file_version_id, role) DO NOTHING
"""
_INSERT_OUTPUT_BINDING: Final = """
INSERT INTO skm_execution.output_file_bindings (
    output_id, attempt_id, workspace_id, file_version_id, role, created_at
) VALUES (%s, %s, %s, %s, %s, clock_timestamp())
ON CONFLICT (output_id, file_version_id, role) DO NOTHING
"""
_INSERT_CHECK_BINDING: Final = """
INSERT INTO skm_execution.check_evidence_bindings (
    check_execution_id, workspace_id, file_version_id, role, created_at
) VALUES (%s, %s, %s, %s, clock_timestamp())
ON CONFLICT (check_execution_id, file_version_id, role) DO NOTHING
"""
_INSERT_REVIEW_BINDING: Final = """
INSERT INTO skm_execution.review_evidence_bindings (
    review_id, workspace_id, file_version_id, role, created_at
) VALUES (%s, %s, %s, %s, clock_timestamp())
ON CONFLICT (review_id, file_version_id, role) DO NOTHING
"""
_SELECT_ATTEMPT_BINDINGS: Final = """
SELECT file_version_id, role FROM skm_execution.attempt_file_bindings
 WHERE attempt_id = %s ORDER BY file_version_id::text ASC, role ASC
"""
_SELECT_OUTPUT_BINDINGS: Final = """
SELECT file_version_id, role FROM skm_execution.output_file_bindings
 WHERE output_id = %s ORDER BY file_version_id::text ASC, role ASC
"""
_SELECT_CHECK_BINDINGS: Final = """
SELECT file_version_id, role FROM skm_execution.check_evidence_bindings
 WHERE check_execution_id = %s ORDER BY file_version_id::text ASC, role ASC
"""
_SELECT_REVIEW_BINDINGS: Final = """
SELECT file_version_id, role FROM skm_execution.review_evidence_bindings
 WHERE review_id = %s ORDER BY file_version_id::text ASC, role ASC
"""


class PostgresAutopilotRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def get(self, project_id: ProjectId, *, for_update: bool = False) -> AutopilotState | None:
        def _op() -> AutopilotState | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if for_update:
                    cur.execute(_LOCK_AUTOPILOT, (project_id,))
                else:
                    cur.execute(_GET_AUTOPILOT, (project_id,))
                row = cur.fetchone()
                return None if row is None else autopilot_from_row(row)

        return run(_op)

    def save(self, state: AutopilotState, *, expected_version: int | None) -> None:
        if state.emergency and state.state is not AutopilotStateKind.STOPPED:
            raise schema_invalid("emergency autopilot state must be stopped", field="emergency")
        if (state.state is AutopilotStateKind.STOPPED) != (state.stop_code is not None):
            raise schema_invalid("stopped autopilot state requires stop_code", field="stop_code")
        if (
            state.state
            in {AutopilotStateKind.RUNNING, AutopilotStateKind.PAUSED, AutopilotStateKind.DRAINING}
            and state.session_started_at is None
        ):
            raise schema_invalid("active autopilot state requires session_started_at")

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if state.current_run_id is not None:
                    cur.execute(_RUN_PROJ, (state.current_run_id,))
                    rw = cur.fetchone()
                    if rw is None or ProjectId(as_uuid(rw["project_id"])) != state.project_id:
                        raise invalid_ref(
                            "fk_autopilot_states__runs", current_run_id=str(state.current_run_id)
                        )
                if expected_version is None:
                    cur.execute(
                        _INSERT_AUTOPILOT,
                        (
                            state.project_id,
                            state.workspace_id,
                            state.state.value,
                            state.emergency,
                            state.current_run_id,
                            opt_aware(state.session_started_at),
                            to_jsonb(thaw_json(state.counters)),
                            to_jsonb(thaw_json(state.session_limits)),
                            state.stop_code,
                            state.stop_detail,
                            state.updated_by,
                            require_aware(state.updated_at),
                        ),
                    )
                    if cur.fetchone() is None:
                        cur.execute(_GET_AUTOPILOT, (state.project_id,))
                        ex = cur.fetchone()
                        raise version_conflict(
                            "autopilot_state",
                            state.project_id,
                            None,
                            None if ex is None else int(ex["row_version"]),
                        )
                    return
                cur.execute(_LOCK_AUTOPILOT, (state.project_id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("autopilot_state", state.project_id)
                cur_st = autopilot_from_row(row)
                if cur_st.row_version != expected_version:
                    raise version_conflict(
                        "autopilot_state", state.project_id, expected_version, cur_st.row_version
                    )
                require_unchanged("autopilot_state", cur_st, state, ("workspace_id",))
                cur.execute(
                    _UPDATE_AUTOPILOT,
                    (
                        state.state.value,
                        state.emergency,
                        state.current_run_id,
                        opt_aware(state.session_started_at),
                        to_jsonb(thaw_json(state.counters)),
                        to_jsonb(thaw_json(state.session_limits)),
                        state.stop_code,
                        state.stop_detail,
                        state.updated_by,
                        require_aware(state.updated_at),
                        expected_version + 1,
                        state.project_id,
                    ),
                )

        run(_op)

    def enabled_project_ids(self, *, limit: int) -> tuple[ProjectId, ...]:
        def _op() -> tuple[ProjectId, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_ENABLED_AUTOPILOT, (limit,))
                return tuple(ProjectId(as_uuid(r["project_id"])) for r in cur.fetchall())

        return run(_op)

    def emergency_project_ids(self) -> frozenset[ProjectId]:
        def _op() -> frozenset[ProjectId]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_EMERGENCY_AUTOPILOT)
                return frozenset(ProjectId(as_uuid(r["project_id"])) for r in cur.fetchall())

        return run(_op)


class PostgresRecoveryRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def add(self, record: RecoveryRecord) -> None:
        at_aw = require_aware(record.at)
        fin_aw = at_aw if record.outcome is not None else None

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_ATTEMPT_WS, (record.attempt_id,))
                arow = cur.fetchone()
                if arow is None:
                    raise invalid_ref("fk_run_recoveries__attempts", attempt_id=str(record.attempt_id))
                cur.execute(
                    _INSERT_RECOVERY,
                    (
                        record.id,
                        record.run_id,
                        record.task_id,
                        record.attempt_id,
                        record.stage_record_id,
                        record.step_id,
                        as_uuid(arow["workspace_id"]),
                        record.trigger,
                        to_jsonb([s.value for s in record.steps_done]),
                        record.snapshot_file_version_id,
                        record.outcome,
                        list(record.reason_codes),
                        at_aw,
                        fin_aw,
                    ),
                )

        run(_op)

    def get(self, recovery_id: RecoveryRecordId) -> RecoveryRecord:
        def _op() -> RecoveryRecord:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_RECOVERY, (recovery_id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("recovery_record", recovery_id)
                return recovery_from_row(row)

        return run(_op)

    def save(self, record: RecoveryRecord) -> None:
        at_aw = require_aware(record.at)
        fin_aw = at_aw if record.outcome is not None else None

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_LOCK_RECOVERY, (record.id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("recovery_record", record.id)
                cur_rec = recovery_from_row(row)
                if cur_rec.outcome is not None and record != cur_rec:
                    raise invalid_transition("finished recovery record is immutable", id=str(record.id))
                require_unchanged("recovery_record", cur_rec, record, _RECOVERY_OWNED)
                cur.execute(
                    _UPDATE_RECOVERY,
                    (
                        to_jsonb([s.value for s in record.steps_done]),
                        record.snapshot_file_version_id,
                        record.outcome,
                        list(record.reason_codes),
                        at_aw,
                        fin_aw,
                        record.id,
                    ),
                )

        run(_op)

    def open_for_stage(self, stage_record_id: StageRecordId) -> RecoveryRecord | None:
        def _op() -> RecoveryRecord | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_OPEN_RECOVERY_FOR_STAGE, (stage_record_id,))
                row = cur.fetchone()
                return None if row is None else recovery_from_row(row)

        return run(_op)

    def count_since(self, run_id: RunId, since: datetime, outcomes: frozenset[str]) -> int:
        since_aw = require_aware(since)
        outs = sorted(outcomes)

        def _op() -> int:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_COUNT_RECOVERIES_SINCE, (run_id, since_aw, outs, outs))
                row = cur.fetchone()
                return 0 if row is None else int(row["cnt"])

        return run(_op)


class PostgresEvidenceBindingRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def bind(
        self,
        owner_kind: EvidenceOwnerKind,
        owner_id: UUID,
        file_version_ids: Sequence[FileVersionId],
        role: BindingRole,
        *,
        step_id: StepId | None = None,
    ) -> None:
        check_binding_role(owner_kind, role.value)
        if step_id is not None and owner_kind != "attempt":
            raise schema_invalid("step_id is only allowed on attempt bindings", field="step_id")

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if owner_kind == "attempt":
                    cur.execute(_ATTEMPT_WS, (owner_id,))
                    ar = cur.fetchone()
                    if ar is None:
                        raise invalid_ref("fk_attempt_file_bindings__attempts", attempt_id=str(owner_id))
                    ws_id = as_uuid(ar["workspace_id"])
                    for fvid in file_version_ids:
                        cur.execute(_INSERT_ATTEMPT_BINDING, (owner_id, ws_id, fvid, role.value, step_id))
                elif owner_kind == "output":
                    cur.execute(_OUTPUT_ATTEMPT_WS, (owner_id,))
                    outr = cur.fetchone()
                    if outr is None:
                        raise invalid_ref("fk_output_file_bindings__attempt_outputs", output_id=str(owner_id))
                    att_id, ws_id = as_uuid(outr["attempt_id"]), as_uuid(outr["workspace_id"])
                    for fvid in file_version_ids:
                        cur.execute(_INSERT_OUTPUT_BINDING, (owner_id, att_id, ws_id, fvid, role.value))
                elif owner_kind == "check_execution":
                    cur.execute(_CHECK_WS, (owner_id,))
                    cr = cur.fetchone()
                    if cr is None:
                        raise invalid_ref(
                            "fk_check_evidence_bindings__check_executions",
                            check_execution_id=str(owner_id),
                        )
                    ws_id = as_uuid(cr["workspace_id"])
                    for fvid in file_version_ids:
                        cur.execute(_INSERT_CHECK_BINDING, (owner_id, ws_id, fvid, role.value))
                elif owner_kind == "review":
                    cur.execute(_REVIEW_WS, (owner_id,))
                    rr = cur.fetchone()
                    if rr is None:
                        raise invalid_ref("fk_review_evidence_bindings__reviews", review_id=str(owner_id))
                    ws_id = as_uuid(rr["workspace_id"])
                    for fvid in file_version_ids:
                        cur.execute(_INSERT_REVIEW_BINDING, (owner_id, ws_id, fvid, role.value))
                else:
                    raise already_exists("unreachable")

        run(_op)

    def for_owner(
        self, owner_kind: EvidenceOwnerKind, owner_id: UUID
    ) -> tuple[tuple[FileVersionId, BindingRole], ...]:
        if owner_kind not in EVIDENCE_BINDING_ROLES:
            raise schema_invalid(f"unknown owner_kind {owner_kind!r}", field="owner_kind")

        def _op() -> tuple[tuple[FileVersionId, BindingRole], ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if owner_kind == "attempt":
                    cur.execute(_SELECT_ATTEMPT_BINDINGS, (owner_id,))
                elif owner_kind == "output":
                    cur.execute(_SELECT_OUTPUT_BINDINGS, (owner_id,))
                elif owner_kind == "check_execution":
                    cur.execute(_SELECT_CHECK_BINDINGS, (owner_id,))
                else:
                    cur.execute(_SELECT_REVIEW_BINDINGS, (owner_id,))
                return tuple(
                    (FileVersionId(as_uuid(r["file_version_id"])), BindingRole(str(r["role"])))
                    for r in cur.fetchall()
                )

        return run(_op)
