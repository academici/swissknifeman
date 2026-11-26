"""Queue of one phase read through the planner plan API (`plan.py show|next --json`)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import task_paths


ROUTING_UNRESOLVED = "ROUTING-UNRESOLVED"
PLAN_UNREADABLE = "PLAN-UNREADABLE"
ITEM_TERMINAL = "ITEM-TERMINAL"
ITEM_BLOCKED = "ITEM-BLOCKED"
PHASE_NOT_DETAILED = "PHASE-NOT-DETAILED"

TERMINAL_STATUSES = ("done", "done_with_deviations", "skipped")

# The worker always executes through the plan-run command; kept as a queue field for consumers.
EXEC_RUN = "run"


def plan_script(planner):
    return task_paths.script_in(planner)


def call_plan(planner, verb, plan_dir, *args, timeout=60):
    """Run `plan.py <verb> <plan_dir> [args] --json`; return `(payload, None)` or `(None, reason)`.

    `planner` is the planner package root (see `task_paths.planner_root`).
    """
    argv = ["python3", str(plan_script(planner)), verb, str(plan_dir), *args, "--json"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"plan.py {verb} did not start: {exc}"
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, (f"plan.py {verb} ended with the code {proc.returncode} without JSON "
                      f"(fail-loud, not «nothing to do»): {proc.stderr.strip()[-800:]}")
    if not isinstance(payload, dict):
        return None, f"plan.py {verb} did not return a JSON object"
    return payload, (None if proc.returncode == 0 or verb == "check" else
                     f"plan.py {verb} ended with the code {proc.returncode}: {proc.stderr.strip()[-400:]}")


def _degraded(plan_dir, phase_id, reason):
    return {
        "plan_dir": str(plan_dir), "phase_id": phase_id,
        "degraded": True, "degraded_reasons": [reason],
        "next_form": None, "items": [], "excluded_terminal": [],
    }


def _route(item):
    route = item.get("route") or {}
    model_class, effort = route.get("class"), route.get("effort")
    if not model_class or not effort:
        return None, f"item route is incomplete: {route!r}"
    return {"model_class": model_class, "effort": effort}, None


def _classify(status, phase_detailed, route, route_error):
    """Drivable iff the phase is detailed, the item is open and its route resolves."""
    if status == "blocked":
        return False, ITEM_BLOCKED, "item is blocked: it needs an owner decision, not a worker"
    if not phase_detailed:
        return False, PHASE_NOT_DETAILED, "phase is a skeleton: design it before running items"
    if route is None:
        return False, ROUTING_UNRESOLVED, route_error or "item route does not resolve"
    return True, None, None


def queue(plan_dir, phase_id):
    """Queue of the phase items: drivable ones, refusals by name, terminal items dequeued."""
    plan_dir = Path(plan_dir)
    try:
        planner = task_paths.planner_root()
    except task_paths.PlannerUnavailable as exc:
        return _degraded(plan_dir, phase_id, (
            f"{exc} (standalone-layout): driver refuses to drive, not silent"))

    phase, reason = call_plan(planner, "show", plan_dir, phase_id)
    if phase is None or reason:
        return _degraded(plan_dir, phase_id, reason or f"phase «{phase_id}» not readable")
    nxt, reason = call_plan(planner, "next", plan_dir)
    if nxt is None or reason:
        return _degraded(plan_dir, phase_id, reason or "next step not readable")

    next_form = {"kind": nxt.get("kind"), "declaring_line": nxt.get("exact") or ""}
    phase_detailed = phase.get("design") == "detailed"

    result_items = []
    excluded_terminal = []
    for item_id in phase.get("items") or []:
        item, reason = call_plan(planner, "show", plan_dir, item_id)
        if item is None or reason:
            return _degraded(plan_dir, phase_id, reason or f"item «{item_id}» not readable")
        status = item.get("status") or ""

        if status in TERMINAL_STATUSES:
            excluded_terminal.append({
                "item_id": item_id, "status": status, "refusal": ITEM_TERMINAL,
            })
            continue

        route, route_error = _route(item)
        drivable, refusal, refusal_detail = _classify(status, phase_detailed, route, route_error)
        result_items.append({
            "item_id": item_id, "status": status,
            "route": route, "route_error": route_error,
            "exec": EXEC_RUN if drivable else None, "exec_error": None,
            "drivable": drivable, "refusal": refusal, "refusal_detail": refusal_detail,
            "next_form": dict(next_form),
        })

    return {
        "plan_dir": str(plan_dir), "phase_id": phase_id,
        "degraded": False, "degraded_reasons": [],
        "next_form": next_form, "items": result_items,
        "excluded_terminal": excluded_terminal,
    }
