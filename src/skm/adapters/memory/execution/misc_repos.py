"""Memory repositories for integration slots, review requests, autopilot, recoveries, and bindings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, cast
from uuid import UUID, uuid4

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.execution.state import check_plan_revision_refs, clone_value, execution_state
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed
from skm.kernel.ids import WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.autopilot import AutopilotState, AutopilotStateKind
from skm.modules.execution.domain.contracts import EvidenceOwnerKind
from skm.modules.execution.domain.ids import IntegrationSlotId
from skm.modules.execution.domain.integration import IntegrationSlot
from skm.modules.execution.domain.stored_payloads import (
    already_exists,
    check_binding_role,
    field_owned,
    invalid_ref,
    invalid_transition,
    not_found,
    schema_invalid,
    version_conflict,
)

if TYPE_CHECKING:
    from skm.kernel.ids import AttemptId, FileVersionId, HostId, ProjectId, RepositoryId, RunId
    from skm.modules.artifacts.public import BindingRole
    from skm.modules.execution.domain.ids import ReviewRequestId, StageRecordId
    from skm.modules.execution.domain.recovery import RecoveryRecord
    from skm.modules.execution.domain.review_request import ReviewRequest

__all__ = [
    "MemoryAutopilotRepository",
    "MemoryEvidenceBindingRepository",
    "MemoryIntegrationSlotRepository",
    "MemoryRecoveryRepository",
    "MemoryReviewRequestRepository",
]

_ACTIVE_AUTOPILOT: Final = frozenset(
    {AutopilotStateKind.RUNNING, AutopilotStateKind.PAUSED, AutopilotStateKind.DRAINING}
)


def _repo_workspace_id(
    state: MemoryBackendState, repository_id: RepositoryId, fallback: WorkspaceId | None
) -> WorkspaceId:
    wstate = state.modules.get("workspace")
    if wstate is not None and isinstance(repos := getattr(wstate, "repositories", None), dict):
        rmap = cast("dict[object, Any]", repos)
        if rmap:
            repo_obj = rmap.get(repository_id)
            if repo_obj is None:
                raise invalid_ref("fk_integration_slots__repositories", repository_id=str(repository_id))
            return WorkspaceId(repo_obj.workspace_id)
    if fallback is not None:
        return fallback
    return WorkspaceId(UUID(int=0))


class MemoryIntegrationSlotRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def _eff_now(self, fallback: datetime) -> datetime:
        clk = self._backend.core.clock.clock
        return clk.now() if clk is not None else fallback

    def _find_by_target(self, repository_id: RepositoryId, branch: str) -> IntegrationSlot | None:
        for slot in self._state.integration_slots.values():
            if slot.repository_id == repository_id and slot.target_branch == branch:
                return slot
        return None

    def current(
        self, repository_id: RepositoryId, branch: str, *, for_update: bool = False
    ) -> IntegrationSlot | None:
        if for_update:
            self._backend.core.require_writable()
        return clone_value(self._find_by_target(repository_id, branch))

    def acquire(
        self,
        repository_id: RepositoryId,
        branch: str,
        attempt_id: AttemptId,
        host_id: HostId,
        now: datetime,
        expires_at: datetime,
    ) -> IntegrationSlot | None:
        self._backend.core.require_writable()
        if not 1 <= len(branch) <= 255:
            raise schema_invalid("target_branch must be 1..255 chars", field="target_branch")
        att = self._state.attempts.get(attempt_id)
        if att is None:
            raise invalid_ref("fk_integration_slots__attempts", attempt_id=str(attempt_id))
        ws_id = _repo_workspace_id(self._backend, repository_id, att.workspace_id)
        eff_now = self._eff_now(now)
        if expires_at <= eff_now:
            raise schema_invalid("expires_at must be strictly after current time", field="expires_at")
        pinned_run = self._state.run_integration_hosts.get((att.run_id, repository_id))
        if pinned_run is not None and pinned_run[0] != host_id:
            raise PreconditionFailed(
                ErrorCode.INTEGRATION_HOST_MISMATCH,
                "run integration host does not match writer host",
                details={"pinned_host_id": str(pinned_run[0]), "host_id": str(host_id)},
            )
        existing = self._find_by_target(repository_id, branch)
        if existing is None:
            created = IntegrationSlot(
                id=IntegrationSlotId(uuid4()),
                workspace_id=ws_id,
                repository_id=repository_id,
                target_branch=branch,
                holder_attempt_id=attempt_id,
                fencing_token=1,
                expires_at=expires_at,
                writer_host_id=host_id,
                row_version=1,
            )
            self._state.integration_slots[created.id] = clone_value(created)
            return clone_value(created)
        if existing.writer_host_id != host_id:
            raise PreconditionFailed(
                ErrorCode.INTEGRATION_HOST_MISMATCH,
                "integration slot is pinned to another writer host",
                details={"writer_host_id": str(existing.writer_host_id), "host_id": str(host_id)},
            )
        free_or_same = (
            existing.holder_attempt_id is None
            or existing.holder_attempt_id == attempt_id
            or (existing.expires_at is not None and existing.expires_at <= eff_now)
        )
        if not free_or_same:
            return None
        updated = replace(
            existing,
            holder_attempt_id=attempt_id,
            fencing_token=existing.fencing_token + 1,
            expires_at=expires_at,
            row_version=existing.row_version + 1,
        )
        self._state.integration_slots[updated.id] = clone_value(updated)
        return clone_value(updated)

    def pin_target_host(
        self, repository_id: RepositoryId, branch: str, host_id: HostId, at: datetime
    ) -> tuple[HostId, bool]:
        self._backend.core.require_writable()
        del at
        if not 1 <= len(branch) <= 255:
            raise schema_invalid("target_branch must be 1..255 chars", field="target_branch")
        existing = self._find_by_target(repository_id, branch)
        if existing is not None:
            return existing.writer_host_id, False
        ws_id = _repo_workspace_id(self._backend, repository_id, None)
        created = IntegrationSlot(
            id=IntegrationSlotId(uuid4()),
            workspace_id=ws_id,
            repository_id=repository_id,
            target_branch=branch,
            holder_attempt_id=None,
            fencing_token=0,
            expires_at=None,
            writer_host_id=host_id,
            row_version=1,
        )
        self._state.integration_slots[created.id] = clone_value(created)
        return host_id, True

    def target_hosts(
        self, targets: Sequence[tuple[RepositoryId, str]]
    ) -> Mapping[tuple[RepositoryId, str], HostId]:
        wanted = set(targets)
        return {
            (s.repository_id, s.target_branch): s.writer_host_id
            for s in self._state.integration_slots.values()
            if (s.repository_id, s.target_branch) in wanted
        }

    def extend(self, attempt_id: AttemptId, expires_at: datetime) -> int:
        self._backend.core.require_writable()
        clk = self._backend.core.clock.clock
        count = 0
        for sid, slot in list(self._state.integration_slots.items()):
            if slot.holder_attempt_id != attempt_id or slot.expires_at is None:
                continue
            if clk is not None and slot.expires_at <= clk.now():
                continue
            if expires_at <= slot.expires_at and clk is not None and expires_at <= clk.now():
                continue
            self._state.integration_slots[sid] = clone_value(
                replace(slot, expires_at=expires_at, row_version=slot.row_version + 1)
            )
            count += 1
        return count

    def release(self, slot_id: IntegrationSlotId, attempt_id: AttemptId, fencing_token: int) -> None:
        self._backend.core.require_writable()
        slot = self._state.integration_slots.get(slot_id)
        if slot is None:
            raise not_found("integration_slot", slot_id)
        if slot.holder_attempt_id != attempt_id or slot.fencing_token != fencing_token:
            raise Conflict(
                ErrorCode.LEASE_LOST,
                "integration slot holder or fencing token does not match",
                details={"slot_id": str(slot_id), "fencing_token": fencing_token},
            )
        self._state.integration_slots[slot_id] = clone_value(
            replace(slot, holder_attempt_id=None, expires_at=None, row_version=slot.row_version + 1)
        )

    def release_for_attempt(self, attempt_id: AttemptId) -> int:
        self._backend.core.require_writable()
        count = 0
        for sid, slot in list(self._state.integration_slots.items()):
            if slot.holder_attempt_id == attempt_id:
                self._state.integration_slots[sid] = clone_value(
                    replace(slot, holder_attempt_id=None, expires_at=None, row_version=slot.row_version + 1)
                )
                count += 1
        return count

    def pin_host(self, run_id: RunId, repository_id: RepositoryId, host_id: HostId, at: datetime) -> HostId:
        self._backend.core.require_writable()
        run = self._state.runs.get(run_id)
        if run is None:
            raise invalid_ref("fk_run_integration_hosts__runs", run_id=str(run_id))
        _repo_workspace_id(self._backend, repository_id, run.workspace_id)
        existing = self._state.run_integration_hosts.get((run_id, repository_id))
        if existing is not None:
            return existing[0]
        self._state.run_integration_hosts[(run_id, repository_id)] = (host_id, at)
        return host_id

    def hosts_for_run(self, run_id: RunId) -> Mapping[RepositoryId, HostId]:
        return {
            repo_id: host_id
            for (rid, repo_id), (host_id, _at) in self._state.run_integration_hosts.items()
            if rid == run_id
        }


class MemoryReviewRequestRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def add(self, request: ReviewRequest) -> None:
        self._backend.core.require_writable()
        if request.id in self._state.review_requests:
            raise already_exists("pk_review_requests", id=str(request.id))
        if any(r.revision_id == request.revision_id for r in self._state.review_requests.values()):
            raise already_exists("uq_review_requests__revision_id", revision_id=str(request.revision_id))
        if not 1 <= len(request.mount) <= 255 or not 1 <= len(request.profile_key) <= 120:
            raise schema_invalid("review_request mount/profile_key out of bounds")
        if len(request.reason) > 2000:
            raise schema_invalid("review_request reason exceeds 2000 chars", field="reason")
        check_plan_revision_refs(
            self._backend, request.workspace_id, request.project_id, request.plan_id, request.revision_id
        )
        self._state.review_requests[request.id] = clone_value(request)

    def get(self, request_id: ReviewRequestId) -> ReviewRequest:
        found = self._state.review_requests.get(request_id)
        if found is None:
            raise not_found("review_request", request_id)
        return clone_value(found)

    def select_run_id(self, selector: JsonObject) -> RunId:
        request_id = UUID(str(selector["request_id"])) if "request_id" in selector else None
        project_id = UUID(str(selector["project_id"])) if "project_id" in selector else None
        mount, tree_digest = selector.get("mount"), selector.get("tree_digest")
        candidates = [
            run
            for run in self._state.runs.values()
            if run.review_request_id is not None
            and (request := self._state.review_requests.get(run.review_request_id)) is not None
            and (
                request.id == request_id
                if request_id is not None
                else request.project_id == project_id and request.mount == mount
            )
        ]

        def order(run: Any) -> Any:
            outputs = [output for output in self._state.outputs.values() if output.run_id == run.id]
            latest = max(outputs, key=lambda o: (o.sealed_at, o.seq), default=None)
            review = max(
                (r for r in self._state.reviews.values() if r.run_id == run.id),
                key=lambda r: (r.round_no, str(r.id)),
                default=None,
            )
            if review is not None:
                latest = self._state.outputs.get(review.output_id)
            return (
                latest is not None and latest.manifest.tree_digest == tree_digest,
                run.created_at,
                str(run.id),
            )

        if not candidates:
            raise not_found("review_receipt", request_id or project_id)
        return max(candidates, key=order).id

    def for_run(self, run_id: RunId) -> ReviewRequest | None:
        run = self._state.runs.get(run_id)
        if run is None:
            raise not_found("run", run_id)
        if run.review_request_id is None:
            return None
        return self.get(run.review_request_id)


class MemoryAutopilotRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def get(self, project_id: ProjectId, *, for_update: bool = False) -> AutopilotState | None:
        del for_update
        found = self._state.autopilot_states.get(project_id)
        return None if found is None else clone_value(found)

    def save(self, state: AutopilotState, *, expected_version: int | None) -> None:
        self._backend.core.require_writable()
        if state.emergency and state.state is not AutopilotStateKind.STOPPED:
            raise schema_invalid("emergency autopilot state must be stopped", field="emergency")
        if (state.state is AutopilotStateKind.STOPPED) != (state.stop_code is not None):
            raise schema_invalid("stopped autopilot requires stop_code and vice versa", field="stop_code")
        if state.state in _ACTIVE_AUTOPILOT and state.session_started_at is None:
            raise schema_invalid("active autopilot requires session_started_at", field="session_started_at")
        if state.current_run_id is not None:
            run = self._state.runs.get(state.current_run_id)
            if run is None or run.project_id != state.project_id or run.workspace_id != state.workspace_id:
                raise invalid_ref("fk_autopilot_states__runs", current_run_id=str(state.current_run_id))
        cur = self._state.autopilot_states.get(state.project_id)
        if expected_version is None:
            if cur is not None:
                raise version_conflict("autopilot_state", state.project_id, None, cur.row_version)
            self._state.autopilot_states[state.project_id] = clone_value(replace(state, row_version=1))
            return
        if cur is None or cur.row_version != expected_version:
            raise version_conflict(
                "autopilot_state",
                state.project_id,
                expected_version,
                None if cur is None else cur.row_version,
            )
        if state.workspace_id != cur.workspace_id:
            raise field_owned("autopilot_state", "workspace_id")
        self._state.autopilot_states[state.project_id] = clone_value(
            replace(state, row_version=expected_version + 1)
        )

    def enabled_project_ids(self, *, limit: int) -> tuple[ProjectId, ...]:
        rows = sorted(
            (s for s in self._state.autopilot_states.values() if s.state in _ACTIVE_AUTOPILOT),
            key=lambda s: (s.updated_at, str(s.project_id)),
        )
        return tuple(s.project_id for s in rows[: max(0, limit)])

    def emergency_project_ids(self) -> frozenset[ProjectId]:
        return frozenset(s.project_id for s in self._state.autopilot_states.values() if s.emergency)


class MemoryRecoveryRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def _check_refs(self, record: RecoveryRecord) -> None:
        att = self._state.attempts.get(record.attempt_id)
        if att is None or att.run_id != record.run_id or att.task_id != record.task_id:
            raise invalid_ref("fk_run_recoveries__attempts", attempt_id=str(record.attempt_id))
        stg = self._state.stages.get(record.stage_record_id)
        if stg is None or stg.attempt_id != record.attempt_id:
            raise invalid_ref(
                "fk_run_recoveries__attempt_stages", stage_record_id=str(record.stage_record_id)
            )
        if record.step_id is not None:
            stp = self._state.steps.get(record.step_id)
            if stp is None or stp.attempt_id != record.attempt_id:
                raise invalid_ref("fk_run_recoveries__attempt_steps", step_id=str(record.step_id))

    def add(self, record: RecoveryRecord) -> None:
        self._backend.core.require_writable()
        if record.id in self._state.recoveries:
            raise already_exists("pk_run_recoveries", id=str(record.id))
        self._check_refs(record)
        if record.outcome is None and any(
            r.stage_record_id == record.stage_record_id and r.outcome is None
            for r in self._state.recoveries.values()
        ):
            raise already_exists(
                "uq_run_recoveries__stage_record_id_open", stage_record_id=str(record.stage_record_id)
            )
        self._state.recoveries[record.id] = clone_value(record)

    def save(self, record: RecoveryRecord) -> None:
        self._backend.core.require_writable()
        cur = self._state.recoveries.get(record.id)
        if cur is None:
            raise not_found("recovery", record.id)
        if cur.outcome is not None:
            raise invalid_transition("finished recovery records are immutable", recovery_id=str(record.id))
        for fname in ("run_id", "task_id", "attempt_id", "stage_record_id", "step_id", "trigger"):
            if getattr(record, fname) != getattr(cur, fname):
                raise field_owned("recovery", fname)
        self._check_refs(record)
        self._state.recoveries[record.id] = clone_value(record)

    def open_for_stage(self, stage_record_id: StageRecordId) -> RecoveryRecord | None:
        for rec in self._state.recoveries.values():
            if rec.stage_record_id == stage_record_id and rec.outcome is None:
                return clone_value(rec)
        return None

    def count_since(self, run_id: RunId, since: datetime, outcomes: frozenset[str]) -> int:
        return sum(
            1
            for r in self._state.recoveries.values()
            if r.run_id == run_id and r.at >= since and (not outcomes or (r.outcome in outcomes))
        )


class MemoryEvidenceBindingRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def _check_owner(self, owner_kind: EvidenceOwnerKind, owner_id: UUID) -> None:
        exists = (
            (owner_kind == "attempt" and owner_id in self._state.attempts)
            or (owner_kind == "output" and owner_id in self._state.outputs)
            or (owner_kind == "check_execution" and owner_id in self._state.checks)
            or (owner_kind == "review" and owner_id in self._state.reviews)
        )
        if not exists:
            raise invalid_ref(
                f"fk_{owner_kind}_evidence__owner", owner_kind=owner_kind, owner_id=str(owner_id)
            )

    def bind(
        self,
        owner_kind: EvidenceOwnerKind,
        owner_id: UUID,
        file_version_ids: Sequence[FileVersionId],
        role: BindingRole,
    ) -> None:
        self._backend.core.require_writable()
        check_binding_role(owner_kind, role.value)
        self._check_owner(owner_kind, owner_id)
        astate = self._backend.modules.get("artifacts")
        if astate is not None and isinstance(fvs := getattr(astate, "file_versions", None), dict) and fvs:
            for fvid in file_version_ids:
                if fvid not in fvs:
                    raise invalid_ref(f"fk_{owner_kind}_evidence__file_versions", file_version_id=str(fvid))
        bucket = self._state.evidence_bindings.setdefault((owner_kind, owner_id), [])
        existing = set(bucket)
        for fvid in file_version_ids:
            pair = (fvid, role)
            if pair not in existing:
                bucket.append(pair)
                existing.add(pair)

    def for_owner(
        self,
        owner_kind: EvidenceOwnerKind,
        owner_id: UUID,
    ) -> tuple[tuple[FileVersionId, BindingRole], ...]:
        rows = self._state.evidence_bindings.get((owner_kind, owner_id), ())
        return tuple(sorted(rows, key=lambda p: (str(p[0]), p[1].value)))
