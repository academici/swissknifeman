"""Queue of one phase read through the Task plan API (`plan.py show|next --json`)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from core import find_monorepo_root


ROUTING_UNRESOLVED = "ROUTING-UNRESOLVED"
PLAN_UNREADABLE = "PLAN-UNREADABLE"
ITEM_TERMINAL = "ITEM-TERMINAL"
ITEM_BLOCKED = "ITEM-BLOCKED"
PHASE_NOT_DETAILED = "PHASE-NOT-DETAILED"

TERMINAL_STATUSES = ("done", "done_with_deviations", "skipped")

# The worker always executes through the plan-run command; kept as a queue field for consumers.
EXEC_RUN = "run"


def plan_script(monorepo_root):
    return Path(monorepo_root) / "packages" / "task" / "scripts" / "plan.py"


def call_plan(monorepo_root, verb, plan_dir, *args, timeout=60):
    """Run `plan.py <verb> <plan_dir> [args] --json`; return `(payload, None)` or `(None, reason)`."""
    argv = ["python3", str(plan_script(monorepo_root)), verb, str(plan_dir), *args, "--json"]
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


def queue(plan_dir, phase_id, *, monorepo_root=None):
    """Queue of the phase items: drivable ones, refusals by name, terminal items dequeued."""
    plan_dir = Path(plan_dir)
    if monorepo_root is None:
        monorepo_root = find_monorepo_root(plan_dir.resolve())
        if monorepo_root is None:
            return _degraded(plan_dir, phase_id, (
                f"monorepo root not found from {plan_dir} — package `task` not available "
                "(standalone-layout): driver refuses to drive, not silent"))
    monorepo_root = Path(monorepo_root)

    phase, reason = call_plan(monorepo_root, "show", plan_dir, phase_id)
    if phase is None or reason:
        return _degraded(plan_dir, phase_id, reason or f"phase «{phase_id}» not readable")
    nxt, reason = call_plan(monorepo_root, "next", plan_dir)
    if nxt is None or reason:
        return _degraded(plan_dir, phase_id, reason or "next step not readable")

    next_form = {"kind": nxt.get("kind"), "declaring_line": nxt.get("exact") or ""}
    phase_detailed = phase.get("design") == "detailed"

    result_items = []
    excluded_terminal = []
    for item_id in phase.get("items") or []:
        item, reason = call_plan(monorepo_root, "show", plan_dir, item_id)
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
