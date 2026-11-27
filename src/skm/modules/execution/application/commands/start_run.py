"""Freeze revision, prospective settings and resource pins before starting a run."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any
from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import RevisionId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.access import public as access
from skm.modules.execution.application._events import cause, emit, save_task, task_created
from skm.modules.execution.application._plain import plain
from skm.modules.execution.application._primitives import budget_accounts
from skm.modules.execution.application._scheduler_materials import refresh_material_waits
from skm.modules.execution.application._start_inputs import compile_spec_tasks, prepare_inputs, value
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.execution_bundle import ExecutionBundle
from skm.modules.execution.domain.ids import ReadinessReportId
from skm.modules.execution.domain.readiness import PROGRESSIVE_MODE, require_fresh
from skm.modules.execution.domain.review_grouping import choose_grouping
from skm.modules.execution.domain.run import Run, RunKind, RunStatus, mark_ready, start
from skm.modules.execution.domain.task import Task, TaskKind, TaskStatus, transition
from skm.modules.execution.domain.task_graph import (
    SelectionRequest,
    TaskEdge,
    ready_task_ids,
)
from skm.modules.execution.generated.commands import StartRun
from skm.modules.execution.generated.results import StartRunResult
from skm.modules.execution.ports import (
    BudgetRepository,
    BundleRepository,
    ReadinessRepository,
    RunRepository,
    TaskRepository,
)
from skm.platform.config import EffectiveConfig


def scope_of(cmd: StartRun) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(cmd.plan_id))


def create_run(
    prepared: Any,
    ctx: Any,
    uow: UnitOfWork,
    *,
    report_id: Any = None,
    visa_id: UUID | None = None,
    audit_report_id: Any = None,
    autopilot: bool = False,
    reason: str = "Semantic readiness audit",
) -> Any:
    rid, now = ctx.ids.new_id(), ctx.clock.now()
    request = prepared.request["selection"]
    selection = (
        None
        if request is None
        else SelectionRequest(
            tuple(request["task_keys"]), tuple(request["phases"]), request.get("stop_after")
        )
    )
    compiled = compile_spec_tasks(
        prepared.spec,
        prepared.graph,
        prepared.workflow,
        prepared.policy,
        selection,
        {},
        run_id=rid,
        workspace_id=prepared.meta.workspace_id,
        revision_id=prepared.meta.revision_id,
        new_task_id=ctx.ids.new_id,
        now=now,
    )
    tasks, edges = compiled.tasks, compiled.edges
    policies = dict(prepared.policies)
    if audit_report_id is not None:
        first = tasks[0]

        first = replace(
            first,
            kind=TaskKind.PLAN_AUDIT,
            spec_entity_id=None,
            display_key="@plan_audit",
            declared_write_scope=(),
            origin=None,
            blocking_reason=blocking_reason(
                BlockingCode.BLOCKED_BY_DEPENDENCY,
                task_id=first.id,
                refs={"prerequisite_task_ids": []},
                now=now,
                message="initial audit",
            ),
        )
        tasks, edges = (first,), ()
        policies = {"@default": policies["@default"], "@plan_audit": policies["@default"]}
    grouping = choose_grouping(tasks, prepared.policy)
    run = Run(
        rid,
        prepared.meta.workspace_id,
        prepared.meta.project_id,
        RunKind.READINESS_AUDIT if audit_report_id is not None else RunKind.PLAN,
        prepared.meta.plan_id,
        prepared.meta.revision_id,
        prepared.meta.revision_no,
        RunStatus.CREATED,
        ctx.actor.principal_id,
        report_id,
        audit_report_id,
        None,
        compiled.compiler_version,
        prepared.workflow_id,
        grouping,
        autopilot,
        False,
        None,
        None,
        None,
        None,
        1,
        now,
        None,
        None,
    )
    frozen = replace(prepared.frozen, run_scope_id=rid)
    bundle = ExecutionBundle(
        rid,
        frozen.to_document(),
        frozen.digest,
        prepared.inputs.policy,
        prepared.pins,
        None if audit_report_id is not None else compiled.selection,
        policies,
        {k: v for k, v in frozen.values.items() if k.startswith("context.")},
        grouping,
        now,
    )
    return persist_and_start(
        run, bundle, tasks, edges, prepared.config, ctx, uow, reason=reason, visa_id=visa_id
    )


def persist_and_start(  # noqa: PLR0913 -- transactional run inputs and provenance
    run: Run,
    bundle: ExecutionBundle,
    tasks: Sequence[Task],
    edges: Sequence[TaskEdge],
    config: EffectiveConfig,
    ctx: CommandContext,
    uow: UnitOfWork,
    *,
    reason: str,
    visa_id: UUID | None = None,
) -> StartRunResult:
    rid, now = run.id, run.created_at
    grouping = run.review_grouping
    values = bundle.config_snapshot["values"]
    uow.repo(ScopeRegistry).create(
        ScopeId(rid),
        ScopeKind.RUN,
        parent=ScopeId(run.plan_id or run.project_id),
        workspace_id=run.workspace_id,
    )
    uow.repo(RunRepository).add(run)
    uow.repo(BundleRepository).add(bundle)
    uow.repo(TaskRepository).add_many(tasks, edges)
    why = cause("run_start")
    emit(
        uow,
        run,
        "run-created",
        {
            "plan_id": None if run.plan_id is None else str(run.plan_id),
            "revision_id": None if run.revision_id is None else str(run.revision_id),
            "revision_no": run.revision_no,
            "kind": run.kind.value,
            "requested_by": str(run.requested_by),
            "reason": reason,
            "bundle_digest": bundle.config_digest,
            **({"visa_id": str(visa_id)} if visa_id is not None else {}),
        },
        why,
    )
    for task in sorted(tasks, key=lambda t: (t.position, str(t.id))):
        task_created(uow, run, task, why)
    uow.repo(BudgetRepository).add_accounts(
        budget_accounts(ctx, rid, tuple(t.id for t in tasks), values, include_run=True)
    )
    ready = mark_ready(run)
    running = [uow.repo(RunRepository).get(i) for i in uow.repo(RunRepository).list_active_ids(limit=500)]
    limit = value(config, "execution.parallel.max_runs_per_project", 1)
    queued = sum(r.project_id == run.project_id and r.status is RunStatus.RUNNING for r in running) >= limit
    if queued:
        ready = replace(ready, queued=True)
    uow.repo(RunRepository).save(ready, expected_version=run.row_version)
    ready_ids = () if queued else ready_task_ids(tasks, edges)
    if ready_ids:
        refresh_material_waits(uow, ctx, run, values, now, initial_ready=ready_ids)
        tasks = uow.repo(TaskRepository).list_for_run(run.id)
        ready_ids = tuple(
            t.id
            for t in tasks
            if t.id in ready_ids
            and (t.blocking_reason is None or t.blocking_reason.code.value != "BLOCKED_BY_MATERIAL")
        )
    if not queued:
        run = start(ready, now=now)
        uow.repo(RunRepository).save(run, expected_version=ready.row_version)
        for task in tasks:
            if task.id in ready_ids:
                updated = transition(task, TaskStatus.READY, rule="T1")
                save_task(uow, run, task, updated, why, now)
                emit(uow, run, "task-ready", {"task_id": str(task.id), "reason": "run_start"}, why)
        emit(
            uow,
            run,
            "run-started",
            {
                "task_count": len(tasks),
                "ready_count": len(ready_ids),
                "bundle_digest": bundle.config_digest,
                "review_grouping": plain(grouping),
            },
            why,
        )
    else:
        run = ready
    return StartRunResult(rid, run.status.value, len(tasks), tuple(ready_ids), bundle.config_digest, queued)


def handle(cmd: StartRun, ctx: CommandContext, uow: UnitOfWork) -> StartRunResult:
    if cmd.autopilot and ctx.actor.principal_id != SYSTEM_PRINCIPAL_ID:
        raise error_for(ErrorCode.FORBIDDEN, "autopilot starts require the system principal")
    runs = uow.repo(RunRepository)
    revision_id = RevisionId(cmd.revision_id)
    runs.lock_revision_start(revision_id)
    prepared = prepare_inputs(
        uow, ctx, cmd.plan_id, cmd.revision_id, cmd.overrides, cmd.selection, mode=cmd.mode
    )
    if runs.has_active_readiness_audit(revision_id):
        raise error_for(ErrorCode.READINESS_REQUIRED, "a readiness audit is active for this revision")
    now = ctx.clock.now()
    max_age = value(prepared.config, "execution.readiness.max_age_seconds", 3600)
    progressive = cmd.mode == PROGRESSIVE_MODE
    readiness = uow.repo(ReadinessRepository)
    report_id = None if cmd.readiness_report_id is None else ReadinessReportId(cmd.readiness_report_id)
    if (progressive or prepared.visa_required) and cmd.visa_id is None:
        raise error_for(ErrorCode.READINESS_REQUIRED, "execution requires a revision visa")
    if cmd.visa_id is not None:
        visa = readiness.get_visa(cmd.visa_id)
        if (
            (visa.workspace_id, visa.plan_id, visa.revision_id)
            != (prepared.meta.workspace_id, cmd.plan_id, cmd.revision_id)
            or visa.selection != prepared.request["selection"]
            or (report_id is not None and report_id != visa.readiness_report_id)
        ):
            raise error_for(
                ErrorCode.READINESS_REQUIRED, "visa belongs to another revision, report or selection"
            )
        if not 0 <= (now - visa.signed_at).total_seconds() < max_age:
            raise error_for(ErrorCode.READINESS_REQUIRED, "revision visa is outside its validity period")
        signer = Actor(visa.signed_by, PrincipalKind.HUMAN, "revision visa signer")
        if "plan.approve" not in access.effective_permissions(uow, signer, ScopeId(cmd.plan_id)):
            raise error_for(ErrorCode.FORBIDDEN, "revision visa signer no longer holds plan.approve")
        report_id = visa.readiness_report_id
    if progressive or cmd.visa_id is not None or value(prepared.config, "execution.readiness.required", True):
        if report_id is None:
            raise error_for(ErrorCode.READINESS_REQUIRED, "a readiness report is required")
        report = readiness.get(report_id)
        if report.plan_id != cmd.plan_id or report.revision_id != cmd.revision_id:
            raise error_for(ErrorCode.READINESS_REQUIRED, "report belongs to another revision")
        require_fresh(
            report,
            prepared.inputs,
            revision_digest=prepared.meta.digest,
            now=now,
            max_age_seconds=max_age,
            start_request=prepared.request,
        )
    return create_run(
        prepared,
        ctx,
        uow,
        report_id=report_id,
        visa_id=cmd.visa_id,
        autopilot=bool(cmd.autopilot),
        reason=cmd.reason,
    )


SPEC = CommandSpec(
    name="execution.start_run",
    dto=StartRun,
    result=StartRunResult,
    permission="run.start",
    scope_of=scope_of,
    handler=handle,
)
