#!/usr/bin/env python3
"""gui-orch: the orchestrator (conductor runs, status, items, observer report, questions, sandbox) as GUI queries; an
aicore command plugin (protocol 1).

The adapter only calls the orch command line (``$SKM_UMBRELLA orch ...``, or ``swissknifeman`` on PATH) in the
project folder and moves fields of its JSON answers into ``view-data/v1``. It reads no state folder of the
orchestrator and imports no module: the list of runs is ``conduct runs``, the report is the file whose path the CLI
prints, read only when its real path lies under ``<project>/.swissknifeman/orch/reports/<run>/``. It computes no
status of its own, only the map from an outcome to a view status. Every string is shown as text (control characters
removed); markdown goes to the host sanitizer. Counts and tokens are integers. Redaction uses the aicore foundation.
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
STEP = re.compile(r"^[a-z][a-z0-9-]*(\.[0-9]+(-q[0-9]+)?)?$")
PROVIDERS = ("claude-code", "codex", "grok")
ROLES = ("context-scout", "executor", "reviewer", "triager", "registrar", "report-fixer", "researcher", "advisor")
STATUSES = ("ok", "warn", "fail", "skip", "unknown")
OUTCOME_STATUS = {"done": "ok", "finished": "ok", "done_with_deviations": "warn", "blocked": "fail", "failed": "fail",
                  "orphaned": "warn", "stopped": "warn", "running": "warn", "waiting": "warn"}
ORPHANED = "RUN_ORPHANED: no live conductor holds the run; resume continues it"
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


def _foundation():
    """Load shared redaction via the foundation root or the hub registry, never a neighbour path."""
    try:
        from aicore.util.redact import env_secrets, redact_text
    except ImportError:
        root = os.environ.get("AICORE_ROOT")
        if not root:
            command = os.environ.get("SKM_UMBRELLA") or shutil.which("swissknifeman")
            if not command:
                raise RuntimeError("AICORE_UNAVAILABLE: the foundation root or hub registry is required") from None
            try:
                result = subprocess.run([command, "units", "list", "--json"], capture_output=True, text=True,
                                        timeout=10, stdin=subprocess.DEVNULL, check=True)
                doc = json.loads(result.stdout)
                unit = next(unit for unit in doc.get("units", []) if unit.get("id") == "aicore")
                root = os.path.join(doc.get("hub_root", ""), unit["root"])
            except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError):
                raise RuntimeError("AICORE_UNAVAILABLE: the hub registry did not locate the foundation") from None
        sys.path.insert(0, os.path.join(root, "lib"))
        from aicore.util.redact import env_secrets, redact_text
    return env_secrets, redact_text


_REDACTION = None


def _redact(value: Any) -> str:
    global _REDACTION
    if _REDACTION is None:
        _REDACTION = _foundation()
    env_secrets, redact_text = _REDACTION
    return redact_text(str(value), secrets=env_secrets())


def safe_text(value: Any, limit: int = 500) -> str:
    redacted = _redact(value)
    text = _CONTROL.sub(" ", _ANSI.sub("", redacted)).strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def md_text(value: Any, limit: int = REPORT_LIMIT) -> str:
    text = _MARKDOWN_CONTROL.sub(" ", _ANSI.sub("", _redact(value))).strip()
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


def _text(value: Any, fallback: str, limit: int = 500) -> str:
    return (safe_text(value, limit) if isinstance(value, (str, int, float, bool)) else "") or fallback


def _run_id(context: Dict[str, Any], params: Dict[str, Any], *, required: bool = True) -> Optional[str]:
    run_id = context.get("run_id") or params.get("run_id")
    if run_id is None and not required:
        return None
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise OrchError("ORCH_CONTEXT_MISSING", "run_id must look like cnd-...")
    return run_id


def _need_root(root: Optional[str]) -> str:
    if not root:
        raise OrchError("ORCH_CONTEXT_MISSING", "the query needs a project")
    return root


def _run_link(run_id: str) -> Dict[str, Any]:
    return {"route": f"{OWNER}.run", "params": {"run_id": safe_text(run_id, 64)}}


def _owner(value: Any) -> str:
    owner = _dict(value)
    if not owner:
        return "-"
    if owner.get("lock") == "unavailable":  # orch could not probe the lease here (a read-only context)
        return "unknown (the lease lock is unavailable here)"
    return safe_text(f"pid {owner.get('pid') or 'unknown'} on {owner.get('host') or 'unknown'} "
                     f"since {owner.get('started_at') or 'unknown'} ({owner.get('command') or 'unknown'})")


def view_status(outcome: Any, running: bool = False) -> str:
    if isinstance(outcome, str) and outcome in OUTCOME_STATUS:
        return OUTCOME_STATUS[outcome]
    return "warn" if outcome is None and running else "unknown"


# --- queries ---------------------------------------------------------------------------------------------------

RUN_COLUMNS = [{"id": "run", "title": "Run", "type": "text"}, {"id": "status", "title": "Status", "type": "status"},
               {"id": "reason", "title": "Reason", "type": "text"}, {"id": "created", "title": "Started", "type": "text"},
               {"id": "items", "title": "Items", "type": "text"}, {"id": "resumes", "title": "Resumes", "type": "number"},
               {"id": "owner", "title": "Owner", "type": "text"}]


def _runs_rows(root: str, timeout_s: float, limit: Optional[int]) -> List[Dict[str, Any]]:
    args = ["conduct", "runs", "--json"] + (["--limit", str(limit)] if limit else [])
    rows = []
    for run in _list(_dict(orch_json(args, root, timeout_s)).get("runs")):
        if not isinstance(run, dict) or not isinstance(run.get("run_id"), str) or not RUN_ID.fullmatch(run["run_id"]):
            continue
        items = [safe_text(item, 64) for item in _list(run.get("items")) if isinstance(item, str)]
        rows.append({"id": safe_text(run["run_id"], 64), "cells": {
            "run": safe_text(run["run_id"], 64), "status": view_status(run.get("status")),
            "reason": ORPHANED if run.get("status") == "orphaned" else _text(run.get("reason_code"), "-", 64),
            "created": _text(run.get("created"), "-", 64), "owner": _owner(run.get("owner")),
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
    fields = [{"label": "Run", "type": "text", "value": safe_text(run_id, 64)},
              {"label": "Status", "type": "status", "value": view_status(found.get("status"))},
              {"label": "State", "type": "text", "value": _text(found.get("status"), "unknown", 64)},
              {"label": "Owner", "type": "text", "value": _owner(found.get("lease"))}]
    if found.get("status") == "orphaned":
        fields.append({"label": "Detail", "type": "text", "value": ORPHANED})
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
    detail: Dict[str, Any] = {"$schema": VIEW, "view": "resource-detail", "title": safe_text(f"Run {run_id}", 64), "fields": fields}
    if found.get("status") in ("orphaned", "stopped", "blocked"):
        detail["actions"] = [{"command": f"{OWNER}.resume", "input": {"run_id": safe_text(run_id, 64)}}]
    elif found.get("status") == "waiting":  # not a failure: the answers come first, then this one command goes on
        detail["actions"] = [{"command": f"{OWNER}.continue", "input": {"run_id": safe_text(run_id, 64)}}]
        waiting = [row for row in _list(found.get("waiting")) if isinstance(row, dict) and row.get("item")]
        if waiting:
            sections.append({"title": "Waiting for an answer", "markdown": "\n".join(
                f"- {md_text(row['item'], 64)}: {md_text(', '.join(str(name) for name in _list(row.get('question_ids'))), 200)}"
                f" since {md_text(row.get('since') or '-', 64)}" for row in waiting)})
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


def _item(context: Dict[str, Any], params: Dict[str, Any]) -> str:
    value = context.get("item") or params.get("item")
    if not isinstance(value, str) or ITEM_REF.fullmatch(value) is None:
        raise OrchError("ORCH_CONTEXT_MISSING", "item must be a single item reference")
    return value


def _route_label(value: Any) -> str:
    route = _dict(value)
    if not route:
        return "unknown"
    return safe_text("/".join(_text(route.get(key), "unknown", 64)
                              for key in ("provider", "model", "effort", "class")))


def routes(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    run_id, item = _run_id(context, params), _item(context, params)
    root = _need_root(root)
    found = _status(run_id, root, timeout_s)
    entry = next((row for row in _list(found.get("items")) if _dict(row).get("item") == item), {})
    recorded = _dict(entry.get("routes"))
    rows = []
    for role in sorted(set(recorded).intersection(ROLES)) or ["executor"]:
        used = _route_label(recorded.get(role))
        try:
            explained = _dict(orch_json(["route", "explain", "--role", role, "--run", run_id,
                                         "--item", item, "--json"], root, timeout_s))
        except OrchError as error:
            rows.append({"id": role, "label": role, "status": "unknown",
                         "detail": safe_text(f"used: {used}; available now: unknown ({error.message})")})
            continue
        now = _dict(explained.get("available_now"))
        available = now.get("available")
        stop = _dict(now.get("stop"))
        detail = f"used: {used}; available now: {_route_label(now.get('route'))}"
        if stop:
            detail += f" ({_text(stop.get('code'), 'unknown', 64)}: {_text(stop.get('message'), '-')})"
        rows.append({"id": role, "label": role, "status": "ok" if available is True else
                     "warn" if available is False else "unknown", "detail": safe_text(detail)})
    return {"$schema": VIEW, "view": "status-table", "rows": rows}


def prompt(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    run_id, item = _run_id(context, params), _item(context, params)
    step = params.get("step")
    if not isinstance(step, str) or STEP.fullmatch(step) is None:
        raise OrchError("ORCH_CONTEXT_MISSING", "step must be a role step such as executor.1")
    doc = _dict(orch_json(["conduct", "prompt", "explain", "--run", run_id, "--item", item,
                           "--step", step, "--json"], _need_root(root), timeout_s))
    fields = []
    for block in _list(doc.get("blocks")):
        block = _dict(block)
        # The projection is deliberately explicit: even an unexpected text/argv field stays private.
        fields.append({"label": _text(block.get("kind"), "unknown", 64), "type": "text",
                       "value": safe_text(f"origin: {_text(block.get('origin'), '-', 64)}; "
                                          f"tokens: {_int(block.get('tokens'))}; "
                                          f"sha256: {_text(block.get('sha256'), '-', 64)[:12]}")})
    for excluded in _list(doc.get("excluded")):
        excluded = _dict(excluded)
        fields.append({"label": safe_text(f"Excluded {_text(excluded.get('kind'), 'skill' if excluded.get('id') else 'unknown', 64)}", 64),
                       "type": "text", "value": _text(excluded.get("reason"), "unknown")})
    for name in ("core", "supporting", "retrieval"):
        amount = _dict(_dict(doc.get("budgets")).get(name)).get("tokens")
        fields.append({"label": name, "type": "number" if isinstance(amount, int) and not isinstance(amount, bool) else "text",
                       "value": _int(amount) if isinstance(amount, int) and not isinstance(amount, bool) else "unknown"})
    return {"$schema": VIEW, "view": "resource-detail", "title": safe_text(f"Prompt {item} {step}", 64), "fields": fields}


TIMELINE_STATUS = ("done", "stopped", "interrupted", "open")


def timeline(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    """The steps of a run as intervals, newest first, from ``conduct timeline --json`` (the adapter reads no file of the
    run): an interrupted and resumed step is two entries, an open step has no end."""
    run_id = _run_id(context, params)
    args = ["conduct", "timeline", "--run", run_id, "--json"]
    item = params.get("item") or context.get("item")
    if item is not None:
        if not isinstance(item, str) or ITEM_REF.fullmatch(item) is None:
            raise OrchError("ORCH_CONTEXT_MISSING", "item must be a plan item reference")
        args[4:4] = ["--item", item]
    found = _dict(orch_json(args, _need_root(root), timeout_s))
    entries = []
    for row in _list(found.get("intervals")):
        row = _dict(row)
        start = row.get("start")
        if not isinstance(start, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", start) is None:
            continue
        status = row.get("status") if row.get("status") in TIMELINE_STATUS else "unknown"
        took = f"{_int(row.get('duration_s'))} s" if isinstance(row.get("duration_s"), int) else "no end"
        detail = f"{status}, {took}; until {_text(row.get('end'), '-', 32)}; {_text(row.get('route'), '-', 64)}"
        if row.get("verdict"):
            detail += f"; {_text(row.get('verdict'), '-', 120)}"
        entries.append({"at": start, "kind": f"step.{status}",
                        "title": safe_text(f"{_text(row.get('item'), '-', 64)} {_text(row.get('stage'), '-', 64)}", 128),
                        "detail": safe_text(detail)})
    entries.sort(key=lambda entry: entry["at"], reverse=True)
    return {"$schema": VIEW, "view": "timeline", "entries": entries}


def budget(root: Optional[str], timeout_s: float, context: Dict[str, Any], params: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    found = _status(_run_id(context, params), _need_root(root), timeout_s)
    limits = _dict(found.get("limits"))
    entries = [row for row in _list(found.get("items")) if isinstance(row, dict)]
    metrics = []

    def add(metric_id, label, tokens, cap, incomplete):
        tokens = _dict(tokens)
        used = _int(tokens.get("input")) + _int(tokens.get("output"))
        known = isinstance(cap, int) and not isinstance(cap, bool)
        suffix = f"limit {cap}" if known and cap else "no limit" if known else "limit unknown"
        if incomplete:
            suffix += "; usage incomplete"
        metrics.append({"id": safe_text(metric_id, 64), "label": safe_text(f"{suffix}: {label}", 64),
                        "value": used, "unit": "fresh tokens", "status": "warn" if incomplete or (known and cap and used >= cap)
                        else "ok" if known and tokens else "unknown"})

    add("run", "Run", found.get("tokens"), _dict(limits.get("run_tokens_hard_max")).get("value"),
        any(row.get("usage_incomplete") is True for row in entries))
    incomplete = sum(row.get("usage_incomplete") is True for row in entries)
    if incomplete:
        metrics.append({"id": "usage_incomplete", "label": "Items with incomplete usage: totals may be understated",
                        "value": incomplete, "status": "warn"})
    for index, row in enumerate(entries):
        item = _text(row.get("item"), "unknown", 64)
        caps = _dict(_dict(limits.get("items")).get(row.get("item")))
        for key in ("tokens_max", "tokens_hard_max"):
            add(f"item.{index}.{key}", f"{item} {key}", row.get("tokens"), caps.get(key), row.get("usage_incomplete") is True)
    return {"$schema": VIEW, "view": "metric-group", "metrics": metrics}


def gates(root: Optional[str], timeout_s: float, **_: Any) -> Dict[str, Any]:
    doc = _dict(orch_json(["conduct", "gates", "--json"], root or os.getcwd(), timeout_s))
    rows = []
    for entry in _list(doc.get("gates")):
        entry = _dict(entry)
        provider = entry.get("provider")
        row = {"id": _text(provider, "unknown", 64), "label": _text(provider, "unknown", 64), "status": "warn",
               "detail": safe_text(f"until {_text(entry.get('until'), 'unknown', 64)}; "
                                   f"{_text(entry.get('class'), 'unknown', 64)} {_text(entry.get('code'), 'unknown', 64)}; "
                                   f"set by {_text(entry.get('set_by'), 'unknown', 64)}")}
        if provider in PROVIDERS:
            row["repair"] = {"command": f"{OWNER}.gates-clear", "input": {"provider": provider}}
        rows.append(row)
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
                "state": "answered — continue" if entry.get("answered") else "open",
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
    f"{OWNER}.report": report, f"{OWNER}.questions": questions, f"{OWNER}.sandbox": sandbox,
    f"{OWNER}.routes": routes, f"{OWNER}.prompt": prompt, f"{OWNER}.budget": budget, f"{OWNER}.gates": gates,
    f"{OWNER}.timeline": timeline}


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
