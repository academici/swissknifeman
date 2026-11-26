"""Routing (runtimes §4.10): the pure, deterministic ``route`` under the requirements of admission (§4.11).

``route_needs`` merges the admission requirements into the request (step 1), ``route`` walks the candidates
through the filters (steps 2 to 4) and ``route_refusal`` picks the error when no candidate passed (step 5).
Loading the catalog, the effective capabilities and the installations is the facade's (``route_role``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, PreconditionFailed

from .admission import admission_allows_resume
from .capability import Capability, CapabilityStatus, SelfLoadKind, explain_self_loads
from .catalog import ModelStatus
from .classes import EFFORT_ORDER, MODEL_CLASS_ORDER, Effort, ModelClass
from .installation import AuthState
from .observation import observed_model_family

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Literal

    from skm.kernel.errors import SkmError
    from skm.kernel.ids import HostId, WorkerId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.runtimes.domain.admission import Admission, Operation, ResumeAllowance
    from skm.modules.runtimes.domain.capability import RuntimeCapabilities, SelfLoadView
    from skm.modules.runtimes.domain.catalog import ModelCatalog, ModelEntry
    from skm.modules.runtimes.domain.classes import RoleId
    from skm.modules.runtimes.domain.ids import Digest, ModelId, RuntimeId
    from skm.modules.runtimes.domain.installation import RuntimeInstallation

type RouteSource = Literal[
    "previous_route", "plan_route", "role_routing", "role_fallback", "preference", "host_substitution"
]


@dataclass(frozen=True, slots=True)
class RouteKey:
    runtime_id: RuntimeId
    model_id: ModelId
    effort: Effort


@dataclass(frozen=True, slots=True)
class HostRouting:
    offers: frozenset[RouteKey]
    substitutions: tuple[tuple[RouteKey, RouteKey], ...] = ()


@dataclass(frozen=True, slots=True)
class RouteRequest:
    role: RoleId
    required_capabilities: frozenset[Capability]
    optional_capabilities: frozenset[Capability]
    model_class: ModelClass
    effort: Effort
    explicit_runtime: RuntimeId | None
    explicit_model: ModelId | None
    host_id: HostId | None
    admission: Admission
    config_mode: Literal["isolated", "inherit"]
    excluded_routes: frozenset[tuple[RuntimeId, ModelId | None]]
    network_read_only: bool
    policy_profile: str | None = None
    isolation_profile: str | None = None
    worker_runtimes: frozenset[RuntimeId] | None = None
    work_allowed: frozenset[RuntimeId] | None = None
    worker_id: WorkerId | None = None
    executor_runtimes: frozenset[RuntimeId] = frozenset()
    executor_families: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class RouteConfig:
    allowed: frozenset[RuntimeId]
    preference: tuple[RuntimeId, ...]
    role_routing: Mapping[RoleId, JsonObject]
    degraded_allow: frozenset[Capability]
    config_isolation_required: bool = True  # runtimes.config_isolation.required
    unknown_model: Literal["warn", "refuse"] = "warn"  # runtimes.routing.unknown_model


@dataclass(frozen=True, slots=True)
class RouteRejection:
    runtime_id: RuntimeId
    model: ModelId | None
    source: str
    reason: str
    detail: str


@dataclass(frozen=True, slots=True)
class RouteDecision:
    runtime_id: RuntimeId
    model: ModelId
    model_class: ModelClass
    effort: Effort
    effort_flag: str
    source: RouteSource
    degraded: frozenset[Capability]
    rejected: tuple[RouteRejection, ...]
    catalog_digest: Digest
    operation: Operation
    admission: Admission
    resume_allowance: ResumeAllowance
    config_mode: Literal["isolated", "inherit"]
    self_loads: tuple[SelfLoadView, ...]
    # §4.10 step 3: the window of the model; an unknown model gets the smallest window of the runtime's
    # catalog models (a runtime without a valid one refuses it: a window is never invented)
    context_window_tokens: int
    # accepted without proof, in gate order: "auth_unknown", "model_unknown"
    degraded_details: tuple[str, ...]
    requested_route: RouteKey | None = field(default=None, kw_only=True)


def route(
    req: RouteRequest,
    cfg: RouteConfig,
    catalog: ModelCatalog,
    caps: Mapping[RuntimeId, RuntimeCapabilities],
    installs: Mapping[RuntimeId, RuntimeInstallation],
    registered: frozenset[RuntimeId],
    *,
    host: HostRouting | None = None,
) -> RouteDecision:
    """§4.10 steps 1 to 5: the first candidate that passes every filter, or the refusal of step 5.

    ``caps`` are effective capabilities: an ``unknown`` status is never taken for support. A required
    capability that is ``unknown`` passes only through ``cfg.degraded_allow`` (recorded in ``degraded``), and
    never when admission requires it (``session_resume`` at ``resume = required``). A candidate is never
    routed on a runtime whose capabilities are not given. Non-suppressible worktree ``project_settings`` are
    refused unless ``req.policy_profile == "trusted-full-access"`` (§4.3.1 rule 7). The effort of a role
    route (or of its fallback) only raises ``need_effort``; one that is no ``Effort`` (the settings
    schema's ``"max"``) is ``effort_unsupported``, never met by a lower one.
    """
    needs = route_needs(req, config_isolation_required=cfg.config_isolation_required)
    rejected: list[RouteRejection] = []
    candidates = _candidates(req, cfg, catalog, needs.model_class, host_aware=host is not None)
    for candidate in _host_candidates(candidates, req, cfg, needs, host):
        runtime_id, model = candidate.runtime_id, candidate.model
        refusal = _gate(candidate, req, cfg, registered)
        runtime_caps = caps.get(runtime_id)
        if refusal is None and runtime_caps is not None and runtime_caps.runtime_id == runtime_id:
            degraded: frozenset[Capability] = frozenset()
            fit: _Fit | None = None
            refusal = _network_gate(runtime_caps, req)
            if refusal is None:
                refusal, degraded = _capability_gate(runtime_caps, needs, req, cfg)
            refusal = refusal or _install_gate(runtime_id, req.host_id, installs)
            if refusal is None:
                gated = _model_gate(candidate, req, cfg, catalog, needs)
                fit, refusal = (gated, None) if isinstance(gated, _Fit) else (None, gated)
            if fit is not None and model is not None:  # _model_gate refuses a candidate without a model
                effort = _candidate_effort(candidate, needs)
                allowance = admission_allows_resume(req.admission, runtime_id, model, runtime_caps)
                if host is not None and RouteKey(runtime_id, model, effort) not in host.offers:
                    refusal = (
                        "host_offer_unavailable",
                        f"{runtime_id}/{model}/{effort.value} has no fresh enabled offer on the host",
                    )
                elif allowance.required and not allowance.allowed:
                    refusal = ("resume_unavailable", allowance.reason)  # rule 3 of §4.11 is never waived
                else:
                    entry = catalog.model(runtime_id, model)
                    return RouteDecision(
                        runtime_id=runtime_id,
                        model=model,
                        model_class=fit.model_class,
                        effort=effort,
                        effort_flag=_effort_flag(catalog, runtime_caps, effort),
                        source=candidate.source,
                        degraded=degraded,
                        rejected=tuple(rejected),
                        catalog_digest=catalog.digest,
                        operation=req.admission.operation,
                        admission=req.admission,
                        resume_allowance=allowance,
                        config_mode=req.config_mode,
                        self_loads=explain_self_loads(runtime_caps, req.config_mode),
                        context_window_tokens=fit.context_window_tokens,
                        degraded_details=_degraded_details(runtime_id, req.host_id, installs, entry),
                        requested_route=candidate.requested_route or RouteKey(runtime_id, model, effort),
                    )
        # no refusal left here means the registered runtime came without effective capabilities
        reason, detail = refusal or ("not_registered", f"no effective capabilities of {runtime_id}")
        rejected.append(
            RouteRejection(
                runtime_id=candidate.runtime_id,
                model=candidate.model,
                source=candidate.source,
                reason=reason,
                detail=detail,
            )
        )
    raise route_refusal(req, rejected)


@dataclass(frozen=True, slots=True)
class _Candidate:
    runtime_id: RuntimeId
    model: ModelId | None  # None: the catalog has no model of the class for the runtime
    source: RouteSource
    # the effort a role route (or its fallback) declares; a ``str`` is a declared value that is no ``Effort``
    effort: Effort | str | None = None
    requested_route: RouteKey | None = None


def _host_candidates(
    candidates: Sequence[_Candidate],
    req: RouteRequest,
    cfg: RouteConfig,
    needs: RouteNeeds,
    host: HostRouting | None,
) -> list[_Candidate]:
    if host is None or req.admission.resume == "required":
        return list(candidates)
    expanded: list[_Candidate] = []
    for candidate in candidates:
        expanded.append(candidate)
        if (
            candidate.model is None
            or candidate.runtime_id not in cfg.allowed
            or _effort_gate(candidate, req, needs) is not None
        ):
            continue
        requested = RouteKey(candidate.runtime_id, candidate.model, _candidate_effort(candidate, needs))
        expanded.extend(
            _Candidate(target.runtime_id, target.model_id, "host_substitution", target.effort, requested)
            for source, target in host.substitutions
            if source == requested and EFFORT_ORDER.index(target.effort) >= EFFORT_ORDER.index(source.effort)
        )
    return expanded


@dataclass(frozen=True, slots=True)
class _Fit:
    """What ``_model_gate`` proved of an accepted candidate: its class and the window to route with."""

    model_class: ModelClass
    context_window_tokens: int


def _rank_class(model_class: ModelClass) -> int:
    return MODEL_CLASS_ORDER.index(model_class)


def _candidate_effort(candidate: _Candidate, needs: RouteNeeds) -> Effort:
    """``need_effort``, raised by the effort the candidate's role route declares; never lowered by it."""
    if not isinstance(candidate.effort, Effort):  # an unsupported one never reaches here (effort_unsupported)
        return needs.effort
    return max(needs.effort, candidate.effort, key=EFFORT_ORDER.index)


_MIN_WINDOW = 1000  # model-catalog.v1: context_window_tokens >= 1000


def _smallest_window(catalog: ModelCatalog, runtime_id: RuntimeId) -> int | None:
    """The smallest window of the runtime's catalog models; ``None`` (no proved minimum) when the runtime has
    no models or any of their windows is not a valid one, so a smaller model can never be hidden."""
    entry = catalog.runtimes.get(runtime_id)
    windows = [model.context_window_tokens for model in entry.models] if entry is not None else []
    valid = all(type(window) is int and window >= _MIN_WINDOW for window in windows)  # a bool is no window
    return min(windows) if windows and valid else None


def _degraded_details(
    runtime_id: RuntimeId,
    host_id: HostId | None,
    installs: Mapping[RuntimeId, RuntimeInstallation],
    entry: ModelEntry | None,
) -> tuple[str, ...]:
    """What the decision accepted without proof (§4.10 step 3): an ``unknown`` auth, an unknown model."""
    details: list[str] = []
    install = installs.get(runtime_id) if host_id is not None else None
    if install is not None and install.auth_state == AuthState.UNKNOWN:
        details.append("auth_unknown")
    if entry is None:
        details.append("model_unknown")
    return tuple(details)


def _text(item: Mapping[str, JsonValue], key: str) -> str | None:
    value = item.get(key)
    return value if isinstance(value, str) and value else None


def _effort_of(item: Mapping[str, JsonValue]) -> Effort | str | None:
    """The declared ``effort``: ``None`` when absent, else the ``Effort``, else the declared value as text.

    A value that is no ``Effort`` of §4.1 (the settings schema's ``"max"`` is above ``xhigh``) is kept as
    text: no runtime effort is proved to reach it, so it is refused (``effort_unsupported``), never met by
    ``xhigh``.
    """
    named = item.get("effort")
    if named is None:
        return None
    if isinstance(named, str) and named in {effort.value for effort in Effort}:
        return Effort(named)
    return named if isinstance(named, str) else repr(named)


def _picked(catalog: ModelCatalog, runtime_id: RuntimeId, model_class: ModelClass) -> ModelId | None:
    entry = catalog.pick(runtime_id, model_class)
    return None if entry is None else entry.id


def _choices(
    catalog: ModelCatalog, runtime_id: RuntimeId, model_class: ModelClass, *, host_aware: bool
) -> tuple[ModelId | None, ...]:
    first = _picked(catalog, runtime_id, model_class)
    entry = catalog.runtimes.get(runtime_id)
    if not host_aware or entry is None or first is None:
        return (first,)
    return (first, *(model for model in entry.class_selectors.get(model_class, ()) if model != first))


def _runtimes_of(
    model: ModelId, cfg: RouteConfig, catalog: ModelCatalog, *, host_aware: bool
) -> tuple[RuntimeId, ...]:
    """Use preference then catalog order when the work specifies only a model."""
    order = (*cfg.preference, *sorted(catalog.runtimes))
    known = tuple(dict.fromkeys(runtime_id for runtime_id in order if catalog.model(runtime_id, model)))
    if not known:
        return cfg.preference[:1]
    return known if host_aware else known[:1]


def _routed(
    item: JsonValue,
    cfg: RouteConfig,
    catalog: ModelCatalog,
    need: ModelClass,
    source: RouteSource,
    effort: Effort | str | None = None,
    *,
    host_aware: bool,
) -> list[_Candidate]:
    """Candidates of a ``runtimes.role_routing`` entry or of one of its ``fallback`` items.

    A fallback item is ``{"runtime"?, "model"?, "model_class"?, "effort"?}`` or a plain runtime id (the
    settings schema); ``effort`` is the effort of the entry, which an item without its own keeps. A route
    without a runtime is tried on each preferred runtime; its ``model_class`` only raises the class of the
    picked model.
    """
    if isinstance(item, str):
        item = {"runtime": item}
    if not isinstance(item, Mapping):
        return []
    runtime, model, named_class = _text(item, "runtime"), _text(item, "model"), _text(item, "model_class")
    pick_class = need
    if named_class in {cls.value for cls in ModelClass}:
        pick_class = max(need, ModelClass(named_class), key=_rank_class)
    if runtime is not None:
        runtimes = (runtime,)
    elif model is not None:
        runtimes = _runtimes_of(model, cfg, catalog, host_aware=host_aware)
    else:
        runtimes = cfg.preference
    declared = _effort_of(item)
    if declared is None:
        declared = effort
    return [
        _Candidate(r, choice, source, declared)
        for r in runtimes
        for choice in ((model,) if model else _choices(catalog, r, pick_class, host_aware=host_aware))
    ]


def _candidates(
    req: RouteRequest, cfg: RouteConfig, catalog: ModelCatalog, need: ModelClass, *, host_aware: bool
) -> list[_Candidate]:
    """Step 2: previous route, then the plan route alone, else role routing and fallback, else preference.

    ``resume = required`` admits only the previous route. Host routing keeps distinct effort candidates.
    """
    admission = req.admission
    found: list[_Candidate] = []
    prefer = admission.prefer_route
    if prefer is not None and admission.resume != "never":
        found.append(_Candidate(prefer.runtime_id, prefer.model, "previous_route"))
    if admission.resume == "required":  # ResumePolicy.REQUIRED; admission imports this module
        return found
    if req.explicit_runtime is not None or req.explicit_model is not None:
        runtimes: tuple[RuntimeId, ...] = ()
        if req.explicit_runtime is not None:
            runtimes = (req.explicit_runtime,)
        elif req.explicit_model is not None:
            runtimes = _runtimes_of(req.explicit_model, cfg, catalog, host_aware=host_aware)
        for runtime in runtimes:
            found.extend(
                _Candidate(runtime, model, "plan_route")
                for model in (
                    (req.explicit_model,)
                    if req.explicit_model
                    else _choices(catalog, runtime, need, host_aware=host_aware)
                )
            )
        return _unique(found, host_aware=host_aware)
    routed: list[_Candidate] = []
    entry = cfg.role_routing.get(req.role)
    if entry is not None:
        routed.extend(_routed(entry, cfg, catalog, need, "role_routing", host_aware=host_aware))
        fallback = entry.get("fallback")
        for item in fallback if isinstance(fallback, list) else []:
            routed.extend(
                _routed(item, cfg, catalog, need, "role_fallback", _effort_of(entry), host_aware=host_aware)
            )
    if not routed:
        routed = [
            _Candidate(r, model, "preference")
            for r in cfg.preference
            for model in _choices(catalog, r, need, host_aware=host_aware)
        ]
    return _unique([*found, *routed], host_aware=host_aware)


def _unique(candidates: Sequence[_Candidate], *, host_aware: bool) -> list[_Candidate]:
    seen: set[tuple[RuntimeId, ModelId | None, str | None]] = set()
    unique: list[_Candidate] = []
    for candidate in candidates:
        key = (candidate.runtime_id, candidate.model, candidate.effort if host_aware else None)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _gate(
    candidate: _Candidate,
    req: RouteRequest,
    cfg: RouteConfig,
    registered: frozenset[RuntimeId],
) -> tuple[str, str] | None:
    runtime_id, model = candidate.runtime_id, candidate.model
    excluded = req.excluded_routes
    if (runtime_id, model) in excluded or (runtime_id, None) in excluded:
        return "excluded_by_retry", f"{runtime_id}/{model or '-'} already failed in this attempt"
    if runtime_id not in cfg.allowed:
        return "not_allowed", f"{runtime_id} is not in runtimes.allowed"
    if runtime_id in req.executor_runtimes:
        return "review_independence", f"{runtime_id} was observed on an executor step"
    if req.executor_families and observed_model_family(runtime_id, model) in req.executor_families:
        return "review_independence", f"{model} shares a model family with an observed executor model"
    if runtime_id not in registered:
        return "not_registered", f"no adapter is registered for {runtime_id}"
    return None


def _network_gate(caps: RuntimeCapabilities, req: RouteRequest) -> tuple[str, str] | None:
    if req.network_read_only and not caps.read_only_network:
        return "read_only_network_unsupported", f"{caps.runtime_id} has no network with an empty fs_write"
    return None


def _capability_gate(
    caps: RuntimeCapabilities, needs: RouteNeeds, req: RouteRequest, cfg: RouteConfig
) -> tuple[tuple[str, str] | None, frozenset[Capability]]:
    """``capability_missing:<cap>`` of step 3, in declaration order; the second item is ``degraded``."""
    if req.policy_profile != "trusted-full-access" and _project_settings_load(caps):
        return ("capability_missing:config_isolation", "project_settings_not_suppressible"), frozenset()
    degraded: set[Capability] = set()
    for cap in Capability:
        if cap not in needs.required or caps.supports(cap):
            continue
        status = caps.status(cap)
        if (
            status is CapabilityStatus.UNKNOWN
            and cap in cfg.degraded_allow
            and cap not in req.admission.required_capabilities
        ):
            degraded.add(cap)
            continue
        detail = (
            f"{cap.value} is {status.value} ({caps.runtime_id} {caps.adapter_version}); "
            f"config_mode {req.config_mode}"
        )
        return (f"capability_missing:{cap.value}", detail), frozenset()
    degraded.update(cap for cap in needs.optional if not caps.supports(cap))
    return None, frozenset(degraded)


def _project_settings_load(caps: RuntimeCapabilities) -> bool:
    """Would the CLI load untrusted worktree settings? ``suppressed_by = "config_isolation"`` is only a static
    claim: it suppresses them only when the effective ``config_isolation`` is supported (native/adapted); an
    ``unknown``, ``unsupported`` or absent record proves nothing, in ``isolated`` and in ``inherit`` alike.
    """
    isolates = caps.supports(Capability.CONFIG_ISOLATION)
    return any(
        load.kind is SelfLoadKind.PROJECT_SETTINGS and (load.suppressed_by == "never" or not isolates)
        for load in caps.self_loads
    )


def _install_gate(
    runtime_id: RuntimeId, host_id: HostId | None, installs: Mapping[RuntimeId, RuntimeInstallation]
) -> tuple[str, str] | None:
    """Only with a host: the runtime is installed on that very host and its auth is not missing/expired
    (an ``unknown`` auth state passes as ``auth_unknown`` of ``RouteDecision.degraded_details``)."""
    if host_id is None:
        return None
    install = installs.get(runtime_id)
    if install is None or install.host_id != host_id or install.runtime_id != runtime_id:
        return "not_installed", f"{runtime_id} is not installed on host {host_id}"
    if install.auth_state == AuthState.MISSING:
        return "auth_missing", f"{runtime_id} on host {host_id} has no credentials"
    if install.auth_state == AuthState.EXPIRED:
        return "auth_expired", f"the credentials of {runtime_id} on host {host_id} expired"
    return None


def _model_gate(
    candidate: _Candidate, req: RouteRequest, cfg: RouteConfig, catalog: ModelCatalog, needs: RouteNeeds
) -> tuple[str, str] | _Fit:
    """``model_unknown`` … ``effort_too_low``/``effort_unsupported`` of step 3, or the fit of the decision.

    A model the catalog does not know proves no class: at ``unknown_model = "warn"`` it is accepted only when
    the needed class is the lowest one, otherwise it is ``class_too_low`` (an unknown never reaches a floor),
    and only with the smallest valid window of the runtime's catalog models: without one it stays
    ``model_unknown`` (no window is invented). An accepted unknown model is recorded in
    ``RouteDecision.degraded_details`` (``model_unknown``).
    """
    runtime_id, model, need = candidate.runtime_id, candidate.model, needs.model_class
    if model is None:
        return "no_model_for_class", f"the catalog has no {need.value} model for {runtime_id}"
    entry = catalog.model(runtime_id, model)
    lowest = MODEL_CLASS_ORDER[0]
    if entry is None:
        if cfg.unknown_model == "refuse":
            return "model_unknown", f"{model} is not in the catalog of {runtime_id}"
        if need is not lowest:
            detail = f"{model} is not in the catalog of {runtime_id}: no class reaching {need.value} is known"
            return "class_too_low", detail
        window = _smallest_window(catalog, runtime_id)
        if window is None:
            detail = (
                f"{model} is not in the catalog of {runtime_id}, which has no valid context window "
                "to bound it (unknown_model warn)"
            )
            return "model_unknown", detail
        fit = _Fit(lowest, window)
    else:
        if entry.status == ModelStatus.DEPRECATED:
            return "model_deprecated", f"{model} of {runtime_id} is deprecated"
        reaching = [
            cls for cls in MODEL_CLASS_ORDER if cls in entry.classes and _rank_class(cls) >= _rank_class(need)
        ]
        if not reaching:
            sources = ",".join(req.admission.class_sources) or "request"
            classes = ",".join(cls.value for cls in MODEL_CLASS_ORDER if cls in entry.classes)
            return "class_too_low", f"{model} is {classes or 'unclassified'}; need {need.value} ({sources})"
        fit = _Fit(reaching[0], entry.context_window_tokens)
    return _effort_gate(candidate, req, needs) or fit


def _effort_gate(candidate: _Candidate, req: RouteRequest, needs: RouteNeeds) -> tuple[str, str] | None:
    """``effort_too_low`` (a plan effort below ``need_effort``), then ``effort_unsupported`` (a declared role
    route effort that is no ``Effort``: no runtime effort reaches it, so it is never met by ``xhigh``)."""
    if candidate.source == "plan_route" and EFFORT_ORDER.index(req.effort) < EFFORT_ORDER.index(needs.effort):
        return (
            "effort_too_low",
            f"plan effort {req.effort.value} is below {needs.effort.value} ({req.admission.operation.value})",
        )
    if isinstance(candidate.effort, str) and not isinstance(candidate.effort, Effort):
        return (
            "effort_unsupported",
            f"{candidate.source} effort {candidate.effort} is no runtime effort (highest "
            f"{EFFORT_ORDER[-1].value}); it is not lowered to one",
        )
    return None


def _effort_flag(catalog: ModelCatalog, caps: RuntimeCapabilities, effort: Effort) -> str:
    """The runtime's flag value for the effort; a runtime without ``effort_control`` gets ``""``."""
    entry = catalog.runtimes.get(caps.runtime_id)
    if entry is None or not caps.supports(Capability.EFFORT_CONTROL):
        return ""
    return entry.effort_selectors.get(effort, "")


@dataclass(frozen=True, slots=True)
class RouteNeeds:
    """What every candidate must satisfy: the request raised to the admission floor (§4.10 step 1)."""

    model_class: ModelClass
    effort: Effort
    required: frozenset[Capability]
    optional: frozenset[Capability]


def route_needs(req: RouteRequest, *, config_isolation_required: bool) -> RouteNeeds:
    """``need_class``/``need_effort``/``need_caps`` of §4.10 step 1; admission can only raise the request.

    Admission-required capabilities (``session_resume`` at ``resume = required``) are required, never
    optional. ``config_isolation`` is required in the isolated mode with
    ``runtimes.config_isolation.required``, otherwise only wanted (§4.3.1 rule 2).
    """
    admission = req.admission
    model_class = max(req.model_class, admission.min_class, key=MODEL_CLASS_ORDER.index)
    effort = max(req.effort, admission.min_effort or Effort.LOW, key=EFFORT_ORDER.index)
    required = set(req.required_capabilities) | set(admission.required_capabilities)
    optional = set(req.optional_capabilities)
    if req.config_mode == "isolated":
        (required if config_isolation_required else optional).add(Capability.CONFIG_ISOLATION)
    return RouteNeeds(
        model_class=ModelClass(model_class),
        effort=Effort(effort),
        required=frozenset(required),
        optional=frozenset(optional - required),
    )


_UNDERSHOOT = frozenset({"class_too_low", "effort_too_low"})


def route_refusal(req: RouteRequest, rejected: Sequence[RouteRejection]) -> SkmError:
    """The error of §4.10 step 5 when no candidate passed; ``details.rejected`` is the full list.

    Every rejection being ``class_too_low``/``effort_too_low`` is ``ROUTE_UNDERSHOOT`` (an explicit route
    below the admission floor, port of ``route_minimum``); otherwise ``resume = required`` (only
    ``prefer_route`` was a candidate) is ``ADMISSION_REFUSED`` (``resume_required_unavailable``); anything
    else ``CAPABILITY_UNAVAILABLE``. No candidate at all is never an undershoot.
    """
    listed: list[JsonValue] = [
        {
            "runtime_id": item.runtime_id,
            "model": item.model,
            "source": item.source,
            "reason": item.reason,
            "detail": item.detail,
        }
        for item in rejected
    ]
    details: dict[str, JsonValue] = {
        "role": req.role.value,
        "operation": req.admission.operation.value,
        "rejected": listed,
    }
    if rejected and all(item.reason in _UNDERSHOOT for item in rejected):
        return CapabilityUnavailable(
            ErrorCode.ROUTE_UNDERSHOOT,
            f"every route of {req.role.value} is below the admission floor "
            f"({req.admission.min_class.value}/{req.admission.min_effort or 'any'} effort)",
            details=details,
        )
    if req.admission.resume == "required":  # ResumePolicy.REQUIRED; admission imports this module
        return PreconditionFailed(
            ErrorCode.ADMISSION_REFUSED,
            f"{req.admission.operation.value} requires resuming the previous route, which is not available",
            details={**details, "reason": "resume_required_unavailable"},
        )
    return CapabilityUnavailable(
        ErrorCode.CAPABILITY_UNAVAILABLE,
        f"no runtime can take role {req.role.value}",
        details=details,
    )


type RouteCandidate = JsonObject
