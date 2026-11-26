"""Memory repositories for assignments, leases, environments, and outputs (DDL ``0014``, ``0028``)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.execution.state import clone_value, execution_state
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.modules.execution.domain.assignment import (
    Assignment,
    AssignmentState,
    WorkerOffer,
    worker_matches,
)
from skm.modules.execution.domain.environment import (
    EnvironmentKind,
    EnvironmentState,
    ExecutionEnvironment,
)
from skm.modules.execution.domain.lease import Lease, ProcessIdentity, issue_lease
from skm.modules.execution.domain.reaping import reap_barrier_satisfied
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.stored_payloads import (
    already_exists,
    field_owned,
    invalid_ref,
    not_found,
    schema_invalid,
    version_conflict,
)

if TYPE_CHECKING:
    from skm.kernel.ids import AttemptId, HostId, ProjectId, RepositoryId, WorkspaceId
    from skm.modules.execution.domain.contracts import RetainPolicy
    from skm.modules.execution.domain.ids import AssignmentId, EnvironmentId, OutputId
    from skm.modules.execution.domain.output import Output

__all__ = [
    "MemoryAssignmentRepository",
    "MemoryEnvironmentRepository",
    "MemoryOutputRepository",
]

_LIVE_ASGN: Final = frozenset({AssignmentState.AVAILABLE, AssignmentState.LEASED})
_CLAIMABLE_RUN_STATUSES: Final = frozenset({RunStatus.READY, RunStatus.RUNNING, RunStatus.WAITING})
_ASGN_OWNED: Final = (
    "run_id",
    "task_id",
    "attempt_id",
    "workspace_id",
    "reconcile_effect_id",
    "reap_stage_record_id",
    "reap_step_id",
    "created_at",
)


class MemoryAssignmentRepository:
    def expiry_candidates(self, *, limit: int) -> tuple[tuple[Assignment, Lease], ...]:
        return self._expired_leases(self._backend.core.clock.now(), limit=limit)

    def for_attempt(self, attempt_id: AttemptId) -> tuple[Assignment, ...]:
        return tuple(
            clone_value(a)
            for a in sorted(self._state.assignments.values(), key=lambda a: str(a.id))
            if a.attempt_id == attempt_id
        )

    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def _check_refs(self, assignment: Assignment) -> None:
        att = self._state.attempts.get(assignment.attempt_id)
        if (
            att is None
            or att.run_id != assignment.run_id
            or att.task_id != assignment.task_id
            or att.workspace_id != assignment.workspace_id
        ):
            raise invalid_ref("fk_assignments__attempts", attempt_id=str(assignment.attempt_id))
        if assignment.reap_stage_record_id is not None:
            stg = self._state.stages.get(assignment.reap_stage_record_id)
            if stg is None or stg.attempt_id != assignment.attempt_id:
                raise invalid_ref(
                    "fk_assignments__reap_stage", stage_record_id=str(assignment.reap_stage_record_id)
                )
        if assignment.reap_step_id is not None:
            stp = self._state.steps.get(assignment.reap_step_id)
            if stp is None or stp.attempt_id != assignment.attempt_id:
                raise invalid_ref("fk_assignments__reap_step", step_id=str(assignment.reap_step_id))
        if assignment.reconcile_effect_id is not None:
            eff = self._state.effects.get(assignment.reconcile_effect_id)
            if (
                eff is None
                or eff.run_id != assignment.run_id
                or eff.task_id != assignment.task_id
                or eff.attempt_id != assignment.attempt_id
            ):
                raise invalid_ref(
                    "fk_assignments__reconcile_effect",
                    reconcile_effect_id=str(assignment.reconcile_effect_id),
                )

    def _check_live_uniqueness(self, assignment: Assignment) -> None:
        if assignment.state not in _LIVE_ASGN:
            return
        for other in self._state.assignments.values():
            if other.id == assignment.id or other.state not in _LIVE_ASGN:
                continue
            if other.attempt_id == assignment.attempt_id:
                raise already_exists("uq_assignments__attempt_id_live", attempt_id=str(assignment.attempt_id))
            if (
                assignment.reconcile_effect_id is not None
                and other.reconcile_effect_id == assignment.reconcile_effect_id
            ):
                raise already_exists(
                    "uq_assignments__reconcile_effect_live",
                    reconcile_effect_id=str(assignment.reconcile_effect_id),
                )

    def add(self, assignment: Assignment) -> None:
        self._backend.core.require_writable()
        if assignment.id in self._state.assignments:
            raise already_exists("pk_assignments", assignment_id=str(assignment.id))
        self._check_refs(assignment)
        self._check_live_uniqueness(assignment)
        self._state.assignments[assignment.id] = clone_value(assignment)

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
        self._backend.core.require_writable()
        clock = self._backend.core.clock.clock
        eff_now = now if clock is None else min(now, clock.now())  # LEAST(now, clock_timestamp()) in PG
        candidates = sorted(
            (
                a
                for a in self._state.assignments.values()
                if a.state is AssignmentState.AVAILABLE
                and a.workspace_id in workspace_ids
                and a.run_id in self._state.runs
                and a.available_at <= eff_now
            ),
            key=lambda a: (
                self._state.runs[a.run_id].started_at or self._state.runs[a.run_id].created_at,
                a.priority,
                a.available_at,
                str(a.id),
            ),
        )
        for cand in candidates:
            run = self._state.runs.get(cand.run_id)
            if run is None:
                continue
            if cand.reconcile_effect_id is None and (
                run.project_id in blocked_project_ids
                or run.status not in _CLAIMABLE_RUN_STATUSES
                or run.queued
            ):
                continue
            if not worker_matches(cand.requirements, worker):
                continue
            if cand.reap_stage_record_id is not None:
                stg = self._state.stages.get(cand.reap_stage_record_id)
                if stg is None or not reap_barrier_satisfied(stg, cand.reap_step_id, worker):
                    continue
            if admit is not None and not admit(clone_value(cand)):
                continue
            eff_now = self._backend.core.clock.now()
            leased_asgn, lease = issue_lease(
                cand,
                worker_id=worker.worker_id,
                now=eff_now,
                ttl=ttl,
                offered_runtimes=worker.offered_runtimes,
            )
            leased_asgn = replace(leased_asgn, row_version=cand.row_version + 1)
            self._state.assignments[cand.id] = clone_value(leased_asgn)
            self._state.leases[cand.id] = clone_value(lease)
            return clone_value(leased_asgn), clone_value(lease)
        return None

    def get(self, assignment_id: AssignmentId, *, for_update: bool = False) -> Assignment:
        del for_update
        found = self._state.assignments.get(assignment_id)
        if found is None:
            raise not_found("assignment", assignment_id)
        return clone_value(found)

    def lease(self, assignment_id: AssignmentId, *, for_update: bool = False) -> Lease | None:
        del for_update
        found = self._state.leases.get(assignment_id)
        return None if found is None else clone_value(found)

    def renew(
        self, lease: Lease, *, expires_at: datetime, heartbeat_at: datetime, identity: ProcessIdentity | None
    ) -> None:
        self._backend.core.require_writable()
        asgn = self._state.assignments.get(lease.assignment_id)
        cur = self._state.leases.get(lease.assignment_id)
        if (
            asgn is None
            or asgn.state is not AssignmentState.LEASED
            or cur is None
            or cur.worker_id != lease.worker_id
            or cur.fencing_token != lease.fencing_token
            or cur.expires_at <= heartbeat_at
        ):
            raise Conflict(
                ErrorCode.LEASE_LOST,
                "cannot renew missing, stale, or expired lease",
                details={"assignment_id": str(lease.assignment_id), "fencing_token": lease.fencing_token},
            )
        updated = Lease(
            assignment_id=cur.assignment_id,
            worker_id=cur.worker_id,
            fencing_token=cur.fencing_token,
            expires_at=expires_at,
            last_heartbeat_at=heartbeat_at,
            process_identity=identity if identity is not None else cur.process_identity,
            offered_runtimes=cur.offered_runtimes,
        )
        self._state.leases[cur.assignment_id] = clone_value(updated)

    def stale_available(self, older_than: datetime, *, limit: int) -> tuple[Assignment, ...]:
        rows = sorted(
            (
                a
                for a in self._state.assignments.values()
                if a.state is AssignmentState.AVAILABLE and a.available_at <= older_than
            ),
            key=lambda a: (a.available_at, str(a.id)),
        )
        return tuple(clone_value(a) for a in rows[: max(0, limit)])

    def save(self, assignment: Assignment, *, expected_version: int) -> None:
        self._backend.core.require_writable()
        cur = self._state.assignments.get(assignment.id)
        if cur is None:
            raise not_found("assignment", assignment.id)
        for fname in _ASGN_OWNED:
            if getattr(assignment, fname) != getattr(cur, fname):
                raise field_owned("assignment", fname)
        if cur.row_version != expected_version:
            raise version_conflict("assignment", assignment.id, expected_version, cur.row_version)
        self._check_refs(assignment)
        self._check_live_uniqueness(assignment)
        self._state.assignments[assignment.id] = clone_value(
            replace(assignment, row_version=expected_version + 1)
        )

    def drop_lease(self, assignment_id: AssignmentId) -> None:
        self._backend.core.require_writable()
        self._state.leases.pop(assignment_id, None)

    def expired(self, now: datetime, *, limit: int) -> tuple[tuple[Assignment, Lease], ...]:
        self._backend.core.require_writable()  # the sweep claims what it returns, as the row locks do in PG
        clock = self._backend.core.clock.clock
        eff_now = now if clock is None else min(now, clock.now())  # LEAST(now, clock_timestamp()) in PG
        return self._expired_leases(eff_now, limit=limit)

    def _expired_leases(self, now: datetime, *, limit: int) -> tuple[tuple[Assignment, Lease], ...]:
        if limit <= 0:
            return ()
        pairs: list[tuple[Assignment, Lease]] = []
        for lse in sorted(self._state.leases.values(), key=lambda x: (x.expires_at, str(x.assignment_id))):
            if lse.expires_at <= now:
                asgn = self._state.assignments.get(lse.assignment_id)
                if asgn is not None and asgn.state is AssignmentState.LEASED:
                    pairs.append((clone_value(asgn), clone_value(lse)))
                    if len(pairs) >= limit:
                        break
        return tuple(pairs)


class MemoryEnvironmentRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def upsert(self, env: ExecutionEnvironment) -> None:
        self._backend.core.require_writable()
        if env.attempt_id not in self._state.attempts:
            raise invalid_ref("fk_execution_environments__attempts", attempt_id=str(env.attempt_id))
        if (env.state in {EnvironmentState.DISCARDED, EnvironmentState.REMOVED}) != (
            env.discarded_at is not None
        ):
            raise schema_invalid("discarded_at is set iff state is discarded or removed")
        for other in self._state.environments.values():
            if other.attempt_id == env.attempt_id and other.id != env.id:
                raise already_exists("uq_execution_environments__attempt_id", attempt_id=str(env.attempt_id))
        self._state.environments[env.id] = clone_value(env)

    def for_attempt(self, attempt_id: AttemptId) -> ExecutionEnvironment | None:
        for env in self._state.environments.values():
            if env.attempt_id == attempt_id:
                return clone_value(env)
        return None

    def removable(
        self, host_id: HostId, retain: RetainPolicy, now: datetime, *, limit: int
    ) -> tuple[ExecutionEnvironment, ...]:
        ttl_raw = retain.get("retain_seconds", 0)
        ttl_sec = int(ttl_raw) if isinstance(ttl_raw, int | float) and not isinstance(ttl_raw, bool) else 0
        cutoff = now - timedelta(seconds=max(0, ttl_sec))
        rows = sorted(
            (
                e
                for e in self._state.environments.values()
                if e.host_id == host_id
                and e.state is EnvironmentState.DISCARDED
                and (e.discarded_at or e.created_at) <= cutoff
            ),
            key=lambda e: (e.discarded_at or e.created_at, str(e.id)),
        )
        return tuple(clone_value(e) for e in rows[: max(0, limit)])

    def mark_removed(self, environment_ids: Sequence[EnvironmentId], host_id: HostId, at: datetime) -> int:
        self._backend.core.require_writable()
        count = 0
        for eid in environment_ids:
            env = self._state.environments.get(eid)
            if env is not None and env.host_id == host_id and env.state is not EnvironmentState.REMOVED:
                self._state.environments[eid] = clone_value(
                    replace(
                        env,
                        state=EnvironmentState.REMOVED,
                        discarded_at=env.discarded_at or at,
                        removed_at=at,
                    )
                )
                count += 1
        return count

    def busy_existing_checkout_repos(
        self, project_id: ProjectId, *, exclude_attempt_id: AttemptId | None = None
    ) -> frozenset[RepositoryId]:
        run_ids = {r.id for r in self._state.runs.values() if r.project_id == project_id}
        busy: set[RepositoryId] = set()
        for env in self._state.environments.values():
            if env.attempt_id == exclude_attempt_id:
                continue
            if env.kind is not EnvironmentKind.EXISTING_CHECKOUT:
                continue
            if env.state not in {EnvironmentState.PREPARING, EnvironmentState.READY}:
                continue
            att = self._state.attempts.get(env.attempt_id)
            if att is not None and att.run_id in run_ids:
                for entry in env.baseline:
                    busy.add(entry.repository_id)
        return frozenset(busy)


class MemoryOutputRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def add(self, output: Output) -> None:
        self._backend.core.require_writable()
        if output.id in self._state.outputs:
            raise already_exists("pk_attempt_outputs", output_id=str(output.id))
        att = self._state.attempts.get(output.attempt_id)
        if att is None or att.run_id != output.run_id or att.task_id != output.task_id:
            raise invalid_ref("fk_attempt_outputs__attempts", attempt_id=str(output.attempt_id))
        if output.produced_by_step_id is not None:
            stp = self._state.steps.get(output.produced_by_step_id)
            if stp is None or stp.attempt_id != output.attempt_id:
                raise invalid_ref(
                    "fk_attempt_outputs__attempt_steps", step_id=str(output.produced_by_step_id)
                )
        if any(
            o.attempt_id == output.attempt_id and o.seq == output.seq for o in self._state.outputs.values()
        ):
            raise already_exists("uq_attempt_outputs__attempt_id_seq", seq=output.seq)
        self._state.outputs[output.id] = clone_value(output)

    def get(self, output_id: OutputId) -> Output:
        found = self._state.outputs.get(output_id)
        if found is None:
            raise not_found("output", output_id)
        return clone_value(found)

    def latest(self, attempt_id: AttemptId) -> Output | None:
        matches = [o for o in self._state.outputs.values() if o.attempt_id == attempt_id]
        return None if not matches else clone_value(max(matches, key=lambda o: o.seq))
