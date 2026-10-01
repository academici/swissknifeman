"""Internal documentation."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from core import find_monorepo_root


EXEC_NOT_RUN = "EXEC-NOT-RUN"
ROUTING_UNRESOLVED = "ROUTING-UNRESOLVED"
NEXT_FORM_UNSUPPORTED = "NEXT-FORM-UNSUPPORTED"
PLAN_UNREADABLE = "PLAN-UNREADABLE"
ITEM_TERMINAL = "ITEM-TERMINAL"



TERMINAL_STATUSES = ("🟢 Done", "🟠 Done with deviations", "⛔ Skipped by decision")






# Routing `Exec` spellings that resolve to the one execution mode `run` (mirrors
# `task_contract.resolve_exec`; `plan-exec`/`manual`/`plan-run` are legacy aliases).
EXEC_RUN_SPELLINGS = frozenset({"run", "plan-run", "plan-exec", "manual"})
EXEC_RUN = "run"





_SECTION_HEADER_RE = re.compile(r"^##\s+\S.*$")
_ROUTING_HEADER_RE = re.compile(r"^##\s+3\.\s+Routing\s*$")
_ROUTING_RANGE_RE = re.compile(r"^(P\d+)\.(\d+)\s*[–-]\s*(P\d+)\.(\d+)$")
_ROUTING_ITEMS_HEADER = "Items"
_ROUTING_EXEC_HEADER = "Exec"





_NEXT_FORM_RE = re.compile(
    r"^(run-items|exec-items|audit-design|design-phase|design-item|audit-phase|close|archive|"
    r"terminal|manual|waiting):")


def _read_plan_lines(path):
    """Internal documentation."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return text.replace("\r\n", "\n").split("\n")


def _split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _routing_table(plan_lines):
    """Internal documentation."""
    header_idxs = [i for i, ln in enumerate(plan_lines) if _SECTION_HEADER_RE.match(ln)]
    body = None
    for idx in header_idxs:
        if _ROUTING_HEADER_RE.match(plan_lines[idx]):
            following = [i for i in header_idxs if i > idx]
            end = following[0] if following else len(plan_lines)
            body = plan_lines[idx + 1:end]
            break
    if body is None:
        return None, None

    table_start = None
    for i, ln in enumerate(body):
        if ln.strip().startswith("|"):
            table_start = i
            break
    if table_start is None:
        return None, None

    headers = _split_row(body[table_start])
    rows = []
    i = table_start + 2
    while i < len(body) and body[i].strip().startswith("|"):
        cells = _split_row(body[i])
        row = {headers[j]: (cells[j] if j < len(cells) else "") for j in range(len(headers))}
        rows.append((row, i))
        i += 1
    return headers, rows


def _row_covers_item(cell, item_id, phase_token, item_n):
    """Internal documentation."""
    if cell == item_id:
        return True
    m = _ROUTING_RANGE_RE.match(cell)
    return bool(m and item_n is not None and m.group(1) == phase_token == m.group(3)
                and int(m.group(2)) <= item_n <= int(m.group(4)))


def _resolve_exec_cell(plan_lines, item_id):
    """Internal documentation."""
    headers, rows = _routing_table(plan_lines)
    if headers is None:
        return None, "in `plan.md` no section «## 3. Routing» with table"
    if _ROUTING_EXEC_HEADER not in headers:
        return None, "table «## 3. Routing» without column «Exec» (legacy form §3 without column)"

    phase_token = item_id.split(".")[0]
    try:
        item_n = int(item_id.split(".")[1])
    except (IndexError, ValueError):
        item_n = None

    for row, _lineno in rows:
        cell = (row.get(_ROUTING_ITEMS_HEADER, "") or "").strip().strip("`")
        if _row_covers_item(cell, item_id, phase_token, item_n):
            value = (row.get(_ROUTING_EXEC_HEADER, "") or "").strip().strip("`")
            return (EXEC_RUN if value in EXEC_RUN_SPELLINGS else value), None

    for row, lineno in rows:
        cell = (row.get(_ROUTING_ITEMS_HEADER, "") or "").strip().strip("`")
        if "," in cell and any(
            _row_covers_item(t.strip().strip("`"), item_id, phase_token, item_n)
            for t in cell.split(",")
        ):
            return None, (
                f"§3 Routing string {cell!r} (string {lineno}) — comma separated list, "
                "illegal cell shape `Items` (canon §9): route from matched "
                "token is not taken, it remains a refusal")

    return None, f"no line §3 Routing, covering {item_id}"


def _resolve_next_form(next_field_text):
    """Internal documentation."""
    declaring_line = next(
        (ln.strip() for ln in (next_field_text or "").splitlines() if ln.strip()), "")
    m = _NEXT_FORM_RE.match(declaring_line)
    return (m.group(1) if m else None), declaring_line


def _call_plan_lint(plan_dir, monorepo_root, *, timeout=60):
    """Internal documentation."""
    script = Path(monorepo_root) / "packages" / "task" / "scripts" / "plan-lint.py"
    try:
        proc = subprocess.run(
            ["python3", str(script), str(plan_dir), "--json"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"plan-lint.py did not start: {exc}"
    if proc.returncode != 0:
        return None, (
            f"plan-lint.py ended with the code {proc.returncode} (fail-loud — source "
            f"S1 not available, not «nothing to do»): {proc.stderr.strip()[-800:]}")
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"plan-lint.py --json not recognized as JSON: {exc}"


def _call_task_contract_build(plan_dir, item_id, monorepo_root, *, timeout=60):
    """Internal documentation."""
    task_lib = str(Path(monorepo_root) / "packages" / "task" / "lib")
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = task_lib if not existing else task_lib + os.pathsep + existing
    try:
        proc = subprocess.run(
            ["python3", "-m", "task.task_contract", "build",
             "--plan-dir", str(plan_dir), "--item", item_id],
            capture_output=True, text=True, timeout=timeout, check=False, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"task.task_contract build did not start: {exc}"
    if proc.returncode != 0:
        return None, (f"task.task_contract build --item {item_id} ended with the code "
                      f"{proc.returncode}: {proc.stderr.strip()[-800:]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return None, f"task.task_contract build --item {item_id}: no output JSON: {exc}"
    required = (payload.get("route") or {}).get("required") or {}
    model_class, effort = required.get("model_class"), required.get("effort")
    if not model_class or not effort:
        return None, (f"task.task_contract build --item {item_id}: route.required "
                      f"is incomplete: {required!r}")
    return {"model_class": model_class, "effort": effort}, None


def _call_plan_layout(plan_dir, monorepo_root, *, timeout=60):
    """S3: task's resolver stays across the subprocess boundary (D29)."""
    task_lib = str(Path(monorepo_root) / "packages" / "task" / "lib")
    env = dict(os.environ)
    env["PYTHONPATH"] = task_lib + os.pathsep + str(monorepo_root)
    code = (
        "import importlib,json,sys; m=importlib.import_module('task.plan_layout'); "
        "d=sys.argv[1]; "
        "x={'core':str(m.plan_core_path(d)), 'layout':m.layout_version(d)}; "
        "print(json.dumps(x))"
    )
    try:
        args = ["python3", "-c", code, str(plan_dir)]
        proc = subprocess.run(args, capture_output=True,
                              text=True, timeout=timeout, check=False, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"layout resolver did not start: {exc}"
    if proc.returncode:
        return None, f"layout resolver failed: {proc.stderr.strip()[-400:]}"
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"layout resolver did not return JSON: {exc}"


def _classify_drivability(exec_value, exec_error, route, route_error):
    """Drivable iff `Exec` resolves to `run` and the item's route resolves."""
    if exec_value != EXEC_RUN:
        return False, EXEC_NOT_RUN, exec_error or f"Exec={exec_value!r} does not resolve to `run`"
    if route is None:
        return False, ROUTING_UNRESOLVED, route_error or "item route does not resolve (S2)"
    return True, None, None


def _degraded(plan_dir, phase_id, reason):
    return {
        "plan_dir": str(plan_dir), "phase_id": phase_id,
        "degraded": True, "degraded_reasons": [reason],
        "next_form": None, "items": [], "excluded_terminal": [],
    }


def queue(plan_dir, phase_id, *, monorepo_root=None):
    """Internal documentation."""
    plan_dir = Path(plan_dir)
    if monorepo_root is None:
        monorepo_root = find_monorepo_root(plan_dir.resolve())
        if monorepo_root is None:
            return _degraded(plan_dir, phase_id, (
                f"monorepo root not found from {plan_dir} — package `task` not available "
                "(standalone-layout): driver refuses to drive, not silent"))
    monorepo_root = Path(monorepo_root)

    layout, layout_error = _call_plan_layout(plan_dir, monorepo_root)
    if layout is None:
        return _degraded(plan_dir, phase_id, layout_error)

    data, reason = _call_plan_lint(plan_dir, monorepo_root)
    if data is None:
        return _degraded(plan_dir, phase_id, reason)

    plan_key = plan_dir.name
    plan_model = (data.get("plans") or {}).get(plan_key)
    if plan_model is None:
        return _degraded(plan_dir, phase_id,
                          f"plan-lint --json does not contain a plan model «{plan_key}»")

    phase_model = (plan_model.get("phases") or {}).get(phase_id)
    if phase_model is None:
        return _degraded(plan_dir, phase_id, f"phase «{phase_id}» not found in plan model")

    handoff = plan_model.get("handoff") or {}
    next_raw = (handoff.get("fields") or {}).get("Next", "") or ""
    next_kind, next_declaring_line = _resolve_next_form(next_raw)
    next_form = {"kind": next_kind, "declaring_line": next_declaring_line}

    plan_lines = _read_plan_lines(layout["core"]) if next_kind is not None else None

    status_rows = phase_model.get("status_table") or []
    items_fields = phase_model.get("items") or {}

    result_items = []
    excluded_terminal = []
    for row in status_rows:
        item_id = row.get("ID")
        if not item_id:
            continue
        fields = (items_fields.get(item_id) or {}).get("fields") or {}
        status = fields.get("Status") or row.get("Status") or ""

        if status in TERMINAL_STATUSES:
            excluded_terminal.append({
                "item_id": item_id, "status": status, "refusal": ITEM_TERMINAL,
            })
            continue

        if next_kind is None:
            result_items.append({
                "item_id": item_id, "status": status,
                "route": None, "route_error": None,
                "exec": None, "exec_error": None,
                "drivable": False, "refusal": NEXT_FORM_UNSUPPORTED,
                "refusal_detail": (
                    f"form owner `handoff.fields.Next` outside closed enum "
                    f"(S5, line: {next_declaring_line!r})"
                    " — driving phase denied entirely, not by item'y"),
            })
            continue

        item_next_kind, item_next_line = next_kind, next_declaring_line
        if plan_lines is None:
            exec_value, exec_error = None, "`plan.md` is not readable §3 Routing"
        else:
            exec_value, exec_error = _resolve_exec_cell(plan_lines, item_id)
        route, route_error = _call_task_contract_build(plan_dir, item_id, monorepo_root)

        drivable, refusal, refusal_detail = _classify_drivability(
            exec_value, exec_error, route, route_error)

        result_items.append({
            "item_id": item_id, "status": status,
            "route": route, "route_error": route_error,
            "exec": exec_value, "exec_error": exec_error,
            "drivable": drivable, "refusal": refusal, "refusal_detail": refusal_detail,
            "next_form": {"kind": item_next_kind, "declaring_line": item_next_line},
        })

    return {
        "plan_dir": str(plan_dir), "phase_id": phase_id,
        "degraded": False, "degraded_reasons": [],
        "next_form": next_form, "items": result_items,
        "excluded_terminal": excluded_terminal,
    }
