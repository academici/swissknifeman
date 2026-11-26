"""Public facade of the ``runtimes`` module (runtimes §13)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from datetime import date
from typing import TYPE_CHECKING, cast

from skm.kernel.isolation import parse_isolation_profile

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from skm.kernel.gateways import Gateways
    from skm.kernel.ids import HostId, WorkerId
    from skm.kernel.json_types import JsonObject
    from skm.kernel.ports_uow import UnitOfWork
    from skm.platform.config import EffectiveConfig

    from .domain.installation import RuntimeInstallation

from skm.modules.extensions.public import PackPins
from skm.platform.system_clock import SystemClock

from .application.activate_catalog import activate_staged_catalog
from .application.catalog_sources import (
    CatalogTransport,
    FallbackGeneralizationsSource,
    ModelsDevSource,
    OpenRouterSource,
    V1ModelsSource,
    default_adapters,
)
from .application.catalog_sync_job import ModelCatalogSyncJob
from .application.commands.record_capability_verification import RecordCapabilityVerification
from .application.host_availability import current_worker_snapshot, host_routing
from .application.queries.get_capabilities import resolve_capabilities
from .application.queries.list_models import (
    resolve_catalog,
    resolve_model_entry,
    resolve_model_guideline,
    resolve_usage_cost,
)
from .application.queries.list_runtimes import ListRuntimesResult
from .application.seed_catalog import seed_builtin_model_catalog
from .domain.admission import (
    ADMISSION_DEFAULTS,
    Admission,
    AdmissionFacts,
    AdmissionPolicy,
    FixBounds,
    Operation,
    OperationContext,
    ResumeAllowance,
    ResumePolicy,
    admission_allows_resume,
    admit,
    classify_operation,
    fix_within_bounds,
    session_policy_for,
)
from .domain.capability import (
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    RuntimeCapabilities,
    SelfLoad,
    SelfLoadedSource,
    SelfLoadKind,
    SelfLoadView,
    StaticCapabilityCatalog,
    VerificationContext,
    config_mode_for,
    explain_self_loads,
    self_loaded_instruction_files,
    verification_context_key,
)
from .domain.catalog import ModelCatalog, ModelEntry, Pricing
from .domain.catalog_sync import (
    ACTIVATION_PACK_SLUG,
    CandidateTrust,
    CatalogCandidate,
    CatalogSourceId,
    CatalogSyncReport,
    PriceQuote,
    StagedCandidate,
    stage_candidates,
)
from .domain.classes import MODEL_CLASS_ORDER, Effort, ModelClass, RoleId
from .domain.error_rules import (
    ErrorClass,
    ErrorScope,
    ProcessOutcome,
    ProviderFailure,
    RuntimeSignals,
    classify,
    process_failure,
)
from .domain.genai_semconv import GenAIInvocationSpan, agent_invocation_span
from .domain.ids import ModelId, RuntimeId, SessionRef, runtime_stream_id
from .domain.installation import AuthState
from .domain.observation import (
    ModelIdentity,
    RuntimeObservation,
    model_identity,
    observation_to_json,
    observed_model_family,
    validate_runtime_observation,
)
from .domain.request import (
    AgentRequest,
    McpServerSpec,
    PermissionGrant,
    ProcessOwner,
    ProcessOwnership,
    RuntimeLimits,
    SecretStr,
    process_ownership_to_json,
    validate_request,
)
from .domain.result import ExitInfo, RuntimeResult, ToolDenial, validate_result_observation
from .domain.routing import RouteConfig, RouteDecision, RouteKey, RouteRequest, route, route_needs
from .domain.session_events import (
    CancelIgnored,
    CheckpointAvailable,
    SessionCompleted,
    SessionEvent,
    SessionFailed,
    SessionStarted,
    TextDelta,
    ToolCompleted,
    ToolRequested,
    UsageReported,
    Violation,
    session_event_to_json,
    validate_event_stream,
)
from .domain.usage import (
    SubagentUsage,
    UsageReport,
    UsageStatus,
    cache_hit_rate,
    cost,
    estimate_from_prompt,
    fresh_tokens,
    merge_usage,
    unknown_usage,
)
from .generated.commands import RecordHostRuntimes
from .generated.host import DetectRuntimesReport, DetectRuntimesRequest
from .generated.queries import ExplainRouting, GetCapabilities, ListModels, ListRuntimes
from .generated.results import RecordCapabilityVerificationResult, RecordHostRuntimesResult
from .generated.views import (
    ModelsView,
    RouteExplainView,
    RuntimeCapabilitiesView,
    RuntimesView,
    RuntimesViewItem,
)
from .ports import (
    AgentRuntime,
    CapabilityCatalog,
    CapabilityVerificationRepository,
    HostRuntimeRepository,
    RuntimeRegistry,
    SessionHandle,
    WorkerModelOfferPolicy,
)


def admission_policy(*, config: EffectiveConfig) -> AdmissionPolicy:
    """``ADMISSION_DEFAULTS`` ∩ ``runtimes.admission.*`` ∩ ``runtimes.role_min_class`` (§13, §4.11 rule 1a).

    A configured ``min_class`` only raises the default floor; ``runtimes.session.resume = never`` gives every
    operation ``resume = never``. An absent key keeps the default.
    """
    min_class: dict[Operation, ModelClass] = {}
    resume: dict[Operation, ResumePolicy] = {}
    for op in Operation:
        default = ADMISSION_DEFAULTS.min_class[op]
        configured = config.get(f"runtimes.admission.{op.value}.min_class")
        candidates = [default] if configured is None else [default, ModelClass(cast("str", configured))]
        min_class[op] = max(candidates, key=MODEL_CLASS_ORDER.index)
        resume[op] = ADMISSION_DEFAULTS.resume[op]
    for op in (Operation.CONTINUATION, Operation.BOUNDED_FIX):  # the only operations with a resume key
        configured = config.get(f"runtimes.admission.{op.value}.resume")
        if configured is not None:
            resume[op] = ResumePolicy(cast("str", configured))
    if config.get("runtimes.session.resume") == "never":
        resume = dict.fromkeys(Operation, ResumePolicy.NEVER)
    below = config.get("runtimes.admission.bounded_fix.below_task_class")
    roles = config.get("runtimes.role_min_class")
    if roles is not None and not isinstance(roles, Mapping):
        raise TypeError("runtimes.role_min_class must be an object")
    role_min = cast("Mapping[str, str]", roles or {})
    return AdmissionPolicy(
        min_class=min_class,
        resume=resume,
        bounded_fix_below_task_class=below is True,
        role_min_class={RoleId(role): ModelClass(cls) for role, cls in role_min.items()},
    )


@dataclass(frozen=True, slots=True)
class HostRoute(RouteDecision):
    """The selected route with the exact installation facts used during admission."""

    installation: RuntimeInstallation
    verification_context: VerificationContext | None


def route_role(
    uow: UnitOfWork,
    gateways: Gateways,
    req: RouteRequest,
    *,
    config: EffectiveConfig,
    pins: PackPins | None = None,
    as_of: datetime | None = None,
) -> RouteDecision:
    """``RouteConfig`` from ``config``, the catalog within ``pins``, effective capabilities by the installed
    version on ``req.host_id`` and the installations of that host, then the pure ``route`` (§13).

    Effective capabilities are those of ``capabilities`` (static declaration merged with verifications):
    a static claim alone never counts as verified here.
    """
    cfg = _route_config(config)
    if req.work_allowed is not None:
        cfg = replace(cfg, allowed=cfg.allowed & req.work_allowed)
    models = catalog(uow, config=config, pins=pins)
    capability_catalog = gateways.get(CapabilityCatalog)
    registered = capability_catalog.registered()
    installs: dict[RuntimeId, RuntimeInstallation] = {}
    now = SystemClock().now() if as_of is None else as_of
    host = None
    if req.host_id is not None:
        snapshot = None if req.worker_id is None else current_worker_snapshot(uow, req.worker_id, as_of=now)
        observations = (
            uow.repo(HostRuntimeRepository).list_for_host(req.host_id)
            if req.worker_id is None
            else (() if snapshot is None else snapshot.installations)
        )
        installs = {item.runtime_id: item for item in observations if item.host_id == req.host_id}
        host = host_routing(
            uow,
            config,
            req.host_id,
            as_of=now,
            worker_runtimes=req.worker_runtimes,
            worker_id=req.worker_id,
            worker_snapshot=snapshot,
        )
    today = now.date()
    caps: dict[RuntimeId, RuntimeCapabilities] = {}
    contexts: dict[RuntimeId, VerificationContext] = {}
    for runtime_id in sorted(registered & cfg.allowed):
        installation = installs.get(runtime_id)
        version = None if installation is None else installation.version
        verification_context = installation_verification_context(
            installation, capability_catalog, req.isolation_profile
        )
        if (
            installation is not None
            and installation.details.get("launch_config_kind") == "inventory_probe"
            and verification_context is not None
        ):
            verification_context = _verified_launch_template(uow, installation, verification_context)
        if verification_context is None:
            caps[runtime_id] = capabilities(uow, gateways, runtime_id, version)
        else:
            contexts[runtime_id] = verification_context
            caps[runtime_id] = capabilities(
                uow,
                gateways,
                runtime_id,
                version,
                verification_context=verification_context,
                config=config,
                today=today,
            )
    decision = route(req, cfg, models, caps, installs, registered, host=host)
    installation = installs.get(decision.runtime_id)
    if installation is None:
        return decision
    selected_caps = caps[decision.runtime_id]
    needs = route_needs(req, config_isolation_required=cfg.config_isolation_required)
    relied_on = needs.required | needs.optional
    if decision.resume_allowance.allowed:
        relied_on |= {Capability.SESSION_RESUME}
    if decision.effort_flag:
        relied_on |= {Capability.EFFORT_CONTROL}
    if req.policy_profile != "trusted-full-access" and any(
        load.kind is SelfLoadKind.PROJECT_SETTINGS for load in selected_caps.self_loads
    ):
        relied_on |= {Capability.CONFIG_ISOLATION}
    verification_context = _route_verification_context(
        selected_caps,
        contexts.get(decision.runtime_id),
        installation.version,
        relied_on=relied_on - decision.degraded,
        config=config,
        today=today,
    )
    if verification_context is None and req.worker_id is None:
        return decision
    return HostRoute(
        **{field.name: getattr(decision, field.name) for field in fields(decision)},
        installation=installation,
        verification_context=verification_context,
    )


def worker_installations(
    uow: UnitOfWork, worker_id: WorkerId, *, as_of: datetime
) -> tuple[RuntimeInstallation, ...]:
    snapshot = current_worker_snapshot(uow, worker_id, as_of=as_of)
    return () if snapshot is None else snapshot.installations


def host_route_is_fresh(
    uow: UnitOfWork,
    config: EffectiveConfig,
    host_id: HostId,
    key: RouteKey,
    *,
    as_of: datetime,
    worker_id: WorkerId,
    runtime_version: str | None,
    binary_sha256: str | None,
) -> bool:
    """Recheck the same worker, route and installation at the runtime handoff."""
    if key.runtime_id not in _route_config(config).allowed:
        return False
    overrides = config.get("runtimes.models.overrides")
    if isinstance(overrides, Mapping):
        override_status = None
        for name in sorted((key.model_id, f"{key.runtime_id}:{key.model_id}")):
            override = overrides.get(name)
            if isinstance(override, Mapping):
                if override.get("disabled") is True:
                    override_status = "deprecated"
                elif override.get("status") is not None:
                    override_status = override["status"]
        if override_status == "deprecated":
            return False
    snapshot = current_worker_snapshot(uow, worker_id, as_of=as_of)
    if snapshot is None:
        return False
    host = host_routing(
        uow,
        config,
        host_id,
        as_of=as_of,
        worker_runtimes=None,
        worker_id=worker_id,
        worker_snapshot=snapshot,
    )
    return key in host.offers and any(
        install.host_id == host_id
        and install.runtime_id == key.runtime_id
        and install.auth_state is AuthState.OK
        and install.version == runtime_version
        and (install.details.get("executable_sha256") or install.details.get("binary_sha256"))
        == binary_sha256
        for install in snapshot.installations
    )


def installation_verification_context(
    installation: RuntimeInstallation | None,
    capability_catalog: CapabilityCatalog,
    isolation_profile: str | None,
) -> VerificationContext | None:
    """Derive the exact verification scope from an installation and the requested isolation profile."""
    if installation is None:
        return None
    details = installation.details
    binary_sha256 = details.get("binary_sha256") or details.get("executable_sha256")
    launch_config_digest = details.get("launch_config_digest")
    if not binary_sha256 or not launch_config_digest:
        return None
    os, kernel = details.get("os", ""), details.get("kernel", "")
    if os_kernel := details.get("os_kernel"):
        # The CLI probe uses a colon between the OS name and kernel release.
        os, _, kernel = os_kernel.partition("/" if "/" in os_kernel else ":")
    if not os or not kernel:
        return None
    adapter_version = (
        details.get("adapter_version") or capability_catalog.static(installation.runtime_id).adapter_version
    )
    try:
        return VerificationContext(
            host_id=installation.host_id,
            binary_sha256=binary_sha256,
            os=os,
            kernel=kernel,
            adapter_version=adapter_version,
            isolation_profile=parse_isolation_profile(isolation_profile or "worktree"),
            launch_config_digest=launch_config_digest,
        )
    except (TypeError, ValueError):
        return None


def _verified_launch_template(
    uow: UnitOfWork, installation: RuntimeInstallation, probe_context: VerificationContext
) -> VerificationContext | None:
    """Inventory probes have no step request. Use recorded templates for that installation."""
    if installation.version is None:
        return None
    records = uow.repo(CapabilityVerificationRepository).latest(
        installation.runtime_id, installation.version, None, installation=probe_context
    )
    contexts = {record.verification_context for record in records if record.verification_context is not None}
    # The worker validates the chosen template against the actual launch. Ambiguous evidence
    # cannot identify a template at route time.
    return next(iter(contexts)) if len(contexts) == 1 else None


def _route_verification_context(
    caps: RuntimeCapabilities,
    context: VerificationContext | None,
    runtime_version: str | None,
    *,
    relied_on: frozenset[Capability],
    config: EffectiveConfig,
    today: date,
) -> VerificationContext | None:
    """Capture the verification scope for an admitted host route that needs executable binding."""
    if context is None or runtime_version is None or context.adapter_version != caps.adapter_version:
        return None
    days = config.get("runtimes.capabilities.stale_after_days")
    stale_after_days = days if type(days) is int and days >= 1 else 30
    if any(
        record.capability in relied_on
        and caps.supports(record.capability)
        and record.verification_context == context
        and record.tested_runtime_version == runtime_version
        and record.last_verified_at is not None
        and (today - record.last_verified_at).days <= stale_after_days
        for record in caps.records.values()
    ):
        return context
    return None


def _route_config(config: EffectiveConfig) -> RouteConfig:
    """``RouteConfig`` of the ``runtimes`` section; an absent list is empty (nothing allowed, fail closed)."""

    def strings(key: str) -> tuple[str, ...]:
        value = config.get(key)
        return tuple(item for item in value if isinstance(item, str)) if isinstance(value, list) else ()

    routing = config.get("runtimes.role_routing")
    roles = {role.value for role in RoleId}
    known = {cap.value for cap in Capability}
    return RouteConfig(
        allowed=frozenset(strings("runtimes.allowed")),
        preference=strings("runtimes.preference"),
        role_routing={
            RoleId(role): cast("JsonObject", entry)
            for role, entry in (routing.items() if isinstance(routing, Mapping) else ())
            if role in roles and isinstance(entry, Mapping)
        },
        degraded_allow=frozenset(
            Capability(cap) for cap in strings("runtimes.degraded.allow") if cap in known
        ),
        config_isolation_required=config.get("runtimes.config_isolation.required") is not False,
        unknown_model="refuse" if config.get("runtimes.routing.unknown_model") == "refuse" else "warn",
    )


def catalog(uow: UnitOfWork, *, config: EffectiveConfig, pins: PackPins | None = None) -> ModelCatalog:
    """Resolved model catalog from ``extensions.runtime_catalog`` + ``runtimes.models.overrides``."""
    return resolve_catalog(uow, config=config, pins=pins)


def capabilities(
    uow: UnitOfWork,
    gateways: Gateways,
    runtime_id: RuntimeId,
    runtime_version: str | None = None,
    *,
    verification_context: VerificationContext | None = None,
    config: EffectiveConfig | None = None,
    today: date | None = None,
) -> RuntimeCapabilities:
    """Effective capabilities of ``runtime_id`` merging static claims with recorded verifications."""
    now_date = SystemClock().now().date() if today is None else today
    return resolve_capabilities(
        uow,
        gateways,
        runtime_id,
        runtime_version,
        verification_context=verification_context,
        config=config,
        today=now_date,
    )


def model_entry(
    uow: UnitOfWork,
    runtime_id: RuntimeId,
    model: ModelId,
    *,
    config: EffectiveConfig,
    pins: PackPins | None = None,
) -> ModelEntry | None:
    """Lookup ``model`` on ``runtime_id`` in the resolved (and optionally pinned) catalog."""
    return resolve_model_entry(uow, runtime_id, model, config=config, pins=pins)


def usage_cost(
    uow: UnitOfWork,
    usage: UsageReport,
    runtime_id: RuntimeId,
    model: ModelId,
    *,
    config: EffectiveConfig,
    pins: PackPins | None = None,
) -> UsageReport:
    """Return ``usage`` with ``cost_usd_micros`` populated from the resolved catalog pricing (or ``None``)."""
    return resolve_usage_cost(uow, usage, runtime_id, model, config=config, pins=pins)


def model_context_window(model_id: str, *, catalog: ModelCatalog) -> int | None:
    """Context window for ``model_id`` if unambiguous across ``catalog``; unknown or ambiguous -> ``None``."""
    matches: list[int] = []
    for runtime_id in sorted(catalog.runtimes):
        entry = catalog.model(runtime_id, model_id)
        if entry is not None:
            matches.append(entry.context_window_tokens)
    if len(matches) == 1:
        return matches[0]
    return None


def summarize_tool_activity(events: Sequence[SessionEvent]) -> JsonObject:
    raise NotImplementedError("runtimes.summarize_tool_activity: owner leaf")


__all__ = [
    "ACTIVATION_PACK_SLUG",
    "Admission",
    "AdmissionFacts",
    "AdmissionPolicy",
    "AgentRequest",
    "AgentRuntime",
    "CancelIgnored",
    "CandidateTrust",
    "Capability",
    "CapabilityRecord",
    "CapabilityStatus",
    "CatalogCandidate",
    "CatalogSourceId",
    "CatalogSyncReport",
    "CatalogTransport",
    "CheckpointAvailable",
    "DetectRuntimesReport",
    "DetectRuntimesRequest",
    "Effort",
    "ErrorClass",
    "ErrorScope",
    "ExitInfo",
    "ExplainRouting",
    "FallbackGeneralizationsSource",
    "FixBounds",
    "GenAIInvocationSpan",
    "GetCapabilities",
    "HostRoute",
    "ListModels",
    "ListRuntimes",
    "ListRuntimesResult",
    "McpServerSpec",
    "ModelCatalog",
    "ModelCatalogSyncJob",
    "ModelClass",
    "ModelEntry",
    "ModelId",
    "ModelIdentity",
    "ModelsDevSource",
    "ModelsView",
    "OpenRouterSource",
    "Operation",
    "OperationContext",
    "PermissionGrant",
    "PriceQuote",
    "Pricing",
    "ProcessOutcome",
    "ProcessOwner",
    "ProcessOwnership",
    "ProviderFailure",
    "RecordCapabilityVerification",
    "RecordCapabilityVerificationResult",
    "RecordHostRuntimes",
    "RecordHostRuntimesResult",
    "ResumeAllowance",
    "RoleId",
    "RouteDecision",
    "RouteExplainView",
    "RouteKey",
    "RouteRequest",
    "RuntimeCapabilities",
    "RuntimeCapabilitiesView",
    "RuntimeId",
    "RuntimeLimits",
    "RuntimeObservation",
    "RuntimeRegistry",
    "RuntimeResult",
    "RuntimeSignals",
    "RuntimesView",
    "RuntimesViewItem",
    "SecretStr",
    "SelfLoad",
    "SelfLoadView",
    "SelfLoadedSource",
    "SessionCompleted",
    "SessionEvent",
    "SessionFailed",
    "SessionHandle",
    "SessionRef",
    "SessionStarted",
    "StagedCandidate",
    "StaticCapabilityCatalog",
    "SubagentUsage",
    "TextDelta",
    "ToolCompleted",
    "ToolDenial",
    "ToolRequested",
    "UsageReport",
    "UsageReported",
    "UsageStatus",
    "V1ModelsSource",
    "VerificationContext",
    "Violation",
    "WorkerModelOfferPolicy",
    "activate_staged_catalog",
    "admission_allows_resume",
    "admission_policy",
    "admit",
    "agent_invocation_span",
    "cache_hit_rate",
    "capabilities",
    "catalog",
    "classify",
    "classify_operation",
    "config_mode_for",
    "cost",
    "default_adapters",
    "estimate_from_prompt",
    "explain_self_loads",
    "fix_within_bounds",
    "fresh_tokens",
    "host_route_is_fresh",
    "installation_verification_context",
    "merge_usage",
    "model_context_window",
    "model_entry",
    "model_identity",
    "observation_to_json",
    "observed_model_family",
    "process_failure",
    "process_ownership_to_json",
    "resolve_model_guideline",
    "route",
    "route_role",
    "runtime_stream_id",
    "seed_builtin_model_catalog",
    "self_loaded_instruction_files",
    "session_event_to_json",
    "session_policy_for",
    "stage_candidates",
    "summarize_tool_activity",
    "unknown_usage",
    "usage_cost",
    "validate_event_stream",
    "validate_request",
    "validate_result_observation",
    "validate_runtime_observation",
    "verification_context_key",
    "worker_installations",
]
