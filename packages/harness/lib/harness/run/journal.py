"""Internal documentation."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from core import find_monorepo_root

from harness.run import worker


DRIVER = "driver"
WORKER = "worker"

CATEGORY_ROUTING_BLOCKED = "routing-blocked"
CATEGORY_NO_OP = "no-op"
CATEGORY_OK_TERMINAL = "ok-terminal"





WHO_WRITES = (
    (CATEGORY_ROUTING_BLOCKED, DRIVER),
    (worker.OUTCOME_TIMEOUT, DRIVER),
    (worker.OUTCOME_TRANSPORT, DRIVER),
    (worker.OUTCOME_QUOTA, DRIVER),
    (worker.OUTCOME_ERROR, DRIVER),
    (CATEGORY_NO_OP, DRIVER),
    (CATEGORY_OK_TERMINAL, WORKER),
)
_WHO_WRITES = dict(WHO_WRITES)








_RESULT_FRICTION = {
    CATEGORY_ROUTING_BLOCKED: ("routing-rejected", ("routing-blocked",)),
    worker.OUTCOME_TIMEOUT: ("block-candidate", ()),
    worker.OUTCOME_TRANSPORT: ("block-candidate", ()),
    worker.OUTCOME_QUOTA: ("block-candidate", ()),
    worker.OUTCOME_ERROR: ("block-candidate", ()),
    CATEGORY_NO_OP: ("no-op", ("no-op",)),
}




_NON_TERMINAL_STATUSES = frozenset({"🟡 In progress", "⬜ Not started"})



_DRIVER_COMMAND = worker.WORKER_COMMAND_ID.rsplit(":", 1)[-1]


class JournalUnavailable(RuntimeError):
    """Internal documentation."""


class JournalWriteRefused(RuntimeError):
    """Internal documentation."""


class JournalCallFailed(RuntimeError):
    """Internal documentation."""


def classify(*, pre_launch, outcome=None, item_status=None):
    """Internal documentation."""
    if pre_launch:
        return CATEGORY_ROUTING_BLOCKED, _WHO_WRITES[CATEGORY_ROUTING_BLOCKED]

    kind = (outcome or {}).get("outcome")
    if kind == worker.OUTCOME_OK:
        terminal = item_status not in _NON_TERMINAL_STATUSES
        category = CATEGORY_OK_TERMINAL if terminal else CATEGORY_NO_OP
        return category, _WHO_WRITES[category]
    if kind in _WHO_WRITES:
        return kind, _WHO_WRITES[kind]
    raise JournalWriteRefused(
        f"unknown run outcome {kind!r} — line is NOT written (Implementation Rule 3)")




def _build_argv(*, plan_dir, plan_id, item_id, run_id, attempt, actor, result, friction, note,
                session_id=None, cost_usd=None, num_turns=None, duration_ms=None):
    argv = ["python3", "-m", "task.journal", "append",
           "--plan-dir", str(plan_dir), "--plan", plan_id, "--item", item_id,
           "--command", _DRIVER_COMMAND, "--result", result, "--actor", actor,
           "--run-id", run_id, "--attempt", str(attempt)]
    if friction:
        argv += ["--friction", ",".join(friction)]
    if session_id is not None:
        argv += ["--session-id", session_id]
    if cost_usd is not None:
        argv += ["--cost-usd", str(cost_usd)]
    if num_turns is not None:
        argv += ["--num-turns", str(num_turns)]
    if duration_ms is not None:
        argv += ["--duration-ms", str(duration_ms)]
    if note is not None:
        argv += ["--note", note]
    return argv


def _task_lib_path(monorepo_root):



    return Path(monorepo_root).joinpath("packages", "task", "lib")


def _resolve_monorepo_root(monorepo_root, plan_dir):
    if monorepo_root is not None:
        return Path(monorepo_root)
    root = find_monorepo_root(Path(plan_dir).resolve())
    if root is None:
        raise JournalUnavailable(
            "monorepo root not found - process CLI log not available "
            "(standalone-layout without owner package)")
    return root


def _run_cli(argv, *, monorepo_root, plan_dir, timeout):
    root = _resolve_monorepo_root(monorepo_root, plan_dir)
    env = dict(os.environ)
    lib_path = str(_task_lib_path(root))
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = lib_path if not existing else os.pathsep.join([lib_path, existing])
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              env=env, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise JournalUnavailable(f"process CLI log failed: {exc}") from exc


def _build_note(run_id, category, *, outcome=None, refusal_detail=None):
    prefix = f"[wave {run_id}]"
    if category == CATEGORY_ROUTING_BLOCKED:
        return f"{prefix} routing-blocked: {refusal_detail or 'item did not start'}"
    if category == CATEGORY_NO_OP:
        return f"{prefix} run completed, but status item'and did not move (no-op)"
    reason = (outcome or {}).get("reason") or category
    return f"{prefix} {category}: {reason}"




def maybe_write(plan_dir, plan_id, item_id, *, run_id, attempt, actor, pre_launch=False,
                refusal_detail=None, outcome=None, item_status=None, monorepo_root=None,
                timeout=30):
    """Internal documentation."""
    if not run_id:
        raise ValueError("run_id is required for the driver line (discriminator IR2)")

    category, who = classify(pre_launch=pre_launch, outcome=outcome, item_status=item_status)
    if who == WORKER:
        return None

    result, friction = _RESULT_FRICTION[category]
    note = _build_note(run_id, category, outcome=outcome, refusal_detail=refusal_detail)
    argv = _build_argv(
        plan_dir=plan_dir, plan_id=plan_id, item_id=item_id, run_id=run_id, attempt=attempt,
        actor=actor, result=result, friction=friction, note=note,
        session_id=(outcome or {}).get("session_id"),
        cost_usd=(outcome or {}).get("total_cost_usd"),
        num_turns=(outcome or {}).get("num_turns"),
        duration_ms=(outcome or {}).get("duration_ms"))

    proc = _run_cli(argv, monorepo_root=monorepo_root, plan_dir=plan_dir, timeout=timeout)
    if proc.returncode != 0:
        raise JournalCallFailed(
            f"task.journal append returned {proc.returncode}: {(proc.stderr or '').strip()[-400:]}")
    return {"category": category, "result": result, "friction": list(friction), "note": note,
           "argv": argv}


def summarize_wave(run_id, records):
    """Internal documentation."""
    counts = {"GREEN": 0, "ATTENTION": 0, "RED": 0}
    interventions = 0
    cost_total, cost_seen = 0.0, False
    duration_total, duration_seen = 0.0, False
    client_versions = set()

    for record in records:
        verdict = record["verdict"]
        counts[verdict] = counts.get(verdict, 0) + 1
        if record.get("wrote_driver_line"):
            interventions += 1
        outcome = record.get("outcome") or {}
        cost = outcome.get("total_cost_usd")
        if cost is not None:
            cost_total += cost
            cost_seen = True
        duration = outcome.get("duration_ms")
        if duration is not None:
            duration_total += duration
            duration_seen = True
        client_version = outcome.get("client_version")
        if client_version:
            client_versions.add(client_version)

    return {
        "run_id": run_id,
        "queued": len(records),
        "green": counts["GREEN"],
        "attention": counts["ATTENTION"],
        "red": counts["RED"],
        "interventions": interventions,
        "cost_usd_total": cost_total if cost_seen else None,
        "duration_ms_total": duration_total if duration_seen else None,
        "client_versions": sorted(client_versions),
        "verdicts": [{"item_id": r["item_id"], "verdict": r["verdict"]} for r in records],
    }
