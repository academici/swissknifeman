#!/usr/bin/env python3
"""gui-planner: the planner (plans, overview, phases, board, graph, items, decisions, evidence, timeline, raw) as GUI
queries; an aicore command plugin (protocol 1).

The adapter only calls the planner command line (``$SKM_UMBRELLA planner --output json ...``, or ``swissknifeman`` on
PATH) in the project folder and moves fields of its JSON answers into ``view-data/v1``. It computes no status,
progress or dependency of its own: progress of a plan is the one of the ``plans`` verb, and the only logic is the
layout of items into board columns by their ``status`` and the map from a planner status to a view status. Every
string of a plan is shown as text (control characters removed); markdown goes to the host sanitizer. stdlib only.
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
from typing import Any, Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
VIEW = "urn:swissknifeman:gui:view-data:v1"
RESPONSE = "urn:swissknifeman:aicore:plugin-response:v1"
OWNER = "gui-planner"

# Statuses of an item in board order, and what each is in a view-data status.
BOARD = (("todo", "To do"), ("in_progress", "In progress"), ("blocked", "Blocked"), ("done", "Done"),
         ("done_with_deviations", "Done with deviations"), ("skipped", "Skipped"))
VIEW_STATUS = {"done": "ok", "done_with_deviations": "ok", "skipped": "ok", "in_progress": "warn", "blocked": "fail",
               "todo": "unknown"}
DONE = ("done", "done_with_deviations", "skipped")

PLAN_REF = re.compile(r"^(?:[0-9]{4}\.[0-9]{2}\.[0-9]{2}-№[0-9]+-[A-Z][A-Z0-9-]*|PLAN[0-9]+)$")
ITEM_REF = re.compile(r"^P[0-9]+\.[0-9]+$")
PHASE_REF = re.compile(r"^P[0-9]+$")
RAW_REF = re.compile(r"^(?:plan|brief|P[0-9]+|P[0-9]+\.[0-9]+|D[0-9]+)$")
TS = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$")
KIND_BAD = re.compile(r"[^a-z0-9._-]+")
_ANSI = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_MARKDOWN_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
RAW_LIMIT = 100_000
EVENT_LIMIT = 200


class PlannerError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def safe_text(value: Any, limit: int = 300) -> str:
    text = _CONTROL.sub(" ", _ANSI.sub("", str(value))).strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def md_text(value: Any, limit: int = 20000) -> str:
    """Markdown source for the host sanitizer: newlines kept, other control characters removed."""
    text = _MARKDOWN_CONTROL.sub(" ", _ANSI.sub("", str(value))).strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def umbrella() -> str:
    found = os.environ.get("SKM_UMBRELLA") or shutil.which("swissknifeman")
    if not found:
        raise PlannerError("PLANNER_UNAVAILABLE",
                           "the hub command line was not found (swissknifeman on PATH or SKM_UMBRELLA)")
    return found


def _run(args: List[str], project_root: str, timeout_s: float) -> "subprocess.CompletedProcess[str]":
    command = [umbrella(), "planner", *args]
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=max(1.0, timeout_s),
                              stdin=subprocess.DEVNULL, cwd=project_root)
    except subprocess.TimeoutExpired:
        raise PlannerError("PLANNER_CLI_FAILED", f"planner {' '.join(args)} did not answer in time") from None
    except OSError as error:
        raise PlannerError("PLANNER_UNAVAILABLE", f"the planner cannot run: {error.strerror}") from None


def _code(value: Any) -> str:
    code = str(value or "")
    return code if re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", code) else "PLANNER_CLI_FAILED"


def _failed(args: List[str], result: "subprocess.CompletedProcess[str]") -> PlannerError:
    tail = [line for line in result.stderr.splitlines() if line.strip()][-1:] or [f"exit {result.returncode}"]
    return PlannerError("PLANNER_CLI_FAILED", f"planner {' '.join(args)} failed: {safe_text(tail[0])}")


def planner_json(args: List[str], project_root: Optional[str], timeout_s: float) -> Any:
    """``data`` of ``planner --output json <args>``; a refusal keeps the code of the planner."""
    if not project_root:
        raise PlannerError("PLANNER_CONTEXT_MISSING", "the query needs a project")
    result = _run(["--output", "json", *args], project_root, timeout_s)
    try:
        doc = json.loads(result.stdout)
    except ValueError:
        if result.returncode != 0:
            raise _failed(args, result) from None
        raise PlannerError("PLANNER_CLI_FAILED", f"planner {' '.join(args)} did not answer JSON") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("ok"), bool):
        raise PlannerError("PLANNER_CLI_FAILED", f"planner {' '.join(args)} did not answer an envelope")
    if not doc["ok"]:
        error = doc.get("error") if isinstance(doc.get("error"), dict) else {}
        raise PlannerError(_code(error.get("code")), safe_text(error.get("message") or "the planner refused"))
    return doc.get("data")


def planner_show(plan_id: str, project_root: Optional[str], timeout_s: float) -> Dict[str, Any]:
    """``planner show <plan> --json``: the one read whose JSON is not in the envelope (a refusal is ``CODE: message``)."""
    if not project_root:
        raise PlannerError("PLANNER_CONTEXT_MISSING", "the query needs a project")
    args = ["show", plan_id, "--json"]
    result = _run(args, project_root, timeout_s)
    if result.returncode != 0:
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        match = re.match(r"^([A-Z][A-Z0-9_]{1,63}): (.*)$", lines[-1]) if lines else None
        if match:
            raise PlannerError(match.group(1), safe_text(match.group(2)))
        raise _failed(args, result)
    try:
        doc = json.loads(result.stdout)
    except ValueError:
        raise PlannerError("PLANNER_CLI_FAILED", "planner show did not answer JSON") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("phases"), list):
        raise PlannerError("PLANNER_CLI_FAILED", "planner show --json has no phases")
    return doc


# --- helpers ---------------------------------------------------------------------------------------------------


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value.strip() else None


def view_status(status: Any) -> str:
    return VIEW_STATUS.get(status, "unknown") if isinstance(status, str) else "unknown"


def _text(value: Any, fallback: str, limit: int = 300) -> str:
    return safe_text(value, limit) or fallback


def _doc(data: Any) -> Dict[str, Any]:
    doc = _dict(data).get("doc")
    if not isinstance(doc, dict):
        raise PlannerError("PLANNER_CLI_FAILED", "planner get has no document")
    return doc


def _plan_id(context: Dict[str, Any], params: Dict[str, Any]) -> str:
    plan_id = context.get("plan_id") or params.get("plan_id")
    if not isinstance(plan_id, str) or not PLAN_REF.match(plan_id):
        raise PlannerError("PLANNER_CONTEXT_MISSING", "the query needs a plan")
    return plan_id


def _item_id(context: Dict[str, Any], params: Dict[str, Any]) -> str:
    item_id = context.get("item_id") or params.get("item_id")
    if not isinstance(item_id, str) or not ITEM_REF.match(item_id):
        raise PlannerError("PLANNER_CONTEXT_MISSING", "the query needs an item")
    return item_id


def _phase(params: Dict[str, Any]) -> Optional[str]:
    phase = params.get("phase")
    if phase is None:
        return None
    if not isinstance(phase, str) or not PHASE_REF.match(phase):
        raise PlannerError("PLANNER_CONTEXT_MISSING", "phase must look like P3")
    return phase


def _item_link(plan_id: str, item_id: str) -> Dict[str, Any]:
    return {"route": f"{OWNER}.item", "params": {"plan_id": plan_id, "item_id": item_id}}


def _items(plan_id: str, phase: Optional[str], root: Optional[str], timeout_s: float) -> List[Dict[str, Any]]:
    args = ["list", plan_id, "item"] + (["--phase", phase] if phase else [])
    rows = _list(planner_json(args, root, timeout_s))
    return [row for row in rows if isinstance(row, dict) and isinstance(row.get("ref"), str)
            and ITEM_REF.match(row["ref"])]


def _phase_of(item_id: str) -> str:
    return item_id.split(".", 1)[0]


def _bullets(values: Any) -> str:
    return "\n".join(f"- {md_text(v, 2000)}" for v in _list(values) if isinstance(v, str) and v.strip())


# --- queries ---------------------------------------------------------------------------------------------------


def plans(root: Optional[str], timeout_s: float, **_: Any) -> Dict[str, Any]:
    rows = []
    # The conformance probe calls without a project: the list then is that of the plugin's working folder.
    for plan in _list(_dict(planner_json(["plans"], root or os.getcwd(), timeout_s)).get("plans")):
        if not isinstance(plan, dict) or not isinstance(plan.get("id"), str):
            continue
        if plan.get("error"):
            rows.append({"id": plan["id"], "cells": {
                "name": _text(plan["id"], "-") + f" (unreadable: {safe_text(plan['error'], 64)})",
                "status": "unknown", "progress": None, "phases": "-"}})
            continue
        progress = _dict(plan.get("progress"))
        items, done = int(progress.get("items") or 0), int(progress.get("items_done") or 0)
        rows.append({"id": plan["id"], "cells": {
            "name": _text(plan.get("title"), plan["id"]), "status": _text(plan.get("status"), "unknown", 64),
            "progress": (done / items) if items else 0,
            "phases": f"{int(progress.get('phases_closed') or 0)}/{int(progress.get('phases') or 0)}"},
            "link": {"route": f"{OWNER}.overview", "params": {"plan_id": plan["id"]}}})
    columns = [{"id": "name", "title": "Plan", "type": "text"}, {"id": "status", "title": "Status", "type": "status"},
               {"id": "progress", "title": "Progress", "type": "progress"},
               {"id": "phases", "title": "Phases closed", "type": "text"}]
    return {"$schema": VIEW, "view": "resource-list", "columns": columns, "rows": rows, "total": len(rows)}


def overview(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any],
             **_: Any) -> Dict[str, Any]:
    plan_id = _plan_id(context, params)
    shown = planner_show(plan_id, root, timeout_s)
    doc = _doc(planner_json(["get", plan_id, "plan"], root, timeout_s))
    row: Dict[str, Any] = {}
    for candidate in _list(_dict(planner_json(["plans"], root, timeout_s)).get("plans")):
        if isinstance(candidate, dict) and plan_id in (candidate.get("id"), candidate.get("short_id")):
            row = _dict(candidate.get("progress"))
    fields = [{"label": "Plan", "type": "text",
               "value": f"{_text(shown.get('short_id'), '')} {_text(shown.get('id'), '')}".strip() or plan_id},
              {"label": "Status", "type": "text", "value": _text(shown.get("status"), "unknown", 64)}]
    goal = _str(doc.get("goal"))
    if goal:
        fields.append({"label": "Goal", "type": "text", "value": safe_text(goal, 300)})
    if row:
        fields.append({"label": "Progress", "type": "text", "value":
                       f"{int(row.get('items_done') or 0)}/{int(row.get('items') or 0)} items, "
                       f"{int(row.get('phases_closed') or 0)}/{int(row.get('phases') or 0)} phases closed"})
    if _str(shown.get("next")):
        fields.append({"label": "Next", "type": "text", "value": safe_text(shown["next"], 300)})
    sections = []
    for title, text in (("Goal", md_text(goal) if goal else ""), ("Context", md_text(doc["context"])
                                                                 if _str(doc.get("context")) else ""),
                        ("Rules", _bullets(doc.get("rules")))):
        if text:
            sections.append({"title": title, "markdown": text})
    detail: Dict[str, Any] = {"$schema": VIEW, "view": "resource-detail",
                              "title": _text(shown.get("title"), plan_id), "fields": fields}
    if sections:
        detail["sections"] = sections
    return detail


def phases(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any],
           **_: Any) -> Dict[str, Any]:
    plan_id = _plan_id(context, params)
    rows = []
    for phase in _list(planner_show(plan_id, root, timeout_s).get("phases")):
        if not isinstance(phase, dict) or not isinstance(phase.get("id"), str):
            continue
        items = [i for i in _list(phase.get("items")) if isinstance(i, dict)]
        done = sum(1 for i in items if i.get("status") in DONE)
        closed = phase.get("closed") if isinstance(phase.get("closed"), dict) else None
        rows.append({"id": phase["id"], "cells": {
            "phase": phase["id"], "title": _text(phase.get("title"), phase["id"]),
            "design": _text(phase.get("design"), "-", 64),
            "result": _text(closed.get("result"), "closed", 64) if closed else "open",
            "progress": (done / len(items)) if items else 0, "items": f"{done}/{len(items)}"},
            "link": {"route": f"{OWNER}.board", "params": {"plan_id": plan_id}}})
    columns = [{"id": "phase", "title": "Phase", "type": "text"}, {"id": "title", "title": "Title", "type": "text"},
               {"id": "design", "title": "Design", "type": "text"}, {"id": "result", "title": "Result", "type": "status"},
               {"id": "progress", "title": "Progress", "type": "progress"},
               {"id": "items", "title": "Items done", "type": "text"}]
    return {"$schema": VIEW, "view": "resource-list", "columns": columns, "rows": rows, "total": len(rows)}


def board(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any],
          **_: Any) -> Dict[str, Any]:
    plan_id = _plan_id(context, params)
    known = [status for status, _title in BOARD]
    columns: Dict[str, List[Dict[str, Any]]] = {status: [] for status in known}
    columns["other"] = []
    for row in _items(plan_id, _phase(params), root, timeout_s):
        status = row.get("status")
        card: Dict[str, Any] = {"id": row["ref"], "title": _text(row.get("title"), row["ref"]),
                                "subtitle": _phase_of(row["ref"]), "status": view_status(status),
                                "link": _item_link(plan_id, row["ref"])}
        columns[status if status in known else "other"].append(card)
    shown = [{"id": status, "title": title, "cards": columns[status]} for status, title in BOARD]
    if columns["other"]:
        shown.append({"id": "other", "title": "Other", "cards": columns["other"]})
    return {"$schema": VIEW, "view": "board", "columns": shown}


def graph(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any],
          **_: Any) -> Dict[str, Any]:
    plan_id = _plan_id(context, params)
    rows = _items(plan_id, _phase(params), root, timeout_s)
    ids = {row["ref"] for row in rows}
    nodes, edges, seen = [], [], set()

    def edge(source: str, target: str, kind: str) -> None:
        if source in ids and target in ids and source != target and (source, target, kind) not in seen:
            seen.add((source, target, kind))
            edges.append({"from": source, "to": target, "kind": kind})

    for row in rows:
        item = _doc(planner_json(["get", plan_id, row["ref"]], root, timeout_s))
        nodes.append({"id": row["ref"], "label": f"{row['ref']} {_text(row.get('title'), '')}".strip(),
                      "status": view_status(row.get("status")), "group": _phase_of(row["ref"])})
        for dependency in _list(item.get("depends_on")):
            if isinstance(dependency, str):
                edge(dependency, row["ref"], "blocks")
        for related in _list(item.get("related")):
            if isinstance(related, dict) and isinstance(related.get("ref"), str):
                edge(row["ref"], related["ref"], "related")
    return {"$schema": VIEW, "view": "dependency-graph", "nodes": nodes, "edges": edges}


def item(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any],
         **_: Any) -> Dict[str, Any]:
    plan_id, item_id = _plan_id(context, params), _item_id(context, params)
    doc = _doc(planner_json(["get", plan_id, item_id], root, timeout_s))
    route, review, authority = _dict(doc.get("route")), _dict(doc.get("review")), _dict(doc.get("authority"))
    fields: List[Dict[str, Any]] = [
        {"label": "Title", "type": "text", "value": _text(doc.get("title"), item_id)},
        {"label": "Status", "type": "text", "value": _text(doc.get("status"), "unknown", 64)},
        {"label": "Phase", "type": "text", "value": _phase_of(item_id)}]
    if route:
        fields.append({"label": "Route", "type": "text", "value":
                       f"{_text(route.get('class'), '-', 64)} / {_text(route.get('effort'), '-', 64)}"})
    if review:
        reviewer = _dict(review.get("reviewer"))
        parts = [_text(review.get("mode"), "-", 64)] + [
            safe_text(reviewer[key], 64) for key in ("class", "provider", "model", "effort") if _str(reviewer.get(key))]
        fields.append({"label": "Review", "type": "text", "value": " / ".join(parts)})
    if authority:
        fields.append({"label": "Authority", "type": "text", "value": _text(authority.get("kind"), "-", 64)})
    depends = [safe_text(d, 32) for d in _list(doc.get("depends_on")) if isinstance(d, str)]
    fields.append({"label": "Depends on", "type": "text", "value": ", ".join(depends) or "-"})
    sections = []
    for title, key in (("Summary", "summary"), ("Why", "why")):
        if _str(doc.get(key)):
            sections.append({"title": title, "markdown": md_text(doc[key])})
    result = _dict(doc.get("result"))
    if result:
        lines = [f"- finished: {safe_text(result['finished_at'], 40)}" if _str(result.get("finished_at")) else ""]
        notes = _str(result.get("notes"))
        text = "\n".join(line for line in lines if line)
        if notes:
            text += ("\n\n" if text else "") + md_text(notes)
        for heading, key in (("Deviations", "deviations"), ("Pending", "pending")):
            bullets = _bullets(result.get(key))
            if bullets:
                text += f"\n\n**{heading}**\n\n{bullets}"
        if text.strip():
            sections.append({"title": "Result", "markdown": text.strip()})
    detail: Dict[str, Any] = {"$schema": VIEW, "view": "resource-detail", "title": f"{item_id} {_text(doc.get('title'), '')}".strip(),
                              "fields": fields}
    if sections:
        detail["sections"] = sections
    return detail


def decisions(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any],
              **_: Any) -> Dict[str, Any]:
    plan_id = _plan_id(context, params)
    rows = []
    for row in _list(planner_json(["list", plan_id, "decision"], root, timeout_s)):
        if not isinstance(row, dict) or not isinstance(row.get("ref"), str):
            continue
        doc = _doc(planner_json(["get", plan_id, row["ref"]], root, timeout_s))
        rows.append({"id": row["ref"], "cells": {
            "id": row["ref"], "title": _text(row.get("title"), row["ref"]), "status": _text(row.get("status"), "unknown", 64),
            "date": _str(doc.get("date"))}})
    columns = [{"id": "id", "title": "Decision", "type": "text"}, {"id": "title", "title": "Title", "type": "text"},
               {"id": "status", "title": "Status", "type": "status"}, {"id": "date", "title": "Date", "type": "text"}]
    return {"$schema": VIEW, "view": "resource-list", "columns": columns, "rows": rows, "total": len(rows)}


def evidence(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any],
             **_: Any) -> Dict[str, Any]:
    plan_id, item_id = _plan_id(context, params), _item_id(context, params)
    doc = _doc(planner_json(["get", plan_id, item_id], root, timeout_s))
    rows = []
    for position, check in enumerate(_list(_dict(doc.get("result")).get("checks"))):
        if isinstance(check, dict) and _str(check.get("id")):
            code = check.get("exit")
            rows.append({"id": f"check-{position}", "cells": {
                "kind": "check", "name": safe_text(check["id"], 64), "path": _str(check.get("evidence")) and safe_text(check["evidence"], 300),
                "outcome": ("exit " + str(code)) if isinstance(code, int) and not isinstance(code, bool) else "-"}})
    for position, artifact in enumerate(_list(doc.get("artifacts"))):
        if isinstance(artifact, dict) and _str(artifact.get("path")):
            rows.append({"id": f"artifact-{position}", "cells": {
                "kind": "artifact", "name": _text(artifact.get("id") or artifact.get("role"), "artifact", 64),
                "path": safe_text(artifact["path"], 300), "outcome": _text(artifact.get("role"), "-", 64)}})
    for position, path in enumerate(_list(_dict(doc.get("result")).get("evidence"))):
        if isinstance(path, str) and path.strip():
            rows.append({"id": f"evidence-{position}", "cells": {
                "kind": "evidence", "name": "evidence", "path": safe_text(path, 300), "outcome": "-"}})
    columns = [{"id": "kind", "title": "Kind", "type": "text"}, {"id": "name", "title": "Name", "type": "text"},
               {"id": "path", "title": "Path", "type": "text"}, {"id": "outcome", "title": "Outcome", "type": "text"}]
    return {"$schema": VIEW, "view": "resource-list", "columns": columns, "rows": rows, "total": len(rows)}


def timeline(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any],
             **_: Any) -> Dict[str, Any]:
    plan_id = _plan_id(context, params)
    only = params.get("item")
    if only is not None and not (isinstance(only, str) and ITEM_REF.match(only)):
        raise PlannerError("PLANNER_CONTEXT_MISSING", "item must look like P3.1")
    args = ["events", plan_id, "--limit", str(EVENT_LIMIT)] + (["--item", only] if only else [])
    entries = []
    for event in reversed(_list(planner_json(args, root, timeout_s))):  # the journal is oldest first
        if not isinstance(event, dict) or not isinstance(event.get("ts"), str) or not TS.match(event["ts"]):
            continue
        kind = KIND_BAD.sub("-", str(event.get("type") or "").lower()).strip("-._")
        entry: Dict[str, Any] = {"at": event["ts"], "kind": kind if re.match(r"^[a-z]", kind) else "event",
                                 "title": _text(event.get("summary"), str(event.get("type") or "event"))}
        actor = _dict(event.get("actor"))
        if _str(actor.get("provider")) and _str(actor.get("model")):
            entry["detail"] = f"actor {safe_text(actor['provider'], 64)}/{safe_text(actor['model'], 64)}"
        if isinstance(event.get("item"), str) and ITEM_REF.match(event["item"]):
            entry["link"] = _item_link(plan_id, event["item"])
        entries.append(entry)
    return {"$schema": VIEW, "view": "timeline", "entries": entries}


def _plan_dir(plan_id: str, root: Optional[str], timeout_s: float) -> str:
    if PLAN_REF.match(plan_id) and not plan_id.startswith("PLAN"):
        return plan_id
    return str(planner_show(plan_id, root, timeout_s).get("id") or plan_id)


def _file_of(ref: str) -> str:
    if ref in ("plan", "brief"):
        return f"{ref}.json"
    if ref.startswith("D"):
        return f"decisions/{ref}.json"
    phase = _phase_of(ref)
    return f"phases/{phase}/phase.json" if ref == phase else f"phases/{phase}/{ref}.json"


def raw(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any],
        **_: Any) -> Dict[str, Any]:
    plan_id, ref = _plan_id(context, params), params.get("ref")
    if not isinstance(ref, str) or not RAW_REF.match(ref):
        raise PlannerError("PLANNER_CONTEXT_MISSING", "ref must be plan, brief, Pn, Pn.m or D#")
    doc = _doc(planner_json(["get", plan_id, ref], root, timeout_s))
    body = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False)
    body = _MARKDOWN_CONTROL.sub(" ", _ANSI.sub("", body))
    if len(body) > RAW_LIMIT:
        body = body[:RAW_LIMIT] + "\n… (truncated)"
    longest = max((len(run) for run in re.findall(r"`+", body)), default=0)
    fence = "`" * max(3, longest + 1)
    where = f"plans/{_plan_dir(plan_id, root, timeout_s)}/{_file_of(ref)}"
    return {"$schema": VIEW, "view": "markdown", "text": f"File: `{where}` (read-only)\n\n{fence}json\n{body}\n{fence}"}


QUERIES: Dict[str, Callable[..., Dict[str, Any]]] = {
    f"{OWNER}.plans": plans, f"{OWNER}.overview": overview, f"{OWNER}.phases": phases, f"{OWNER}.board": board,
    f"{OWNER}.graph": graph, f"{OWNER}.item": item, f"{OWNER}.decisions": decisions, f"{OWNER}.evidence": evidence,
    f"{OWNER}.timeline": timeline, f"{OWNER}.raw": raw}


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
        return {**reply, "status": "error", "error": {"code": "PLANNER_UNKNOWN_QUERY",
                                                      "message": f"no query {safe_text(given.get('id'))}"}}
    host = request.get("context") if isinstance(request.get("context"), dict) else {}
    context = given.get("context") if isinstance(given.get("context"), dict) else {}
    params = given.get("params") if isinstance(given.get("params"), dict) else {}
    timeout_s = max(1.0, float(request.get("deadline_ms", 60000)) / 1000 - 1)
    try:
        return {**reply, "status": "ok", "output": query(
            host.get("project_root"), timeout_s, context=context, params=params)}
    except PlannerError as error:
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
