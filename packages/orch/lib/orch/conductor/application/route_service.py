"""The routes of a piece in a run: the launch catalog of the run, the route of each role and its fallback, the
admission of a route (startable here, not gated, not below the minimum of the work) and the preflight before any work.
The rules are ``policies/routing.py`` and ``policies/sandbox.py``; this module probes the machine (``sandbox.probe``,
``process.available``, ``gates.blocked``), keeps the routes of the piece and says what moved."""
from __future__ import annotations

import contextlib
from typing import Optional

from aicore.provider.models import admitted_class

from orch import bindings, catalog as catalogs, launch, sandbox
from orch.conductor import gates, options as opts, process, records
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import cli_probe, clock
from orch.conductor.policies import authority as authority_rules, isolation as isolation_rules, routing as route_rules
from orch.conductor.policies import sandbox as sandbox_rules
from orch.conductor.policies.routing import OPTIONAL_ROLES


def _policy_scenario(self, item: Item) -> str:
    policy = getattr(item, "policy", None) or {}
    claim = getattr(item, "claim", None) or {}
    return policy.get("policy_id") or claim.get("scenario") or "-"


def policy_stage_unavailable(self, item: Item, preview: bool = False) -> dict:
    """Refuse a required stage the conductor does not run; beacon an optional one once per run.

    A preview (``run --dry-run``) does not stop: both cases are returned as ``unavailable`` with the same text.
    The beacon flag lives on the run state so a later piece or a resume does not repeat it.
    """
    required, optional = route_rules.unsupported_stages(getattr(item, "policy", None))
    unavailable = {}
    scenario = _policy_scenario(self, item)
    if optional:
        message = f"{scenario}: {route_rules.stage_list(optional)} is not run by the conductor; skipped"
        for _stage_id, role in optional:
            unavailable[role] = f"POLICY_STAGE_SKIPPED: {message}"
        if not (getattr(self, "state", None) or {}).get("policy_stage_skipped"):
            self.state["policy_stage_skipped"] = True
            run_id = getattr(self, "run_id", "") or ""
            if getattr(self, "store", None) is not None and run_id not in ("", "cnd-dry-run"):
                self._save()
            progress = getattr(self, "progress", None)
            if progress is not None:
                progress.emit("info", item=getattr(item, "ref", None), reason_code="POLICY_STAGE_SKIPPED",
                              message=message)
    if required:
        message = (f"{scenario}: {route_rules.stage_list(required)} is not run by the conductor; "
                   "choose another scenario or run the plan natively")
        if preview:
            for _stage_id, role in required:
                unavailable[role] = f"POLICY_STAGE_UNSUPPORTED: {message}"
        else:
            raise Stop("POLICY_STAGE_UNSUPPORTED", message)
    return unavailable


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
    """``[orch.launch] access`` of this run (:func:`policies.routing.launch_access`); a run without settings is ``open``."""
    return route_rules.launch_access(getattr(getattr(self, "settings", None), "launch", None))


def entry(self, role: str, provider: str) -> dict:
    return route_rules.entry(self._launch_catalog(), role, provider)


def routes(self, item: Item, persist: bool = True, preview: bool = False) -> dict:
    """Select routes and return unavailable roles for a preview; required launch errors stop a real run."""
    unavailable = {}
    # Before any role of the piece: a required stage this conductor does not run stops a real run here
    # (the first call is persist=False, still before prepare). A dry-run only reports it.
    review_only = item.input_doc.get("provenance", {}).get("kind") == "review"
    if not review_only:
        unavailable.update(policy_stage_unavailable(self, item, preview=preview))
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
    if review_only:
        roles = ["reviewer", self._triage_role(item)]
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
    if self._bounded_corrections(item):  # optional: without a route the corrections stay with the executor
        try:
            item.routes["bounded-implementer"] = self._selected(item, "bounded-implementer", persist)
        except Stop as stop:
            item.routes.pop("bounded-implementer", None)
            unavailable["bounded-implementer"] = f"{stop.code}: {stop.message}"
    if "executor" in item.routes:
        self._route_minimum(item)
    receipt_problems = current_input_receipt_unavailable(item)
    if receipt_problems and not preview:
        raise Stop("CURRENT_INPUT_RECEIPT_UNSUPPORTED", "; ".join(receipt_problems.values()))
    unavailable.update({role: f"CURRENT_INPUT_RECEIPT_UNSUPPORTED: {message}"
                        for role, message in receipt_problems.items()})
    if persist:
        self._preflight(item)
        records.write(item.directory / "routes.json", item.routes, "item-routes")
    return unavailable


def route_problem(self, route: dict) -> str | None:
    """Why a route cannot run, as ``CODE: text``; ``None`` when it can. An ``acp`` role is never driven by the
    conductor (D4), whatever command line stands in for it; a Codex route confined by ``--sandbox`` needs the
    provider sandbox to start on this machine."""
    disabled = self.provider_disabled(route["provider"])
    if disabled:
        return disabled
    if route["provider"] == "antigravity" and not launch.agy_role_opted_in(route.get("role"), getattr(self, "env", None)):
        return launch.ANTIGRAVITY_AUTHORITY_PROBLEM
    if route["provider"] == "antigravity" and route.get("transport") != "jsonl":
        return "TRANSPORT_UNSUPPORTED: Antigravity roles require jsonl"
    if route["transport"] == "acp":
        return "TRANSPORT_UNSUPPORTED: the conductor does not drive acp roles"
    refused = route_rules.registrar_problem(route, project=str(getattr(self, "project", "")), access=self._launch_access())
    if refused:
        return refused
    if self._codex_sandboxed(route) and not sandbox.probe()["available"]:
        return f"SANDBOX_UNAVAILABLE: {sandbox.probe()['reason']}"
    if not process.available(route["argv"]):
        return f"PROVIDER_UNAVAILABLE: {route['argv'][0]} not found"
    gate = gates.blocked(route["provider"], clock.wall())
    if gate:
        return f"PROVIDER_QUOTA: {route['provider']} is gated until {gate['until']}"
    return None


def provider_disabled(self, provider: str) -> str | None:
    """:func:`policies.routing.provider_disabled` over the ``aicore`` settings of this run (none: nothing is disabled)."""
    return route_rules.provider_disabled(self.settings.aicore if self.settings is not None else None, provider)


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
    reason = "CAPACITY_GATED" if gate else (problem or "").split(":", 1)[0]
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
    if role == "bounded-implementer":  # also a fallback route taken after a quota: the same minimum every time
        why = route_rules.correction_refusal(correction_minimum(item), route, item.ref)
        if why:
            return why
    return self.route_problem(route) or self._claude_sandbox_problem(item, route)


def refuse_acp(self, item: Item) -> None:
    route_rules.refuse_acp(item.routes)


def current_input_receipt_unavailable(item: Item) -> dict:
    """Mandatory receipt requirements, separate from executable availability and completed usage support."""
    required = {role: route for role, route in item.routes.items()
                if opts.stage_route(item.options, role).get("require_current_input_receipt")}
    if not required:
        return {}
    capabilities = bindings.load_capabilities()
    return {role: bindings.current_input_receipt_problem("native", route["provider"],
                                                        capabilities.get(("native", route["provider"])))
            for role, route in required.items()}


def preflight(self, item: Item) -> None:
    """Every required role can start before any work is done: an acp route or a missing CLI stops the run now with a
    plain message, not after an hour of executor work (an optional scout or report-fixer is only skipped)."""
    receipt_problems = current_input_receipt_unavailable(item)
    if receipt_problems:
        raise Stop("CURRENT_INPUT_RECEIPT_UNSUPPORTED", "; ".join(receipt_problems.values()))
    if item.input_doc.get("provenance", {}).get("kind") != "review":
        policy_stage_unavailable(self, item, preview=False)
    self._refuse_acp(item)
    required = {role: route for role, route in item.routes.items() if role not in OPTIONAL_ROLES}
    if any(route.get("provider") == "antigravity" and not launch.agy_role_opted_in(role, getattr(self, "env", None))
           for role, route in required.items()):
        code, reason = launch.ANTIGRAVITY_AUTHORITY_PROBLEM.split(": ", 1)
        raise Stop(code, reason)
    if any(route.get("provider") == "antigravity" and route.get("transport") != "jsonl"
           for route in required.values()):
        raise Stop("TRANSPORT_UNSUPPORTED", "Antigravity roles require jsonl")
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
    # the profiles are read (ISOLATION_PROFILES_INVALID) and, under require, every isolated role must be isolated fully
    isolated = {role: route for role, route in required.items()
                if role in item.options["instructions"]["isolate_roles"]
                and item.options["instructions"].get("isolation", "prefer") != "off"}
    plans = [self._isolation_plan(item, role, route) for role, route in isolated.items()]
    refused = [text.split(": ", 1)[1] for text in map(isolation_rules.problem, plans) if text]
    if not refused and item.options["instructions"].get("isolation") == "require":  # the project settings stay out too
        refused = [text.split(": ", 1)[1] for plan, (role, route) in zip(plans, isolated.items())
                   if route.get("provider") == "claude-code"
                   for text in [authority_rules.setting_sources_problem(
                       self._authority(item, role, route, admit=False, quiet=True), plan)] if text]
    if refused:
        raise Stop("ISOLATION_UNAVAILABLE", " | ".join(refused))
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
    """The route of ``role`` over the options, the claim and the launch plan of ``item``, the configuration of the run and
    its catalogs; ``override`` (a ``fallback_routes`` entry or retry.decide's route) replaces the provider, the model
    class and, when it has one, the effort of the stage. The rules are ``policies/routing.py``; the lookups between them
    (the reviewer selector, the launch entry and catalog, the model catalog, the access) are made here, in that order and
    only when a rule needs them."""
    reviewer = self._reviewer_selector(item) if role == "reviewer" and not override else None
    target = route_rules.route_target(role=role, item_options=item.options, conductor_cfg=self.conductor,
                                      override=override, reviewer=reviewer)
    entry = self._entry(role, target["provider"])
    chosen = route_rules.route_model(target, role=role, entry=entry, claim=item.claim, launch_plan=item.launch_plan)
    if chosen["needs_model"]:
        try:
            chosen["model"] = self._catalog_get().resolve_model(chosen["provider"], chosen["model_class"])
        except catalogs.CatalogError as error:
            raise Stop(error.code, str(error)) from None
    chosen = named_model_class(self, item, role, target, chosen)
    builds = route_rules.builds_argv(role, chosen["effort"], self.conductor)
    return route_rules.route(role=role, item_options=item.options, chosen=chosen, entry=entry,
                             conductor_cfg=self.conductor, project=self.project,
                             launch_catalog=self._launch_catalog() if builds else None,
                             access=self._launch_access() if builds else None)


def named_model_class(self, item: Item, role: str, target: dict, chosen: dict) -> dict:
    """``chosen`` with the class the model catalog knows for a model the layers name (``admitted_class``), when that is
    lower than the label of the stage or of the launch entry: the route minimum then sees the model, not the label. A
    model the catalog does not know keeps the label and is said once per role (``ROUTE_MODEL_UNKNOWN``, info)."""
    model = chosen.get("model") if chosen["provider"] == "antigravity" else target["model"]
    if not model:
        if chosen["provider"] == "antigravity":
            raise Stop("AGY_MODEL_CLASS_UNVERIFIED", f"{role}: Antigravity model ID is missing")
        return chosen
    known = admitted_class(self._catalog_get().models, chosen["provider"], model)
    if known is None:
        if chosen["provider"] == "antigravity":
            if (launch.agy_role_opted_in(role, getattr(self, "env", None)) and model == "gemini-4-argon-high"
                    and target.get("model") == model):
                return chosen
            raise Stop("AGY_MODEL_CLASS_UNVERIFIED",
                       f"{role}: {model} has no verified Antigravity model class")
        noted = self.__dict__.setdefault("_model_unknown_noted", set())
        mark = (item.ref, role, chosen["provider"], model)
        if mark not in noted and self.progress is not None:
            noted.add(mark)
            self.progress.emit("info", item=item.ref, role=role, reason_code="ROUTE_MODEL_UNKNOWN",
                               message=f"{role}: {chosen['provider']}/{model} is not in the model catalog; the "
                                       f"class {chosen['model_class']} of its stage or launch entry is taken as is")
        return chosen
    lowered = route_rules.lowered_class(chosen["model_class"], known)
    return chosen if lowered == chosen["model_class"] else {**chosen, "model_class": lowered}


def bounded_corrections(self, item: Item) -> bool:
    """Whether the corrections of confirmed review findings may run on the bounded-implementer
    (``review.correction_route``) in a piece that is reviewed."""
    return item.options["review"].get("correction_route") == "bounded-implementer" and self._reviewing(item)


def correction_minimum(item: Item) -> dict:
    """:func:`policies.routing.correction_minimum` of ``item``: its claim's ``route.correction``, else the full ordinary
    minimum (the claim's route and the execution-input ``route.minimum`` with its provider and model pins)."""
    return route_rules.correction_minimum(item.claim.get("route"), (item.input_doc.get("route") or {}).get("minimum"))


def correction_role(self, item: Item, blockers: bool) -> str:
    """The role that runs the next correction of confirmed review findings. ``executor`` unless
    ``review.correction_route`` is ``bounded-implementer`` and the correction has no Blocker finding; the bounded route
    must exist, start here and meet the claim's ``route.correction`` (else its ``route``), or the executor takes it with
    ``CORRECTION_ROUTE_REFUSED`` (info)."""
    if item.options["review"].get("correction_route") != "bounded-implementer" or blockers:
        return "executor"
    route = item.routes.get("bounded-implementer")
    if route is None:
        try:
            self._route(item, "bounded-implementer")
            why = "ROUTE_UNAVAILABLE: no bounded-implementer route could be selected for this piece"
        except Stop as stop:
            why = f"{stop.code}: {stop.message}"
    else:
        why = self._admit(item, "bounded-implementer", route)
    if why is None:
        return "bounded-implementer"
    self.progress.emit("info", item=item.ref, role="bounded-implementer", reason_code="CORRECTION_ROUTE_REFUSED",
                       message=f"the correction stays with the executor: {why}")
    return "executor"


def reviewer_selector(self, item: Item) -> tuple:
    """:func:`policies.routing.reviewer_selector` of ``item``."""
    return route_rules.reviewer_selector(item.options, item.sources, item.input_doc)


def route_minimum(self, item: Item, route: Optional[dict] = None) -> None:
    """:func:`policies.routing.route_minimum`: ``route`` (the executor route of ``item`` by default) against the route
    its claim requires."""
    minimum = item.claim.get("route") or {}
    route_rules.route_minimum(minimum, route or item.routes["executor"], item.ref)


def claude_sandbox_problem(self, item: Item, route: dict) -> Optional[str]:
    """:func:`policies.sandbox.claude_sandbox_problem` over the sandbox probe of this machine and the flags the CLI
    lists, probed here only for a Claude Code shell under ``require`` (the CLI only when the sandbox starts)."""
    if not sandbox_rules.claude_confinement_required(item.options, route, access=self._launch_access()):
        return None
    probed = sandbox.probe()
    listed = self._knows(route["argv"], ["--settings"]) if probed["available"] else None
    return sandbox_rules.claude_sandbox_problem(item.options, route, probe=probed, settings_listed=listed,
                                                access=self._launch_access())


def sandbox_facts(self, item: Item, role: str, route: dict, quiet: bool = False) -> dict:
    """``{mode, available, reason, settings_listed}``: what the Claude Code sandbox of ``role`` on ``route`` depends on,
    probed only for a Claude Code role with Bash and a ``mode`` not ``off`` (the CLI only when the sandbox starts). A
    sandbox that cannot start never leaves the commands unconfined silently: ``prefer`` says so once and goes on under
    the filesystem guard, ``require`` was stopped in the preflight. ``quiet`` probes the same facts and says nothing
    (the identity of an executor session). A piece without instructions (a batch role of a piece the run did not
    resolve) has the default mode ``prefer``."""
    mode = self._sandbox_mode(item) if "instructions" in (item.options or {}) else "prefer"
    found = {"mode": mode, "available": None, "reason": None, "settings_listed": None}
    if mode == "off" or not route.get("argv") or not self._claude_bash(route) \
            or not sandbox_rules.filesystem(role) == "write" or self._launch_access() == "open":
        return found
    probed = sandbox.probe()
    found.update(available=bool(probed["available"]), reason=probed["reason"])
    if not probed["available"]:
        if mode == "prefer" and not quiet:
            note_isolation(self, route["provider"], "sandbox",
                           f"sandbox unavailable: {probed['reason']}; the commands of claude-code roles run under the "
                           "filesystem guard only")
        return found
    found["settings_listed"] = (cli_probe.knows if quiet else self._knows)(route["argv"], ["--settings"])
    return found


def launch_facts(self, item: Item, role: str, route: dict, quiet: bool = False) -> dict:
    """``{sandbox, access, declared_network}``: what the authority envelope of a launch of ``role`` on ``route`` is
    computed over from this layer (:func:`sandbox_facts`, ``[orch.launch] access``, ``tools.network`` of the role)."""
    return {"sandbox": sandbox_facts(self, item, role, route, quiet=quiet), "access": self._launch_access(),
            "declared_network": self.declared_network(role)}


def sandbox_args(self, item: Item, role: str, route: dict) -> list:
    """``--settings`` with only the ``sandbox`` block for a Claude Code role with Bash (the provider merges it with
    the user's settings), with a write grant for ``scope.extra_paths`` when the role writes (:func:`sandbox_facts`)."""
    facts = sandbox_facts(self, item, role, route)
    if not facts["available"] or not facts["settings_listed"]:
        return []
    return sandbox_rules.sandbox_args(item.options, role, route,
                                      extra_paths=self._scope_option(item, "extra_paths", []),
                                      network=self.declared_network(role), access=self._launch_access())


def note_isolation(self, provider: str, reason: str, message: str) -> None:
    """``ISOLATION_PARTIAL`` (info) once per run, provider and reason: the keys said are ``state.isolation_noted``
    (``provider:reason``), saved with the run, so a later piece or a resume does not say it again."""
    state = getattr(self, "state", None)
    noted = state.setdefault("isolation_noted", []) if isinstance(state, dict) \
        else self.__dict__.setdefault("_isolation_noted", [])  # a facade without a run
    key = f"{provider}:{reason}"
    store = getattr(self, "store", None)
    with store.mutating() if store is not None else contextlib.nullcontext():
        if key in noted:
            return
        noted.append(key)
        if store is not None and getattr(self, "run_id", "") not in ("", "cnd-dry-run"):
            self._save()
    if getattr(self, "progress", None) is not None:
        self.progress.emit("info", reason_code="ISOLATION_PARTIAL", message=message)


def knows(self, argv: list, flags: list, *, help_argv: Optional[list] = None) -> bool:
    """:func:`infrastructure.cli_probe.knows` for the run: a flag the CLI does not list is said once per run, provider
    and flags (``ISOLATION_PARTIAL``); the cache of the probe never decides whether it is said."""
    if cli_probe.knows(argv, flags, help_argv=help_argv):
        return True
    missing = [flag for flag in flags if not cli_probe.knows(argv, [flag], help_argv=help_argv)] or list(flags)
    cli = cli_probe.command(argv) or (argv[0] if argv else "-")
    asked = " ".join([cli, *(help_argv[1:] if help_argv else ["--help"])])
    why = f"{asked} could not be read" if cli_probe.failed(argv, help_argv=help_argv) \
        else f"{cli} does not list {' '.join(missing)}"
    note_isolation(self, cli_probe.provider(argv) or "-", " ".join(missing),
                   f"{why}; roles are isolated by the environment only")
    return False


def note_plan(self, item: Item, isolation: dict) -> None:
    """What a ``prefer`` isolation plan leaves out (:func:`policies.isolation.partial_notes`), once per run, provider and
    reason."""
    for reason, message in isolation_rules.partial_notes(isolation):
        note_isolation(self, isolation["provider"], reason, f"{isolation['role']}/{message}")
