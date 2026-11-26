"""PostgreSQL repository for assignments and leases (DDL ``0014``, ``0028``)."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import (
    assignment_from_row,
    lease_from_row,
    stage_from_row,
)
from skm.adapters.postgres.execution.mapping import (
    opt_jsonb,
    process_identity_to_json,
    require_unchanged,
    run,
)
from skm.adapters.postgres.jsonb import require_aware
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import AttemptId, ProjectId, WorkspaceId
from skm.modules.execution.domain.assignment import (
    Assignment,
    AssignmentState,
    WorkerOffer,
    worker_matches,
)
from skm.modules.execution.domain.ids import AssignmentId
from skm.modules.execution.domain.lease import Lease, ProcessIdentity
from skm.modules.execution.domain.reaping import reap_barrier_satisfied
from skm.modules.execution.domain.stored_payloads import not_found, schema_invalid, version_conflict

__all__ = ["PostgresAssignmentRepository"]

# One read for the whole page of expired leases instead of one per lease.
_LEASED_ASSIGNMENTS: Final = """
SELECT * FROM skm_execution.assignments WHERE id = ANY(%s::uuid[]) AND state = 'leased'
"""
_ASSIGNMENT_OWNED: Final = (
    "run_id",
    "task_id",
    "attempt_id",
    "workspace_id",
    "reconcile_effect_id",
    "reap_stage_record_id",
    "reap_step_id",
    "created_at",
)


class _SkipCandidate(Exception):
    """Rolls back the per-candidate savepoint so skipped rows do not retain locks."""


class PostgresAssignmentRepository:
    def expiry_candidates(self, *, limit: int) -> tuple[tuple[Assignment, Lease], ...]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT a.*, l.assignment_id, l.worker_id, l.fencing_token,
                    l.expires_at, l.last_heartbeat_at, l.process_identity, l.offered_runtimes
                FROM skm_execution.assignments a JOIN skm_execution.assignment_leases l
                  ON l.assignment_id=a.id
                WHERE a.state='leased' AND l.expires_at <= clock_timestamp()
                ORDER BY l.expires_at, a.id LIMIT %s""",
                (max(0, limit),),
            )
            return tuple((assignment_from_row(row), lease_from_row(row)) for row in cur.fetchall())

    def for_attempt(self, attempt_id: AttemptId) -> tuple[Assignment, ...]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM skm_execution.assignments WHERE attempt_id = %s ORDER BY id", (attempt_id,)
            )
            return tuple(assignment_from_row(row) for row in cur.fetchall())

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, assignment: Assignment) -> None:
        req = assignment.requirements

        def _ins() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO skm_execution.assignments (
                        id, run_id, task_id, attempt_id, workspace_id, state, available_at,
                        required_capabilities, required_host_id, required_labels,
                        environment_kind, required_isolation_profiles,
                        priority, last_fencing_token, reconcile_effect_id,
                        reap_stage_record_id, reap_step_id, row_version, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        UUID(str(assignment.id)),
                        UUID(str(assignment.run_id)),
                        UUID(str(assignment.task_id)),
                        UUID(str(assignment.attempt_id)),
                        UUID(str(assignment.workspace_id)),
                        assignment.state.value,
                        require_aware(assignment.available_at),
                        sorted(req.capabilities),
                        None if req.required_host_id is None else UUID(str(req.required_host_id)),
                        sorted(req.required_labels),
                        req.environment_kind.value,
                        sorted(req.isolation_profiles),
                        assignment.priority,
                        assignment.last_fencing_token,
                        (
                            None
                            if assignment.reconcile_effect_id is None
                            else UUID(str(assignment.reconcile_effect_id))
                        ),
                        (
                            None
                            if assignment.reap_stage_record_id is None
                            else UUID(str(assignment.reap_stage_record_id))
                        ),
                        None if assignment.reap_step_id is None else UUID(str(assignment.reap_step_id)),
                        assignment.row_version,
                        require_aware(assignment.created_at),
                        require_aware(assignment.created_at),
                    ),
                )

        run(_ins)

    def _try_claim_candidate(
        self,
        cand_meta: dict[str, object],
        *,
        worker: WorkerOffer,
        blocked_set: set[UUID],
        now_aw: datetime,
        exp_aw: datetime,
        admit: Callable[[Assignment], bool] | None,
    ) -> tuple[Assignment, Lease]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT project_id, status, queued FROM skm_execution.runs WHERE id = %s FOR UPDATE",
                (cand_meta["run_id"],),
            )
            rrow = cur.fetchone()
            if rrow is None or (
                cand_meta["reconcile_effect_id"] is None
                and (
                    rrow["project_id"] in blocked_set
                    or rrow["status"] not in ("ready", "running", "waiting")
                    or bool(rrow["queued"])
                )
            ):
                raise _SkipCandidate
            cur.execute(
                "SELECT id FROM skm_execution.run_tasks WHERE id = %s FOR UPDATE", (cand_meta["task_id"],)
            )
            if cur.fetchone() is None:
                raise _SkipCandidate
            cur.execute(
                "SELECT id FROM skm_execution.attempts WHERE id = %s FOR UPDATE", (cand_meta["attempt_id"],)
            )
            if cur.fetchone() is None:
                raise _SkipCandidate
            cur.execute(
                """
                SELECT * FROM skm_execution.assignments
                 WHERE id = %s AND state = 'available' AND available_at <= %s
                   FOR UPDATE SKIP LOCKED
                """,
                (cand_meta["id"], now_aw),
            )
            arow = cur.fetchone()
            if arow is None:
                raise _SkipCandidate
            asg = assignment_from_row(arow)
            # Recheck time after the ownership locks; candidate scan time cannot grant an expired lease.
            cur.execute("SELECT clock_timestamp() AS db_now")
            clock_row = cur.fetchone()
            if clock_row is None:
                raise _SkipCandidate
            ttl = exp_aw - now_aw
            now_aw = clock_row["db_now"]
            exp_aw = now_aw + ttl
            if asg.available_at > now_aw:
                raise _SkipCandidate
            if not worker_matches(asg.requirements, worker):
                raise _SkipCandidate
            if asg.reap_stage_record_id is not None:
                cur.execute(
                    "SELECT * FROM skm_execution.attempt_stages WHERE id = %s",
                    (UUID(str(asg.reap_stage_record_id)),),
                )
                srow = cur.fetchone()
                stg = None if srow is None else stage_from_row(srow)
                if not reap_barrier_satisfied(stg, asg.reap_step_id, worker):
                    raise _SkipCandidate
            if admit is not None and not admit(asg):
                raise _SkipCandidate
            cur.execute("SELECT clock_timestamp() AS db_now")
            admitted_at = cur.fetchone()
            if admitted_at is None:
                raise _SkipCandidate
            now_aw = admitted_at["db_now"]
            exp_aw = now_aw + ttl
            cur.execute(
                """
                UPDATE skm_execution.assignments
                   SET state = 'leased',
                       last_fencing_token = last_fencing_token + 1,
                       row_version = row_version + 1,
                       updated_at = clock_timestamp()
                 WHERE id = %s
             RETURNING last_fencing_token, row_version
                """,
                (UUID(str(asg.id)),),
            )
            upd = cur.fetchone()
            if upd is None:
                raise _SkipCandidate
            tok, new_ver = int(upd["last_fencing_token"]), int(upd["row_version"])
            cur.execute(
                """
                INSERT INTO skm_execution.assignment_leases (
                    assignment_id, workspace_id, worker_id, fencing_token,
                    expires_at, last_heartbeat_at, process_identity, offered_runtimes
                ) VALUES (%s, %s, %s, %s, %s, %s, NULL, %s)
                """,
                (
                    UUID(str(asg.id)),
                    UUID(str(asg.workspace_id)),
                    UUID(str(worker.worker_id)),
                    tok,
                    exp_aw,
                    now_aw,
                    sorted(worker.offered_runtimes),
                ),
            )
            leased = dataclasses.replace(
                asg, state=AssignmentState.LEASED, last_fencing_token=tok, row_version=new_ver
            )
            return leased, Lease(asg.id, worker.worker_id, tok, exp_aw, now_aw, None, worker.offered_runtimes)

    def claim(
        self,
        *,
        worker: WorkerOffer,
        workspace_ids: frozenset[WorkspaceId],
        blocked_project_ids: frozenset[ProjectId],
        now: datetime,
        ttl: timedelta,
        admit: Callable[[Assignment], bool] | None = None,
    ) -> tuple[Assignment, Lease] | None:
        if ttl <= timedelta(0):
            raise schema_invalid("lease ttl must be positive", field="ttl")
        if not workspace_ids or not worker.environment_kinds:
            return None
        ws_arr = [UUID(str(w)) for w in workspace_ids]
        blocked_set = {UUID(str(p)) for p in blocked_project_ids}
        blk_arr = list(blocked_set)
        env_arr = [k.value for k in worker.environment_kinds]
        now_aw = require_aware(now)
        exp_aw = require_aware(now + ttl)

        def _claim() -> tuple[Assignment, Lease] | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT a.id, a.run_id, a.task_id, a.attempt_id, a.reconcile_effect_id
                      FROM skm_execution.assignments a
                      JOIN skm_execution.runs r ON r.id = a.run_id
                     WHERE a.state = 'available'
                       AND a.workspace_id = ANY(%s::uuid[])
                       AND a.available_at <= %s
                       AND (a.reconcile_effect_id IS NOT NULL OR (
                            NOT (r.project_id = ANY(%s::uuid[]))
                            AND r.status IN ('ready', 'running', 'waiting') AND NOT r.queued))
                       AND (a.required_host_id IS NULL OR a.required_host_id = %s)
                       AND a.required_capabilities <@ %s::text[]
                       AND a.required_labels <@ %s::text[]
                       AND a.required_isolation_profiles <@ %s::text[]
                       AND a.environment_kind = ANY(%s::text[])
                     ORDER BY COALESCE(r.started_at, r.created_at) ASC,
                              a.priority ASC, a.available_at ASC, a.id ASC
                    """,
                    (
                        ws_arr,
                        now_aw,
                        blk_arr,
                        UUID(str(worker.host_id)),
                        sorted(worker.capabilities),
                        sorted(worker.labels),
                        sorted(worker.isolation_profiles),
                        env_arr,
                    ),
                )
                candidates = cur.fetchall()
            for cand in candidates:
                try:
                    with self._conn.transaction():
                        return self._try_claim_candidate(
                            cand,
                            worker=worker,
                            blocked_set=blocked_set,
                            now_aw=now_aw,
                            exp_aw=exp_aw,
                            admit=admit,
                        )
                except _SkipCandidate:
                    continue
            return None

        return run(_claim)

    def get(self, assignment_id: AssignmentId, *, for_update: bool = False) -> Assignment:
        def _q() -> Assignment:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if for_update:
                    cur.execute(
                        "SELECT * FROM skm_execution.assignments WHERE id = %s FOR UPDATE",
                        (UUID(str(assignment_id)),),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM skm_execution.assignments WHERE id = %s",
                        (UUID(str(assignment_id)),),
                    )
                row = cur.fetchone()
            if row is None:
                raise not_found("assignment", assignment_id)
            return assignment_from_row(row)

        return run(_q)

    def lease(self, assignment_id: AssignmentId, *, for_update: bool = False) -> Lease | None:
        def _q() -> Lease | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if for_update:
                    cur.execute(
                        "SELECT * FROM skm_execution.assignment_leases WHERE assignment_id = %s FOR UPDATE",
                        (UUID(str(assignment_id)),),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM skm_execution.assignment_leases WHERE assignment_id = %s",
                        (UUID(str(assignment_id)),),
                    )
                row = cur.fetchone()
            return None if row is None else lease_from_row(row)

        return run(_q)

    def renew(
        self,
        lease: Lease,
        *,
        expires_at: datetime,
        heartbeat_at: datetime,
        identity: ProcessIdentity | None,
    ) -> None:
        exp_aw, hb_aw = require_aware(expires_at), require_aware(heartbeat_at)

        def _upd() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT l.*, a.state AS asg_state, clock_timestamp() AS db_now
                      FROM skm_execution.assignment_leases l
                      JOIN skm_execution.assignments a ON a.id = l.assignment_id
                     WHERE l.assignment_id = %s
                       FOR UPDATE OF l, a
                    """,
                    (UUID(str(lease.assignment_id)),),
                )
                row = cur.fetchone()
                if (
                    row is None
                    or row["asg_state"] != "leased"
                    or UUID(str(row["worker_id"])) != UUID(str(lease.worker_id))
                    or int(row["fencing_token"]) != lease.fencing_token
                    or row["expires_at"] <= max(hb_aw, row["db_now"])
                ):
                    raise Conflict(
                        ErrorCode.LEASE_LOST,
                        "lease is missing, stale, or expired",
                        details={"assignment_id": str(lease.assignment_id)},
                    )
                cur_lease = lease_from_row(row)
                eff_id = identity if identity is not None else cur_lease.process_identity
                cur.execute(
                    """
                    UPDATE skm_execution.assignment_leases
                       SET expires_at = %s, last_heartbeat_at = %s, process_identity = %s
                     WHERE assignment_id = %s
                       AND fencing_token = %s
                       AND expires_at > %s
                    """,
                    (
                        exp_aw,
                        hb_aw,
                        opt_jsonb(process_identity_to_json(eff_id)),
                        UUID(str(lease.assignment_id)),
                        lease.fencing_token,
                        hb_aw,
                    ),
                )
                if cur.rowcount != 1:
                    raise Conflict(
                        ErrorCode.LEASE_LOST,
                        "lease expired",
                        details={"assignment_id": str(lease.assignment_id)},
                    )

        run(_upd)

    def stale_available(self, older_than: datetime, *, limit: int) -> tuple[Assignment, ...]:
        def _q() -> tuple[Assignment, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM skm_execution.assignments
                     WHERE state = 'available' AND available_at <= %s
                     ORDER BY available_at ASC, id ASC
                     LIMIT %s
                    """,
                    (require_aware(older_than), max(0, limit)),
                )
                return tuple(assignment_from_row(r) for r in cur.fetchall())

        return run(_q)

    def save(self, assignment: Assignment, *, expected_version: int) -> None:
        current = self.get(assignment.id, for_update=True)
        if current.row_version != expected_version:
            raise version_conflict("assignment", assignment.id, expected_version, current.row_version)
        require_unchanged("assignment", current, assignment, _ASSIGNMENT_OWNED)
        new_ver = (
            assignment.row_version if assignment.row_version > expected_version else expected_version + 1
        )
        req = assignment.requirements

        def _upd() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE skm_execution.assignments
                       SET state = %s, available_at = %s,
                           required_capabilities = %s, required_host_id = %s, required_labels = %s,
                           environment_kind = %s, required_isolation_profiles = %s,
                           priority = %s, last_fencing_token = %s,
                           row_version = %s, updated_at = clock_timestamp()
                     WHERE id = %s AND row_version = %s
                    """,
                    (
                        assignment.state.value,
                        require_aware(assignment.available_at),
                        sorted(req.capabilities),
                        None if req.required_host_id is None else UUID(str(req.required_host_id)),
                        sorted(req.required_labels),
                        req.environment_kind.value,
                        sorted(req.isolation_profiles),
                        assignment.priority,
                        assignment.last_fencing_token,
                        new_ver,
                        UUID(str(assignment.id)),
                        expected_version,
                    ),
                )
                if cur.rowcount != 1:
                    raise version_conflict("assignment", assignment.id, expected_version, None)

        run(_upd)

    def drop_lease(self, assignment_id: AssignmentId) -> None:
        def _del() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM skm_execution.assignment_leases WHERE assignment_id = %s",
                    (UUID(str(assignment_id)),),
                )

        run(_del)

    def expired(self, now: datetime, *, limit: int) -> tuple[tuple[Assignment, Lease], ...]:
        now_aw = require_aware(now)

        def _q() -> tuple[tuple[Assignment, Lease], ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT l.assignment_id, l.worker_id, l.fencing_token,
                           l.expires_at, l.last_heartbeat_at, l.process_identity, l.offered_runtimes
                      FROM skm_execution.assignment_leases l
                      JOIN skm_execution.assignments a ON a.id = l.assignment_id
                     WHERE l.expires_at <= LEAST(%s, clock_timestamp())
                       AND a.state = 'leased'
                     ORDER BY l.expires_at ASC, l.assignment_id ASC
                     LIMIT %s
                       FOR UPDATE OF l SKIP LOCKED
                    """,
                    (now_aw, max(0, limit)),
                )
                lrows = cur.fetchall()
                if not lrows:
                    return ()
                cur.execute(_LEASED_ASSIGNMENTS, ([lr["assignment_id"] for lr in lrows],))
                leased = {ar["id"]: assignment_from_row(ar) for ar in cur.fetchall()}
                return tuple(
                    (leased[lr["assignment_id"]], lease_from_row(lr))
                    for lr in lrows
                    if lr["assignment_id"] in leased
                )

        return run(_q)
