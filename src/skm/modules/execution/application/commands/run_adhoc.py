"""Admit one project-scoped task with a pinned inline specification."""

import json
from dataclasses import replace
from typing import cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed, error_for
from skm.kernel.ids import ProjectId, ResourceVersionId, RunId, ScopeId, TaskId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._adhoc_spec import INLINE_SPEC, MAX_SPEC_BYTES
from skm.modules.execution.application._json_report import retain_json_document
from skm.modules.execution.application._start_inputs import (
    execution_policy,
    pin_workflow_inputs,
    prospective_config,
    work_policy_inputs,
)
from skm.modules.execution.application.commands.start_run import persist_and_start
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.execution_bundle import ExecutionBundle, ResourcePin
from skm.modules.execution.domain.review_grouping import choose_grouping
from skm.modules.execution.domain.run import Run, RunKind, RunStatus
from skm.modules.execution.domain.task import ReviewMode, Task, TaskKind, TaskStatus
from skm.modules.execution.domain.work_policy import resolve_work_policy
from skm.modules.execution.domain.workflow.adhoc import default_adhoc_workflow, parse_adhoc_workflow
from skm.modules.execution.generated.commands import RunAdhoc
from skm.modules.execution.generated.results import StartRunResult
from skm.modules.execution.ports import AutopilotRepository
from skm.modules.extensions import public as extensions
from skm.modules.policy.public import effective_permissions, permissions_digest
from skm.modules.workspace import public as workspace


def scope_of(command: RunAdhoc) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(command.project_id))


def handle(command: RunAdhoc, ctx: CommandContext, uow: UnitOfWork) -> StartRunResult:
    project_id = ProjectId(command.project_id)
    workspace.require_active_project(uow, project_id)
    if project_id in uow.repo(AutopilotRepository).emergency_project_ids():
        raise error_for(ErrorCode.EMERGENCY_STOPPED, "project emergency stop is active")
    if ctx.config.get("execution.kill_switch") is True:
        raise error_for(ErrorCode.FORBIDDEN, "live policy kill switch")
    if not command.prompt.strip() or "\x00" in command.prompt:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "prompt must contain nonblank text without NUL")

    document = default_adhoc_workflow() if command.workflow is None else command.to_json()["workflow"]
    spec: JsonObject = {"schema": INLINE_SPEC, "prompt": command.prompt, "workflow": document}
    try:
        size = len(json.dumps(spec, ensure_ascii=False).encode("utf-8"))
    except UnicodeError as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "inline specification must be UTF-8") from exc
    if size > MAX_SPEC_BYTES:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "inline specification exceeds the size limit")

    work_kind = command.work_kind or "research"
    cfg = prospective_config(ctx.config, {}, parent_id=project_id)
    packs = extensions.pinned_pack_versions(uow, config=cfg)
    # Keep the versioned resource binding required by the run ledger. The immutable
    # specification carries the executable per-run workflow.
    base = extensions.resolve_resource(
        uow, extensions.ResourceKind.WORKFLOW, "quick-fix", config=cfg, pins=packs
    )
    base_id = ResourceVersionId(base.resource_version_id)
    workflow = parse_adhoc_workflow(document, work_kind)
    pin = ResourcePin("workflow", base.key, base_id, base.digest)
    pins, profiles, _, _ = pin_workflow_inputs(uow, cfg, packs, workflow.stages, pin)
    settings, ceilings = work_policy_inputs(cfg, profiles)
    work_policy = resolve_work_policy(settings, ceilings=ceilings)
    permission_set = effective_permissions(
        uow,
        scope_chain=tuple(ScopeRef(scope.kind, scope.id) for scope in ctx.scope_chain),
        config=cfg,
        profile_id=None,
        role_layer=None,
        task_layer=None,
        allow_unconfined=False,
    )

    project = workspace.get_project(uow, project_id)
    workspace_id = WorkspaceId(project.workspace_id)
    now, run_id, task_id = ctx.clock.now(), RunId(ctx.ids.new_id()), TaskId(ctx.ids.new_id())
    task = Task(
        id=task_id,
        run_id=run_id,
        workspace_id=workspace_id,
        kind=TaskKind.ADHOC,
        spec_entity_id=None,
        display_key="ADHOC-1",
        origin=None,
        position=0,
        status=TaskStatus.BLOCKED,
        work_kind=work_kind,
        review_mode=ReviewMode.SELF,
        review_profile=None,
        declared_write_scope=(),
        required_host_id=None,
        current_attempt_id=None,
        accepted_attempt_id=None,
        accepted_output_id=None,
        check_fix_rounds=0,
        review_rounds=0,
        attempt_count=0,
        row_version=1,
        blocking_reason=blocking_reason(
            BlockingCode.BLOCKED_BY_DEPENDENCY,
            task_id=task_id,
            refs={"prerequisite_task_ids": []},
            now=now,
            message="run admission",
        ),
    )
    grouping = choose_grouping((task,), execution_policy(cfg))
    frozen = replace(cfg.freeze(cfg.registry), run_scope_id=run_id)
    version_id = retain_json_document(
        uow,
        ctx,
        (workspace_id, project_id),
        spec,
        title="Ad hoc specification",
        filename="adhoc.json",
        source_ref=f"run:{run_id}",
        origin=artifacts.FileOrigin.CAPTURE,
    )
    run = Run(
        id=run_id,
        workspace_id=workspace_id,
        project_id=project_id,
        kind=RunKind.ADHOC,
        plan_id=None,
        revision_id=None,
        revision_no=None,
        status=RunStatus.CREATED,
        requested_by=ctx.actor.principal_id,
        readiness_report_id=None,
        audited_report_id=None,
        review_request_id=None,
        compiler_version=1,
        workflow_resource_version_id=base_id,
        review_grouping=grouping,
        autopilot=False,
        queued=False,
        pause_reason=None,
        pause_source=None,
        stop_code=None,
        unmetered_at=None,
        row_version=1,
        created_at=now,
        started_at=None,
        finished_at=None,
        inline_spec_file_version_id=version_id,
    )
    bundle = ExecutionBundle(
        run_id,
        cast("JsonObject", frozen.to_document()),
        frozen.digest,
        permissions_digest(permission_set),
        pins,
        None,
        {"@default": work_policy, task.display_key: work_policy},
        {key: value for key, value in frozen.values.items() if key.startswith("context.")},
        grouping,
        now,
    )
    return persist_and_start(run, bundle, (task,), (), cfg, ctx, uow, reason="Ad hoc run")


SPEC = CommandSpec(
    name="execution.run_adhoc",
    dto=RunAdhoc,
    result=StartRunResult,
    permission="run.start",
    scope_of=scope_of,
    handler=handle,
    idempotency=IdempotencyMode.OPTIONAL,
)
