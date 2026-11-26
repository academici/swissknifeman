"""Agent context draft, token metadata and immutable ready payload."""

from dataclasses import replace
from typing import Any, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed, error_for
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access import public as access
from skm.modules.context.public import (
    ContextRequest,
    PayloadCompiler,
    PermissionsSummary,
    ResumeInfo,
    RunParams,
    RuntimeTarget,
    assemble_draft,
    get_manifest,
)
from skm.modules.context.public import (
    StepPurpose as ContextStepPurpose,
)
from skm.modules.execution.application._adhoc_spec import load_run_workflow, task_instructions
from skm.modules.execution.application._incident_gate import (
    REPAIR_ACTION_DIGEST,
    REPAIR_REVIEW_REQUIRED,
    is_repair,
)
from skm.modules.execution.application._live_control import controlled_selection
from skm.modules.execution.application._stage_agent_helpers import (
    agent_role,
    estimate,
    profile_and_permissions,
    route_agent,
    route_snapshot,
    runtime_limits,
    session_decision,
)
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application._worker_budget import amounts, reserve_step
from skm.modules.execution.application._worker_dtos import digest, document, parse_datetime
from skm.modules.execution.application._worker_inputs import execution_blocks
from skm.modules.execution.application._worker_protocol import grant_inputs, locked_stage
from skm.modules.execution.application.loaders import load_effective_bundle, require_task_work_policy
from skm.modules.execution.domain.role_contracts import ROLE_CONTRACTS
from skm.modules.execution.domain.session import Resume
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES
from skm.modules.execution.domain.step import AttemptStep, RoleId, StepPurpose, StepState
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.ports import StageRepository, StepRepository
from skm.modules.extensions.public import PackPins
from skm.modules.policy.public import (
    permission_set_to_view,
)
from skm.modules.runtimes.public import (
    RoleId as RuntimeRoleId,
)
from skm.modules.runtimes.public import (
    admission_policy,
    resolve_model_guideline,
    session_policy_for,
)
from skm.modules.runtimes.public import catalog as runtime_catalog
from skm.modules.workspace import public as workspace

_DEFAULT_ASSIGNMENT_PERMISSIONS = (
    "project.read",
    "plan.read",
    "run.read",
    "context.read",
    "file.read",
    "policy.read",
    "memory.read",
    "lesson.read",
    "ext.read",
    "runtime.read",
    "step.note",
)


def issue_step_token(uow: UnitOfWork, ctx: Any, fenced: Any, step: Any, secret: Any) -> Any:
    stage = locked_stage(uow, fenced, step.stage_record_id)
    saved = next((s for s in uow.repo(StepRepository).for_stage(stage.id) if s.id == step.id), step)
    if stage.state not in ACTIVE_STAGE_STATES or saved.state is not StepState.STARTED:
        raise error_for(ErrorCode.INVALID_TRANSITION, "terminal step cannot receive runtime authority")
    if not isinstance(secret, str):
        raise error_for(ErrorCode.FORBIDDEN, "runtime token secret is required")
    try:
        token = access.parse_secret(secret)
    except ValidationFailed as exc:
        raise error_for(ErrorCode.SCHEMA_INVALID, "invalid runtime token secret") from exc
    try:
        permissions = ctx.config.get("access.tokens.assignment_permissions")
    except ValidationFailed as exc:
        if exc.code != ErrorCode.CONFIG_UNKNOWN_KEY:
            raise
        permissions = None
    return access.issue_assignment_token(
        uow,
        worker=ctx.actor,
        secret=token,
        run_scope_id=ScopeId(fenced.run.id),
        assignment_id=fenced.assignment.id,
        step_id=step.id,
        expires_at=fenced.lease.expires_at,
        permissions=frozenset(_DEFAULT_ASSIGNMENT_PERMISSIONS if permissions is None else permissions),
        pepper=ctx.gateways.get(access.TokenPepperSource).pepper(),
        now=fenced.now,
    )


def _runtime_target(
    uow: UnitOfWork, ctx: Any, fenced: Any, route: Any, role: RoleId, pins: PackPins
) -> RuntimeTarget:
    catalog = runtime_catalog(uow, config=ctx.config, pins=pins)
    entry = catalog.model(route.runtime_id, route.model)
    guideline = resolve_model_guideline(
        uow, route.runtime_id, route.model, catalog=catalog, config=ctx.config, pins=pins
    )
    if guideline is not None:
        PayloadCompiler.validate_role(route.model, role.value, guideline.get("suited_roles", ()))
    if role is RoleId.ADVISOR:
        previous = uow.repo(StepRepository).last_for_role(fenced.attempt.id, RoleId.EXECUTOR)
        if previous is not None:
            executor = resolve_model_guideline(
                uow,
                previous.runtime_id,
                previous.model,
                config=ctx.config,
                pins=pins,
                catalog=catalog,
            )
            if executor is not None:
                PayloadCompiler.validate_advisor(
                    executor["model_id"],
                    executor.get("suited_roles", ()),
                    route.model,
                    executor.get("compatible_advisor_models"),
                    advisor_profile_model=guideline["model_id"] if guideline else None,
                )
    notes = (entry.notes,) if entry and entry.notes else ()
    if guideline is not None:
        notes = tuple(filter(None, (guideline.get("notes"), *guideline["prompt_style"]["instructions"])))
    return RuntimeTarget(
        runtime_id=route.runtime_id,
        model=route.model,
        context_window_tokens=route.context_window_tokens,
        capabilities=frozenset(),
        tools=frozenset(),
        notes=notes,
        route_source=str(route.source),
        operation=route.operation.value,
        config_mode=route.config_mode,
        self_loads=route.self_loads,
        degraded=frozenset(str(c) for c in route.degraded),
        self_loaded_instruction_files=(),
        forbidden_params=tuple(guideline["forbidden_params"]) if guideline else (),
        legacy_prompt_phrases=tuple(guideline.get("legacy_prompt_phrases", ())) if guideline else (),
        incompatible_param_groups=tuple(tuple(g) for g in guideline.get("incompatible_param_groups", ()))
        if guideline
        else (),
        parameters={"model": route.model, "effort": route.effort.value},
    )


def build_context(  # noqa: PLR0913 -- atomic stage data and terminal metadata
    uow: UnitOfWork,
    ctx: Any,
    fenced: Any,
    selected: Any,
    step_id: Any,
    role: Any,
    profile_id: Any,
    route: Any,
    perms: Any,
    session: Any,
    *,
    steering: str | None = None,
) -> Any:
    loaded = load_effective_bundle(uow, fenced.run.id)
    wp = require_task_work_policy(uow, fenced.task.id)
    request = ContextRequest(
        fenced.run.workspace_id,
        fenced.run.project_id,
        fenced.run.plan_id,
        fenced.run.revision_id,
        fenced.task.spec_entity_id,
        workspace.get_project(uow, fenced.run.project_id).slug,
        ContextStepPurpose(
            role.value, selected.stage_id, str(step_id), fenced.attempt.attempt_no, selected.round_no
        ),
        profile_id,
        _runtime_target(uow, ctx, fenced, route, role, cast("PackPins", loaded.bundle.resource_pins.packs)),
        PermissionsSummary(
            tuple(f"{p.mount}:{p.pattern}" for p in fenced.task.granted_write_scope),
            ("repo:**",),
            (),
            (),
            perms.network.mode.value,
            tuple(sorted({h for group in perms.network.hosts for h in group})),
            (),
        ),
        RunParams(
            str(fenced.run.id),
            "pinned",
            fenced.attempt.attempt_no,
            selected.round_no,
            None,
            "integration_only",
            "notes",
            "auto",
            (),
        ),
        replace(execution_blocks(uow, fenced, selected, wp), operator_steering=steering),
        ResumeInfo(session.session_ref, digest({"entity": str(fenced.task.spec_entity_id)}))
        if isinstance(session, Resume)
        else None,
        "medium",
        (),
        loaded.bundle.resource_pins.packs,
    )
    instructions = task_instructions(uow, fenced.run)
    return assemble_draft(
        uow,
        ctx.gateways,
        request,
        config=ctx.config,
        owner_ref=f"step:{step_id}",
        actor=ctx.actor,
        inline_task=None if instructions is None else (instructions, fenced.task.work_kind),
    )


def context_host_limits(uow: UnitOfWork, run_id: Any) -> JsonObject:
    """Read work-chain limits from the run's frozen bundle, never the worker host chain."""
    _, values = effective_values(uow, run_id)
    return {
        "max_bytes": int(values["context.host_inputs.max_bytes"]),
        "max_work_paths": int(values["context.work_paths.max"]),
    }


def prepare_agent_step(
    uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any, selected: Any, secret: Any
) -> tuple[Any, Any]:
    repo = uow.repo(StepRepository)
    # A repair consumes its pinned instruction. Later live changes remain queued for the next step.
    repair = fenced.run.autopilot and is_repair(selected)
    pending = {} if repair else repo.live_controls(fenced.task.id)
    selected = controlled_selection(selected, pending)
    workflow = load_run_workflow(uow, fenced.run, fenced.task)
    role = agent_role(workflow, selected)
    view, profile, perms = profile_and_permissions(uow, ctx, fenced, selected, role)
    route, admission, request = route_agent(
        uow, ctx, fenced, selected, role, profile, perms, offered_runtimes=fenced.lease.offered_runtimes
    )
    session, fingerprint = session_decision(
        uow, ctx, fenced, selected, role, route, perms, force_fresh=bool(pending)
    )
    steering = pending.get("steer_task")
    step_id = ctx.ids.new_id()
    draft = build_context(
        uow,
        ctx,
        fenced,
        selected,
        step_id,
        role,
        view.resource_version_id,
        route,
        perms,
        session,
        steering=str(steering["instructions"]) if isinstance(steering, dict) else None,
    )
    previous = uow.repo(StepRepository).last_for_role(fenced.attempt.id, role)
    retry = selected.mode in {StageMode.RETRY, StageMode.RESUME_INTERRUPTED} or (
        selected.retry_of_id is not None or selected.feedback_refs.interrupted_stage_record_id is not None
    )
    origin = (
        previous.admission.get("emergency_origin", previous.started_at.isoformat())
        if retry and previous is not None
        else fenced.now.isoformat()
    )
    snapshot = route_snapshot(uow, fenced, route, request, view.resource_version_id)
    sequence = 1 + max(
        (
            s.seq
            for entry in uow.repo(StageRepository).history(fenced.attempt.id).entries
            for s in entry.steps
        ),
        default=0,
    )
    step = AttemptStep(
        step_id,
        fenced.attempt.id,
        stage.id,
        None if previous is None else previous.id,
        sequence,
        role,
        StepPurpose.RESULT_RETRY
        if selected.feedback_refs.schema_errors_step_id is not None
        else StepPurpose.PRIMARY,
        route.runtime_id,
        route.model,
        route.effort.value,
        route.operation.value,
        {
            **admission,
            **(
                {key: selected.params[key] for key in (REPAIR_ACTION_DIGEST, REPAIR_REVIEW_REQUIRED)}
                if repair
                else {}
            ),
            **(
                {"live_actor_profile": selected.params["operator_profile"]}
                if "override_actor" in pending
                else {}
            ),
            "emergency_origin": origin,
            "context_host_limits": context_host_limits(uow, fenced.run.id),
            "profile_key": view.key,
            **(
                {"fix_brief_id": str(selected.feedback_refs.fix_brief_id)}
                if selected.feedback_refs.fix_brief_id is not None
                else {}
            ),
            **(
                {"reviewer_with_fix": True}
                if role is RoleId.REVIEWER and selected.params.get("reviewer_with_fix") is True
                else {}
            ),
        },
        str(route.source),
        snapshot["route_reason"],
        draft.manifest_id,
        "resume" if isinstance(session, Resume) else "new",
        session.session_ref if isinstance(session, Resume) else None,
        fingerprint,
        digest(fingerprint),
        None if isinstance(session, Resume) else session.reason,
        StepState.STARTED,
        None,
        None,
        (),
        (),
        None,
        None,
        None,
        None,
        snapshot,
        None,
        None,
        None,
        None,
        None,
        fenced.now,
        None,
    )
    usage = estimate(
        uow,
        ctx,
        fenced,
        step,
        sum(b.tokens_estimate for b in draft.blocks),
        profile.limits.max_output_tokens or 0,
    )
    wanted = amounts(usage, review=role is RoleId.REVIEWER)
    reserve_step(uow, ctx, fenced, step, wanted, precheck=True)
    token = issue_step_token(uow, ctx, fenced, step, secret)
    step = replace(
        step,
        admission={
            **step.admission,
            "runtime_token": {
                "token_id": str(token.token_id),
                "permissions": list(token.permissions or ()),
                "scope_ancestors": [str(scope.id) for scope in ctx.scope_chain[:-1]],
            },
        },
    )
    uow.repo(StepRepository).add(step)
    reservations = reserve_step(uow, ctx, fenced, step, wanted)
    manifest = get_manifest(uow, draft.manifest_id)
    grant_inputs(
        uow,
        ctx,
        fenced,
        [
            UUID(b.source_ref.removeprefix("file_version:"))
            for b in manifest.blocks
            if b.source_kind == "file_version" and b.source_version is not None
        ],
    )
    payload = ready_step(uow, ctx, fenced, step, token=token, draft=draft, profile=profile, perms=perms)
    payload["budget_reservation_id"] = str(reservations[0].id) if reservations else None
    if pending:
        repo.save_live_controls(fenced.task.id, {})
    return step, payload


def ready_step(
    uow: UnitOfWork,
    ctx: Any,
    fenced: Any,
    step: Any,
    *,
    token: Any,
    draft: Any = None,
    profile: Any = None,
    perms: Any = None,
) -> dict[str, Any]:
    from types import SimpleNamespace

    if profile is None:
        selected = SimpleNamespace(
            params={
                "operator_profile": step.admission.get("live_actor_profile"),
                "profile": step.admission.get("profile_key"),
                "reviewer_with_fix": step.admission.get("reviewer_with_fix"),
            }
        )
        _, profile, perms = profile_and_permissions(uow, ctx, fenced, selected, step.role)
    manifest = get_manifest(uow, step.context_manifest_id)
    schema_errors = ()
    if step.purpose is StepPurpose.RESULT_RETRY and step.parent_step_id is not None:
        schema_errors = uow.repo(StepRepository).get(step.parent_step_id).schema_errors
    # Saved admission pins new steps; legacy active steps use their frozen run bundle.
    host_limits = step.admission.get("context_host_limits")
    if host_limits is None:
        host_limits = context_host_limits(uow, fenced.run.id)
    return {
        "step_id": str(step.id),
        "role": step.role.value,
        "purpose": step.purpose.value,
        "operation": step.operation,
        "admission": document(step.admission),
        "route_snapshot": document(step.route_snapshot),
        "route": {
            "runtime_id": step.runtime_id,
            "model": step.model,
            "effort": step.effort,
            "source": step.route_source,
            "reason": step.route_reason,
        },
        "context": {
            "manifest_id": str(step.context_manifest_id),
            "draft": document(draft),
            "host_inputs": document(manifest.host_inputs),
            "budget_policy": None if draft is None else document(draft.budget),
            "estimator_id": manifest.estimator_id,
            "host_limits": document(host_limits),
        },
        "result_schema_urn": ROLE_CONTRACTS[step.role].result_schema_urn,
        "result_contract": {
            "schema_urn": ROLE_CONTRACTS[step.role].result_schema_urn,
            "schema_errors": document(schema_errors),
        },
        "session": {
            "mode": step.session_mode,
            "resume_ref": step.session_ref,
            "fresh_reason": step.fresh_reason,
            "handoff": step.fresh_reason is not None and step.parent_step_id is not None,
        },
        "session_policy": document(
            session_policy_for(
                RuntimeRoleId(step.role.value),
                admission_policy(config=ctx.config),
                resume_mode=ctx.config.get("runtimes.session.resume"),
            )
        ),
        "limits": runtime_limits(
            uow,
            ctx,
            fenced,
            step.role,
            profile,
            started_at=parse_datetime(step.admission.get("emergency_origin", step.started_at.isoformat())),
        ),
        "permissions": permission_set_to_view(perms),
        "isolation_profile": profile.isolation,
        "runtime_token": {
            "token_id": str(token.token_id),
            "prefix": token.prefix,
            "expires_at": token.expires_at.isoformat(),
        },
    }
