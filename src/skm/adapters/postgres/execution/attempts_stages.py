"""PostgreSQL repositories for attempts and stage records (DDL ``0014``, ``0027``)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Final
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.assignments import PostgresAssignmentRepository
from skm.adapters.postgres.execution.autopilot_recovery import PostgresRecoveryRepository
from skm.adapters.postgres.execution.codecs import attempt_from_row, stage_from_row, step_from_row
from skm.adapters.postgres.execution.mapping import (
    opt_aware,
    opt_jsonb,
    process_identity_to_json,
    require_unchanged,
    run,
    validate_continuation_payload,
)
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.kernel.ids import AttemptId, RunId, TaskId
from skm.modules.execution.domain.assignment import WorkerOffer
from skm.modules.execution.domain.attempt import Attempt, continuation_to_json
from skm.modules.execution.domain.health import reap_proven
from skm.modules.execution.domain.ids import AssignmentId, StageRecordId
from skm.modules.execution.domain.reaping import (
    reap_receipt,
    timeout_cancel_outcome,
    timeout_cancel_requested,
)
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES, StageRecord
from skm.modules.execution.domain.stored_payloads import not_found, version_conflict
from skm.modules.execution.domain.workflow.history import StageEntry, StageHistory

__all__ = [
    "PostgresAttemptRepository",
    "PostgresStageRepository",
]

_ATTEMPT_OWNED: Final = ("run_id", "task_id", "workspace_id", "attempt_no", "started_at")
# run_recoveries is indexed by run, not by stage: the stage row names the run, so a stall check reads
# the recoveries of one run instead of scanning those of every run.
_REAP_CONFIRMED: Final = """
SELECT EXISTS(
    SELECT 1
      FROM skm_execution.attempt_stages s
      JOIN skm_execution.run_recoveries r ON r.run_id = s.run_id AND r.stage_record_id = s.id
     WHERE s.id = %s AND r.outcome = 'not_needed' AND r.reason_codes @> ARRAY['OS_STOP_PROVEN'])
"""
_STAGE_OWNED: Final = (
    "attempt_id",
    "run_id",
    "task_id",
    "seq",
    "stage_id",
    "stage_type",
    "round_no",
    "mode",
    "retry_of_id",
    "input_digest",
    "started_at",
    "fencing_token",
)


class PostgresAttemptRepository:
    def version(self, attempt_id: AttemptId) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT row_version FROM skm_execution.attempts WHERE id = %s FOR UPDATE", (attempt_id,)
            )
            row = cur.fetchone()
        if row is None:
            raise not_found("attempt", attempt_id)
        return int(row[0])

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, attempt: Attempt) -> None:
        validate_continuation_payload(attempt, None)
        route_doc = (
            None
            if attempt.executor_route is None
            else {
                "runtime_id": attempt.executor_route.runtime_id,
                "model": attempt.executor_route.model,
                "effort": attempt.executor_route.effort,
            }
        )
        cont_doc = None if attempt.continuation is None else continuation_to_json(attempt.continuation)

        def _ins() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO skm_execution.attempts (
                        id, run_id, task_id, workspace_id, attempt_no, state,
                        worker_id, host_id, environment_id, current_output_id, executor_route,
                        continuation, started_at, finished_at, end_reason, row_version, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, 1, %s
                    )
                    """,
                    (
                        UUID(str(attempt.id)),
                        UUID(str(attempt.run_id)),
                        UUID(str(attempt.task_id)),
                        UUID(str(attempt.workspace_id)),
                        attempt.attempt_no,
                        attempt.state.value,
                        None if attempt.worker_id is None else UUID(str(attempt.worker_id)),
                        None if attempt.host_id is None else UUID(str(attempt.host_id)),
                        None if attempt.environment_id is None else UUID(str(attempt.environment_id)),
                        None if attempt.current_output_id is None else UUID(str(attempt.current_output_id)),
                        opt_jsonb(route_doc),
                        opt_jsonb(cont_doc),
                        require_aware(attempt.started_at),
                        opt_aware(attempt.finished_at),
                        attempt.end_reason,
                        require_aware(attempt.started_at),
                    ),
                )

        run(_ins)

    def get(self, attempt_id: AttemptId, *, for_update: bool = False) -> Attempt:
        def _q() -> Attempt:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if for_update:
                    cur.execute(
                        "SELECT * FROM skm_execution.attempts WHERE id = %s FOR UPDATE",
                        (UUID(str(attempt_id)),),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM skm_execution.attempts WHERE id = %s",
                        (UUID(str(attempt_id)),),
                    )
                row = cur.fetchone()
            if row is None:
                raise not_found("attempt", attempt_id)
            return attempt_from_row(row)

        return run(_q)

    def save(self, attempt: Attempt, *, expected_version: int) -> None:
        def _upd() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM skm_execution.attempts WHERE id = %s FOR UPDATE",
                    (UUID(str(attempt.id)),),
                )
                row = cur.fetchone()
                if row is None:
                    raise not_found("attempt", attempt.id)
                actual_ver = int(row["row_version"])
                if actual_ver != expected_version:
                    raise version_conflict("attempt", attempt.id, expected_version, actual_ver)
                current = attempt_from_row(row)
                require_unchanged("attempt", current, attempt, _ATTEMPT_OWNED)
                validate_continuation_payload(attempt, current)
                route_doc = (
                    None
                    if attempt.executor_route is None
                    else {
                        "runtime_id": attempt.executor_route.runtime_id,
                        "model": attempt.executor_route.model,
                        "effort": attempt.executor_route.effort,
                    }
                )
                cont_doc = (
                    None if attempt.continuation is None else continuation_to_json(attempt.continuation)
                )
                cur.execute(
                    """
                    UPDATE skm_execution.attempts
                       SET state = %s, worker_id = %s, host_id = %s, environment_id = %s,
                           current_output_id = %s, executor_route = %s, continuation = %s,
                           finished_at = %s, end_reason = %s, row_version = row_version + 1
                     WHERE id = %s AND row_version = %s
                    """,
                    (
                        attempt.state.value,
                        None if attempt.worker_id is None else UUID(str(attempt.worker_id)),
                        None if attempt.host_id is None else UUID(str(attempt.host_id)),
                        None if attempt.environment_id is None else UUID(str(attempt.environment_id)),
                        None if attempt.current_output_id is None else UUID(str(attempt.current_output_id)),
                        opt_jsonb(route_doc),
                        opt_jsonb(cont_doc),
                        opt_aware(attempt.finished_at),
                        attempt.end_reason,
                        UUID(str(attempt.id)),
                        expected_version,
                    ),
                )
                if cur.rowcount != 1:
                    raise version_conflict("attempt", attempt.id, expected_version, None)

        run(_upd)

    def list_for_task(self, task_id: TaskId) -> tuple[Attempt, ...]:
        def _q() -> tuple[Attempt, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM skm_execution.attempts WHERE task_id = %s ORDER BY attempt_no ASC",
                    (UUID(str(task_id)),),
                )
                return tuple(attempt_from_row(r) for r in cur.fetchall())

        return run(_q)

    def list_for_run(self, run_id: RunId) -> tuple[Attempt, ...]:
        def _q() -> tuple[Attempt, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM skm_execution.attempts WHERE run_id = %s ORDER BY task_id, attempt_no",
                    (run_id,),
                )
                return tuple(attempt_from_row(row) for row in cur.fetchall())

        return run(_q)

    def next_attempt_no(self, task_id: TaskId) -> int:
        def _q() -> int:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM skm_execution.attempts WHERE task_id = %s",
                    (UUID(str(task_id)),),
                )
                row = cur.fetchone()
                return int(row[0]) if row is not None else 1

        return run(_q)


class PostgresStageRepository:
    def request_cancel(
        self,
        stage_id: StageRecordId,
        assignment_id: AssignmentId,
        fencing_token: int,
        deadline_at: datetime,
        now: datetime,
        *,
        grace_deadline_at: datetime,
    ) -> bool:
        stage = self.get(stage_id, for_update=True)
        assignments = PostgresAssignmentRepository(self._conn)
        outcome = timeout_cancel_outcome(
            stage,
            assignments.get(assignment_id),
            assignments.lease(assignment_id),
            assignment_id=assignment_id,
            fencing_token=fencing_token,
            deadline_at=deadline_at,
            grace_deadline_at=grace_deadline_at,
            now=now,
        )
        if outcome is None:
            return False
        self.save(replace(stage, outcome=outcome))
        return True

    def cancel_requested(self, attempt_id: AttemptId, fencing_token: int) -> bool:
        return timeout_cancel_requested(self.started_without_result(attempt_id), fencing_token)

    def confirm_reap(
        self, stage_id: StageRecordId, worker: WorkerOffer, now: datetime, *, receipt_id: UUID
    ) -> bool:
        stage = self.get(stage_id, for_update=True)
        if stage.state in ACTIVE_STAGE_STATES or not reap_proven(stage, worker):
            return False
        if not self.reap_confirmed(stage_id):
            PostgresRecoveryRepository(self._conn).add(reap_receipt(receipt_id, stage, now))
        return True

    def reap_confirmed(self, stage_id: StageRecordId) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(_REAP_CONFIRMED, (stage_id,))
            row = cur.fetchone()
            return bool(row and row[0])

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, record: StageRecord) -> None:
        pids = [process_identity_to_json(pi) for pi in record.process_identities]

        def _ins() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO skm_execution.attempt_stages (
                        id, run_id, task_id, attempt_id, seq, stage_id, stage_type,
                        round_no, mode, retry_of_id, state, input_digest,
                        outcome_kind, outcome, error_code, fencing_token,
                        runtime_started_at, process_identities, reused_from_step_id,
                        started_at, finished_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s
                    )
                    """,
                    (
                        UUID(str(record.id)),
                        UUID(str(record.run_id)),
                        UUID(str(record.task_id)),
                        UUID(str(record.attempt_id)),
                        record.seq,
                        record.stage_id,
                        record.stage_type,
                        record.round_no,
                        record.mode.value,
                        None if record.retry_of_id is None else UUID(str(record.retry_of_id)),
                        record.state.value,
                        record.input_digest,
                        None if record.outcome_kind is None else record.outcome_kind.value,
                        opt_jsonb(record.outcome),
                        record.error_code,
                        record.fencing_token,
                        opt_aware(record.runtime_started_at),
                        to_jsonb(pids),
                        None if record.reused_from_step_id is None else UUID(str(record.reused_from_step_id)),
                        require_aware(record.started_at),
                        opt_aware(record.finished_at),
                    ),
                )

        run(_ins)

    def find(
        self, attempt_id: AttemptId, stage_id: str, round_no: int, input_digest: str
    ) -> StageRecord | None:
        def _q() -> StageRecord | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM skm_execution.attempt_stages
                     WHERE attempt_id = %s AND stage_id = %s AND round_no = %s AND input_digest = %s
                     ORDER BY seq DESC
                     LIMIT 1
                    """,
                    (UUID(str(attempt_id)), stage_id, round_no, input_digest),
                )
                row = cur.fetchone()
            return None if row is None else stage_from_row(row)

        return run(_q)

    def history(self, attempt_id: AttemptId) -> StageHistory:
        def _q() -> StageHistory:
            uid = UUID(str(attempt_id))
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM skm_execution.attempt_stages WHERE attempt_id = %s ORDER BY seq ASC",
                    (uid,),
                )
                recs = [stage_from_row(r) for r in cur.fetchall()]
                cur.execute(
                    "SELECT * FROM skm_execution.attempt_steps WHERE attempt_id = %s ORDER BY seq ASC",
                    (uid,),
                )
                steps = [step_from_row(r) for r in cur.fetchall()]
            by_stg: dict[StageRecordId, list[object]] = {}
            for st in steps:
                by_stg.setdefault(st.stage_record_id, []).append(st)
            return StageHistory(
                tuple(StageEntry(r, tuple(st for st in steps if st.stage_record_id == r.id)) for r in recs)
            )

        return run(_q)

    def get(self, stage_record_id: StageRecordId, *, for_update: bool = False) -> StageRecord:
        def _q() -> StageRecord:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if for_update:
                    cur.execute(
                        "SELECT * FROM skm_execution.attempt_stages WHERE id = %s FOR UPDATE",
                        (UUID(str(stage_record_id)),),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM skm_execution.attempt_stages WHERE id = %s",
                        (UUID(str(stage_record_id)),),
                    )
                row = cur.fetchone()
            if row is None:
                raise not_found("stage_record", stage_record_id)
            return stage_from_row(row)

        return run(_q)

    def save(self, record: StageRecord) -> None:
        current = self.get(record.id, for_update=True)
        require_unchanged("stage_record", current, record, _STAGE_OWNED)
        pids = [process_identity_to_json(pi) for pi in record.process_identities]

        def _upd() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE skm_execution.attempt_stages
                       SET state = %s, outcome_kind = %s, outcome = %s, error_code = %s,
                           runtime_started_at = %s, process_identities = %s,
                           reused_from_step_id = %s, finished_at = %s
                     WHERE id = %s
                    """,
                    (
                        record.state.value,
                        None if record.outcome_kind is None else record.outcome_kind.value,
                        opt_jsonb(record.outcome),
                        record.error_code,
                        opt_aware(record.runtime_started_at),
                        to_jsonb(pids),
                        None if record.reused_from_step_id is None else UUID(str(record.reused_from_step_id)),
                        opt_aware(record.finished_at),
                        UUID(str(record.id)),
                    ),
                )

        run(_upd)

    def started_without_result(self, attempt_id: AttemptId) -> StageRecord | None:
        def _q() -> StageRecord | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM skm_execution.attempt_stages
                     WHERE attempt_id = %s AND state IN ('started', 'context_draft', 'running')
                     ORDER BY seq DESC
                     LIMIT 1
                    """,
                    (UUID(str(attempt_id)),),
                )
                row = cur.fetchone()
            return None if row is None else stage_from_row(row)

        return run(_q)
