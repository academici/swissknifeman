#!/usr/bin/env python3
"""gui-orch: the orchestrator (conductor runs, status, items, observer report, questions, sandbox) as GUI queries; an
aicore command plugin (protocol 1).

The adapter only calls the orch command line (``$SKM_UMBRELLA orch ...``, or ``swissknifeman`` on PATH) in the
project folder and moves fields of its JSON answers into ``view-data/v1``. It reads no state folder of the
orchestrator and imports no module: the list of runs is ``conduct runs``, the report is the file whose path the CLI
prints, read only when its real path lies under ``<project>/.swissknifeman/orch/reports/<run>/``. It computes no
status of its own, only the map from an outcome to a view status. Every string is shown as text (control characters
removed); markdown goes to the host sanitizer. Counts and tokens are integers. stdlib only.
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
OWNER = "gui-orch"

RUN_ID = re.compile(r"^cnd-[0-9A-Za-z-]+$")
PLAN_REF = re.compile(r"^(?:[0-9]{4}\.[0-9]{2}\.[0-9]{2}-№[0-9]+-[A-Z][A-Z0-9-]*|PLAN[0-9]+)$")
ITEM_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
STATUSES = ("ok", "warn", "fail", "skip", "unknown")
OUTCOME_STATUS = {"done": "ok", "finished": "ok", "done_with_deviations": "warn", "blocked": "fail", "failed": "fail"}
REPORT_LIMIT = 200_000
SANDBOX_NOTE = ("The provider sandbox restricts the commands of orch roles; GUI plugin processes are not sandboxed "
                "(permissions are advisory).")
_ANSI = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_MARKDOWN_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


class OrchError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def safe_text(value: Any, limit: int = 300) -> str:
    text = _CONTROL.sub(" ", _ANSI.sub("", str(value))).strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def md_text(value: Any, limit: int = REPORT_LIMIT) -> str:
    text = _MARKDOWN_CONTROL.sub(" ", _ANSI.sub("", str(value))).strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def umbrella() -> str:
    found = os.environ.get("SKM_UMBRELLA") or shutil.which("swissknifeman")
    if not found:
        raise OrchError("ORCH_UNAVAILABLE", "the hub command line was not found (swissknifeman on PATH or SKM_UMBRELLA)")
    return found


def orch_raw(args: List[str], project_root: str, timeout_s: float) -> str:
    """Standard output of ``swissknifeman orch <args>``; a refusal is ``ORCH_RUN_NOT_FOUND`` or ``ORCH_CLI_FAILED``."""
    command = [umbrella(), "orch", *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=max(1.0, timeout_s),
                                stdin=subprocess.DEVNULL, cwd=project_root)
    except subprocess.TimeoutExpired:
        raise OrchError("ORCH_CLI_FAILED", f"orch {' '.join(args)} did not answer in time") from None
    except OSError as error:
        raise OrchError("ORCH_UNAVAILABLE", f"orch cannot run: {error.strerror}") from None
    if result.returncode != 0:
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        match = re.match(r"^([A-Z][A-Z0-9_]{1,63}): (.*)$", _ANSI.sub("", lines[-1])) if lines else None
        if match and match.group(1) == "RUN_UNKNOWN":
            raise OrchError("ORCH_RUN_NOT_FOUND", safe_text(match.group(2)))
        text = safe_text(lines[-1]) if lines else f"exit {result.returncode}"
        raise OrchError("ORCH_CLI_FAILED", f"orch {' '.join(args)} failed: {text}")
    return result.stdout


def orch_json(args: List[str], project_root: str, timeout_s: float) -> Any:
    try:
        return json.loads(orch_raw(args, project_root, timeout_s))
    except ValueError:
        raise OrchError("ORCH_CLI_FAILED", f"orch {' '.join(args)} did not answer JSON") from None


# --- helpers ---------------------------------------------------------------------------------------------------


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _text(value: Any, fallback: str, limit: int = 300) -> str:
    return (safe_text(value, limit) if value is not None else "") or fallback


def _run_id(context: Dict[str, Any], params: Dict[str, Any], *, required: bool = True) -> Optional[str]:
    run_id = context.get("run_id") or params.get("run_id")
    if run_id is None and not required:
        return None
    if not isinstance(run_id, str) or not RUN_ID.match(run_id):
        raise OrchError("ORCH_CONTEXT_MISSING", "run_id must look like cnd-...")
    return run_id


def _need_root(root: Optional[str]) -> str:
    if not root:
        raise OrchError("ORCH_CONTEXT_MISSING", "the query needs a project")
    return root


def _run_link(run_id: str) -> Dict[str, Any]:
    return {"route": f"{OWNER}.run", "params": {"run_id": run_id}}


def view_status(outcome: Any, running: bool = False) -> str:
    if isinstance(outcome, str) and outcome in OUTCOME_STATUS:
        return OUTCOME_STATUS[outcome]
    return "warn" if outcome is None and running else "unknown"


# --- queries ---------------------------------------------------------------------------------------------------

RUN_COLUMNS = [{"id": "run", "title": "Run", "type": "text"}, {"id": "status", "title": "Status", "type": "status"},
               {"id": "reason", "title": "Reason", "type": "text"}, {"id": "created", "title": "Started", "type": "text"},
               {"id": "items", "title": "Items", "type": "text"}, {"id": "resumes", "title": "Resumes", "type": "number"}]


def _runs_rows(root: str, timeout_s: float, limit: Optional[int]) -> List[Dict[str, Any]]:
    args = ["conduct", "runs", "--json"] + (["--limit", str(limit)] if limit else [])
    rows = []
    for run in _list(_dict(orch_json(args, root, timeout_s)).get("runs")):
        if not isinstance(run, dict) or not isinstance(run.get("run_id"), str) or not RUN_ID.match(run["run_id"]):
            continue
        items = [safe_text(item, 64) for item in _list(run.get("items")) if isinstance(item, str)]
        rows.append({"id": run["run_id"], "cells": {
            "run": run["run_id"], "status": _text(run.get("status"), "unknown", 64),
            "reason": _text(run.get("reason_code"), "-", 64), "created": _text(run.get("created"), "-", 64),
            "items": ", ".join(items[:6]) + (f" +{len(items) - 6}" if len(items) > 6 else "") if items else "-",
            "resumes": _int(run.get("resumes"))}, "link": _run_link(run["run_id"])})
    return rows


def runs(root: Optional[str], timeout_s: float, **_: Any) -> Dict[str, Any]:
    # The conformance probe calls without a project: there is nothing to list.
    rows = _runs_rows(root, timeout_s, None) if root else []
    return {"$schema": VIEW, "view": "resource-list", "columns": RUN_COLUMNS, "rows": rows, "total": len(rows)}


def latest(root: Optional[str], timeout_s: float, **_: Any) -> Dict[str, Any]:
    rows = _runs_rows(root, timeout_s, 1) if root else []
    return {"$schema": VIEW, "view": "resource-list", "columns": RUN_COLUMNS, "rows": rows[:1], "total": len(rows[:1])}


def _status(run_id: str, root: str, timeout_s: float) -> Dict[str, Any]:
    return _dict(orch_json(["conduct", "status", "--run", run_id, "--json"], root, timeout_s))


def run(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    run_id = _run_id(context, params)
    found = _status(run_id, _need_root(root), timeout_s)
    current = _dict(found.get("current"))
    tokens = _dict(found.get("tokens"))
    fields = [{"label": "Run", "type": "text", "value": run_id},
              {"label": "Status", "type": "text", "value": _text(found.get("status"), "unknown", 64)}]
    if found.get("reason_code"):
        fields.append({"label": "Reason code", "type": "text", "value": _text(found["reason_code"], "-", 64)})
    if current:
        fields.append({"label": "Now", "type": "text", "value": safe_text(
            f"{current.get('item') or '-'} {current.get('stage') or ''} {current.get('role') or ''} "
            f"since {current.get('since') or '-'}")})
    if found.get("last_ts"):
        fields.append({"label": "Last journal line", "type": "text", "value": _text(found["last_ts"], "-", 64)})
    fields.append({"label": "Tokens", "type": "text",
                   "value": f"{_int(tokens.get('input'))} in, {_int(tokens.get('output'))} out"})
    if found.get("stop"):
        stop = found["stop"]
        fields.append({"label": "Stop", "type": "text", "value": safe_text(
            stop if isinstance(stop, str) else json.dumps(stop, ensure_ascii=False, sort_keys=True))})
    sections = []
    items = [row for row in _list(found.get("items")) if isinstance(row, dict) and row.get("item")]
    if items:
        sections.append({"title": "Items", "markdown": "\n".join(
            f"- {md_text(row['item'], 64)}: {md_text(row.get('outcome') or 'running', 64)}"
            + (f" ({md_text(row['reason_code'], 64)})" if row.get("reason_code") else "") for row in items)})
    agents = [row for row in _list(found.get("agents")) if isinstance(row, dict)]
    if agents:
        sections.append({"title": "Agents", "markdown": "\n".join(
            f"- {md_text(row.get('role'), 64)} {md_text(row.get('step'), 64)}: {md_text(row.get('status'), 64)}"
            for row in agents)})
    detail: Dict[str, Any] = {"$schema": VIEW, "view": "resource-detail", "title": f"Run {run_id}", "fields": fields,
                              "actions": [{"command": f"{OWNER}.resume", "input": {"run_id": run_id}}]}
    if sections:
        detail["sections"] = sections
    return detail


def items(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    run_id = _run_id(context, params)
    found = _status(run_id, _need_root(root), timeout_s)
    running = found.get("status") == "running"
    rows = []
    for row in _list(found.get("items")):
        if not isinstance(row, dict) or not isinstance(row.get("item"), str):
            continue
        last = _dict(row.get("last"))
        detail = f"{_text(row.get('outcome'), 'running', 64)}"
        if row.get("reason_code"):
            detail += f" ({safe_text(row['reason_code'], 64)})"
        detail += f"; {_int(row.get('stages'))} step(s)"
        if last.get("stage"):
            detail += f", last {safe_text(last['stage'], 64)} {safe_text(last.get('verdict') or '', 64)}".rstrip()
        rows.append({"id": safe_text(row["item"], 64), "label": safe_text(row["item"], 64),
                     "status": view_status(row.get("outcome"), running), "detail": safe_text(detail, 500)})
    return {"$schema": VIEW, "view": "status-table", "rows": rows}


def _report_path(printed: Any, root: str, run_id: str) -> str:
    """The real path of ``observer.md`` when the CLI printed one that lies under the reports folder of this run."""
    if not isinstance(printed, str) or not printed:
        raise OrchError("ORCH_CLI_FAILED", "orch conduct observe printed no report path")
    base = os.path.join(os.path.realpath(root), ".swissknifeman", "orch", "reports", run_id)
    target = os.path.realpath(printed)
    if os.path.basename(target) != "observer.md" or os.path.dirname(target) != base:
        raise OrchError("ORCH_CLI_FAILED", "the report path is outside the reports folder of the run")
    return target


def report(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    run_id = _run_id(context, params)
    root = _need_root(root)
    try:
        printed = json.loads(orch_raw(["conduct", "observe", "--run", run_id], root, timeout_s))
    except ValueError:
        raise OrchError("ORCH_CLI_FAILED", "orch conduct observe did not answer JSON") from None
    path = _report_path(_dict(printed).get("markdown"), root, run_id)
    try:
        with open(path, "rb") as handle:
            data = handle.read(REPORT_LIMIT + 1)
    except OSError as error:
        raise OrchError("ORCH_CLI_FAILED", f"the report cannot be read: {error.strerror}") from None
    return {"$schema": VIEW, "view": "markdown", "text": md_text(data.decode("utf-8", errors="replace")) or "(empty report)"}


def questions(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    run_id = _run_id(context, params, required=False)
    rows = []
    if root:
        try:
            found = orch_json(["conduct", "questions", "--json"] + (["--run", run_id] if run_id else []), root, timeout_s)
        except OrchError as error:
            if error.code != "ORCH_RUN_NOT_FOUND" or run_id:
                raise
            found = {}
        for entry in _list(_dict(found).get("questions")):
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                continue
            item = safe_text(entry.get("item"), 64) or "-"
            rows.append({"id": f"{item}:{safe_text(entry['id'], 64)}", "cells": {
                "item": item, "question": _text(entry.get("text"), "-"), "kind": _text(entry.get("kind"), "-", 64),
                "state": "answered, waits for resume" if entry.get("answered") else "open",
                "age_s": _int(entry.get("age_s")), "overdue": "yes" if entry.get("overdue") else "no"}})
    columns = [{"id": "item", "title": "Item", "type": "text"}, {"id": "question", "title": "Question", "type": "text"},
               {"id": "kind", "title": "Kind", "type": "text"}, {"id": "state", "title": "State", "type": "text"},
               {"id": "age_s", "title": "Age (s)", "type": "number"}, {"id": "overdue", "title": "Overdue", "type": "text"}]
    return {"$schema": VIEW, "view": "resource-list", "columns": columns, "rows": rows, "total": len(rows)}


def sandbox(root: Optional[str], timeout_s: float, **_: Any) -> Dict[str, Any]:
    results = _list(orch_json(["doctor", "--json"], root or os.getcwd(), timeout_s))
    rows, seen = [], set()
    for result in results:
        if not isinstance(result, dict) or not str(result.get("check_id") or "").startswith("orch.") \
                or result["check_id"] in seen:
            continue
        seen.add(result["check_id"])
        evidence = [safe_text(line, 120) for line in _list(result.get("evidence")) if isinstance(line, str)]
        detail = "; ".join([part for part in [safe_text(result.get("observed") or ""), *evidence] if part])
        rows.append({"id": safe_text(result["check_id"], 64), "label": safe_text(result["check_id"], 64),
                     "status": result["status"] if result.get("status") in STATUSES else "unknown",
                     "detail": safe_text(detail, 500) if detail else safe_text(result.get("observed") or "-")})
    rows.sort(key=lambda row: (row["id"] != "orch.sandbox", row["id"]))
    rows.append({"id": "scope", "label": "What the sandbox covers", "status": "unknown", "detail": SANDBOX_NOTE})
    return {"$schema": VIEW, "view": "status-table", "rows": rows}


QUERIES: Dict[str, Callable[..., Dict[str, Any]]] = {
    f"{OWNER}.runs": runs, f"{OWNER}.latest": latest, f"{OWNER}.run": run, f"{OWNER}.items": items,
    f"{OWNER}.report": report, f"{OWNER}.questions": questions, f"{OWNER}.sandbox": sandbox}


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
        return {**reply, "status": "error", "error": {
            "code": "ORCH_UNKNOWN_QUERY",
            "message": f"no {'query' if request.get('point') == 'gui:query' else 'command'} {safe_text(given.get('id'))}"}}
    host = request.get("context") if isinstance(request.get("context"), dict) else {}
    context = given.get("context") if isinstance(given.get("context"), dict) else {}
    params = given.get("params") if isinstance(given.get("params"), dict) else {}
    timeout_s = max(1.0, float(request.get("deadline_ms", 60000)) / 1000 - 1)
    try:
        return {**reply, "status": "ok", "output": query(host.get("project_root"), timeout_s, context=context,
                                                          params=params)}
    except OrchError as error:
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
