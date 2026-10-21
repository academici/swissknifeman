"""The route of each role: the stage options over the launch catalog, the fallback routes, and the admission of a
route (startable here, not gated, not below the minimum of the work) before any work is done."""
from __future__ import annotations

from typing import Optional

from aicore.provider.config import routing_available

from orch import catalog as catalogs, launch, sandbox
from orch.conductor import gates, options as opts, process
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import write_json
from orch.settings import ORCH_ROOT

CLASS_RANK = {"economy": 0, "implementation": 1, "frontier": 2}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4, "ultra": 5}
LAUNCH_ROLE = {"context-scout": "scout"}
OPTIONAL_ROLES = {"context-scout", "report-fixer"}  # skipped, not refused, when they cannot start
PLAN_REVIEW_SOURCE = "plan:review.reviewer"  # the reviewer route came from the plan item (execution-input review_route)


def launch_catalog(self) -> dict:
    """The launch catalog of this run: the shipped one, or the file and the entry changes ``[orch.launch]`` names; read
    and checked once."""
    found = getattr(self, "_launch_cache", None)
    if found is None:
        try:
            found = self._launch_cache = launch.effective_catalog(getattr(getattr(self, "settings", None), "launch", None))
        except launch.LaunchError as error:
            raise Stop(error.code, str(error)) from None
    return found


def launch_access(self) -> str:
    """``[orch.launch] access`` of this run: ``open`` (default) or ``confined``; it sets the ``{write_sandbox}`` of the
    roles that write."""
    found = getattr(getattr(self, "settings", None), "launch", None)
    return (found or {}).get("access") or "open" if isinstance(found, dict) else "open"


def entry(self, role: str, provider: str) -> dict:
    try:
        return launch.entry(self._launch_catalog(), LAUNCH_ROLE.get(role, role), provider)
    except launch.LaunchError as error:
        raise Stop(error.code, str(error)) from None


def routes(self, item: Item, persist: bool = True, preview: bool = False) -> dict:
    """Select routes and return unavailable roles for a preview; required launch errors stop a real run."""
    unavailable = {}
    roles = ["executor"]
    if self._scout_stage(item) is not None:
        roles.insert(0, "context-scout")
    if self._research_wanted(item):
        roles.insert(1 if roles[0] == "context-scout" else 0, "researcher")
    if self._reviewing(item):
        roles += ["reviewer", self._triage_role(item)]
    if self._closer_named(item):
        roles.append("registrar")
    if self._advisor_on():
        roles.append("advisor")
    for role in roles:
        try:
            item.routes[role] = self._selected(item, role, persist)
        except Stop as stop:
            if stop.code not in ("LAUNCH_UNKNOWN", "LAUNCH_REFUSED") or (not preview and role not in OPTIONAL_ROLES):
                raise
            item.routes.pop(role, None)
            unavailable[role] = f"{stop.code}: {stop.message}"
            if persist and self.progress is not None:
                self.progress.emit("stage.skip", item=item.ref, stage="scout", role=role,
                                   reason_code=stop.code, message=f"{stop.message}; optional stage skipped")
    if item.options["limits"].get("repairs", 0) > 0:
        try:  # optional: without a launch entry or a model for it, results are only healed and repeated
            item.routes["report-fixer"] = self._selected(item, "report-fixer", persist)
        except Stop as stop:
            item.routes.pop("report-fixer", None)
            unavailable["report-fixer"] = f"{stop.code}: {stop.message}"
    if "executor" in item.routes:
        self._route_minimum(item)
    if persist:
        self._preflight(item)
        write_json(item.directory / "routes.json", item.routes)
    return unavailable


def route_problem(self, route: dict) -> str | None:
    """Why a route cannot run, as ``CODE: text``; ``None`` when it can. An ``acp`` role is never driven by the
    conductor (D4), whatever command line stands in for it; a Codex route confined by ``--sandbox`` needs the
    provider sandbox to start on this machine."""
    disabled = self.provider_disabled(route["provider"])
    if disabled:
        return disabled
    if route["transport"] == "acp":
        return "TRANSPORT_UNSUPPORTED: the conductor does not drive acp roles"
    if self._codex_sandboxed(route) and not sandbox.probe()["available"]:
        return f"SANDBOX_UNAVAILABLE: {sandbox.probe()['reason']}"
    if not process.available(route["argv"]):
        return f"PROVIDER_UNAVAILABLE: {route['argv'][0]} not found"
    gate = gates.blocked(route["provider"], clock.wall())
    if gate:
        return f"PROVIDER_QUOTA: {route['provider']} is gated until {gate['until']}"
    return None


def provider_disabled(self, provider: str) -> str | None:
    """``PROVIDER_DISABLED: ...`` with the layer that set it when ``aicore.providers.available.<provider>.enabled`` is
    false (machine, invocation or flags: a project cannot enable what the machine disabled); ``None`` otherwise. The
    axis is independent of ``providers.selection``, which only decides which surfaces are rolled out."""
    found = self.settings.aicore if self.settings is not None else None
    if found is None:
        return None
    available, layer = routing_available(provider, resolved=found)
    if available:
        return None
    return f"PROVIDER_DISABLED: aicore.providers.available.{provider}.enabled = false ({layer})"


def selected(self, item: Item, role: str, persist: bool) -> dict:
    """The route of ``role`` that can start: its own, or, when its provider is gated (the account quota is known to
    be exhausted until a reset) or cannot start here (no CLI, a sandbox that does not start), the first declared
    fallback route that passes the admission. A gated route with no such fallback stops the run with
    ``PROVIDER_QUOTA``; one that cannot start keeps its route and is refused by the preflight with its own code (the
    optional scout is left to its own step: it is skipped when it may be)."""
    kept = (item.state.get("route_overrides") or {}).get(role)  # a fallback taken before a stop: a resume keeps it
    route = self._route(item, role, kept) if kept else self._route(item, role)
    gate = gates.blocked(route["provider"], clock.wall())
    problem = None if gate else self.route_problem(route)
    if gate is None and problem is None:
        return route
    found, refused = self._fallback(item, role, route)
    until = f"{route['provider']} is gated until {gate['until']} ({gate['class']} {gate['code']}, set by {gate['set_by']})" \
        if gate else problem
    if found is None:
        if gate is None or role == "context-scout":
            return route
        raise Stop("PROVIDER_QUOTA", f"{role}: {until}" + (f"; no fallback: {'; '.join(refused)}" if refused else "")
                   + "; resume after the reset, or remove the gate with orch conduct gates --clear")
    reason = "CAPACITY_GATED" if gate else problem.split(":", 1)[0]
    item.route_notes.append({"role": role, "reason_code": reason, "from": self.label(route), "to": self.label(found),
                             "detail": until})
    if persist and self.progress is not None:
        if gate:
            self.progress.emit("info", item=item.ref, role=role, route=self.label(found), reason_code="CAPACITY_GATED",
                               message=f"{role}: {until}")
            self._provider_limit(item, None, role, route["provider"], gate["class"], "CAPACITY_GATED",
                                 until=gate["until"])
        self.progress.emit("info", item=item.ref, role=role, route=self.label(found), reason_code="ROUTE_FALLBACK",
                           message=f"{role}: {self.label(route)} -> {self.label(found)} ({reason})")
        self._route_fallback(item, None, role, route, found, [reason])
    return found


def fallback(self, item: Item, role: str, current: dict, declared: Optional[dict] = None) -> tuple:
    """``(route, refused)``: the first declared fallback route of ``role`` other than ``current`` that passes
    ``_admit`` (``declared`` narrows the choice to the route retry.decide named), and why the others were refused."""
    refused = []
    for entry in item.options.get("fallback_routes", []):
        if entry["role"] != role or (entry["provider"], entry["model_class"]) == (current["provider"],
                                                                                current["model_class"]):
            continue
        if declared is not None and (entry["provider"], entry["model_class"]) != (declared["provider"],
                                                                                declared["model_class"]):
            continue
        try:
            candidate = self._route(item, role, entry)
        except Stop as stop:
            refused.append(f"{entry['provider']}/{entry['model_class']}: {stop.code}: {stop.message}")
            continue
        problem = self._admit(item, role, candidate)
        if problem is None:
            return candidate, refused
        refused.append(f"{self.label(candidate)}: {problem}")
    return None, refused


def admit(self, item: Item, role: str, route: dict) -> Optional[str]:
    """Why ``route`` may not take over the work of ``role``, as ``CODE: text``; ``None`` when it may: not below the
    class and effort the work requires, startable here (transport, sandbox, command) and not gated."""
    if role == "executor":
        try:
            self._route_minimum(item, route)
        except Stop as stop:
            return f"{stop.code}: {stop.message}"
    return self.route_problem(route) or self._claude_sandbox_problem(item, route)


def refuse_acp(self, item: Item) -> None:
    unsupported = [(role, route) for role, route in item.routes.items()
                   if role not in OPTIONAL_ROLES and route["transport"] == "acp"]
    if unsupported:
        raise Stop("TRANSPORT_UNSUPPORTED", "; ".join(
            f"{role} on {route['provider']}: the conductor does not drive acp roles; "
            "use claude-code or codex for this role" for role, route in unsupported))


def preflight(self, item: Item) -> None:
    """Every required role can start before any work is done: an acp route or a missing CLI stops the run now with a
    plain message, not after an hour of executor work (an optional scout or report-fixer is only skipped)."""
    self._refuse_acp(item)
    required = {role: route for role, route in item.routes.items() if role not in OPTIONAL_ROLES}
    codex = [(role, route) for role, route in required.items() if self._codex_sandboxed(route)]
    claude = self._sandbox_mode(item) == "require" and any(self._claude_bash(route) for route in required.values())
    blocked = []
    if (codex or claude) and not sandbox.probe()["available"]:  # probed only when a role depends on it
        reason = sandbox.probe()["reason"]
        blocked = [f"{role} on {route['provider']}: the provider sandbox cannot start ({reason})"
                   for role, route in codex]
        if claude:
            blocked.append(f"instructions.sandbox is require, and the sandbox cannot start ({reason})")
    elif claude:  # the sandbox starts, but a CLI that does not list --settings would run the role unconfined
        blocked = [f"{role}: instructions.sandbox is require, and the claude CLI does not list --settings"
                   for role, route in required.items()
                   if self._claude_bash(route) and not self._knows(route["argv"], ["--settings"])]
    if blocked:
        raise Stop("SANDBOX_UNAVAILABLE", "; ".join(blocked))
    off = [f"{role}: {self.provider_disabled(route['provider'])}" for role, route in required.items()
           if self.provider_disabled(route["provider"])]
    if off:
        raise Stop("PROVIDER_UNAVAILABLE", f"cannot start {'; '.join(off)}")
    missing = [f"{role} ({route['argv'][0]})" for role, route in item.routes.items()
               if role not in OPTIONAL_ROLES and not process.available(route["argv"])]
    if missing:
        raise Stop("PROVIDER_UNAVAILABLE", f"cannot start {', '.join(missing)}: install or log in the CLI, then resume")
    gated = [f"{role} on {route['provider']} until {gate['until']}" for role, route in required.items()
             for gate in [gates.blocked(route["provider"], clock.wall())] if gate]
    if gated:
        raise Stop("PROVIDER_QUOTA", f"{'; '.join(gated)}: the account quota is exhausted; resume after the reset, "
                                     "or remove the gate with orch conduct gates --clear")


def route(self, item: Item, role: str, override: Optional[dict] = None) -> dict:
    """The route of ``role``; ``override`` (a ``fallback_routes`` entry or retry.decide's route) replaces the
    provider, the model class and, when it has one, the effort of the stage and drops its model."""
    wanted = opts.stage_route(item.options, role)
    if override:
        wanted = {**{key: value for key, value in wanted.items() if key not in ("provider", "model", "model_class")},
                  **{key: override[key] for key in ("provider", "model_class", "effort") if override.get(key)}}
    review_class = None  # the class the plan's review route asks of the reviewer
    if role == "reviewer" and not override:
        selector, review_class, _ = self._reviewer_selector(item)
        provider, model, effort = selector["provider"], selector.get("model"), selector.get("effort")
    else:
        provider = wanted.get("provider") or self.conductor.get("provider") or "claude-code"
        model, effort = wanted.get("model"), wanted.get("effort")
    entry = self._entry(role, provider)
    model_class = review_class or wanted.get("model_class") or entry["model_class"]
    if role == "executor" and not effort:
        effort = (item.claim.get("route") or {}).get("effort")
    effort = effort or entry["effort"]
    if entry["model_set"] == "supported" and not model:
        planned = next((stage for stage in item.launch_plan.get("stages", [])
                        if LAUNCH_ROLE.get(stage.get("role"), stage.get("role")) == LAUNCH_ROLE.get(role, role)
                        and stage.get("provider") == provider and stage.get("model")
                        and not wanted.get("model_class") and not review_class), None)
        try:
            model = planned["model"] if planned else self._catalog_get().resolve_model(provider, model_class)
        except catalogs.CatalogError as error:
            raise Stop(error.code, str(error)) from None
    values = {"model": model or "", "effort": effort, "cwd": str(self.project), "orch": str(ORCH_ROOT)}
    argv_override = (self.conductor.get("argv") or {}).get(role)
    resume_argv = None
    try:
        if argv_override:
            argv = catalogs.substitute(list(argv_override), values)
        elif effort not in launch.EFFORTS:
            raise Stop("ROUTE_UNDERSHOOT", f"{role} needs effort {effort}, which {provider} cannot start")
        else:
            argv = launch.build_argv(self._launch_catalog(), LAUNCH_ROLE.get(role, role), provider, model=model,
                                     effort=effort, cwd=self.project, access=self._launch_access())
            resume_argv = launch.build_resume_argv(self._launch_catalog(), LAUNCH_ROLE.get(role, role), provider,
                                                   model=model, effort=effort, cwd=self.project,
                                                   access=self._launch_access())
    except launch.LaunchError as error:
        raise Stop(error.code, str(error)) from None
    # The wall of a role: ``stage_timeout_s`` when set; else, for a streaming role, ``role_timeout_s`` of its role (an
    # auxiliary role must not hang a run forever; the executor and the bounded-implementer have none, silence is caught
    # by ``stage_idle_timeout_s``). A ``text`` role writes only at its end, so the catalog timeout stays its ceiling.
    limits, streaming = item.options["limits"], entry["transport"] != "text"
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


def reviewer_selector(self, item: Item) -> tuple:
    """``(selector, model_class, source)`` of the reviewer of ``item``. A reviewer a layer sets (the configuration, a
    work-source layer, ``--options``) wins over the plan, as an explicit executor does; without one the plan's
    ``review_route`` of the piece completes the default reviewer (source ``plan:review.reviewer``); else the default
    (source ``None``)."""
    selector = opts.parse_selector(item.options["reviewer"])
    source = item.sources.get("reviewer")
    planned = item.input_doc.get("review_route") or {}
    if source or not planned:
        return selector, None, source
    found, model_class = planned_reviewer(selector, planned)
    return found, model_class, PLAN_REVIEW_SOURCE


def route_minimum(self, item: Item, route: Optional[dict] = None) -> None:
    minimum = item.claim.get("route") or {}
    route = route or item.routes["executor"]
    if minimum.get("class") and CLASS_RANK.get(route["model_class"], -1) < CLASS_RANK[minimum["class"]]:
        raise Stop("ROUTE_UNDERSHOOT", f"the executor class {route['model_class']} is below "
                                       f"{minimum['class']} required by {item.ref}")
    if minimum.get("effort") and EFFORT_RANK.get(route["effort"], -1) < EFFORT_RANK[minimum["effort"]]:
        raise Stop("ROUTE_UNDERSHOOT", f"the executor effort {route['effort']} is below "
                                       f"{minimum['effort']} required by {item.ref}")


def label(route: dict) -> str:
    return "/".join(part for part in (route.get("provider"), route.get("model"), route.get("effort")) if part)


def actor(self, role_route: dict) -> dict:
    return {key: role_route[key] for key in ("provider", "model", "effort") if role_route.get(key)}
