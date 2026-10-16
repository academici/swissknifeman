#!/usr/bin/env python3
"""gui-hub: the hub (fleet, control surface, doctor, units) as GUI queries; an aicore command plugin (protocol 1).

The adapter only calls the hub command line (``$SKM_UMBRELLA`` or ``swissknifeman`` on PATH) and moves fields of
its JSON answers into ``view-data/v1``. It computes no status, layer or fix of its own: the one piece of mapping is
the table from ``fixes[].layer`` to the four control-surface layers. A repair is offered only for a fix that is
``maind sync ... --only <cap>`` with a cap of the allowlist; any other fix stays text. stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
VIEW = "urn:swissknifeman:gui:view-data:v1"
RESPONSE = "urn:swissknifeman:aicore:plugin-response:v1"
CAPS = ("mcp", "code-graph", "graph", "memory", "memory-hook", "health-hook", "health-doc", "feature-log-hook",
        "ecosystem-skill", "agent-pack")
# The four layers of docs/control-surface.md, in their order, and where a fix of the hub lands.
LAYERS = (("skills", "Skills"), ("agents", "Roles/agents"), ("mcp", "MCP"), ("memory", "Memory/graph"))
LAYER_OF = {"skills": "skills", "skill": "skills", "agent-pack": "agents", "agents": "agents", "roles": "agents",
            "mcp": "mcp", "memory": "memory", "graph": "memory", "code-graph": "memory"}
STATUSES = ("ok", "warn", "fail", "skip", "unknown")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


class HubError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def safe_text(value: Any, limit: int = 300) -> str:
    text = _CONTROL.sub(" ", str(value)).strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def umbrella() -> str:
    found = os.environ.get("SKM_UMBRELLA") or shutil.which("swissknifeman")
    if not found:
        raise HubError("HUB_UNAVAILABLE", "the hub command line was not found (swissknifeman on PATH or SKM_UMBRELLA)")
    return found


def hub_json(args: List[str], timeout_s: float) -> Any:
    """The JSON answer of ``swissknifeman <args>``; ``HUB_CLI_FAILED`` for an exit other than 0 or a non-JSON answer."""
    command = [umbrella(), *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=max(1.0, timeout_s),
                                stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise HubError("HUB_CLI_FAILED", f"swissknifeman {' '.join(args)} did not answer in time") from None
    except OSError as error:
        raise HubError("HUB_UNAVAILABLE", f"swissknifeman cannot run: {error.strerror}") from None
    if result.returncode != 0:
        tail = [line for line in result.stderr.splitlines() if line.strip()][-1:] or [f"exit {result.returncode}"]
        raise HubError("HUB_CLI_FAILED", f"swissknifeman {' '.join(args)} failed: {safe_text(tail[0])}")
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise HubError("HUB_CLI_FAILED", f"swissknifeman {' '.join(args)} did not answer JSON") from None


def _projects(doc: Any) -> List[Dict[str, Any]]:
    projects = doc.get("projects") if isinstance(doc, dict) else None
    if not isinstance(projects, list):
        raise HubError("HUB_CLI_FAILED", "swissknifeman status --all --json has no projects list")
    return [project for project in projects if isinstance(project, dict) and isinstance(project.get("id"), str)]


def _same(first: str, second: str) -> bool:
    return os.path.realpath(first) == os.path.realpath(second)


def find_project(doc: Any, root: str) -> Optional[Dict[str, Any]]:
    """The fleet project whose path is ``root`` after realpath (the only link between a gui and a maind project)."""
    for project in _projects(doc):
        if isinstance(project.get("path"), str) and _same(project["path"], root):
            return project
    return None


def repair_cap(fix: Any) -> Optional[str]:
    """The cap of ``maind sync ... --only <cap>`` when it is one allowlisted cap; anything else is no repair."""
    if not isinstance(fix, str):
        return None
    tokens = fix.split()
    if tokens[:2] != ["maind", "sync"] or "--only" not in tokens:
        return None
    position = tokens.index("--only") + 1
    cap = tokens[position] if position < len(tokens) else ""
    return cap if cap in CAPS else None


# --- queries ---------------------------------------------------------------------------------------------------


def fleet(timeout_s: float, **_: Any) -> Dict[str, Any]:
    rows = []
    for project in _projects(hub_json(["status", "--all", "--json"], timeout_s)):
        skills = project.get("skills") if isinstance(project.get("skills"), dict) else {}
        packs = project.get("agent_packs") if isinstance(project.get("agent_packs"), dict) else {}
        fixes = project.get("fixes") if isinstance(project.get("fixes"), list) else []
        rows.append({"id": project["id"], "cells": {
            "name": str(project.get("name") or project["id"]), "status": str(project.get("status") or "unknown"),
            "trusted": "yes" if project.get("trusted") else "no", "skills": int(skills.get("total") or 0),
            "packs": int(packs.get("count") or 0), "fixes": len(fixes)}})
    columns = [{"id": "name", "title": "Project", "type": "text"}, {"id": "status", "title": "Status", "type": "status"},
               {"id": "trusted", "title": "Trusted", "type": "text"}, {"id": "skills", "title": "Skills", "type": "number"},
               {"id": "packs", "title": "Agent packs", "type": "number"}, {"id": "fixes", "title": "Fixes", "type": "number"}]
    return {"$schema": VIEW, "view": "resource-list", "columns": columns, "rows": rows, "total": len(rows)}


def fleet_summary(timeout_s: float, **_: Any) -> Dict[str, Any]:
    doc = hub_json(["status", "--all", "--json"], timeout_s)
    projects = _projects(doc)
    hub = doc.get("hub") if isinstance(doc.get("hub"), dict) else {}
    memory = hub.get("memory") if isinstance(hub.get("memory"), dict) else {}
    with_fixes = sum(1 for project in projects if project.get("fixes"))
    running = bool(memory.get("running"))
    return {"$schema": VIEW, "view": "metric-group", "metrics": [
        {"id": "projects", "label": "Projects", "value": len(projects), "status": "ok"},
        {"id": "connected", "label": "Connected", "value": sum(1 for p in projects if p.get("status") == "connected"),
         "status": "ok"},
        {"id": "with_fixes", "label": "With fixes", "value": with_fixes, "status": "warn" if with_fixes else "ok"},
        {"id": "memory", "label": "Memory daemon", "value": 1 if running else 0, "status": "ok" if running else "warn"}]}


def layers(timeout_s: float, project_root: Optional[str] = None, **_: Any) -> Dict[str, Any]:
    if not project_root:
        raise HubError("HUB_CONTEXT_MISSING", "the layers query needs a project")
    project = find_project(hub_json(["status", "--all", "--json"], timeout_s), project_root)
    if project is None:
        return {"$schema": VIEW, "view": "status-table", "rows": [
            {"id": "project", "label": "Project", "status": "unknown", "detail": "the project is not registered in maind"}]}
    found: Dict[str, List[Dict[str, Any]]] = {}
    for fix in project.get("fixes") or ():
        if isinstance(fix, dict):
            found.setdefault(LAYER_OF.get(str(fix.get("layer")), "other"), []).append(fix)
    rows = []
    for layer, label in (*LAYERS, ("other", "Other")):
        fixes = found.get(layer, [])
        if layer == "other" and not fixes:
            continue
        row: Dict[str, Any] = {"id": layer, "label": label, "status": "fail" if fixes else "ok"}
        if fixes:
            row["detail"] = "; ".join(safe_text(fix.get("issue") or fix.get("fix") or "needs attention")
                                      for fix in fixes)
            caps = [cap for cap in (repair_cap(fix.get("fix")) for fix in fixes) if cap]
            if caps:
                row["repair"] = {"command": "gui-hub.sync", "input": {"cap": caps[0]}}
        rows.append(row)
    return {"$schema": VIEW, "view": "status-table", "rows": rows}


def doctor(timeout_s: float, **_: Any) -> Dict[str, Any]:
    doc = hub_json(["doctor", "--json"], timeout_s)
    results = doc.get("results") if isinstance(doc, dict) else None
    if not isinstance(results, list):
        raise HubError("HUB_CLI_FAILED", "swissknifeman doctor --json has no results")
    rows, seen = [], set()
    for result in results:
        if not isinstance(result, dict) or not result.get("check_id"):
            continue
        check, unit = str(result["check_id"]), str(result.get("unit") or "-")
        row_id = check if check not in seen else f"{unit}:{check}"
        seen.add(row_id)
        status = result.get("status") if result.get("status") in STATUSES else "unknown"
        row = {"id": row_id, "label": f"{unit} · {check}", "status": status}
        if result.get("observed"):
            row["detail"] = safe_text(result["observed"], 500)
        rows.append(row)
    return {"$schema": VIEW, "view": "status-table", "rows": rows}


def units(timeout_s: float, **_: Any) -> Dict[str, Any]:
    doc = hub_json(["units", "list", "--json"], timeout_s)
    entries = doc.get("units") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        raise HubError("HUB_CLI_FAILED", "swissknifeman units list --json has no units")
    rows = [{"id": str(unit["id"]), "cells": {name: str(unit.get(name) or "-") for name in
                                               ("kind", "version", "stability", "destination")}}
            for unit in entries if isinstance(unit, dict) and unit.get("id")]
    columns = [{"id": "kind", "title": "Kind", "type": "text"}, {"id": "version", "title": "Version", "type": "text"},
               {"id": "stability", "title": "Stability", "type": "text"},
               {"id": "destination", "title": "Destination", "type": "text"}]
    return {"$schema": VIEW, "view": "resource-list", "columns": columns, "rows": rows, "total": len(rows)}


QUERIES = {"gui-hub.fleet": fleet, "gui-hub.fleet-summary": fleet_summary, "gui-hub.layers": layers,
           "gui-hub.doctor": doctor, "gui-hub.units": units}


# --- the plugin protocol ---------------------------------------------------------------------------------------


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def answer(request: Dict[str, Any]) -> Dict[str, Any]:
    reply: Dict[str, Any] = {"$schema": RESPONSE, "protocol": "1", "request_id": request.get("request_id", "0" * 32)}
    if request.get("protocol") != "1":
        return {**reply, "status": "error", "error": {"code": "PROTOCOL_UNSUPPORTED", "message": "protocol 1 only"}}
    manifest = json.loads((HERE / "extension.json").read_text(encoding="utf-8"))
    if request.get("op") == "describe":
        return {**reply, "status": "ok", "output": {
            "$schema": "urn:swissknifeman:aicore:plugin-describe:v1", "protocol": "1", "id": manifest["id"],
            "kind": manifest["kind"], "version": manifest["version"],
            "capabilities_digest": "sha256:" + hashlib.sha256(_canonical(manifest["provides"])).hexdigest(),
            "transport": "stdio-json"}}
    given = request.get("input") if isinstance(request.get("input"), dict) else {}
    query = QUERIES.get(given.get("id")) if request.get("point") == "gui:query" else None
    if query is None:
        return {**reply, "status": "error", "error": {"code": "HUB_UNKNOWN_QUERY",
                                                      "message": f"no query {safe_text(given.get('id'))}"}}
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    timeout_s = max(1.0, float(request.get("deadline_ms", 60000)) / 1000 - 1)
    try:
        return {**reply, "status": "ok", "output": query(timeout_s, project_root=context.get("project_root"))}
    except HubError as error:
        return {**reply, "status": "error", "error": {"code": error.code, "message": safe_text(error.message)}}


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except ValueError:
        request = {}
    sys.stdout.write(json.dumps(answer(request if isinstance(request, dict) else {}), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
