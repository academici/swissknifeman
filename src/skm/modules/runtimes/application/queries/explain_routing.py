"""``runtimes.explain_routing`` (runtimes §8): dry-run admission and routing explanation."""

from __future__ import annotations

from collections.abc import Mapping

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import NotFound, SkmError
from skm.kernel.generated.defs import ScopeRefDto
from skm.kernel.ids import HostId, ResourceVersionId, ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.extensions import public as extensions
from skm.modules.runtimes.domain.admission import (
    Admission,
    AdmissionFacts,
    AdmissionPolicy,
    FixBriefFacts,
    Operation,
    OperationContext,
    admit,
    classify_operation,
)
from skm.modules.runtimes.domain.capability import Capability, config_mode_for
from skm.modules.runtimes.domain.classes import Effort, ModelClass, RoleId
from skm.modules.runtimes.domain.routing import RouteDecision, RouteRequest
from skm.modules.runtimes.generated.queries import ExplainRouting
from skm.modules.runtimes.generated.views import RoleId as ViewRoleId
from skm.modules.runtimes.generated.views import (
    RouteExplainView,
    RouteExplainViewError,
)
from skm.modules.runtimes.public import admission_policy, route_role

__all__ = ["SPEC", "handle"]

_EXPLAIN_CONTRACT_DIGEST = "sha256:" + "0" * 64


def _scope_of(query: ExplainRouting) -> ScopeRef | None:
    if query.scope.kind == "instance":
        return None
    return ScopeRef(ScopeKind(query.scope.kind), ScopeId(query.scope.id))


def _resolve_profile(
    uow: UnitOfWork,
    role: RoleId,
    query: ExplainRouting,
    ctx: QueryContext,
) -> tuple[ModelClass, Effort, frozenset[Capability], frozenset[Capability], bool, str | None, str | None]:
    profile: extensions.AgentProfile | None = None
    if query.profile_key is not None:
        view = extensions.resolve_resource(
            uow,
            extensions.ResourceKind.AGENT_PROFILE,
            query.profile_key,
            config=ctx.config,
        )
        extensions.require_role(view.manifest.get("role"), key=query.profile_key, expected=role.value)
        profile = extensions.load_agent_profile(uow, ResourceVersionId(view.resource_version_id))
    elif isinstance(ctx.config.get("extensions.role_profiles"), Mapping):
        try:
            view = extensions.select_agent_profile(uow, role.value, stage_profile=None, config=ctx.config)
            profile = extensions.load_agent_profile(uow, ResourceVersionId(view.resource_version_id))
        except NotFound:
            profile = None

    known_caps = {cap.value for cap in Capability}
    if profile is None:
        default_class = (
            ModelClass.ECONOMY
            if role in (RoleId.RESEARCHER, RoleId.SCOUT, RoleId.REGISTRAR)
            else ModelClass.IMPLEMENTATION
        )
        return (
            default_class,
            Effort.MEDIUM,
            frozenset(),
            frozenset(),
            False,
            None,
            None,
        )

    req_caps = frozenset(Capability(c) for c in profile.required_capabilities if c in known_caps)
    opt_caps = frozenset(Capability(c) for c in profile.optional_capabilities if c in known_caps)
    inherit = profile.context.get("inherit_user_global") is True
    return (
        ModelClass(profile.model_class),
        Effort(profile.effort),
        req_caps,
        opt_caps,
        inherit,
        profile.permissions.policy_profile,
        profile.isolation,
    )


def _admission_view(adm: Admission) -> JsonObject:
    prefer: JsonObject | None = None
    if adm.prefer_route is not None:
        prefer = {
            "runtime_id": adm.prefer_route.runtime_id,
            "model": adm.prefer_route.model,
            "model_class": adm.prefer_route.model_class.value,
            "effort": adm.prefer_route.effort.value,
            "session_ref": adm.prefer_route.session_ref,
            "step_ref": adm.prefer_route.step_ref,
        }
    return {
        "requested": adm.requested.value,
        "operation": adm.operation.value,
        "min_class": adm.min_class.value,
        "class_sources": list(adm.class_sources),
        "min_effort": None if adm.min_effort is None else adm.min_effort.value,
        "resume": adm.resume.value,
        "prefer_route": prefer,
        "required_capabilities": list[JsonValue](sorted(cap.value for cap in adm.required_capabilities)),
        "notes": [{"code": note.code, "detail": note.detail} for note in adm.notes],
    }


def _decision_view(decision: RouteDecision) -> JsonObject:
    return {
        "runtime_id": decision.runtime_id,
        "model": decision.model,
        "model_class": decision.model_class.value,
        "effort": decision.effort.value,
        "effort_flag": decision.effort_flag,
        "source": decision.source,
        "operation": decision.operation.value,
        "degraded": list[JsonValue](sorted(cap.value for cap in decision.degraded)),
        "degraded_details": list(decision.degraded_details),
        "resume_allowance": {
            "allowed": decision.resume_allowance.allowed,
            "required": decision.resume_allowance.required,
            "session_ref": decision.resume_allowance.session_ref,
            "reason": decision.resume_allowance.reason,
        },
        "config_mode": decision.config_mode,
        "self_loads": [
            {
                "kind": view.kind.value,
                "locator": view.locator,
                "when": view.when,
                "active": view.active,
                "reason": view.reason,
            }
            for view in decision.self_loads
        ],
        "catalog_digest": decision.catalog_digest,
        "context_window_tokens": decision.context_window_tokens,
    }


def _texts(raw: JsonValue) -> list[JsonValue]:
    """The strings of a configured list; a missing or malformed list is empty."""
    return [x for x in raw if isinstance(x, str)] if isinstance(raw, list) else []


def _config_view(ctx: QueryContext, role: RoleId, op: Operation, policy: AdmissionPolicy) -> JsonObject:
    raw_allowed = ctx.config.get("runtimes.allowed")
    raw_pref = ctx.config.get("runtimes.preference")
    raw_routing = ctx.config.get("runtimes.role_routing")
    raw_degraded = ctx.config.get("runtimes.degraded.allow")
    role_entry = raw_routing.get(role.value) if isinstance(raw_routing, Mapping) else None
    role_routing_dict = dict(role_entry) if isinstance(role_entry, Mapping) else None
    return {
        "allowed": _texts(raw_allowed),
        "preference": _texts(raw_pref),
        "role_routing": role_routing_dict,
        "admission": {
            "min_class": policy.min_class[op].value,
            "resume": policy.resume[op].value,
        },
        "degraded_allow": _texts(raw_degraded),
        "config_isolation_required": ctx.config.get("runtimes.config_isolation.required") is not False,
    }


def handle(query: ExplainRouting, ctx: QueryContext, uow: UnitOfWork) -> RouteExplainView:
    role = RoleId(query.role.value)
    requested_op = (
        Operation(query.operation)
        if query.operation is not None
        else classify_operation(
            OperationContext(
                role=role,
                stage_final=False,
                has_fix_brief=False,
                wip_present=False,
                contract_changed=False,
            )
        )
    )
    policy = admission_policy(config=ctx.config)
    task_min = ModelClass(query.task_min_class.value) if query.task_min_class is not None else None

    needs_output = requested_op in (Operation.BOUNDED_FIX, Operation.REVIEW, Operation.FINAL_CLOSE)
    facts = AdmissionFacts(
        operation=requested_op,
        role=role,
        task_min_class=task_min,
        task_min_effort=None,
        started_by=None,
        previous=None,
        contract_digest=_EXPLAIN_CONTRACT_DIGEST,
        previous_contract_digest=_EXPLAIN_CONTRACT_DIGEST
        if requested_op in (Operation.CONTINUATION, Operation.BOUNDED_FIX)
        else None,
        fix_brief=FixBriefFacts(1, 0, ("explain",)) if requested_op is Operation.BOUNDED_FIX else None,
        previous_output_id="explain-preview" if needs_output else None,
    )
    admission = admit(facts, policy)

    (
        prof_class,
        prof_effort,
        prof_req_caps,
        prof_opt_caps,
        prof_inherit,
        policy_profile,
        isolation_profile,
    ) = _resolve_profile(uow, role, query, ctx)

    model_class = ModelClass(query.model_class.value) if query.model_class is not None else prof_class
    effort = Effort(query.effort.value) if query.effort is not None else prof_effort
    req_caps = (
        prof_req_caps | frozenset(Capability(c.value) for c in query.required_capabilities)
        if query.required_capabilities is not None
        else prof_req_caps
    )
    scope_inherit = ctx.config.get("context.inherit_user_global") is True
    config_mode, _ = config_mode_for(prof_inherit, scope_inherit=scope_inherit)
    host_id = HostId(query.host_id) if query.host_id is not None else None

    req = RouteRequest(
        role=role,
        required_capabilities=req_caps,
        optional_capabilities=prof_opt_caps,
        model_class=model_class,
        effort=effort,
        explicit_runtime=query.explicit_runtime,
        explicit_model=query.explicit_model,
        host_id=host_id,
        admission=admission,
        config_mode=config_mode,
        excluded_routes=frozenset(),
        network_read_only=False,
        policy_profile=policy_profile,
        isolation_profile=isolation_profile,
    )

    try:
        decision = route_role(uow, ctx.gateways, req, config=ctx.config, as_of=ctx.clock.now())
        return RouteExplainView(
            role=ViewRoleId(role.value),
            scope=ScopeRefDto(kind=query.scope.kind, id=query.scope.id),
            host_id=query.host_id,
            admission=_admission_view(admission),
            decision=_decision_view(decision),
            rejected=tuple(
                {
                    "runtime_id": item.runtime_id,
                    "model": item.model,
                    "source": item.source,
                    "reason": item.reason,
                    "detail": item.detail,
                }
                for item in decision.rejected
            ),
            config=_config_view(ctx, role, admission.operation, policy),
            error=None,
        )
    except SkmError as err:
        raw_rejected = err.details.get("rejected")
        rejected = (
            tuple(item for item in raw_rejected if isinstance(item, dict))
            if isinstance(raw_rejected, list)
            else ()
        )
        return RouteExplainView(
            role=ViewRoleId(role.value),
            scope=ScopeRefDto(kind=query.scope.kind, id=query.scope.id),
            host_id=query.host_id,
            admission=_admission_view(admission),
            decision=None,
            rejected=rejected,
            config=_config_view(ctx, role, admission.operation, policy),
            error=RouteExplainViewError(code=err.code.value, message=err.message),
        )


SPEC = QuerySpec(
    name="runtimes.explain_routing",
    dto=ExplainRouting,
    result=RouteExplainView,
    permission="runtime.read",
    scope_of=_scope_of,
    handler=handle,
)
