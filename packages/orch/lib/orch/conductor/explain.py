"""``orch.py route explain``: why a role of the conductor runs on the route it does.

The candidates are the routes the layers name (the ``stages`` of the options, the reviewer selector, ``[orch.conductor]``
and the launch catalog) and the ``fallback_routes`` of the role; each one is checked with the rules a run applies
(``aicore.providers.available``, the command, the transport, the sandbox, the capacity gates). ``selected`` is the route
route choice would take, with the layer each of its fields came from. Nothing is written and no role is started.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from aicore.provider.config import routing_available

from orch.conductor import engine, gates, options as opts

ROLES = ("context-scout", "executor", "reviewer", "triager", "registrar", "report-fixer")
DEFAULT_SOURCE = "default"


class ExplainError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _latest_item_run(project: Path, plan: str, ref: str) -> Optional[tuple]:
    """``(run_id, options.json)`` of the newest conductor run of ``plan`` that ran ``ref``, or ``None``."""
    found = []
    root = engine.runs_root(project)
    for directory in root.glob("cnd-*"):
        doc = engine.read_json(directory / engine.RUN_FILE)
        options = engine.read_json(directory / engine.safe(ref) / "options.json")
        if doc and options and doc.get("plan") == plan:
            found.append((directory.name, options))
    return max(found, key=lambda pair: pair[0]) if found else None


def _provider_layer(conductor: engine.Conductor) -> str:
    """``[orch.conductor].provider`` with the configuration layer that set it (``defaults`` when none did)."""
    resolved = conductor.settings.resolved
    layer = resolved.explain("conductor.provider")[0].layer if resolved is not None else "defaults"
    return f"config:orch.conductor.provider ({layer})"


def _field_sources(conductor: engine.Conductor, item: engine.Item, role: str) -> dict:
    """The layer each of provider, model_class, effort and model of the route comes from."""
    options, sources = item.options, item.sources
    stage = opts.stage_route(options, role)
    stage_source = sources.get(f"stages.{role}")
    sources_of = {}
    if role == "reviewer":
        selector = opts.parse_selector(options["reviewer"])
        reviewer = sources.get("reviewer", DEFAULT_SOURCE)
        sources_of["provider"] = reviewer
        sources_of["model"] = reviewer
        if selector.get("effort"):
            sources_of["effort"] = reviewer
    for key in ("provider", "model_class", "effort", "model"):
        if key in sources_of:
            continue
        if stage.get(key):
            sources_of[key] = stage_source
        elif key == "provider" and conductor.conductor.get("provider"):
            sources_of[key] = _provider_layer(conductor)
        elif key == "effort" and role == "executor" and (item.claim.get("route") or {}).get("effort"):
            sources_of[key] = "claim:route"
        elif key == "model":
            sources_of[key] = "model-catalog (class)"
        else:
            sources_of[key] = f"launch-catalog ({DEFAULT_SOURCE})"
    return sources_of


def _row(conductor: engine.Conductor, item: engine.Item, role: str, origin: str, layer: Optional[str],
         override: Optional[dict]) -> dict:
    """One candidate with its route and why it can or cannot start."""
    row = {"origin": origin, "layer": layer}
    try:
        route = conductor._route(item, role, override)
    except engine.Stop as stop:
        return {**row, **{key: (override or {}).get(key) for key in ("provider", "model_class", "effort")},
                "available": False, "problem": f"{stop.code}: {stop.message}"}
    problem = conductor._admit(item, role, route)  # the rules of a run: start, gate, sandbox, and the minimum of the work
    return {**row, "provider": route["provider"], "model": route["model"], "model_class": route["model_class"],
            "effort": route["effort"], "transport": route["transport"], "available": problem is None,
            "problem": problem}


def explain(conductor: engine.Conductor, role: str, *, scenario: Optional[str] = None, plan: Optional[str] = None,
            ref: Optional[str] = None) -> dict:
    """The explanation of the route of ``role``; raises ``ExplainError``."""
    if role not in ROLES:
        raise ExplainError("ROLE_UNKNOWN", f"{role!r} is not a role of the conductor: {', '.join(ROLES)}")
    claim = {"scenario": scenario or conductor.settings.default_profile, "options": []}
    item = engine.Item(ref=ref or "(configuration)", orch_run="-", state={}, directory=Path(), claim=claim)
    conductor.run_id, conductor.run_doc = "cnd-explain", {"options_file": None}
    origin = "configuration"
    try:
        if plan or ref:
            if not (plan and ref):
                raise ExplainError("ARGUMENTS_INVALID", "--plan and --item go together")
            recorded = _latest_item_run(conductor.project, plan, ref)
            if recorded is None:
                raise ExplainError("ITEM_UNKNOWN", f"no conductor run of {ref} in plan {plan} in this project; "
                                   "omit --plan and --item to explain the configuration")
            run_id, doc = recorded
            claim["scenario"] = doc.get("scenario") or claim["scenario"]
            if doc.get("claim_route"):
                claim["route"] = doc["claim_route"]  # the class and effort the work requires of its executor
            conductor._resolve(item, persist=False)  # the policy of the scenario; the options are the recorded ones
            item.options, item.sources, origin = doc["options"], doc.get("sources") or {}, f"run {run_id}"
        else:
            conductor._resolve(item, persist=False)
        stages = [stage["role"] for stage in item.policy.get("stages", [])]
        rows = []
        stage = opts.stage_route(item.options, role)
        named = any(stage.get(key) for key in ("provider", "model", "model_class", "effort"))  # not a bare role entry
        if named:
            rows.append(_row(conductor, item, role, "stages", item.sources.get(f"stages.{role}"), None))
        if role == "reviewer":
            rows.append(_row(conductor, item, role, "reviewer", item.sources.get("reviewer", DEFAULT_SOURCE), None))
        elif not named:
            layer = _provider_layer(conductor) if conductor.conductor.get("provider") else f"launch-catalog ({DEFAULT_SOURCE})"
            rows.append(_row(conductor, item, role, "orch.conductor" if conductor.conductor.get("provider")
                             else "launch-catalog", layer, None))
        for entry in item.options.get("fallback_routes", []):
            if entry["role"] == role:
                rows.append(_row(conductor, item, role, "fallback_routes", item.sources.get("fallback_routes"), entry))
        selected, stop = None, None
        try:
            route = conductor._selected(item, role, False)
            selected = {key: route.get(key) for key in ("provider", "model", "model_class", "effort", "transport")}
            selected["sources"] = _field_sources(conductor, item, role)
            moved = next((note for note in item.route_notes if note["role"] == role), None)
            selected["moved"] = moved
            problem = conductor._admit(item, role, route)  # what the preflight would refuse before any work
            if problem:
                code, _, message = problem.partition(": ")
                stop = {"code": code, "message": message}
        except engine.Stop as error:
            stop = {"code": error.code, "message": error.message}
    except engine.Stop as error:
        raise ExplainError(error.code, error.message) from None
    providers = sorted({row["provider"] for row in rows if row.get("provider")} |
                       ({selected["provider"]} if selected else set()))
    config = {}
    for name in providers:
        enabled, layer = routing_available(name, resolved=conductor.settings.aicore) if conductor.settings.aicore else (True, "defaults")
        config[name] = {"enabled": enabled, "layer": layer}
    return {"role": role, "scenario": claim["scenario"], "source": origin, "stages": stages,
            "selected": selected, "stop": stop, "candidates": rows,
            "providers": config, "gates": [{"provider": name, **entry}
                                           for name, entry in sorted(gates.active(engine.wall()).items())]}


def text(found: dict) -> str:
    """The explanation as plain text."""
    lines = [f"role {found['role']} (scenario {found['scenario']}, options from {found['source']})"]
    selected = found["selected"]
    if selected:
        route = "/".join(part for part in (selected["provider"], selected["model"], selected["effort"]) if part)
        lines.append(f"selected: {route} (class {selected['model_class']}, transport {selected['transport']})")
        lines += [f"  {key}: {value}" for key, value in selected["sources"].items()]
        if selected.get("moved"):
            moved = selected["moved"]
            lines.append(f"  moved: {moved['from']} -> {moved['to']} ({moved['reason_code']})")
    else:
        lines.append(f"selected: none — {found['stop']['code']}: {found['stop']['message']}")
    lines.append("candidates:")
    for row in found["candidates"]:
        route = "/".join(part for part in (row.get("provider"), row.get("model"), row.get("effort")) if part)
        state = "available" if row["available"] else row["problem"]
        lines.append(f"  [{row['origin']}] {route or '-'} class {row.get('model_class')} — {state}"
                     + (f" (layer {row['layer']})" if row.get("layer") else ""))
    for name, item in found["providers"].items():
        lines.append(f"provider {name}: aicore.providers.available.{name}.enabled = {str(item['enabled']).lower()} "
                     f"({item['layer']})")
    for gate in found["gates"]:
        lines.append(f"gate {gate['provider']}: until {gate['until']} ({gate['class']} {gate['code']})")
    return "\n".join(lines) + "\n"
