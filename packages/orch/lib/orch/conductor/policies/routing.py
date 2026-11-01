"""The rules of the route of each role: the stage options over the launch catalog, the reviewer the layers or the plan
name, the minimum class and effort of the work, and the roles and transports the conductor runs. The probes, the
fallback and the preflight of a run are ``application/route_service.py``."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from aicore.provider.config import routing_available

from orch import catalog as catalogs, launch
from orch.conductor import options as opts, scope as scopes
from orch.conductor.domain.route import actor, label  # noqa: F401 — re-export
from orch.conductor.domain.stop import Stop
from orch.settings import ORCH_ROOT

CLASS_RANK = {"economy": 0, "implementation": 1, "frontier": 2}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4, "ultra": 5}
LAUNCH_ROLE = {"context-scout": "scout"}
# skipped, not refused, when they cannot start (the bounded-implementer: its corrections then stay with the executor)
OPTIONAL_ROLES = {"context-scout", "report-fixer", "bounded-implementer"}
# Roles the conductor actually runs. A policy stage whose role is outside this set is not silently dropped:
# required + on_unavailable refuse stops the run; anything else is skipped once (POLICY_STAGE_SKIPPED).
CONDUCTOR_ROLES = ("deterministic", "scout", "context-scout", "executor", "reviewer", "triager", "registrar",
                   "report-fixer", "researcher", "advisor")
PLAN_REVIEW_SOURCE = "plan:review.reviewer"  # the reviewer route came from the plan item (execution-input review_route)


def unsupported_stages(policy) -> tuple:
    """``(required, optional)`` stages whose role the conductor does not run.

    ``required`` is a stage with ``required`` and ``on_unavailable: refuse`` (the run stops). Every other stage
    outside :data:`CONDUCTOR_ROLES` is ``optional`` (one beacon per run, the run continues). Rows are ``(id, role)``.
    """
    required, optional = [], []
    for stage in (policy or {}).get("stages") or []:
        if not isinstance(stage, dict):
            continue
        role = stage.get("role")
        if role in CONDUCTOR_ROLES:
            continue
        row = (str(stage.get("id") or "-"), str(role or "-"))
        if stage.get("required") and stage.get("on_unavailable") == "refuse":
            required.append(row)
        else:
            optional.append(row)
    return required, optional


def stage_list(rows) -> str:
    return "; ".join(f"stage {stage_id} (role {role})" for stage_id, role in rows)


def launch_access(launch_settings) -> str:
    """``[orch.launch] access`` of ``launch_settings``: ``open`` (default) or ``confined``; it sets the
    ``{write_sandbox}`` of the roles that write."""
    found = launch_settings
    return (found or {}).get("access") or "open" if isinstance(found, dict) else "open"


def registrar_problem(route: dict, *, project: str, access: str) -> Optional[str]:
    """Refuse a registrar whose guard cannot write the external plan workspace, before starting its CLI."""
    if route.get("role") != "registrar":
        return None
    provider = route.get("provider")
    guard = "landlock-protect" if provider in ("claude-code", "antigravity") else "codex-sandbox" \
        if provider == "codex" and access == "confined" else None
    if guard is None:
        return None
    return (f"LAUNCH_REFUSED: registrar/{provider}: writes the plan workspace outside {project}; "
            f"{guard} confines writes to the checkout")


def entry(launch_catalog: dict, role: str, provider: str) -> dict:
    try:
        return launch.entry(launch_catalog, LAUNCH_ROLE.get(role, role), provider)
    except launch.LaunchError as error:
        raise Stop(error.code, str(error)) from None


def provider_disabled(aicore_settings, provider: str) -> str | None:
    """``PROVIDER_DISABLED: ...`` with the layer that set it when ``aicore.providers.available.<provider>.enabled`` is
    false (machine, invocation or flags: a project cannot enable what the machine disabled); ``None`` otherwise, and
    without ``aicore_settings``. The axis is independent of ``providers.selection``, which only decides which surfaces
    are rolled out."""
    found = aicore_settings
    if found is None:
        return None
    available, layer = routing_available(provider, resolved=found)
    if available:
        return None
    return f"PROVIDER_DISABLED: aicore.providers.available.{provider}.enabled = false ({layer})"


def refuse_acp(routes: dict) -> None:
    unsupported = [(role, route) for role, route in routes.items()
                   if role not in OPTIONAL_ROLES and route["transport"] == "acp"]
    if unsupported:
        raise Stop("TRANSPORT_UNSUPPORTED", "; ".join(
            f"{role} on {route['provider']}: the conductor does not drive acp roles; "
            "use claude-code or codex for this role" for role, route in unsupported))


def route_target(*, role: str, item_options: dict, conductor_cfg: dict, override: Optional[dict],
                 reviewer: Optional[tuple]) -> dict:
    """``{wanted, provider, model, effort, review_class}``: what the layers ask of the route of ``role``; ``override`` (a
    ``fallback_routes`` entry or retry.decide's route) replaces the provider, the model class and, when it has one, the
    effort of the stage and drops its model. ``reviewer`` is the reviewer selector of the piece (:func:`reviewer_selector`),
    read only for the reviewer without an override."""
    wanted = opts.stage_route(item_options, role)
    if override:
        wanted = {**{key: value for key, value in wanted.items() if key not in ("provider", "model", "model_class")},
                  **{key: override[key] for key in ("provider", "model_class", "effort") if override.get(key)}}
    review_class = None  # the class the plan's review route asks of the reviewer
    if role == "reviewer" and not override:
        selector, review_class, _ = reviewer
        provider, model, effort = selector["provider"], selector.get("model"), selector.get("effort")
    else:
        provider = wanted.get("provider") or conductor_cfg.get("provider") or "claude-code"
        model, effort = wanted.get("model"), wanted.get("effort")
    return {"wanted": wanted, "provider": provider, "model": model, "effort": effort, "review_class": review_class}


def route_model(target: dict, *, role: str, entry: dict, claim: dict, launch_plan: dict) -> dict:
    """``target`` with the ``model_class``, the ``effort`` and the ``model`` of the route over the launch ``entry`` of its
    provider: a model the layers name, else the one the launch plan of the piece planned; ``needs_model`` when the
    model catalog has to resolve one for the class."""
    wanted, provider, model, effort = target["wanted"], target["provider"], target["model"], target["effort"]
    review_class = target["review_class"]
    model_class = review_class or wanted.get("model_class") or entry["model_class"]
    if role == "executor" and not effort:
        effort = (claim.get("route") or {}).get("effort")
    effort = effort or entry["effort"]
    needs_model = False
    if entry["model_set"] == "supported" and not model:
        planned = next((stage for stage in launch_plan.get("stages", [])
                        if LAUNCH_ROLE.get(stage.get("role"), stage.get("role")) == LAUNCH_ROLE.get(role, role)
                        and stage.get("provider") == provider and stage.get("model")
                        and not wanted.get("model_class") and not review_class), None)
        if planned:
            model = planned["model"]
        else:
            needs_model = True
    return {**target, "model_class": model_class, "effort": effort, "model": model, "needs_model": needs_model}


def builds_argv(role: str, effort: str, conductor_cfg: dict) -> bool:
    """Whether the command line of ``role`` comes from the launch catalog (no ``[orch.conductor.argv]`` for it, an effort
    the launch catalog starts): only then does :func:`route` need the catalog and the access of the run."""
    return not (conductor_cfg.get("argv") or {}).get(role) and effort in launch.EFFORTS


def route(*, role: str, item_options: dict, chosen: dict, entry: dict, conductor_cfg: dict, project: Path,
          launch_catalog: Optional[dict], access: Optional[str]) -> dict:
    """The route of ``role`` from the ``chosen`` provider, model, class and effort (:func:`route_model`, the model
    resolved) and its launch ``entry``: the command line (``[orch.conductor.argv]`` or the ``launch_catalog`` with
    ``access``, given when :func:`builds_argv`), the resume command line and the walls of the role."""
    provider, model, effort, model_class = chosen["provider"], chosen["model"], chosen["effort"], chosen["model_class"]
    if provider == "antigravity" and effort not in ("low", "medium", "high"):
        raise Stop("ROUTE_UNDERSHOOT", f"{role} needs effort {effort}, which antigravity cannot start")
    values = {"model": model or "", "effort": effort, "cwd": str(project), "orch": str(ORCH_ROOT)}
    argv_override = (conductor_cfg.get("argv") or {}).get(role)
    resume_argv = None
    try:
        if argv_override:
            argv = catalogs.substitute(list(argv_override), values)
        elif effort not in launch.EFFORTS:
            raise Stop("ROUTE_UNDERSHOOT", f"{role} needs effort {effort}, which {provider} cannot start")
        else:
            argv = launch.build_argv(launch_catalog, LAUNCH_ROLE.get(role, role), provider, model=model,
                                     effort=effort, cwd=project, access=access)
            resume_argv = launch.build_resume_argv(launch_catalog, LAUNCH_ROLE.get(role, role), provider,
                                                   model=model, effort=effort, cwd=project, access=access)
    except launch.LaunchError as error:
        raise Stop(error.code, str(error)) from None
    # The wall of a role: ``stage_timeout_s`` when set; else, for a streaming role, ``role_timeout_s`` of its role (an
    # auxiliary role must not hang a run forever; the executor and the bounded-implementer have none, silence is caught
    # by ``stage_idle_timeout_s``). A ``text`` role writes only at its end, so the catalog timeout stays its ceiling.
    limits, streaming = item_options["limits"], entry["transport"] != "text"
    timeout = limits.get("stage_timeout_s") or ((limits.get("role_timeout_s") or {}).get(role, 0) if streaming
                                                else entry["timeout_s"])
    idle = limits.get("stage_idle_timeout_s", 0) if streaming else 0
    found = {"role": role, "provider": provider, "model": model, "effort": effort, "model_class": model_class,
             "transport": entry["transport"], "timeout_s": timeout, "idle_timeout_s": idle, "argv": argv}
    if resume_argv:  # the command that continues a session of this provider (``{session}`` is filled at the start)
        found["resume_argv"] = resume_argv
    return found


def planned_reviewer(selector: dict, planned: dict) -> tuple:
    """``(selector, model_class)``: the plan's review route of a piece (``review_route`` {provider, model, effort, class})
    over the default reviewer ``selector``. Another provider or a class drops the default model, so the model catalog
    resolves one for the class; a partial route (only class or effort) completes the default."""
    provider = planned.get("provider") or selector["provider"]
    keep = provider == selector["provider"] and not planned.get("class")
    found = {"provider": provider}
    model = planned.get("model") or (selector.get("model") if keep else None)
    if model:
        found["model"] = model
    if keep and model == selector.get("model") and selector.get("context"):
        found["context"] = selector["context"]
    effort = planned.get("effort") or selector.get("effort")
    if effort:
        found["effort"] = effort
    return found, planned.get("class")


def reviewer_selector(item_options: dict, item_sources: dict, input_doc: dict) -> tuple:
    """``(selector, model_class, source)`` of the reviewer of a piece. A reviewer a layer sets (the configuration, a
    work-source layer, ``--options``) wins over the plan, as an explicit executor does; without one the plan's
    ``review_route`` of the piece completes the default reviewer (source ``plan:review.reviewer``); else the default
    (source ``None``)."""
    selector = opts.parse_selector(item_options["reviewer"])
    source = item_sources.get("reviewer")
    planned = input_doc.get("review_route") or {}
    if source or not planned:
        return selector, None, source
    found, model_class = planned_reviewer(selector, planned)
    return found, model_class, PLAN_REVIEW_SOURCE


def lowered_class(model_class: str, known: Optional[str]) -> str:
    """``model_class``, the label the layers or the launch catalog give a route, or the class the model catalog knows for
    the model the route names (``aicore.provider.models.admitted_class``) when that is lower: a label above the
    known class of a named model is not taken."""
    if known and CLASS_RANK.get(known, -1) < CLASS_RANK.get(model_class, -1):
        return known
    return model_class


def correction_minimum(claim_route: Optional[dict], input_minimum: Optional[dict] = None) -> dict:
    """The minimum a bounded correction route meets: the claim's ``route.correction`` when the plan names one, else the
    whole ordinary minimum of the work (no ``route.correction``, no relaxation): the claim's ``route`` completed by the
    execution-input ``route.minimum``, which also carries the provider and model the plan pins."""
    route = claim_route or {}
    if route.get("correction"):
        return dict(route["correction"])
    return {**{key: value for key, value in route.items() if key != "correction"}, **(input_minimum or {})}


def correction_refusal(minimum: dict, route: dict, item_ref: str) -> Optional[str]:
    """Why the bounded-implementer ``route`` may not correct piece ``item_ref``, as ``CODE: text``; ``None`` when it may:
    not below the class or effort of ``minimum`` and on the provider and model it pins."""
    try:
        route_minimum(minimum, route, item_ref)
    except Stop as stop:
        return f"{stop.code}: {stop.message.replace('the executor', 'the bounded-implementer', 1)}"
    for field in ("provider", "model"):
        if minimum.get(field) and minimum[field] != route.get(field):
            return f"ROUTE_MISMATCH: {item_ref} pins {field} {minimum[field]!r} for a correction"
    return None


def grown_paths(changed, allowed_findings, write_set) -> list:
    """The paths a correction round changed beyond what it was handed: not a path of the findings of its fix-brief
    (``allowed_findings``), not a test inside ``write_set`` (``*/tests/*``, ``test_*.py``), not ``CHANGELOG.md`` and not
    documentation (``docs/**``, ``packages/*/docs/**``)."""
    def allowed(path: str) -> bool:
        name = path.rsplit("/", 1)[-1]
        test = ("/tests/" in f"/{path}" or (name.startswith("test_") and name.endswith(".py"))) \
            and not scopes.outside([path], write_set)
        docs = path == "CHANGELOG.md" or scopes.under(path, ["docs/**", "packages/*/docs/**", "bridges/*/docs/**"])
        return path in allowed_findings or test or docs
    return sorted(path for path in changed if not allowed(path))


def route_minimum(minimum: dict, route: dict, item_ref: str) -> None:
    """``ROUTE_UNDERSHOOT`` when the executor ``route`` is below the class or the effort ``minimum`` (the claim's
    ``route``) of piece ``item_ref``."""
    if minimum.get("class") and CLASS_RANK.get(route["model_class"], -1) < CLASS_RANK[minimum["class"]]:
        raise Stop("ROUTE_UNDERSHOOT", f"the executor class {route['model_class']} is below "
                                       f"{minimum['class']} required by {item_ref}")
    if minimum.get("effort") and EFFORT_RANK.get(route["effort"], -1) < EFFORT_RANK[minimum["effort"]]:
        raise Stop("ROUTE_UNDERSHOOT", f"the executor effort {route['effort']} is below "
                                       f"{minimum['effort']} required by {item_ref}")
