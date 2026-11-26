"""Capture a prospective run from public facades in one UoW (K14, K19)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, cast
from uuid import UUID, uuid5

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.ids import ResourceVersionId, RunId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeRef
from skm.modules.access import public as access
from skm.modules.context.public import design_research_evidence
from skm.modules.execution.application._plain import plain
from skm.modules.execution.application._preview_facts import gate_facts, material_facts, progressive_facts
from skm.modules.execution.domain.execution_bundle import ResourcePin, ResourcePins
from skm.modules.execution.domain.readiness import (
    PROGRESSIVE_MODE,
    ReadinessSnapshot,
    canonical_start_request,
    design_research_refs,
    snapshot_readiness_inputs,
)
from skm.modules.execution.domain.task_graph import SelectionRequest, compile_run_tasks
from skm.modules.execution.domain.work_policy import (
    ROLE_NAMES,
    HardCeilings,
    Intensity,
    SettingSource,
    WorkPolicyOverride,
    WorkPolicySettings,
    resolve_work_policy,
    work_policy_to_json,
)
from skm.modules.execution.domain.workflow.definition import StageDefinition, applies_to_kind, parse_workflow
from skm.modules.execution.ports import AutopilotRepository
from skm.modules.extensions import public as extensions
from skm.modules.planning import public as planning
from skm.modules.policy.public import effective_permissions as policy_permissions
from skm.modules.policy.public import permissions_digest
from skm.modules.runtimes.public import (
    Admission,
    Capability,
    Effort,
    ModelClass,
    Operation,
    ResumePolicy,
    RoleId,
    RouteRequest,
    route_role,
)
from skm.modules.workspace import public as workspace
from skm.platform.config.effective import ProcessConfig
from skm.platform.config.keys import Level, MergeStrategy
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.merge import narrow_widens
from skm.platform.config.resolver import resolve
from skm.platform.config.scopes import ScopeChain
from skm.platform.config.scopes import ScopeRef as ConfigScope


def value(config: Any, key: str, default: Any = None) -> Any:
    return config.get(key) if key in config.resolved_keys() else default


def prospective_config(
    config: Any, overrides: Any, *, parent_id: Any, uow: UnitOfWork | None = None, actor: Any = None
) -> Any:
    overrides = dict(overrides or {})
    if (
        overrides
        and uow is not None
        and "config.write" not in access.effective_permissions(uow, actor, ScopeId(parent_id))
    ):
        raise error_for(ErrorCode.FORBIDDEN, "run overrides require config.write")
    scope_id = uuid5(UUID(str(parent_id)), "readiness-prospective-run")
    scopes = (
        *tuple(s for s in config.chain.scopes if s.level is not Level.RUN),
        ConfigScope(Level.RUN, scope_id),
    )
    grouped: dict[Any, dict[str, Any]] = {}
    process_values: dict[str, Any] = {}
    has_process = False

    def group_ref(ref: Any) -> Any:
        label = ref.level.value if ref.scope_id is not None else ref.label
        return LayerRef(ref.level, ref.scope_id, label, ref.pack_id, ref.pack_priority, ref.source)

    for key in config.resolved_keys():
        for trace in config.resolution(key).trace:
            contribution = trace.contribution
            if contribution.layer.level is Level.PROCESS:
                has_process = True
                if config.present(key):
                    process_values[key] = config.get(key)
            elif contribution.layer.level is not Level.RUN:
                grouped.setdefault(group_ref(contribution.layer), {})[key] = contribution
    for scope in scopes:
        grouped.setdefault(LayerRef(scope.level, scope.scope_id, scope.level.value), {})
    layer_ref = LayerRef(Level.RUN, scope_id, "run")
    for key, requested in overrides.items():
        spec = config.registry.spec(key)
        if Level.RUN not in spec.levels:
            raise error_for(
                ErrorCode.CONFIG_SCOPE_NOT_ALLOWED,
                "key cannot be overridden at run level",
                details={"key": key},
            )
        if config.resolution(key).locked_by is not None or (
            spec.merge is MergeStrategy.NARROW and narrow_widens(spec, config.get(key), requested)
        ):
            raise error_for(
                ErrorCode.FORBIDDEN, "override exceeds a current lock or ceiling", details={"key": key}
            )
        grouped.setdefault(layer_ref, {})[key] = Contribution(layer_ref, "set", requested)
    rank = {level: i for i, level in enumerate(Level)}
    layers = [
        Layer(ref, contributions)
        for ref, contributions in sorted(
            grouped.items(),
            key=lambda item: (
                rank[item[0].level],
                item[0].pack_priority or 0,
                0 if item[0].source == "env" else 2 if item[0].source == "cli" else 1,
            ),
        )
    ]
    resolved = resolve(
        config.registry,
        ScopeChain(config.chain.kind, scopes),
        layers,
        generation=config.generation,
        pack_generation=config.pack_generation,
    )
    if not has_process:
        return resolved
    # PROCESS is selected provenance, not an input layer. Preserve its chosen restart
    # values after resolving the legal run layer, including pending restart changes.
    process_generation = next(
        (
            d.details["process_generation"]
            for d in config.diagnostics
            if d.code == "CONFIG_RESTART_PENDING" and d.details is not None
        ),
        config.generation,
    )
    return resolved.with_overrides(
        process=ProcessConfig(
            work=process_values,
            host={},
            generation=process_generation,
            instance_scope_id=config.chain.scopes[0].scope_id,
        )
    )


def resource_body(uow: UnitOfWork, version_id: Any) -> Any:
    # The extensions owner validates and parses versioned manifests on ingestion.
    # Control-plane code reads that immutable document, without parsing source files.
    return plain(extensions.get_resource_version(uow, version_id).manifest)


def load_workflow(uow: UnitOfWork, version_id: Any) -> Any:
    workflow, errors = parse_workflow(resource_body(uow, version_id))
    if errors or workflow is None:
        raise error_for(
            ErrorCode.CONFIG_INVALID, "pinned workflow is invalid", details={"violations": plain(errors)}
        )
    return workflow


POLICY_ALIASES = {
    "budgets.task.max_attempts": "attempts_max",
    "execution.parallel.max_units": "parallel_max_units",
    "execution.review.max_rounds": "review_max_rounds",
    "execution.rework.max_rounds": "rework_max_rounds",
    "execution.kill_switch": "kill_switch",
    "execution.run.on_task_failed": "on_task_failed",
    "execution.review.strategy": "review_strategy",
    "execution.review.grouping": "review_grouping",
    "execution.gates.phase_review": "phase_review",
    "execution.scout.mode": "scout_mode",
    "execution.research.policy": "research_policy",
    "execution.review.final_correction": "review_final_correction",
    "execution.review.accept_findings_only": "review_accept_findings_only",
    "execution.review.attention_policy": "review_attention_policy",
    "execution.review.followups_max": "followups_max",
    "execution.review.risk.threshold": "risk_threshold",
    "execution.review.risk.weights": "risk_weights",
    "execution.review.risk.patterns": "risk_patterns",
    "execution.review.risk.diff_lines": "risk_diff_lines",
    "execution.review.risk.critical": "risk_critical",
    "execution.scope.outside_policy": "scope_outside_policy",
    "execution.integration.rerun_checks": "integration_rerun_checks",
    "execution.step.max_result_retries": "step_max_result_retries",
    "execution.step.max_infra_retries": "step_max_infra_retries",
    "execution.checks.error_retries": "checks_error_retries",
    "execution.advisor.enabled": "advisor_enabled",
    "execution.advisor.max_rounds": "advisor_max_rounds",
    "execution.advisor.human_gate": "human_gate",
    "execution.advisor.min_confidence": "advisor_min_confidence",
    "execution.autonomy.question_policy": "question_policy",
    "execution.autonomy.max_questions_per_task": "max_questions_per_task",
    "execution.autonomy.category_audience": "category_audience",
    "execution.retry.provider_wait_max_seconds": "retry_provider_wait_max_seconds",
    "execution.retry.budget_total_max": "retry_budget_total_max",
}


def policy_from_values(values: Any) -> dict[str, Any]:
    policy = {alias: plain(values[key]) for key, alias in POLICY_ALIASES.items() if key in values}
    policy["retry"] = {
        name: plain(values["execution.retry." + name])
        for name in ("on_error", "fallback_routes")
        if "execution.retry." + name in values
    }
    return policy


def execution_policy(config: Any) -> dict[str, Any]:
    return policy_from_values(
        {
            key: config.get(key)
            for key in (*POLICY_ALIASES, "execution.retry.on_error", "execution.retry.fallback_routes")
            if key in config.resolved_keys()
        }
    )


def pin_workflow_inputs(
    uow: UnitOfWork,
    cfg: Any,
    packs: extensions.PackPins,
    stages: Sequence[StageDefinition],
    workflow_pin: ResourcePin,
    *,
    ctx: Any = None,
) -> tuple[ResourcePins, dict[str, Any], dict[str, Any], dict[str, Any]]:
    resources = [workflow_pin]
    profiles: dict[str, Any] = {}
    routing: dict[str, Any] = {}
    requirements: dict[str, Any] = {}
    role_profiles = sorted({(s.role.value, s.params.profile or "") for s in stages if s.role is not None})
    for role, stage_profile in role_profiles:
        profile_view = extensions.select_agent_profile(
            uow, role, stage_profile=stage_profile or None, config=cfg, pins=packs
        )
        profile = extensions.load_agent_profile(uow, ResourceVersionId(profile_view.resource_version_id))
        if role not in profiles or profile.limits.timeout_seconds < profiles[role].limits.timeout_seconds:
            profiles[role] = profile
        resources.append(
            ResourcePin(
                "agent_profile",
                profile_view.key,
                ResourceVersionId(profile_view.resource_version_id),
                profile_view.digest,
            )
        )
        requirements[role + ":" + profile_view.key] = {
            "capabilities": sorted(profile.required_capabilities),
            "class": profile.model_class,
            "effort": profile.effort,
        }
        for keys in profile.prompt.blocks.values():
            for key in keys:
                block = extensions.resolve_resource(
                    uow, extensions.ResourceKind.PROMPT_BLOCK, key, config=cfg, pins=packs
                )
                resources.append(
                    ResourcePin(
                        "prompt_block", key, ResourceVersionId(block.resource_version_id), block.digest
                    )
                )
        if ctx is None:
            continue
        operation = Operation.REVIEW if role == "reviewer" else Operation.NEW_IMPLEMENTATION
        admission = Admission(
            operation,
            operation,
            ModelClass(profile.model_class),
            Effort(profile.effort),
            (),
            frozenset(Capability(c) for c in profile.required_capabilities),
            ResumePolicy.NEVER,
            None,
            (),
        )
        req = RouteRequest(
            RoleId(role),
            admission.required_capabilities,
            frozenset(Capability(c) for c in profile.optional_capabilities),
            admission.min_class,
            Effort(profile.effort),
            None,
            None,
            None,
            admission,
            "isolated",
            frozenset(),
            False,
            profile.permissions.policy_profile,
        )
        try:
            route_role(uow, ctx.gateways, req, config=cfg, pins=packs)
            routing.setdefault(role, {"available": True})
        except SkmError:
            routing[role] = {"available": False}
    pins = ResourcePins(tuple({(p.kind, p.key): p for p in resources}.values()), packs)
    return pins, profiles, routing, requirements


def work_policy_inputs(cfg: Any, profiles: Mapping[str, Any]) -> tuple[WorkPolicySettings, HardCeilings]:
    role_int: Any = value(cfg, "execution.work_policy.role_intensity")
    if not isinstance(role_int, Mapping) or set(cast("Mapping[str, Any]", role_int)) != set(ROLE_NAMES):
        raise error_for(ErrorCode.CONFIG_INVALID, "complete work policy settings are required")
    sources: dict[str, Any] = {}
    locks: dict[str, Any] = {}
    for name in ("role_intensity", "verification_intensity"):
        provenance = cfg.provenance("execution.work_policy." + name)
        sources[name] = SettingSource(
            "settings", provenance.winner.display if provenance.winner else "default"
        )
        if provenance.locked_by is not None:
            locks[name] = provenance.locked_by.display
    settings = WorkPolicySettings(
        {r: Intensity(role_int[r]) for r in ROLE_NAMES},
        Intensity(value(cfg, "execution.work_policy.verification_intensity")),
        value(cfg, "execution.work_policy.role_warn_seconds"),
        value(cfg, "execution.work_policy.repro_warn_seconds"),
        sources,
        locks,
    )
    ceilings = HardCeilings(
        {r: p.limits.timeout_seconds for r, p in profiles.items()},
        value(cfg, "execution.timeouts.role_wall_seconds", {}),
        value(cfg, "execution.timeouts.step_wall_seconds"),
    )
    return settings, ceilings


@dataclass(frozen=True)
class PreparedStart:
    meta: Any
    spec: Any
    graph: Any
    workflow: Any
    workflow_id: Any
    config: Any
    frozen: Any
    policy: Any
    pins: Any
    compiled: Any
    policies: Any
    request: Any
    inputs: Any
    evaluation: Any
    visa_required: bool


def prepare_inputs(  # noqa: PLR0913 -- prospective request and observation options
    uow: UnitOfWork,
    ctx: Any,
    plan_id: Any,
    revision_id: Any,
    overrides: Any,
    selection: Any,
    *,
    workflow_key: str | None = None,
    mode: Any = None,
    read_only: bool = False,
) -> PreparedStart:
    planning.get_plan_ref(uow, plan_id) if read_only else planning.require_active_plan(uow, plan_id)
    meta = planning.get_revision_meta(uow, revision_id)
    if meta.plan_id != plan_id:
        raise error_for(ErrorCode.NOT_FOUND, "revision does not belong to the authorized plan")
    workspace.require_active_project(uow, meta.project_id)
    if meta.project_id in uow.repo(AutopilotRepository).emergency_project_ids():
        raise error_for(ErrorCode.EMERGENCY_STOPPED, "project emergency stop")
    request: Any = canonical_start_request(dict(overrides or {}), plain(selection), mode=mode)
    cfg = prospective_config(
        ctx.config, overrides, parent_id=plan_id, uow=None if read_only else uow, actor=ctx.actor
    )
    frozen = cfg.freeze(cfg.registry)
    packs = extensions.pinned_pack_versions(uow, config=cfg)
    wf_view = extensions.resolve_resource(
        uow,
        extensions.ResourceKind.WORKFLOW,
        workflow_key or value(cfg, "execution.workflow.profile", "reviewed-development"),
        config=cfg,
        pins=packs,
    )
    wf = load_workflow(uow, wf_view.resource_version_id)
    spec = planning.get_revision_specification(uow, revision_id)
    source = planning.compile_execution_graph(spec, revision_id)
    graph = plain(source)
    for task in graph["tasks"]:
        task["phase"] = task.pop("phase_key")
        task["item"] = task.pop("item_key")
    for group in graph["batch_groups"]:
        group["phase"] = group.pop("phase_key")
        group["batch"] = group.pop("batch_key")
    policy_doc = execution_policy(cfg)
    selected = (
        None
        if request["selection"] is None
        else SelectionRequest(
            tuple(request["selection"]["task_keys"]),
            tuple(request["selection"]["phases"]),
            request["selection"].get("stop_after"),
        )
    )
    counter = iter(range(1, 100000))
    compiled = compile_run_tasks(
        graph,
        wf,
        policy_doc,
        selected,
        {},
        run_id=RunId(uuid5(plan_id, "preview")),
        workspace_id=meta.workspace_id,
        revision_id=revision_id,
        new_task_id=lambda: UUID(int=next(counter)),
        now=ctx.clock.now(),
    )
    stages = wf.stages
    if request.get("mode") == PROGRESSIVE_MODE:
        kinds = {task.kind for task in compiled.tasks}
        stages = [stage for stage in stages if any(applies_to_kind(stage, kind) for kind in kinds)]
    roles = sorted({stage.role.value for stage in stages if stage.role is not None})
    workflow_pin = ResourcePin(
        "workflow", wf_view.key, ResourceVersionId(wf_view.resource_version_id), wf_view.digest
    )
    pins, profiles, routing, requirements = pin_workflow_inputs(
        uow, cfg, packs, wf.stages, workflow_pin, ctx=ctx
    )
    routing = {role: routing[role] for role in roles if role in routing}
    settings, ceilings = work_policy_inputs(cfg, profiles)
    policies = {"@default": resolve_work_policy(settings, ceilings=ceilings)}
    by_key = {t["task_key"]: t for t in graph["tasks"]}
    for task in compiled.tasks:
        raw = by_key.get(task.display_key, {})
        policies[task.display_key] = resolve_work_policy(
            settings,
            item=WorkPolicyOverride.from_json(raw.get("item_work_policy")),
            unit=WorkPolicyOverride.from_json(raw.get("unit_work_policy")),
            ceilings=ceilings,
            item_ref=str(raw.get("item", task.display_key)),
            unit_ref=task.display_key,
        )
    permission_set = policy_permissions(
        uow,
        scope_chain=tuple(ScopeRef(s.kind, s.id) for s in ctx.scope_chain),
        config=cfg,
        profile_id=None,
        role_layer=None,
        task_layer=None,
        allow_unconfined=False,
    )
    policy_digest = permissions_digest(permission_set)
    material_refs = planning.revision_materials(uow, revision_id)
    tasks_for_rules = gate_facts(compiled, graph, wf, spec)
    doc = plain(spec)
    readiness_graph = graph
    if request.get("mode") == PROGRESSIVE_MODE:
        doc, readiness_graph, tasks_for_rules, material_refs = progressive_facts(
            doc, graph, tasks_for_rules, compiled, material_refs, set(request["selection"]["phases"])
        )
    materials = material_facts(uow, meta.workspace_id, material_refs, ctx.clock.now())
    query_ids = tuple(
        dict.fromkeys(query_id for item in doc["items"] for query_id in (design_research_refs(item) or ()))
    )
    design_evidence = (
        design_research_evidence(replace(ctx, config=cfg), uow, meta.workspace_id, meta.project_id, query_ids)
        if query_ids
        else {}
    )
    material_inputs: JsonObject = {"materials": materials, "design_research_evidence": design_evidence}
    visa_required = False
    if spec.design_brief_id is not None:
        brief = planning.get_design_brief(uow, plan_id, spec.design_brief_id)
        visa_required = brief.visa_policy == "required"
        material_inputs["design_brief"] = {
            **({"visa_policy": "required"} if visa_required else {}),
            "id": str(brief.id),
            "goal": brief.goal,
            "context_md": brief.context_md,
            "constraints": list(brief.constraints),
            "rag_file_version_ids": plain(brief.rag_file_version_ids),
            "research_references": plain(brief.research_references),
        }
    snapshot = ReadinessSnapshot(
        doc,
        readiness_graph,
        request["selection"],
        tuple(t.display_key for t in compiled.tasks),
        {},
        requirements,
        policy_digest,
        frozen.to_document(),
        plain(pins),
        material_inputs,
        request,
        policies,
    )
    inputs = snapshot_readiness_inputs(snapshot)
    evaluation = {
        **doc,
        "tasks": tasks_for_rules,
        "edges": readiness_graph["edges"],
        "routing": routing,
        "required_roles": roles,
        "policy_live_ok": not value(cfg, "execution.kill_switch", False),
        "compiled_keys": list(policies),
        "work_policies": {k: work_policy_to_json(p) for k, p in policies.items()},
        "material_inputs": plain(inputs),
        "materials": materials,
        "design_research_evidence": design_evidence,
        "start_request": request,
        "require_coverage": value(cfg, "execution.readiness.require_coverage", False),
        "require_acceptance_links": value(cfg, "planning.validation.require_acceptance_links", True),
    }
    return PreparedStart(
        meta,
        spec,
        graph,
        wf,
        wf_view.resource_version_id,
        cfg,
        frozen,
        policy_doc,
        pins,
        compiled,
        policies,
        request,
        inputs,
        evaluation,
        visa_required,
    )
