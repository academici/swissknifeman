"""Pinned runtime routing, effective authority and session decisions."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any, Literal

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.execution.application._adhoc_spec import load_run_workflow
from skm.modules.execution.application._incident_gate import is_repair
from skm.modules.execution.application._json_reads import optional_text
from skm.modules.execution.application._live_control import controlled_selection
from skm.modules.execution.application._state import effective_values, load_state
from skm.modules.execution.application._worker_dtos import digest, document
from skm.modules.execution.application._worker_events import observed_binding
from skm.modules.execution.application._worker_inputs import brief_facts, task_route_and_contract
from skm.modules.execution.application.loaders import load_effective_bundle, require_task_work_policy
from skm.modules.execution.domain.attempt import SelectedStage
from skm.modules.execution.domain.role_contracts import ROLE_CONTRACTS
from skm.modules.execution.domain.session import RouteRef, SessionFacts, SessionFingerprint, decide_session
from skm.modules.execution.domain.stage_record import AGENT_STAGE_TYPES
from skm.modules.execution.domain.step import RoleId, is_output_author
from skm.modules.execution.domain.task import GATE_KINDS
from skm.modules.execution.domain.work_policy import remaining_emergency_seconds
from skm.modules.execution.domain.workflow.actions import Ctx
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.ports import (
    EnvironmentRepository,
    OutputRepository,
    StageRepository,
    StepRepository,
)
from skm.modules.extensions import public as extensions
from skm.modules.planning import public as planning
from skm.modules.policy.public import (
    effective_permissions,
    parse_layer,
    permissions_digest,
)
from skm.modules.runtimes.public import (
    AdmissionFacts,
    Capability,
    Effort,
    HostRoute,
    ModelClass,
    Operation,
    OperationContext,
    ResumeAllowance,
    RouteKey,
    RouteRequest,
    VerificationContext,
    admission_policy,
    admit,
    classify_operation,
    estimate_from_prompt,
    observed_model_family,
    route_role,
    usage_cost,
    verification_context_key,
    worker_installations,
)
from skm.modules.runtimes.public import (
    RoleId as RuntimeRoleId,
)
from skm.platform.config import ConfigLoader, ConfigStore, PackConfigSource, ScopeTree


@dataclass(frozen=True)
class _PreviousRoute:
    runtime_id: Any
    model: Any
    model_class: Any
    effort: Any
    session_ref: Any
    step_ref: Any


@dataclass(frozen=True, slots=True)
class _StageRoute:
    runtime_id: str
    model: str
    effort: Effort
    source: str
    catalog_digest: str
    operation: Operation
    resume_allowance: ResumeAllowance
    config_mode: Literal["isolated", "inherit"]
    self_loads: tuple[JsonObject, ...]
    degraded: frozenset[Capability]
    context_window_tokens: int
    runtime_version: str | None
    installation_details: Mapping[str, str]
    verification_context: VerificationContext | None
    requested_route: RouteKey | None


def agent_role(workflow: Any, selected: Any) -> RoleId:
    definition = next((item for item in workflow.stages if item.id == selected.stage_id), None)
    if definition is not None and definition.role is not None:
        return RoleId(definition.role.value)
    defaults = {"agent_review": "reviewer", "advisor_consult": "advisor"}
    return RoleId(
        selected.params.get("role")
        or defaults.get(selected.stage_type, "scout" if selected.stage_id == "scout" else "executor")
    )


def first_agent_after_prepare(uow: UnitOfWork, task: Any, workflow: Any, selected: Any, now: Any) -> Any:
    """Preview the next agent before preparation pins an otherwise free host."""
    state, _ = load_state(uow, task.id)
    workflow_ctx = Ctx(state, workflow, state.effective_policy, now)
    following = workflow_ctx.next_applicable(selected.stage_id)
    if following is None or following.type.value not in AGENT_STAGE_TYPES:
        return None
    return SelectedStage(
        stage_id=following.id,
        stage_type=following.type.value,
        params=following.params.as_json(),
        route_override=None,
        feedback_refs=FeedbackRefs(),
        mode=StageMode.NORMAL,
        round_no=1,
        not_before=None,
        input_output_id=None,
        retry_of_id=None,
    )


def stage_route_available(
    uow: UnitOfWork,
    ctx: Any,
    run: Any,
    task: Any,
    attempt: Any,
    worker: Any,
    *,
    offered_runtimes: frozenset[str] | None = None,
) -> bool:
    cursor = attempt.continuation
    if cursor is None or cursor.kind != "stage":
        return False
    selected = cursor.stage
    if selected.stage_type != "prepare_environment" and selected.stage_type not in AGENT_STAGE_TYPES:
        return True
    workflow = load_run_workflow(uow, run, task)
    if selected.stage_type == "prepare_environment":
        selected = first_agent_after_prepare(uow, task, workflow, selected, ctx.clock.now())
        if selected is None:
            return True
    if not (run.autopilot and is_repair(selected)):
        selected = controlled_selection(selected, uow.repo(StepRepository).live_controls(task.id))
    scope = ScopeRef(ScopeKind.RUN, ScopeId(run.id))
    config = ConfigLoader(ctx.config.registry, uow.repo(PackConfigSource)).effective(
        uow.repo(ConfigStore), uow.repo(ScopeTree), scope
    )
    scoped = replace(ctx, config=config, scope=scope, scope_chain=uow.repo(ScopeRegistry).ancestors(scope.id))
    fenced = SimpleNamespace(run=run, task=task, attempt=attempt, worker=worker, now=ctx.clock.now())
    role = agent_role(workflow, selected)
    try:
        _, profile, perms = profile_and_permissions(uow, scoped, fenced, selected, role)
        route_agent(uow, scoped, fenced, selected, role, profile, perms, offered_runtimes=offered_runtimes)
    except SkmError as exc:
        if exc.code not in {
            ErrorCode.CAPABILITY_UNAVAILABLE,
            ErrorCode.ROUTE_UNDERSHOOT,
            ErrorCode.ADMISSION_REFUSED,
            ErrorCode.CONFIG_INVALID,
            ErrorCode.EXTENSION_INCOMPATIBLE,
            ErrorCode.EXTENSION_PROFILE_ROLE_MISMATCH,
        }:
            raise
        return False
    return True


def profile_and_permissions(
    uow: UnitOfWork, ctx: Any, fenced: Any, selected: Any, role: Any
) -> tuple[Any, Any, Any]:
    loaded: Any = load_effective_bundle(uow, fenced.run.id)
    view: Any = extensions.select_agent_profile(
        uow,
        role.value,
        stage_profile=selected.params.get("operator_profile")
        or (
            fenced.task.review_profile
            if role.value == "reviewer" and fenced.run.kind.value == "review_request"
            else selected.params.get("profile")
        ),
        config=ctx.config,
        pins=loaded.bundle.resource_pins.packs,
    )
    profile = extensions.load_agent_profile(uow, view.resource_version_id)
    role_layer = (
        None if profile.permissions.layer is None else parse_layer(profile.permissions.layer, source="role")
    )
    review_fix = role is RoleId.REVIEWER and selected.params.get("reviewer_with_fix") is True
    if review_fix and (
        fenced.task.kind in GATE_KINDS
        or fenced.run.kind.value == "review_request"
        or selected.params.get("audit_scope") == "range"
        or not fenced.task.granted_write_scope
    ):
        raise error_for(ErrorCode.CONFIG_INVALID, "reviewer_with_fix requires a writable task output")
    scope = [
        {"scope": "worktree", "mount": p.mount, "pattern": p.pattern}
        for p in fenced.task.granted_write_scope
        if role is not RoleId.REVIEWER or review_fix
    ]
    task_layer = parse_layer({"fs": {"write": {"allow": scope}}}, source="task")
    perms = effective_permissions(
        uow,
        scope_chain=ctx.scope_chain,
        config=ctx.config,
        profile_id=profile.permissions.policy_profile,
        role_layer=role_layer,
        task_layer=task_layer,
        allow_unconfined=False,
    )
    return view, profile, perms


def live_step_profile_and_permissions(
    uow: UnitOfWork, ctx: Any, fenced: Any, step: Any
) -> tuple[Any, Any, Any]:
    return profile_and_permissions(
        uow,
        ctx,
        fenced,
        SimpleNamespace(
            params={
                "operator_profile": step.admission.get("live_actor_profile"),
                "profile": step.admission.get("profile_key"),
                "reviewer_with_fix": step.admission.get("reviewer_with_fix"),
            }
        ),
        step.role,
    )


def route_agent(
    uow: UnitOfWork,
    ctx: Any,
    fenced: Any,
    selected: Any,
    role: RoleId,
    profile: Any,
    perms: Any,
    *,
    offered_runtimes: frozenset[str] | None = None,
) -> tuple[_StageRoute, Any, RouteRequest]:
    previous = uow.repo(StepRepository).last_for_role(fenced.attempt.id, role)
    first = uow.repo(StepRepository).first_writing(fenced.attempt.id)
    wp = require_task_work_policy(uow, fenced.task.id)
    planned, contract = task_route_and_contract(uow, fenced, wp.digest)

    def prior(step: Any) -> Any:
        if step is None:
            return None
        return _PreviousRoute(
            runtime_id=step.runtime_id,
            model=step.model,
            model_class=ModelClass(step.admission["min_class"]),
            effort=Effort(step.effort or "high"),
            session_ref=step.session_ref,
            step_ref=str(step.id),
        )

    operation = classify_operation(
        OperationContext(
            RuntimeRoleId(role.value),
            bool(selected.params.get("final")),
            selected.feedback_refs.fix_brief_id is not None,
            fenced.attempt.current_output_id is not None,
            previous is not None and previous.admission.get("contract_digest") != contract,
        )
    )
    facts = AdmissionFacts(
        operation,
        RuntimeRoleId(role.value),
        None if planned is None else ModelClass(planned.model_class.value),
        None if planned is None else Effort(planned.effort.value),
        prior(first),
        prior(previous),
        contract,
        None
        if previous is None
        else optional_text(previous.admission.get("contract_digest"), "admission.contract_digest"),
        brief_facts(uow, fenced, selected),
        None if fenced.attempt.current_output_id is None else str(fenced.attempt.current_output_id),
    )
    admission = admit(facts, admission_policy(config=ctx.config))
    model_class, effort = ModelClass(profile.model_class), Effort(profile.effort)
    if (
        admission.operation is Operation.BOUNDED_FIX
        and planned is not None
        and planned.correction is not None
    ):
        # Correction floors apply only after admission has confirmed the bounded operation.
        # route_role still enforces the admission/task floor and all explicit route pins.
        model_class = max(
            model_class, ModelClass(planned.correction.model_class.value), key=tuple(ModelClass).index
        )
        effort = max(effort, Effort(planned.correction.effort.value), key=tuple(Effort).index)
    override = selected.route_override
    loaded, values = effective_values(uow, fenced.run.id)
    frozen_allowed = values.get("runtimes.allowed")
    worker_runtimes = frozenset(fenced.worker.capabilities.runtimes)
    if offered_runtimes is not None:
        worker_runtimes &= offered_runtimes
    executor_runtimes, executor_families = observed_executor_routes(uow, fenced, role)
    req = RouteRequest(
        RuntimeRoleId(role.value),
        frozenset(Capability(c) for c in profile.required_capabilities),
        frozenset(Capability(c) for c in profile.optional_capabilities),
        model_class,
        effort,
        override.runtime_id if override is not None else None if planned is None else planned.runtime,
        override.model if override is not None else None if planned is None else planned.model,
        fenced.worker.host_id,
        admission,
        "isolated",
        frozenset(),
        perms.network.mode.value != "none" and role is not RoleId.EXECUTOR,
        policy_profile=profile.permissions.policy_profile,
        isolation_profile=profile.isolation,
        worker_runtimes=worker_runtimes,
        worker_id=fenced.worker.worker_id,
        work_allowed=None if frozen_allowed is None else frozenset(frozen_allowed),
        executor_runtimes=executor_runtimes,
        executor_families=executor_families,
    )
    route = route_role(
        uow, ctx.gateways, req, config=ctx.config, pins=loaded.bundle.resource_pins.packs, as_of=fenced.now
    )
    if isinstance(route, HostRoute):
        installation, verification = route.installation, route.verification_context
    else:
        installation = next(
            (
                i
                for i in worker_installations(uow, fenced.worker.worker_id, as_of=fenced.now)
                if i.host_id == req.host_id and i.runtime_id == route.runtime_id
            ),
            None,
        )
        if installation is None:
            raise error_for(ErrorCode.CAPABILITY_UNAVAILABLE, "the resolved host runtime is not installed")
        verification = None
    admission_doc = {**document(admission), "contract_digest": contract}
    if verification is not None:
        admission_doc["verification_context"] = {
            **document(verification),
            "runtime_version": installation.version,
        }
    stage_route = _StageRoute(
        runtime_id=route.runtime_id,
        model=route.model,
        effort=route.effort,
        source=route.source,
        catalog_digest=route.catalog_digest,
        operation=route.operation,
        resume_allowance=route.resume_allowance,
        config_mode=route.config_mode,
        self_loads=tuple(document(load) for load in route.self_loads),
        degraded=route.degraded,
        context_window_tokens=route.context_window_tokens,
        runtime_version=installation.version,
        installation_details=installation.details,
        verification_context=verification,
        requested_route=route.requested_route,
    )
    return stage_route, admission_doc, req


def observed_executor_routes(
    uow: UnitOfWork, fenced: Any, role: RoleId
) -> tuple[frozenset[str], frozenset[str]]:
    if role is not RoleId.REVIEWER or fenced.run.revision_id is None:
        return frozenset(), frozenset()
    spec = planning.get_revision_specification(uow, fenced.run.revision_id)
    entity = fenced.task.spec_entity_id
    review = None if entity is None else spec.review_requirement_for(entity)
    if getattr(review, "independence", None) != "separate_runtime":
        return frozenset(), frozenset()
    output_id = fenced.attempt.current_output_id
    output_producer = (
        None if output_id is None else uow.repo(OutputRepository).get(output_id).produced_by_step_id
    )
    bindings = [
        binding
        for entry in uow.repo(StageRepository).history(fenced.attempt.id).entries
        for step in entry.steps
        if is_output_author(step, output_producer)
        if (binding := observed_binding(step.route_snapshot, step.runtime_observation)) is not None
    ]
    return (
        frozenset(binding["runtime_id"] for binding in bindings),
        frozenset(
            family
            for binding in bindings
            if (family := observed_model_family(binding["runtime_id"], binding["provider_reported_model"]))
            is not None
        ),
    )


def route_snapshot(
    uow: UnitOfWork, fenced: Any, route: _StageRoute, req: RouteRequest, profile_id: Any
) -> dict[str, Any]:
    loaded: Any = load_effective_bundle(uow, fenced.run.id)
    details = route.installation_details
    verification = route.verification_context
    reason = {
        "role_fallback": "ROUTE_FALLBACK",
        "previous_route": "ROUTE_DEFAULT",
        "plan_route": "ROUTE_OVERRIDE",
        "host_substitution": "ROUTE_FALLBACK",
    }.get(str(route.source), "ROUTE_DEFAULT")
    selected = {"runtime_id": route.runtime_id, "model": route.model, "effort": route.effort.value}
    requested = route.requested_route
    return {
        "requested": {
            "runtime_id": req.explicit_runtime,
            "model": req.explicit_model,
            "model_class": req.model_class.value,
            "effort": req.effort.value,
        },
        "resolved": selected,
        "requested_route": selected
        if requested is None
        else {
            "runtime_id": requested.runtime_id,
            "model": requested.model_id,
            "effort": requested.effort.value,
        },
        "selected_route": selected,
        "route_source": str(route.source),
        "route_reason": reason,
        "host_id": str(fenced.worker.host_id),
        "executable_sha256": (
            (details.get("executable_sha256") or details.get("binary_sha256"))
            if verification is None
            else verification.binary_sha256
        ),
        "verification_key": None if verification is None else verification_context_key(verification),
        "runtime_version": route.runtime_version,
        "adapter_version": details.get("adapter_version")
        if verification is None
        else verification.adapter_version,
        "catalog_digest": route.catalog_digest,
        "profile_version_id": str(profile_id),
        "effective_config_digest": loaded.effective_config_digest,
        "reconfiguration_ids": [str(r) for r in loaded.reconfiguration_ids],
    }


def session_decision(
    uow: UnitOfWork,
    ctx: Any,
    fenced: Any,
    selected: Any,
    role: Any,
    route: Any,
    perms: Any,
    *,
    force_fresh: bool = False,
) -> tuple[Any, Any]:
    env = uow.repo(EnvironmentRepository).for_attempt(fenced.attempt.id)
    if env is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "agent stage requires a prepared environment")
    fingerprint = SessionFingerprint(
        route.runtime_id,
        fenced.run.project_id,
        env.id,
        role,
        fenced.attempt.id,
        digest(
            {
                "entity": str(fenced.task.spec_entity_id),
                "scope": document(fenced.task.declared_write_scope),
                "role": role.value,
                "result": ROLE_CONTRACTS[role].result_schema_urn,
            }
        ),
        permissions_digest(perms),
        RouteRef(route.runtime_id, route.model, route.effort.value),
        fenced.attempt.current_output_id,
    )
    previous = uow.repo(StepRepository).last_for_role(fenced.attempt.id, role)
    usage = None if previous is None else previous.usage
    tokens = (
        None
        if usage is None or usage.input_tokens is None
        else usage.input_tokens + (usage.output_tokens or 0)
    )
    facts = SessionFacts(
        previous,
        route.resume_allowance.allowed,
        tokens,
        int(ctx.config.get("execution.session.max_resume_context_tokens") or 120000),
        selected.mode,
        route.resume_allowance,
        previous is not None and selected.retry_of_id == previous.stage_record_id,
        None if previous is None else previous.error_code,
        frozenset(),
    )
    return decide_session(fingerprint, facts, force_fresh=force_fresh), fingerprint


def estimate(uow: UnitOfWork, ctx: Any, fenced: Any, step: Any, tokens: int, output_limit: int) -> Any:
    usage = estimate_from_prompt(tokens, output_limit)
    loaded: Any = load_effective_bundle(uow, fenced.run.id)
    return usage_cost(
        uow, usage, step.runtime_id, step.model, config=ctx.config, pins=loaded.bundle.resource_pins.packs
    )


def runtime_limits(
    uow: UnitOfWork, ctx: Any, fenced: Any, role: Any, profile: Any, *, started_at: Any
) -> dict[str, Any]:
    wp = require_task_work_policy(uow, fenced.task.id)
    role_ceilings: Any = ctx.config.get("execution.timeouts.role_wall_seconds") or {}
    remaining = remaining_emergency_seconds(
        wp,
        role.value,
        started_at=started_at,
        now=fenced.now,
        extra_ceilings=(
            profile.limits.timeout_seconds,
            int(role_ceilings.get(role.value, 0)),
            int(ctx.config.get("execution.timeouts.step_wall_seconds") or 0),
        ),
    )
    return {
        "timeout_seconds": remaining,
        "idle_timeout_seconds": profile.limits.idle_timeout_seconds,
        "max_output_tokens": profile.limits.max_output_tokens,
        "max_turns": profile.limits.max_turns,
    }
