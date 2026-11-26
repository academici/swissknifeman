"""Memory repositories for runs, bundles, readiness reports, and tasks (DDL ``0013``, ``0029``)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Final

from skm.adapters.memory.artifacts.state import artifacts_state
from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.execution.state import (
    check_plan_revision_refs,
    check_spec_entity_ref,
    clone_value,
    execution_state,
    schema_registry,
)
from skm.adapters.memory.workspace.state import workspace_state
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind
from skm.modules.execution.domain.health import active_stage_seconds
from skm.modules.execution.domain.run import TERMINAL_RUN_STATUSES, Run, RunKind
from skm.modules.execution.domain.stored_payloads import (
    already_exists,
    config_snapshot_document,
    field_owned,
    invalid_ref,
    not_found,
    schema_invalid,
    validate_readiness_report,
    version_conflict,
    work_policies_document,
)
from skm.modules.execution.domain.task import Task, TaskKind, TaskStatus
from skm.modules.execution.ports import ReconfigurationRecord

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from skm.kernel.ids import AttemptId, ProjectId, RevisionId, RunId, TaskId
    from skm.modules.execution.domain.blocking_reason import BlockingCode
    from skm.modules.execution.domain.execution_bundle import ExecutionBundle
    from skm.modules.execution.domain.ids import ReadinessReportId, StageRecordId
    from skm.modules.execution.domain.readiness import ReadinessReport, RevisionVisa
    from skm.modules.execution.domain.task_graph import TaskEdge

__all__ = [
    "MemoryBundleRepository",
    "MemoryReadinessRepository",
    "MemoryRunRepository",
    "MemoryTaskRepository",
]

_DIGEST_RE: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUN_OWNED: Final = (
    "workspace_id",
    "project_id",
    "kind",
    "plan_id",
    "revision_id",
    "revision_no",
    "inline_spec_file_version_id",
    "requested_by",
    "compiler_version",
    "workflow_resource_version_id",
    "created_at",
)
_TASK_OWNED: Final = (
    "run_id",
    "workspace_id",
    "kind",
    "spec_entity_id",
    "display_key",
    "position",
    "work_kind",
    "review_mode",
)


class MemoryRunRepository:
    def lock_revision_start(self, revision_id: RevisionId, *, audit: bool = False) -> None:  # noqa: ARG002
        # The memory UoW already holds the backend write lock until commit or rollback.
        self._backend.core.require_writable()

    def has_active_readiness_audit(self, revision_id: RevisionId) -> bool:
        return any(
            run.revision_id == revision_id
            and run.kind is RunKind.READINESS_AUDIT
            and run.status not in TERMINAL_RUN_STATUSES
            for run in self._state.runs.values()
        )

    def now(self) -> datetime:
        return self._backend.core.clock.now()

    def lock_active(self, run_ids: Sequence[RunId]) -> tuple[Run, ...]:
        return tuple(
            self.get(rid, for_update=True)
            for rid in sorted(set(run_ids), key=str)
            if self.get(rid).status not in TERMINAL_RUN_STATUSES
        )

    def project_has_slot(self, project_id: ProjectId, maximum: int) -> bool:
        return (
            sum(r.project_id == project_id and r.status.value == "running" for r in self._state.runs.values())
            < maximum
        )

    def active_seconds(
        self,
        run_id: RunId,
        now: datetime,
        *,
        task_id: TaskId | None = None,
        attempt_id: AttemptId | None = None,
        stage_id: StageRecordId | None = None,
    ) -> float:
        intervals = tuple(
            (s.started_at, s.finished_at)
            for s in self._state.stages.values()
            if s.run_id == run_id
            and (task_id is None or s.task_id == task_id)
            and (attempt_id is None or s.attempt_id == attempt_id)
            and (stage_id is None or s.id == stage_id)
        )
        transitions = tuple(
            (e.type.split(":")[-2], e.recorded_at)
            for e in self._backend.core.events
            if e.stream_kind == "run" and e.stream_id == run_id
        )
        if self.get(run_id).status.value == "paused" and not any(n == "run-paused" for n, _ in transitions):
            transitions += (("run-paused", self.get(run_id).created_at),)
        return active_stage_seconds(intervals, transitions, now)

    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def get(self, run_id: RunId, *, for_update: bool = False) -> Run:
        del for_update
        found = self._state.runs.get(run_id)
        if found is None:
            raise not_found("run", run_id)
        return clone_value(found)

    def add(self, run: Run) -> None:
        self._backend.core.require_writable()
        if run.id in self._state.runs:
            raise already_exists("pk_runs", run_id=str(run.id))
        parent_id = run.project_id if run.kind is RunKind.ADHOC else run.require_plan()
        scope = self._backend.core.scopes.get(ScopeId(run.id))
        if scope is None or (scope.kind, scope.workspace_id, scope.parent_id) != (
            ScopeKind.RUN,
            run.workspace_id,
            ScopeId(parent_id),
        ):
            raise schema_invalid("run scope must match the workspace and exact run parent")
        if run.kind is RunKind.ADHOC:
            project = workspace_state(self._backend).projects.get(run.project_id)
            if project is None or project.workspace_id != run.workspace_id:
                raise invalid_ref("fk_runs__projects", project_id=str(run.project_id))
            artifacts = artifacts_state(self._backend)
            version_id = run.inline_spec_file_version_id
            version = artifacts.versions.get(version_id) if version_id is not None else None
            file = artifacts.files.get(version.file_id) if version is not None else None
            if (
                version is None
                or version.workspace_id != run.workspace_id
                or file is None
                or (file.workspace_id, file.project_id) != (run.workspace_id, run.project_id)
            ):
                raise schema_invalid("inline spec must belong to the run project")
        else:
            check_plan_revision_refs(
                self._backend, run.workspace_id, run.project_id, run.require_plan(), run.require_revision()
            )
        for report_id, fk in (
            (run.readiness_report_id, "fk_runs__readiness_reports"),
            (run.audited_report_id, "fk_runs__audited_report"),
        ):
            if report_id is not None:
                rep = self._state.readiness_reports.get(report_id)
                if rep is None or (rep.workspace_id, rep.plan_id, rep.revision_id) != (
                    run.workspace_id,
                    run.plan_id,
                    run.revision_id,
                ):
                    raise invalid_ref(fk, report_id=str(report_id))
        if run.review_request_id is not None:
            req = self._state.review_requests.get(run.review_request_id)
            if req is None or (req.workspace_id, req.project_id) != (run.workspace_id, run.project_id):
                raise invalid_ref("fk_runs__review_requests", review_request_id=str(run.review_request_id))
            if any(r.review_request_id == run.review_request_id for r in self._state.runs.values()):
                raise already_exists(
                    "uq_runs__review_request_id", review_request_id=str(run.review_request_id)
                )
        if (run.kind is RunKind.REVIEW_REQUEST) != (run.review_request_id is not None):
            raise schema_invalid("review_request_id is set iff kind == review_request")
        if (run.kind is RunKind.READINESS_AUDIT) != (run.audited_report_id is not None):
            raise schema_invalid("audited_report_id is set iff kind == readiness_audit")
        self._state.runs[run.id] = clone_value(run)

    def save(self, run: Run, *, expected_version: int) -> None:
        self._backend.core.require_writable()
        cur = self._state.runs.get(run.id)
        if cur is None:
            raise not_found("run", run.id)
        for fname in _RUN_OWNED:
            if getattr(run, fname) != getattr(cur, fname):
                raise field_owned("run", fname)
        if cur.row_version != expected_version:
            raise version_conflict("run", run.id, expected_version, cur.row_version)
        self._state.runs[run.id] = clone_value(replace(run, row_version=expected_version + 1))

    def list_active_ids(self, *, limit: int) -> tuple[RunId, ...]:
        active = sorted(
            (r for r in self._state.runs.values() if r.status not in TERMINAL_RUN_STATUSES),
            key=lambda r: (r.created_at, str(r.id)),
        )
        return tuple(r.id for r in active[: max(0, limit)])


class MemoryBundleRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def add(self, bundle: ExecutionBundle) -> None:
        self._backend.core.require_writable()
        if bundle.run_id in self._state.bundles:
            raise already_exists("pk_execution_bundles", run_id=str(bundle.run_id))
        if bundle.run_id not in self._state.runs:
            raise invalid_ref("fk_execution_bundles__runs", run_id=str(bundle.run_id))
        config_snapshot_document(bundle)
        work_policies_document(bundle.work_policies)
        self._state.bundles[bundle.run_id] = clone_value(bundle)

    def get(self, run_id: RunId) -> ExecutionBundle:
        found = self._state.bundles.get(run_id)
        if found is None:
            raise not_found("execution_bundle", run_id)
        return clone_value(found)

    def add_reconfiguration(self, record: ReconfigurationRecord) -> None:
        self._backend.core.require_writable()
        if record.id in self._state.reconfigurations:
            raise already_exists("pk_run_reconfigurations", id=str(record.id))
        if record.run_id not in self._state.runs:
            raise invalid_ref("fk_run_reconfigurations__runs", run_id=str(record.run_id))
        if not record.changes or not 1 <= len(record.reason) <= 2000:
            raise schema_invalid("reconfiguration requires non-empty changes and reason 1..2000")
        self._state.reconfigurations[record.id] = clone_value(record)

    def reconfigurations(self, run_id: RunId) -> tuple[ReconfigurationRecord, ...]:
        rows = sorted(
            (r for r in self._state.reconfigurations.values() if r.run_id == run_id),
            key=lambda r: (r.changed_at, str(r.id)),
        )
        return tuple(clone_value(r) for r in rows)


class MemoryReadinessRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def add(self, report: ReadinessReport) -> None:
        self._backend.core.require_writable()
        if report.id in self._state.readiness_reports:
            raise already_exists("pk_readiness_reports", report_id=str(report.id))
        check_plan_revision_refs(
            self._backend, report.workspace_id, report.project_id, report.plan_id, report.revision_id
        )
        for dg in (report.revision_digest, report.inputs_digest, report.policy_digest):
            if not _DIGEST_RE.fullmatch(dg):
                raise schema_invalid("readiness digest must be sha256:<64 hex>")
        if report.validator_version < 1:
            raise schema_invalid("validator_version >= 1")
        if report.supersedes_report_id is not None:
            if report.supersedes_report_id == report.id or report.audit is None:
                raise schema_invalid("supersedes_report_id requires audit and another report")
            prev = self._state.readiness_reports.get(report.supersedes_report_id)
            if prev is None or (prev.workspace_id, prev.plan_id, prev.revision_id) != (
                report.workspace_id,
                report.plan_id,
                report.revision_id,
            ):
                raise invalid_ref(
                    "fk_readiness_reports__supersedes", report_id=str(report.supersedes_report_id)
                )
        validate_readiness_report(report, require_valid=schema_registry().require_valid)
        self._state.readiness_reports[report.id] = clone_value(report)

    def get(self, report_id: ReadinessReportId) -> ReadinessReport:
        found = self._state.readiness_reports.get(report_id)
        if found is None:
            raise not_found("readiness_report", report_id)
        return clone_value(found)

    def add_visa(self, visa: RevisionVisa) -> None:
        self._backend.core.require_writable()
        if visa.id in self._state.revision_visas:
            raise already_exists("pk_revision_visas", visa_id=str(visa.id))
        report = self._state.readiness_reports.get(visa.readiness_report_id)
        if report is None or (report.workspace_id, report.plan_id, report.revision_id) != (
            visa.workspace_id,
            visa.plan_id,
            visa.revision_id,
        ):
            raise invalid_ref("fk_revision_visas__readiness_report", visa_id=str(visa.id))
        if not 1 <= len(visa.reason) <= 2000 or not visa.reason.strip():
            raise schema_invalid("visa reason must contain 1 to 2000 characters")
        self._state.revision_visas[visa.id] = clone_value(visa)

    def get_visa(self, visa_id: UUID) -> RevisionVisa:
        found = self._state.revision_visas.get(visa_id)
        if found is None:
            raise not_found("revision_visa", visa_id)
        return clone_value(found)

    def latest_visa_for(self, revision_id: RevisionId) -> RevisionVisa | None:
        matches = (visa for visa in self._state.revision_visas.values() if visa.revision_id == revision_id)
        latest = max(matches, key=lambda visa: (visa.signed_at, visa.id), default=None)
        return None if latest is None else clone_value(latest)

    def latest_for(self, revision_id: RevisionId) -> ReadinessReport | None:
        matches = [r for r in self._state.readiness_reports.values() if r.revision_id == revision_id]
        if not matches:
            return None
        best = max(matches, key=lambda r: (r.created_at, str(r.id)))
        return clone_value(best)


class MemoryTaskRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def _check_task(self, task: Task) -> None:
        run = self._state.runs.get(task.run_id)
        if run is None or run.workspace_id != task.workspace_id:
            raise invalid_ref("fk_run_tasks__runs", run_id=str(task.run_id))
        if (task.kind is TaskKind.ADHOC) != (run.kind is RunKind.ADHOC):
            raise schema_invalid("adhoc tasks require an adhoc run and vice versa")
        spec_backed = task.kind in {TaskKind.UNIT, TaskKind.ITEM, TaskKind.ITEM_GATE, TaskKind.PHASE_GATE}
        if spec_backed != (task.spec_entity_id is not None):
            raise schema_invalid("spec_entity_id required iff task is spec-backed")
        if task.spec_entity_id is not None:
            check_spec_entity_ref(
                self._backend,
                task.workspace_id,
                run.require_plan(),
                run.require_revision(),
                task.spec_entity_id,
            )
        if task.current_attempt_id is not None:
            att = self._state.attempts.get(task.current_attempt_id)
            if att is None or att.task_id != task.id:
                raise invalid_ref("fk_run_tasks__current_attempt", attempt_id=str(task.current_attempt_id))
        if task.accepted_attempt_id is not None:
            att = self._state.attempts.get(task.accepted_attempt_id)
            if att is None or att.task_id != task.id:
                raise invalid_ref("fk_run_tasks__accepted_attempt", attempt_id=str(task.accepted_attempt_id))
        if task.accepted_output_id is not None:
            if task.accepted_attempt_id is None:
                raise schema_invalid("accepted_output_id requires accepted_attempt_id")
            out = self._state.outputs.get(task.accepted_output_id)
            if out is None or out.attempt_id != task.accepted_attempt_id:
                raise invalid_ref("fk_run_tasks__accepted_output", output_id=str(task.accepted_output_id))

    def add_many(self, tasks: Sequence[Task], edges: Sequence[TaskEdge]) -> None:
        self._backend.core.require_writable()
        staged_tasks: dict[TaskId, Task] = {}
        seen_keys: set[tuple[RunId, str]] = {(t.run_id, t.display_key) for t in self._state.tasks.values()}
        for task in tasks:
            if task.id in self._state.tasks or task.id in staged_tasks:
                raise already_exists("pk_run_tasks", task_id=str(task.id))
            if (task.run_id, task.display_key) in seen_keys:
                raise already_exists("uq_run_tasks__run_id_display_key", display_key=task.display_key)
            self._check_task(task)
            seen_keys.add((task.run_id, task.display_key))
            staged_tasks[task.id] = clone_value(task)

        all_tasks = {**self._state.tasks, **staged_tasks}
        staged_edges: dict[tuple[RunId, TaskId, TaskId], TaskEdge] = {}
        for edge in edges:
            key = (edge.run_id, edge.dependent_task_id, edge.prerequisite_task_id)
            if edge.dependent_task_id == edge.prerequisite_task_id:
                raise schema_invalid("task edge cannot reference itself")
            if key in self._state.task_edges or key in staged_edges:
                raise already_exists("pk_run_task_edges", dependent=str(edge.dependent_task_id))
            dep = all_tasks.get(edge.dependent_task_id)
            if dep is None or dep.run_id != edge.run_id:
                raise invalid_ref("fk_run_task_edges__dependent", run_id=str(edge.run_id))
            pre = all_tasks.get(edge.prerequisite_task_id)
            if pre is None or pre.run_id != edge.run_id:
                raise invalid_ref("fk_run_task_edges__prerequisite", run_id=str(edge.run_id))
            staged_edges[key] = clone_value(edge)

        self._state.tasks.update(staged_tasks)
        self._state.task_edges.update(staged_edges)

    def add_synthetic(self, task: Task, edges: Sequence[TaskEdge]) -> None:
        self.add_many((task,), edges)

    def get(self, task_id: TaskId, *, for_update: bool = False) -> Task:
        del for_update
        found = self._state.tasks.get(task_id)
        if found is None:
            raise not_found("task", task_id)
        return clone_value(found)

    def list_for_run(self, run_id: RunId, *, blocking_code: BlockingCode | None = None) -> tuple[Task, ...]:
        rows = sorted(
            (
                task
                for task in self._state.tasks.values()
                if task.run_id == run_id
                and (
                    blocking_code is None
                    or (task.blocking_reason is not None and task.blocking_reason.code is blocking_code)
                )
            ),
            key=lambda t: (t.position, str(t.id)),
        )
        return tuple(clone_value(t) for t in rows)

    def statuses_for_run(self, run_id: RunId) -> frozenset[TaskStatus]:
        return frozenset(task.status for task in self._state.tasks.values() if task.run_id == run_id)

    def edges_for_run(self, run_id: RunId) -> tuple[TaskEdge, ...]:
        rows = sorted(
            (e for e in self._state.task_edges.values() if e.run_id == run_id),
            key=lambda e: (str(e.dependent_task_id), str(e.prerequisite_task_id)),
        )
        return tuple(clone_value(e) for e in rows)

    def save(self, task: Task, *, expected_version: int) -> None:
        self._backend.core.require_writable()
        cur = self._state.tasks.get(task.id)
        if cur is None:
            raise not_found("task", task.id)
        for fname in _TASK_OWNED:
            if getattr(task, fname) != getattr(cur, fname):
                raise field_owned("task", fname)
        if cur.row_version != expected_version:
            raise version_conflict("task", task.id, expected_version, cur.row_version)
        self._check_task(task)
        self._state.tasks[task.id] = clone_value(replace(task, row_version=expected_version + 1))
