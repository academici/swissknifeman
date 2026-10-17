#!/usr/bin/env python3
"""gui-workspace: the portable workspace as GUI queries; an aicore command plugin (protocol 1).

The adapter only runs ``workspace ... --json`` (``$SKM_WORKSPACE_MODULE_ROOT/bin/workspace``, else ``swissknifeman
workspace``) and moves fields of its JSON answers into ``view-data/v1``. It reads no workspace file and decides
nothing: statuses come from the verdicts the CLI reports. A URL with userinfo in any answer is refused
(``WORKSPACE_REMOTE_LEAK``), so a token never reaches the page even if the CLI failed to redact it. stdlib only.
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
from typing import Any, Dict, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
VIEW = "urn:swissknifeman:gui:view-data:v1"
RESPONSE = "urn:swissknifeman:aicore:plugin-response:v1"
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_USERINFO = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/?#\s]*@")
_VERDICT = {"ok": "ok", "warn": "warn", "block": "fail"}


class WorkspaceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def safe_text(value: Any, limit: int = 300) -> str:
    text = _CONTROL.sub(" ", str(value)).strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def has_userinfo(text: Any) -> bool:
    """True when ``text`` holds a ``scheme://user@host`` URL."""
    return isinstance(text, str) and _USERINFO.search(text) is not None


def workspace_command() -> List[str]:
    """The argv prefix of the workspace command line."""
    module = os.environ.get("SKM_WORKSPACE_MODULE_ROOT")
    if module:
        launcher = Path(module) / "bin" / "workspace"
        if not launcher.is_file():
            raise WorkspaceError("WORKSPACE_UNAVAILABLE", "SKM_WORKSPACE_MODULE_ROOT has no bin/workspace")
        return [str(launcher)]
    found = os.environ.get("SKM_UMBRELLA") or shutil.which("swissknifeman")
    if not found:
        raise WorkspaceError("WORKSPACE_UNAVAILABLE",
                             "the workspace command line was not found (SKM_WORKSPACE_MODULE_ROOT or swissknifeman on PATH)")
    return [found, "workspace"]


def workspace_json(args: Sequence[str], timeout_s: float, *, accept: Sequence[int] = (0,)) -> Any:
    """The JSON answer of ``workspace <args> --json``; an exit in ``accept`` is fine when stdout is JSON."""
    command = [*workspace_command(), *args, "--json"]
    label = " ".join(args)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=max(1.0, timeout_s),
                                stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise WorkspaceError("WORKSPACE_CLI_FAILED", f"workspace {label} did not answer in time") from None
    except OSError as error:
        raise WorkspaceError("WORKSPACE_UNAVAILABLE", f"workspace cannot run: {error.strerror}") from None
    if result.returncode not in accept:
        tail = [line for line in result.stderr.splitlines() if line.strip()][-1:] or [f"exit {result.returncode}"]
        raise WorkspaceError("WORKSPACE_CLI_FAILED", f"workspace {label} failed: {safe_text(tail[0])}")
    if has_userinfo(result.stdout):
        raise WorkspaceError("WORKSPACE_REMOTE_LEAK", f"workspace {label} answered a URL with userinfo; refused")
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise WorkspaceError("WORKSPACE_CLI_FAILED", f"workspace {label} did not answer JSON") from None


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _status_doc(timeout_s: float) -> Dict[str, Any]:
    doc = workspace_json(["status"], timeout_s)
    if not isinstance(doc, dict) or not isinstance(doc.get("git"), dict):
        raise WorkspaceError("WORKSPACE_CLI_FAILED", "workspace status --json has no git state")
    return doc


def _publish(timeout_s: float) -> Optional[Dict[str, Any]]:
    """The publish-safety report (exit 1 with a JSON report means blocked), or None when it cannot be read."""
    try:
        doc = workspace_json(["doctor", "--publish-safety"], timeout_s, accept=(0, 1))
    except WorkspaceError as error:
        if error.code == "WORKSPACE_REMOTE_LEAK":
            raise
        return None
    return doc if isinstance(doc, dict) and isinstance(doc.get("verdict"), str) else None


# --- queries ---------------------------------------------------------------------------------------------------


def overview(timeout_s: float, **_: Any) -> Dict[str, Any]:
    doc = _status_doc(timeout_s)
    git = doc["git"]
    projects = [p for p in _list(doc.get("projects")) if isinstance(p, dict)]
    bound = sum(1 for p in projects if p.get("bound"))
    dirty, behind, ahead = _int(git.get("dirty")), _int(git.get("behind")), _int(git.get("ahead"))
    report = _publish(timeout_s)
    verdict = _VERDICT.get(report["verdict"], "unknown") if report else "unknown"
    return {"$schema": VIEW, "view": "metric-group", "metrics": [
        {"id": "projects", "label": "Projects", "value": len(projects), "status": "ok"},
        {"id": "bound", "label": "Bound on this machine", "value": bound,
         "status": "ok" if bound == len(projects) else "warn"},
        {"id": "dirty", "label": "Changed files", "value": dirty, "status": "warn" if dirty else "ok"},
        {"id": "ahead", "label": "Ahead of remote", "value": ahead, "status": "ok"},
        {"id": "behind", "label": "Behind remote", "value": behind, "status": "warn" if behind else "ok"},
        {"id": "diverged", "label": "Diverged", "value": 1 if git.get("diverged") else 0,
         "status": "fail" if git.get("diverged") else "ok"},
        {"id": "remote", "label": "Remote connected", "value": 1 if git.get("remote") else 0,
         "status": "ok" if git.get("remote") else "warn"},
        {"id": "publish", "label": "Publish safety (0 ok, 1 warn, 2 block)",
         "value": {"ok": 0, "warn": 1, "fail": 2}.get(verdict, 0), "status": verdict}]}


def projects(timeout_s: float, **_: Any) -> Dict[str, Any]:
    listed = workspace_json(["project", "list"], timeout_s)
    rows_in = [p for p in _list(_dict(listed).get("projects")) if isinstance(p, dict) and p.get("project_id")]
    extra = {p.get("project_id"): p for p in _list(_status_doc(timeout_s).get("projects")) if isinstance(p, dict)}
    rows = []
    for project in rows_in:
        more = _dict(extra.get(project["project_id"]))
        paths = [str(p) for p in _list(project.get("paths"))]
        plans = more.get("plans")
        rows.append({"id": str(project["project_id"]), "cells": {
            "name": safe_text(project.get("name") or project["project_id"]),
            "status": safe_text(project.get("status") or "unknown"),
            "bound": "yes" if project.get("bound") else "no",
            "paths": safe_text(", ".join(paths) or "-", 500),
            "plans_store": safe_text(more.get("plans_store") or "-"),
            "plans": plans if isinstance(plans, int) and not isinstance(plans, bool) else None}})
    columns = [{"id": "name", "title": "Project", "type": "text"}, {"id": "status", "title": "Status", "type": "text"},
               {"id": "bound", "title": "Bound here", "type": "text"}, {"id": "paths", "title": "Paths", "type": "text"},
               {"id": "plans_store", "title": "Plans store", "type": "text"},
               {"id": "plans", "title": "Plans", "type": "number"}]
    return {"$schema": VIEW, "view": "resource-list", "columns": columns, "rows": rows, "total": len(rows)}


def migration(timeout_s: float, **_: Any) -> Dict[str, Any]:
    doc = workspace_json(["migrate", "discover"], timeout_s)
    rows = []
    for candidate in _list(_dict(doc).get("candidates")):
        if not isinstance(candidate, dict) or not isinstance(candidate.get("path"), str):
            continue
        path, marker, counts = candidate["path"], _dict(candidate.get("marker")), _dict(candidate.get("plans"))
        legacy = _int(counts.get("legacy"))
        detail = (f"{_int(counts.get('v4'))} plans, {legacy} legacy, {_int(counts.get('files'))} files; "
                  f"store {marker.get('plans_store') or '-'}; project {marker.get('project_id') or 'no marker'}")
        if candidate.get("marker_error"):
            status, detail = "fail", safe_text(candidate["marker_error"])
        elif legacy:
            status = "warn"
        else:
            status = "ok"
        row: Dict[str, Any] = {"id": path, "label": path, "status": status, "detail": safe_text(detail, 500)}
        if status == "warn":
            row["repair"] = {"command": "gui-workspace.migrate-plan", "input": {"project": path}}
        rows.append(row)
    return {"$schema": VIEW, "view": "status-table", "rows": rows}


def _findings(items: Any, status: str) -> List[Dict[str, Any]]:
    rows = []
    for index, item in enumerate(_list(items)):
        if isinstance(item, dict):
            rows.append({"id": f"{status}-{index}-{safe_text(item.get('path'), 80)}",
                         "label": f"{item.get('rule', 'finding')} · {safe_text(item.get('path'), 120)}",
                         "status": status, "detail": safe_text(item.get("detail") or "", 300)})
    return rows


def sync(timeout_s: float, **_: Any) -> Dict[str, Any]:
    doc = _status_doc(timeout_s)
    git, last = doc["git"], _dict(doc.get("last_sync"))
    remote = git.get("remote")
    rows: List[Dict[str, Any]] = []
    target = (f"{remote} · branch {git.get('branch')} · ahead {_int(git.get('ahead'))}, behind {_int(git.get('behind'))}"
              if remote else "no remote connected")
    row: Dict[str, Any] = {"id": "push-target", "label": "Push target", "status": "ok" if remote else "warn",
                           "detail": safe_text(target, 500)}
    if remote:
        row["repair"] = {"command": "gui-workspace.sync-push"}
    rows.append(row)
    report = _publish(timeout_s)
    if report is None:
        rows.append({"id": "publish", "label": "Publish safety", "status": "unknown",
                     "detail": "the publish-safety report could not be read"})
    else:
        rows.append({"id": "publish", "label": "Publish safety", "status": _VERDICT.get(report["verdict"], "unknown"),
                     "detail": f"{len(_list(report.get('block')))} block, {len(_list(report.get('warn')))} warn, "
                               f"{len(_list(report.get('local_only')))} local-only"})
        rows += _findings(report.get("block"), "fail") + _findings(report.get("warn"), "warn")
    result = last.get("last_result")
    rows.append({"id": "last-operation", "label": "Last operation", "status": "unknown" if not last else
                 ("ok" if result in (None, "ok") else "fail"),
                 "detail": safe_text(result if result else ("none yet" if not last else "ok"))})
    return {"$schema": VIEW, "view": "status-table", "rows": rows}


def conflicts(timeout_s: float, **_: Any) -> Dict[str, Any]:
    last = _dict(_status_doc(timeout_s).get("last_sync"))
    pending = _dict(last.get("pending_resolutions"))
    rows = []
    for item in _list(_dict(last.get("last_conflicts")).get("conflicts")):
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            rows.append({"id": item["path"], "cells": {
                "path": safe_text(item["path"], 500), "project": safe_text(item.get("project_id") or "-"),
                "plan": safe_text(item.get("plan") or "-"), "ref": safe_text(item.get("ref") or "-"),
                "decision": safe_text(pending.get(item["path"]) or "-")}})
    columns = [{"id": "path", "title": "Path", "type": "text"}, {"id": "project", "title": "Project", "type": "text"},
               {"id": "plan", "title": "Plan", "type": "text"}, {"id": "ref", "title": "Ref", "type": "text"},
               {"id": "decision", "title": "Decision", "type": "text"}]
    return {"$schema": VIEW, "view": "resource-list", "columns": columns, "rows": rows, "total": len(rows)}


QUERIES = {"gui-workspace.overview": overview, "gui-workspace.projects": projects,
           "gui-workspace.migration": migration, "gui-workspace.sync": sync, "gui-workspace.conflicts": conflicts}


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
        return {**reply, "status": "error", "error": {"code": "WORKSPACE_UNKNOWN_QUERY",
                                                      "message": f"no query {safe_text(given.get('id'))}"}}
    timeout_s = max(1.0, float(request.get("deadline_ms", 60000)) / 1000 - 1)
    try:
        return {**reply, "status": "ok", "output": query(timeout_s)}
    except WorkspaceError as error:
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
