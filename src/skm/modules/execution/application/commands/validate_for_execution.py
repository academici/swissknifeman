"""Persist readiness for the exact prospective StartRun request."""

from __future__ import annotations

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import RevisionId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.execution.application._events import event_class
from skm.modules.execution.application._plain import plain
from skm.modules.execution.application._start_inputs import prepare_inputs, value
from skm.modules.execution.domain.readiness import (
    PROGRESSIVE_MODE,
    ReadinessStatus,
    canonical_digest,
    evaluate_readiness,
    write_scope_overlaps,
)
from skm.modules.execution.domain.task_graph import EdgeKind
from skm.modules.execution.generated.commands import ValidateForExecution
from skm.modules.execution.generated.results import ValidateForExecutionResult
from skm.modules.execution.ports import ReadinessRepository, RunRepository

from .start_run import create_run


def scope_of(cmd: ValidateForExecution) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(cmd.plan_id))


def handle(cmd: ValidateForExecution, ctx: CommandContext, uow: UnitOfWork) -> ValidateForExecutionResult:
    if cmd.semantic_audit and not value(ctx.config, "execution.readiness.semantic_audit_allowed", False):
        raise error_for(
            ErrorCode.FORBIDDEN,
            "semantic audit is disabled",
            details={"reason_code": "SEMANTIC_AUDIT_NOT_ALLOWED"},
        )
    if cmd.mode == PROGRESSIVE_MODE and cmd.scope is not None:
        raise error_for(ErrorCode.SCHEMA_INVALID, "progressive readiness derives its scope from selection")
    if cmd.semantic_audit:
        uow.repo(RunRepository).lock_revision_start(RevisionId(cmd.revision_id), audit=True)
    prepared = prepare_inputs(
        uow, ctx, cmd.plan_id, cmd.revision_id, cmd.overrides, cmd.selection, mode=cmd.mode
    )
    evaluation = dict(prepared.evaluation)
    frozen = prepared.frozen.values
    estimate = {
        **evaluation.get("estimate", {}),
        "token_budget": {
            "task_warn_tokens": frozen.get("budgets.task.warn_tokens"),
            "task_max_tokens": frozen.get("budgets.task.max_tokens"),
            "run_max_tokens": frozen.get("budgets.run.max_tokens"),
        },
    }
    compiled = prepared.compiled
    task_keys = {task.id: task.display_key for task in compiled.tasks}
    evaluation.update(
        estimate=estimate,
        write_scope_overlaps=write_scope_overlaps(
            [
                {"task_key": task.display_key, "write_scope": plain(task.granted_write_scope)}
                for task in compiled.tasks
                if task.granted_write_scope
            ],
            [
                {
                    "dependent": task_keys[edge.dependent_task_id],
                    "prerequisite": task_keys[edge.prerequisite_task_id],
                }
                for edge in compiled.edges
                if edge.kind is not EdgeKind.BATCH
            ],
        ),
        id=str(ctx.ids.new_id()),
        workspace_id=str(prepared.meta.workspace_id),
        project_id=str(prepared.meta.project_id),
        plan_id=str(cmd.plan_id),
        revision_id=str(cmd.revision_id),
        revision_digest=prepared.meta.digest,
        created_by=str(ctx.actor.principal_id),
        created_at=ctx.clock.now().isoformat(),
        scope=plain(cmd.scope) if cmd.scope else {"kind": "plan"},
    )
    if cmd.mode == PROGRESSIVE_MODE:
        evaluation["scope"] = {
            "kind": "selection",
            "phase_keys": [phase["key"] for phase in evaluation["phases"]],
        }
    report = evaluate_readiness(evaluation)
    uow.repo(ReadinessRepository).add(report)
    uow.record(
        event_class("urn:skm:execution:event:readiness-reported:v1")(
            cmd.plan_id,
            report.workspace_id,
            {
                "workspace_id": str(report.workspace_id),
                "project_id": str(report.project_id),
                "report_id": str(report.id),
                "plan_id": str(cmd.plan_id),
                "revision_id": str(cmd.revision_id),
                "status": report.status.value,
                "finding_counts": {
                    "error": sum(f.severity == "error" for f in report.findings),
                    "advisory": sum(f.severity == "advisory" for f in report.findings),
                },
                "supersedes_report_id": None,
            },
        )
    )
    audit_id = None
    if cmd.semantic_audit and report.status is not ReadinessStatus.NOT_READY:
        audit = prepare_inputs(
            uow,
            ctx,
            cmd.plan_id,
            cmd.revision_id,
            cmd.overrides,
            cmd.selection if cmd.mode == PROGRESSIVE_MODE else None,
            workflow_key="plan-audit",
            mode=cmd.mode,
        )
        audit_id = create_run(audit, ctx, uow, audit_report_id=report.id).run_id
    return ValidateForExecutionResult.from_json(
        {
            "report_id": str(report.id),
            "status": report.status.value,
            "findings": plain(report.findings),
            "estimate": report.estimate,
            "inputs_digest": report.inputs_digest,
            "start_request_digest": canonical_digest(prepared.request),
            "work_policies": evaluation["work_policies"],
            **({"audit_run_id": str(audit_id)} if audit_id else {}),
        }
    )


SPEC = CommandSpec(
    name="execution.validate_for_execution",
    dto=ValidateForExecution,
    result=ValidateForExecutionResult,
    permission="run.start",
    scope_of=scope_of,
    handler=handle,
)
