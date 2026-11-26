"""Memory repositories for attempts, stages, steps, and step notes (DDL ``0014``, ``0026-0027``)."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Final
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.execution.assignments import MemoryAssignmentRepository
from skm.adapters.memory.execution.misc_repos import MemoryRecoveryRepository
from skm.adapters.memory.execution.state import (
    clone_value,
    execution_state,
    validate_continuation_payload,
    validate_step_payloads,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.modules.execution.domain.assignment import AssignmentState, WorkerOffer
from skm.modules.execution.domain.health import reap_proven
from skm.modules.execution.domain.reaping import (
    reap_receipt,
    timeout_cancel_outcome,
    timeout_cancel_requested,
)
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES, StageRecord
from skm.modules.execution.domain.step import AttemptStep, RoleId, StepState
from skm.modules.execution.domain.stored_payloads import (
    already_exists,
    field_owned,
    invalid_ref,
    not_found,
    validate_step_note,
    version_conflict,
)
from skm.modules.execution.domain.workflow.history import StageEntry, StageHistory

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from skm.kernel.ids import AttemptId, PrincipalId, ProjectId, RunId, TaskId
    from skm.kernel.json_types import JsonObject
    from skm.modules.execution.domain.attempt import Attempt
    from skm.modules.execution.domain.ids import AssignmentId, StageRecordId, StepId
    from skm.modules.execution.domain.lease import ProcessIdentity
    from skm.modules.execution.domain.live_control import IncidentGate, ToolCallObservation
    from skm.modules.execution.domain.step_note import StepNote
    from skm.modules.runtimes.public import UsageReport

__all__ = [
    "MemoryAttemptRepository",
    "MemoryStageRepository",
    "MemoryStepRepository",
]

_ATTEMPT_OWNED: Final = ("run_id", "task_id", "workspace_id", "attempt_no", "started_at")
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
)
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
    "session_fingerprint_digest",
    "started_at",
)


class MemoryAttemptRepository:
    def version(self, attempt_id: AttemptId) -> int:
        self.get(attempt_id, for_update=True)
        return self._state.attempt_versions.get(attempt_id, 1)

    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def _check_refs(self, attempt: Attempt) -> None:
        task = self._state.tasks.get(attempt.task_id)
        if task is None or task.run_id != attempt.run_id or task.workspace_id != attempt.workspace_id:
            raise invalid_ref("fk_attempts__run_tasks", task_id=str(attempt.task_id))
        if attempt.environment_id is not None:
            env = self._state.environments.get(attempt.environment_id)
            if env is None or env.attempt_id != attempt.id:
                raise invalid_ref(
                    "fk_attempts__execution_environments", environment_id=str(attempt.environment_id)
                )
        if attempt.current_output_id is not None:
            out = self._state.outputs.get(attempt.current_output_id)
            if out is None or out.attempt_id != attempt.id:
                raise invalid_ref("fk_attempts__current_output", output_id=str(attempt.current_output_id))

    def add(self, attempt: Attempt) -> None:
        self._backend.core.require_writable()
        if attempt.id in self._state.attempts:
            raise already_exists("pk_attempts", attempt_id=str(attempt.id))
        if any(
            a.task_id == attempt.task_id and a.attempt_no == attempt.attempt_no
            for a in self._state.attempts.values()
        ):
            raise already_exists("uq_attempts__task_id_attempt_no", attempt_no=attempt.attempt_no)
        self._check_refs(attempt)
        validate_continuation_payload(attempt, None)
        self._state.attempts[attempt.id] = clone_value(attempt)
        self._state.attempt_versions[attempt.id] = 1

    def get(self, attempt_id: AttemptId, *, for_update: bool = False) -> Attempt:
        del for_update
        found = self._state.attempts.get(attempt_id)
        if found is None:
            raise not_found("attempt", attempt_id)
        return clone_value(found)

    def save(self, attempt: Attempt, *, expected_version: int) -> None:
        self._backend.core.require_writable()
        cur = self._state.attempts.get(attempt.id)
        if cur is None:
            raise not_found("attempt", attempt.id)
        for fname in _ATTEMPT_OWNED:
            if getattr(attempt, fname) != getattr(cur, fname):
                raise field_owned("attempt", fname)
        cur_ver = self._state.attempt_versions.get(attempt.id, 1)
        if cur_ver != expected_version:
            raise version_conflict("attempt", attempt.id, expected_version, cur_ver)
        self._check_refs(attempt)
        validate_continuation_payload(attempt, cur)
        self._state.attempts[attempt.id] = clone_value(attempt)
        self._state.attempt_versions[attempt.id] = expected_version + 1

    def list_for_task(self, task_id: TaskId) -> tuple[Attempt, ...]:
        rows = sorted(
            (a for a in self._state.attempts.values() if a.task_id == task_id),
            key=lambda a: a.attempt_no,
        )
        return tuple(clone_value(a) for a in rows)

    def list_for_run(self, run_id: RunId) -> tuple[Attempt, ...]:
        rows = sorted(
            (attempt for attempt in self._state.attempts.values() if attempt.run_id == run_id),
            key=lambda attempt: (attempt.task_id, attempt.attempt_no),
        )
        return tuple(clone_value(attempt) for attempt in rows)

    def next_attempt_no(self, task_id: TaskId) -> int:
        return (
            max((a.attempt_no for a in self._state.attempts.values() if a.task_id == task_id), default=0) + 1
        )


class MemoryStageRepository:
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
        assignments = MemoryAssignmentRepository(self._backend)
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
            MemoryRecoveryRepository(self._backend).add(reap_receipt(receipt_id, stage, now))
        return True

    def reap_confirmed(self, stage_id: StageRecordId) -> bool:
        return any(
            r.stage_record_id == stage_id and r.outcome == "not_needed" and "OS_STOP_PROVEN" in r.reason_codes
            for r in self._state.recoveries.values()
        )

    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def _check_refs(self, record: StageRecord) -> None:
        att = self._state.attempts.get(record.attempt_id)
        if att is None or att.run_id != record.run_id or att.task_id != record.task_id:
            raise invalid_ref("fk_attempt_stages__attempts", attempt_id=str(record.attempt_id))
        if record.retry_of_id is not None:
            prev = self._state.stages.get(record.retry_of_id)
            if prev is None or prev.attempt_id != record.attempt_id:
                raise invalid_ref("fk_attempt_stages__retry_of", retry_of_id=str(record.retry_of_id))
        if record.reused_from_step_id is not None and record.reused_from_step_id not in self._state.steps:
            raise invalid_ref("fk_attempt_stages__reused_from_step", step_id=str(record.reused_from_step_id))

    def add(self, record: StageRecord) -> None:
        self._backend.core.require_writable()
        if record.id in self._state.stages:
            raise already_exists("pk_attempt_stages", stage_record_id=str(record.id))
        if any(
            s.attempt_id == record.attempt_id and s.seq == record.seq for s in self._state.stages.values()
        ):
            raise already_exists("uq_attempt_stages__attempt_id_seq", seq=record.seq)
        if record.state in ACTIVE_STAGE_STATES and any(
            s.attempt_id == record.attempt_id and s.state in ACTIVE_STAGE_STATES
            for s in self._state.stages.values()
        ):
            raise already_exists("uq_attempt_stages__attempt_id_active", attempt_id=str(record.attempt_id))
        self._check_refs(record)
        self._state.stages[record.id] = clone_value(record)

    def find(
        self, attempt_id: AttemptId, stage_id: str, round_no: int, input_digest: str
    ) -> StageRecord | None:
        matches = [
            s
            for s in self._state.stages.values()
            if s.attempt_id == attempt_id
            and s.stage_id == stage_id
            and s.round_no == round_no
            and s.input_digest == input_digest
        ]
        if not matches:
            return None
        return clone_value(max(matches, key=lambda s: s.seq))

    def history(self, attempt_id: AttemptId) -> StageHistory:
        stages = sorted(
            (s for s in self._state.stages.values() if s.attempt_id == attempt_id),
            key=lambda s: s.seq,
        )
        entries = tuple(
            StageEntry(
                record=clone_value(stg),
                steps=tuple(
                    clone_value(st)
                    for st in sorted(
                        (x for x in self._state.steps.values() if x.stage_record_id == stg.id),
                        key=lambda x: x.seq,
                    )
                ),
            )
            for stg in stages
        )
        return StageHistory(entries=entries)

    def get(self, stage_record_id: StageRecordId, *, for_update: bool = False) -> StageRecord:
        del for_update
        found = self._state.stages.get(stage_record_id)
        if found is None:
            raise not_found("stage_record", stage_record_id)
        return clone_value(found)

    def save(self, record: StageRecord) -> None:
        self._backend.core.require_writable()
        cur = self._state.stages.get(record.id)
        if cur is None:
            raise not_found("stage_record", record.id)
        for fname in _STAGE_OWNED:
            if getattr(record, fname) != getattr(cur, fname):
                raise field_owned("stage_record", fname)
        if record.state in ACTIVE_STAGE_STATES and any(
            s.id != record.id and s.attempt_id == record.attempt_id and s.state in ACTIVE_STAGE_STATES
            for s in self._state.stages.values()
        ):
            raise already_exists("uq_attempt_stages__attempt_id_active", attempt_id=str(record.attempt_id))
        self._check_refs(record)
        self._state.stages[record.id] = clone_value(record)

    def started_without_result(self, attempt_id: AttemptId) -> StageRecord | None:
        for s in sorted(
            (x for x in self._state.stages.values() if x.attempt_id == attempt_id),
            key=lambda x: x.seq,
            reverse=True,
        ):
            if s.state in ACTIVE_STAGE_STATES:
                return clone_value(s)
        return None


class MemoryStepRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def _check_refs(self, step: AttemptStep) -> None:
        stg = self._state.stages.get(step.stage_record_id)
        if stg is None or stg.attempt_id != step.attempt_id:
            raise invalid_ref("fk_attempt_steps__attempt_stages", stage_record_id=str(step.stage_record_id))
        if step.parent_step_id is not None:
            par = self._state.steps.get(step.parent_step_id)
            if par is None or par.attempt_id != step.attempt_id:
                raise invalid_ref("fk_attempt_steps__parent", parent_step_id=str(step.parent_step_id))

    def add(self, step: AttemptStep) -> None:
        self._backend.core.require_writable()
        if step.id in self._state.steps:
            raise already_exists("pk_attempt_steps", step_id=str(step.id))
        if any(s.attempt_id == step.attempt_id and s.seq == step.seq for s in self._state.steps.values()):
            raise already_exists("uq_attempt_steps__attempt_id_seq", seq=step.seq)
        self._check_refs(step)
        validate_step_payloads(step, None)
        self._state.steps[step.id] = clone_value(step)

    def save(self, step: AttemptStep) -> None:
        self._backend.core.require_writable()
        cur = self._state.steps.get(step.id)
        if cur is None:
            raise not_found("attempt_step", step.id)
        for fname in _STEP_OWNED:
            if getattr(step, fname) != getattr(cur, fname):
                raise field_owned("attempt_step", fname)
        self._check_refs(step)
        validate_step_payloads(step, cur)
        self._state.steps[step.id] = clone_value(step)

    def get(self, step_id: StepId) -> AttemptStep:
        found = self._state.steps.get(step_id)
        if found is None:
            raise not_found("attempt_step", step_id)
        return clone_value(found)

    def for_stage(self, stage_record_id: StageRecordId) -> tuple[AttemptStep, ...]:
        rows = sorted(
            (s for s in self._state.steps.values() if s.stage_record_id == stage_record_id),
            key=lambda s: s.seq,
        )
        return tuple(clone_value(s) for s in rows)

    def last_for_role(self, attempt_id: AttemptId, role: RoleId) -> AttemptStep | None:
        matches = [s for s in self._state.steps.values() if s.attempt_id == attempt_id and s.role is role]
        return None if not matches else clone_value(max(matches, key=lambda s: s.seq))

    def first_writing(self, attempt_id: AttemptId) -> AttemptStep | None:
        matches = [
            s for s in self._state.steps.values() if s.attempt_id == attempt_id and s.role is RoleId.EXECUTOR
        ]
        if not matches:
            return None
        first = min(matches, key=lambda s: (self._state.stages[s.stage_record_id].seq, s.seq))
        return clone_value(first)

    def touch_progress(
        self,
        step_id: StepId,
        at: datetime,
        *,
        usage_so_far: UsageReport | None,
        identity: ProcessIdentity | None,
    ) -> None:
        self._backend.core.require_writable()
        cur = self._state.steps.get(step_id)
        if cur is None:
            raise not_found("attempt_step", step_id)
        updated = replace(
            cur,
            last_progress_at=at,
            usage_so_far=usage_so_far if usage_so_far is not None else cur.usage_so_far,
            process_identity=identity if identity is not None else cur.process_identity,
        )
        self._state.steps[step_id] = clone_value(updated)

    def find_reusable_scout(self, project_id: ProjectId, reuse_key: str) -> AttemptStep | None:
        run_ids = {r.id for r in self._state.runs.values() if r.project_id == project_id}
        matches = [
            s
            for s in self._state.steps.values()
            if s.role is RoleId.SCOUT
            and s.state is StepState.SUCCEEDED
            and s.reuse_key == reuse_key
            and (stg := self._state.stages.get(s.stage_record_id)) is not None
            and stg.run_id in run_ids
        ]
        if not matches:
            return None
        best = max(matches, key=lambda s: (s.finished_at or s.started_at, str(s.id)))
        return clone_value(best)

    def add_note(
        self,
        note: StepNote,
        *,
        assignment_id: AssignmentId,
        fencing_token: int,
        created_by: PrincipalId,
    ) -> None:
        del created_by
        self._backend.core.require_writable()
        if note.id in self._state.step_notes:
            raise already_exists("pk_step_notes", id=str(note.id))
        step = self._state.steps.get(note.step_id)
        if step is None:
            raise not_found("attempt_step", note.step_id)
        validate_step_note(note)
        asgn = self._state.assignments.get(assignment_id)
        lease = self._state.leases.get(assignment_id)
        now = (
            self._backend.core.clock.clock.now()
            if self._backend.core.clock.clock is not None
            else note.recorded_at
        )
        if (
            asgn is None
            or asgn.attempt_id != step.attempt_id
            or asgn.state is not AssignmentState.LEASED
            or lease is None
            or lease.fencing_token != fencing_token
            or lease.expires_at <= now
        ):
            raise Conflict(
                ErrorCode.LEASE_LOST,
                "step note requires a live matching lease",
                details={"assignment_id": str(assignment_id), "fencing_token": fencing_token},
            )
        self._state.step_notes[note.id] = clone_value(note)

    def add_tool_calls(self, calls: Sequence[ToolCallObservation]) -> int:
        self._backend.core.require_writable()
        rows = self._state.step_tool_calls
        before = len(rows)
        for entry in calls:
            self.get(entry.step_id)
            rows.setdefault((entry.step_id, entry.call.call_id), entry)
        return len(rows) - before

    def tool_calls(self, step_id: StepId, *, after: str, limit: int) -> tuple[ToolCallObservation, ...]:
        return tuple(
            sorted(
                (
                    entry
                    for entry in self._state.step_tool_calls.values()
                    if entry.step_id == step_id and entry.call.call_id > after
                ),
                key=lambda entry: entry.call.call_id,
            )[:limit]
        )

    def live_controls(self, task_id: TaskId) -> JsonObject:
        return clone_value(self._state.task_live_controls.get(task_id, {}))

    def save_live_controls(self, task_id: TaskId, pending: JsonObject) -> None:
        self._backend.core.require_writable()
        if task_id not in self._state.tasks:
            raise not_found("task", task_id)
        self._state.task_live_controls[task_id] = clone_value(pending)

    def incident_gates(self, task_id: TaskId) -> tuple[IncidentGate, ...]:
        gates = (g for g in self._state.incident_gates.values() if g.task_id == task_id)
        return tuple(clone_value(g) for g in sorted(gates, key=lambda g: (g.created_at, g.id)))

    def add_incident_gate(self, gate: IncidentGate) -> None:
        self._backend.core.require_writable()
        if gate.id in self._state.incident_gates:
            raise already_exists("pk_incident_gates", id=str(gate.id))
        self._state.incident_gates[gate.id] = clone_value(gate)

    def notes_for_step(self, step_id: StepId) -> tuple[StepNote, ...]:
        rows = sorted(
            (n for n in self._state.step_notes.values() if n.step_id == step_id),
            key=lambda n: (n.recorded_at, str(n.id)),
        )
        return tuple(clone_value(n) for n in rows)
