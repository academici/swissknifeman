"""Driver friction events of a run wave, written through `plan.py log`."""
from __future__ import annotations

import subprocess
from pathlib import Path

from harness.run import plan_reader, task_paths, worker


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








# category -> `plan.py log` type: a refused launch is a blocker, a failed or idle run a difficulty
_EVENT_TYPE = {
    CATEGORY_ROUTING_BLOCKED: "blocker",
    worker.OUTCOME_TIMEOUT: "difficulty",
    worker.OUTCOME_TRANSPORT: "difficulty",
    worker.OUTCOME_QUOTA: "difficulty",
    worker.OUTCOME_ERROR: "difficulty",
    CATEGORY_NO_OP: "difficulty",
}

# the driver identity recorded as the event actor (`PROVIDER/MODEL`)
DRIVER_ACTOR = "harness/driver"

_NON_TERMINAL_STATUSES = frozenset({"in_progress", "todo"})




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




def _build_argv(*, plan_dir, item_id, run_id, event_type, note, task,
                session_id=None, cost_usd=None, num_turns=None, duration_ms=None):
    argv = ["python3", str(plan_reader.plan_script(task)), "log",
            str(plan_dir), item_id, "--type", event_type, "--summary", note,
            "--actor", DRIVER_ACTOR, "--ref", f"run:{run_id}"]
    metrics = [f"{key}={value}" for key, value in (
        ("session", session_id), ("cost_usd", cost_usd), ("turns", num_turns),
        ("duration_ms", duration_ms)) if value is not None]
    if metrics:
        argv += ["--impact", " ".join(metrics)]
    return argv


def _resolve_task_root(monorepo_root, plan_dir):
    try:
        return task_paths.task_root(Path(plan_dir).resolve(), monorepo_root=monorepo_root)
    except task_paths.TaskUnavailable as exc:
        raise JournalUnavailable(f"{exc} (process CLI log not available)") from exc


def _run_cli(argv, *, timeout):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise JournalUnavailable(f"plan.py log failed: {exc}") from exc


def _build_note(run_id, category, *, outcome=None, refusal_detail=None):
    prefix = f"[wave {run_id}]"
    if category == CATEGORY_ROUTING_BLOCKED:
        return f"{prefix} routing-blocked: {refusal_detail or 'item did not start'}"
    if category == CATEGORY_NO_OP:
        return f"{prefix} run completed, but status item'and did not move (no-op)"
    reason = (outcome or {}).get("reason") or category
    return f"{prefix} {category}: {reason}"




def maybe_write(plan_dir, item_id, *, run_id, pre_launch=False,
                refusal_detail=None, outcome=None, item_status=None, monorepo_root=None,
                timeout=30):
    """Internal documentation."""
    if not run_id:
        raise ValueError("run_id is required for the driver line (discriminator IR2)")

    category, who = classify(pre_launch=pre_launch, outcome=outcome, item_status=item_status)
    if who == WORKER:
        return None

    event_type = _EVENT_TYPE[category]
    note = _build_note(run_id, category, outcome=outcome, refusal_detail=refusal_detail)
    task = _resolve_task_root(monorepo_root, plan_dir)
    argv = _build_argv(
        plan_dir=plan_dir, item_id=item_id, run_id=run_id, event_type=event_type, note=note,
        task=task,
        session_id=(outcome or {}).get("session_id"),
        cost_usd=(outcome or {}).get("total_cost_usd"),
        num_turns=(outcome or {}).get("num_turns"),
        duration_ms=(outcome or {}).get("duration_ms"))

    proc = _run_cli(argv, timeout=timeout)
    if proc.returncode != 0:
        raise JournalCallFailed(
            f"plan.py log returned {proc.returncode}: {(proc.stderr or '').strip()[-400:]}")
    return {"category": category, "type": event_type, "note": note, "argv": argv}


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
