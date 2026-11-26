"""Publish a service revision and start its isolated review run in the caller's UoW."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import FileVersionId, ProjectId, RepositoryId, ResourceVersionId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._events import cause, emit, save_task, task_created
from skm.modules.execution.application._plain import plain
from skm.modules.execution.application._primitives import budget_accounts
from skm.modules.execution.application._start_inputs import prepare_inputs, value
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.domain.execution_bundle import ExecutionBundle, ResourcePin, ResourcePins
from skm.modules.execution.domain.ids import ReviewRequestId
from skm.modules.execution.domain.review_grouping import choose_grouping
from skm.modules.execution.domain.review_request import (
    CommitReviewTarget,
    ReviewRequest,
    WorkingTreeReviewTarget,
    validate_target,
)
from skm.modules.execution.domain.review_request import (
    RequestReview as RequestReview,
)
from skm.modules.execution.domain.run import Run, RunKind, RunStatus, mark_ready, start
from skm.modules.execution.domain.task import TaskStatus, transition
from skm.modules.execution.domain.task_graph import SelectionRequest, compile_run_tasks
from skm.modules.execution.ports import (
    AutopilotRepository,
    BudgetRepository,
    BundleRepository,
    ReviewRequestRepository,
    RunRepository,
    TaskRepository,
)
from skm.modules.extensions import public as extensions
from skm.modules.planning import public as planning
from skm.modules.workspace import public as workspace
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.keys import Level
from skm.platform.config.scopes import ScopeChain
from skm.platform.config.scopes import ScopeRef as ConfigScope


class RequestReviewResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:request-review:v1"


def scope_of(cmd: RequestReview) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(cmd["project_id"])))


def create_review_run(prepared: Any, request: ReviewRequest, ctx: Any, uow: UnitOfWork) -> Run:
    rid, now = ctx.ids.new_id(), ctx.clock.now()
    compiled = compile_run_tasks(
        prepared.graph,
        prepared.workflow,
        prepared.policy,
        SelectionRequest(("P1.1",), (), None),
        {},
        run_id=rid,
        workspace_id=request.workspace_id,
        revision_id=request.revision_id,
        new_task_id=ctx.ids.new_id,
        now=now,
    )
    if len(compiled.tasks) != 1 or compiled.edges:
        raise error_for(ErrorCode.CONFIG_INVALID, "review-only must compile exactly one independent task")
    tasks = tuple(
        replace(t, declared_write_scope=(), review_profile=request.profile_key) for t in compiled.tasks
    )
    grouping = choose_grouping(tasks, prepared.policy)
    run = Run(
        id=rid,
        workspace_id=request.workspace_id,
        project_id=request.project_id,
        kind=RunKind.REVIEW_REQUEST,
        plan_id=request.plan_id,
        revision_id=request.revision_id,
        revision_no=prepared.meta.revision_no,
        status=RunStatus.CREATED,
        requested_by=ctx.actor.principal_id,
        readiness_report_id=None,
        audited_report_id=None,
        review_request_id=request.id,
        compiler_version=compiled.compiler_version,
        workflow_resource_version_id=prepared.workflow_id,
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
    )
    uow.repo(ScopeRegistry).create(
        ScopeId(rid),
        ScopeKind.RUN,
        parent=ScopeId(run.require_plan()),
        workspace_id=run.workspace_id,
    )
    repo = uow.repo(RunRepository)
    repo.add(run)
    frozen = replace(prepared.frozen, run_scope_id=rid)
    bundle = ExecutionBundle(
        rid,
        frozen.to_document(),
        frozen.digest,
        prepared.inputs.policy,
        prepared.pins,
        compiled.selection,
        prepared.policies,
        {k: v for k, v in frozen.values.items() if k.startswith("context.")},
        grouping,
        now,
    )
    uow.repo(BundleRepository).add(bundle)
    uow.repo(TaskRepository).add_many(tasks, ())
    why = cause("run_start")
    emit(
        uow,
        run,
        "review-requested",
        {
            "request_id": str(request.id),
            "mount": request.mount,
            "target_kind": request.target.kind,
            "base_commit": request.target.base_commit,
            "head_commit": request.target.head_commit
            if isinstance(request.target, CommitReviewTarget)
            else None,
            "profile_key": request.profile_key,
        },
        why,
    )
    emit(
        uow,
        run,
        "run-created",
        {
            "kind": run.kind.value,
            "plan_id": str(run.plan_id),
            "revision_id": str(run.revision_id),
            "revision_no": run.revision_no,
            "requested_by": str(run.requested_by),
            "reason": request.reason,
            "bundle_digest": bundle.config_digest,
        },
        why,
    )
    task = tasks[0]
    task_created(uow, run, task, why)
    uow.repo(BudgetRepository).add_accounts(
        budget_accounts(ctx, rid, (task.id,), frozen.values, include_run=True)
    )
    limit = value(prepared.config, "execution.parallel.max_runs_per_project", 1)
    queued = not repo.project_has_slot(run.project_id, limit)
    ready = replace(mark_ready(run), queued=queued)
    repo.save(ready, expected_version=run.row_version)
    if queued:
        return ready
    running = start(ready, now=now)
    repo.save(running, expected_version=ready.row_version)
    save_task(uow, running, task, transition(task, TaskStatus.READY, rule="T1"), why, now)
    emit(uow, running, "task-ready", {"task_id": str(task.id), "reason": "run_start"}, why)
    emit(
        uow,
        running,
        "run-started",
        {
            "task_count": 1,
            "ready_count": 1,
            "bundle_digest": bundle.config_digest,
            "review_grouping": plain(grouping),
        },
        why,
    )
    return running


def handle(cmd: RequestReview, ctx: Any, uow: UnitOfWork) -> RequestReviewResult:
    project_id = ProjectId(UUID(cmd["project_id"]))
    workspace.require_active_project(uow, project_id)
    if project_id in uow.repo(AutopilotRepository).emergency_project_ids():
        raise error_for(ErrorCode.EMERGENCY_STOPPED, "project emergency stop")
    project = workspace.get_project(uow, project_id)
    mount = next(
        (m for m in workspace.project_repositories(uow, project_id) if m.mount_name == cmd["mount"]), None
    )
    if mount is None:
        raise error_for(ErrorCode.NOT_FOUND, "project mount not found")
    raw = cmd["target"]
    target_fields = {
        "commits": {"kind", "base_commit", "head_commit"},
        "working_tree": {"kind", "base_commit", "patch_file_version_id"},
    }
    if set(raw) != target_fields.get(raw["kind"]):
        raise error_for(ErrorCode.SCHEMA_INVALID, "review target does not match its discriminator")
    if raw["kind"] == "commits":
        target = CommitReviewTarget("commits", raw["base_commit"], raw["head_commit"])
        plan_target = planning.CommitReviewTarget("commits", target.base_commit, target.head_commit)
    elif raw["kind"] == "working_tree":
        target = WorkingTreeReviewTarget(
            "working_tree", raw["base_commit"], FileVersionId(UUID(raw["patch_file_version_id"]))
        )
        artifacts.require_ready_versions(
            uow, WorkspaceId(project.workspace_id), (target.patch_file_version_id,)
        )
        plan_target = planning.WorkingTreeReviewTarget(
            "working_tree", target.base_commit, target.patch_file_version_id
        )
    else:
        raise error_for(ErrorCode.SCHEMA_INVALID, "unknown review target kind")
    validate_target(target)
    request_id = ReviewRequestId(ctx.ids.new_id())
    profile = cmd.get("profile_key", "reviewer")
    spec = planning.ReviewRequestSpec(request_id, cmd["mount"], plan_target, profile, cmd["reason"])
    meta = planning.publish_review_request_revision(
        uow, ctx.actor, project_id, spec, ids=ctx.ids, now=ctx.clock.now()
    )
    inherited = ctx.config
    plan_config = EffectiveConfig(
        registry=inherited.registry,
        chain=ScopeChain(
            inherited.chain.kind, (*inherited.chain.scopes, ConfigScope(Level.PLAN, meta.plan_id))
        ),
        resolutions={key: inherited.resolution(key) for key in inherited.resolved_keys()},
        invalid=inherited.invalid_keys(),
        diagnostics=inherited.diagnostics,
        generation=inherited.generation,
        pack_generation=inherited.pack_generation,
        digest=inherited.digest,
    )
    plan_ctx = replace(
        ctx, config=plan_config, scope_chain=uow.repo(ScopeRegistry).ancestors(ScopeId(meta.plan_id))
    )
    prepared = prepare_inputs(
        uow,
        plan_ctx,
        meta.plan_id,
        meta.revision_id,
        {},
        None,
        workflow_key=value(ctx.config, "execution.review.request_workflow", "review-only"),
    )
    selected = extensions.select_agent_profile(
        uow,
        "reviewer",
        stage_profile=profile,
        config=prepared.config,
        pins=prepared.pins.packs,
    )
    resources = [
        *prepared.pins.resources,
        ResourcePin(
            "agent_profile",
            selected.key,
            ResourceVersionId(selected.resource_version_id),
            selected.digest,
        ),
    ]
    reviewer = extensions.load_agent_profile(uow, ResourceVersionId(selected.resource_version_id))
    for keys in reviewer.prompt.blocks.values():
        for key in keys:
            block = extensions.resolve_resource(
                uow,
                extensions.ResourceKind.PROMPT_BLOCK,
                key,
                config=prepared.config,
                pins=prepared.pins.packs,
            )
            resources.append(
                ResourcePin("prompt_block", key, ResourceVersionId(block.resource_version_id), block.digest)
            )
    prepared = replace(
        prepared,
        pins=ResourcePins(
            tuple({(pin.kind, pin.key): pin for pin in resources}.values()),
            prepared.pins.packs,
        ),
    )
    stages = prepared.workflow.stages
    if (
        [s.type.value for s in stages]
        != ["prepare_environment", "agent_review", "agent_step", "acceptance_gate"]
        or stages[2].role.value != "triager"
        or stages[0].params.baseline_strategy != "review_request"
        or stages[1].params.audit_scope != "range"
    ):
        raise error_for(
            ErrorCode.CONFIG_INVALID,
            "review-only requires prepare, range review, triage and report acceptance",
        )
    request = ReviewRequest(
        request_id,
        WorkspaceId(project.workspace_id),
        project_id,
        cmd["mount"],
        RepositoryId(mount.repository.repository_id),
        target,
        profile,
        cmd["reason"],
        ctx.actor.principal_id,
        meta.plan_id,
        meta.revision_id,
        ctx.clock.now(),
    )
    uow.repo(ReviewRequestRepository).add(request)
    run = create_review_run(prepared, request, ctx, uow)
    return RequestReviewResult(
        request_id=str(request.id),
        run_id=str(run.id),
        revision_id=str(meta.revision_id),
        status=run.status.value,
    )


SPEC = CommandSpec(
    name="execution.request_review",
    dto=RequestReview,
    result=RequestReviewResult,
    permission="run.start",
    scope_of=scope_of,
    handler=handle,
    idempotency=IdempotencyMode.REQUIRED,
)
