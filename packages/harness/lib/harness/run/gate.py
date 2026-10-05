"""Verdict of one worker run, computed from git and the Task plan API (`plan.py show|check`)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from core import find_monorepo_root

from . import plan_reader

GREEN = "GREEN"
ATTENTION = "ATTENTION"
RED = "RED"
_RANK = {RED: 0, ATTENTION: 1, GREEN: 2}


class GateUnavailable(RuntimeError):
    """The gate cannot observe git or the plan: the run has no verdict."""


def _git(args, cwd, *, timeout=30):
    try:
        return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                              text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateUnavailable(f"git {' '.join(args)} failed: {exc}") from exc


def _resolve_git_root(plan_dir, *, timeout=30):
    proc = _git(["rev-parse", "--show-toplevel"], cwd=plan_dir, timeout=timeout)
    if proc.returncode != 0:
        raise GateUnavailable(
            f"«{plan_dir}» out git-repository (or git not installed): {proc.stderr.strip()}")
    return Path(proc.stdout.strip())


def _porcelain_lines(git_root, plan_rel, *, timeout=30):
    """Dirty paths of the repository outside the plan directory (plan JSON is bookkeeping)."""
    proc = _git(["status", "--porcelain", "-z"], cwd=git_root, timeout=timeout)
    if proc.returncode != 0:
        raise GateUnavailable(f"git status --porcelain failed: {proc.stderr.strip()}")
    prefix = plan_rel + "/"
    lines, entries = [], iter(proc.stdout.split("\0"))
    for entry in entries:
        if len(entry) < 4:
            continue
        if entry[0] in "RC" or entry[1] in "RC":
            next(entries, None)  # the original path of a rename/copy
        if not entry[3:].startswith(prefix):
            lines.append(entry)
    return lines


def snapshot_before(plan_dir, *, timeout=30):
    """Fix HEAD and the dirty paths before a worker starts."""
    plan_dir = Path(plan_dir)
    git_root = _resolve_git_root(plan_dir, timeout=timeout)
    plan_rel = str(plan_dir.resolve().relative_to(git_root))
    head = _git(["rev-parse", "HEAD"], cwd=git_root, timeout=timeout)
    if head.returncode != 0:
        raise GateUnavailable(f"git rev-parse HEAD failed: {head.stderr.strip()}")
    return {
        "sha": head.stdout.strip(),
        "dirty": _porcelain_lines(git_root, plan_rel, timeout=timeout),
        "git_root": str(git_root),
        "plan_rel": plan_rel,
    }


def _read_closure(before, *, timeout=30):
    """Commits made since the snapshot and the uncommitted remainder outside the plan."""
    git_root = Path(before["git_root"])
    log = _git(["log", "--format=%H", f"{before['sha']}..HEAD"], cwd=git_root, timeout=timeout)
    if log.returncode != 0:
        raise GateUnavailable(f"git log failed: {log.stderr.strip()}")
    commits = [ln for ln in log.stdout.splitlines() if ln.strip()]
    remainder = set(_porcelain_lines(git_root, before["plan_rel"], timeout=timeout))
    return {
        "commit_count": len(commits),
        "commits": commits,
        "dirty_remainder": sorted(remainder - set(before["dirty"])),
    }


def _read_check_signals(plan_dir, monorepo_root, *, timeout=60):
    """`plan.py check`: errors are RED, warnings are ATTENTION, silence is clean."""
    payload, reason = plan_reader.call_plan(monorepo_root, "check", plan_dir, timeout=timeout)
    if payload is None or reason:
        return {"degraded": True, "clean": False, "errors": True, "warnings": False,
                "lint_class": "degraded", "reason": reason}
    errors, warnings = int(payload.get("errors") or 0), int(payload.get("warnings") or 0)
    lint_class = "errors" if errors else "warnings" if warnings else "clean"
    return {"degraded": False, "clean": lint_class == "clean", "errors": errors > 0,
            "warnings": warnings > 0 and errors == 0, "lint_class": lint_class,
            "reason": None}


def _read_item_after(plan_dir, item_id, monorepo_root, *, timeout=60):
    """Item JSON after the run: status, pending work, deviations, escalation."""
    item, reason = plan_reader.call_plan(monorepo_root, "show", plan_dir, item_id, timeout=timeout)
    if item is None or reason:
        return {"available": False, "reason": reason or f"item {item_id} not readable"}
    result = item.get("result") or {}
    return {
        "available": True,
        "status": item.get("status") or None,
        "pending_work_nonempty": bool(result.get("pending")),
        "known_deviations_nonempty": bool(result.get("deviations")),
        "escalation_needed_yes": bool((result.get("escalation") or "").strip()),
    }


TABLE = (
    ("outcome-not-ok", RED, lambda s: s["outcome_class"] != "ok"),
    ("check-errors", RED, lambda s: s["check_errors"]),
    ("no-commits", RED, lambda s: s["commit_count"] == 0),
    ("dirty-remainder", RED, lambda s: bool(s["dirty_remainder"])),
    ("status-blocked", RED, lambda s: s["item_status"] == "blocked"),
    ("escalation-needed-yes", RED, lambda s: s["escalation_needed_yes"]),
    ("escalation-in-report", RED, lambda s: "ESCALATION-REQUIRED:" in (s["result_text"] or "")),
    ("no-op", RED, lambda s: s["item_status"] in ("in_progress", "todo")),
    ("item-fields-unavailable", RED, lambda s: not s["item_fields_available"]),
    ("status-deviations", ATTENTION, lambda s: s["item_status"] == "done_with_deviations"),
    ("permission-denials", ATTENTION, lambda s: bool(s["permission_denials"])),
    ("pending-work", ATTENTION, lambda s: s["pending_work_nonempty"]),
    ("known-deviations", ATTENTION, lambda s: s["known_deviations_nonempty"]),
    ("check-warnings", ATTENTION, lambda s: s["check_warnings"]),
    ("all-clear", GREEN, lambda s: (
        s["outcome_class"] == "ok" and s["check_clean"]
        and not s["dirty_remainder"] and s["commit_count"] > 0
        and s["item_fields_available"] and s["item_status"] == "done")),
)


def _classify(signals):
    """Worst class among matched rows; no match is RED (doubt → strict verdict)."""
    matched = [(name, klass) for name, klass, predicate in TABLE if predicate(signals)]
    if not matched:
        matched = [("no-signal-matched-default", RED)]
    _, worst_klass = min(matched, key=lambda m: _RANK[m[1]])
    return worst_klass, [name for name, _ in matched]


def pre_launch_verdict(queue_item):
    """RED verdict for an item the driver refused to launch."""
    if queue_item.get("drivable"):
        raise ValueError("pre_launch_verdict is called only for NOT-drivable item'a")
    return {
        "verdict": RED,
        "signals_matched": ["pre-launch-refusal"],
        "lint_class": None,
        "raw": {"refusal": queue_item.get("refusal"), "detail": queue_item.get("refusal_detail")},
    }


def verdict(plan_id, item_id, phase_id, plan_dir, before, outcome, *, monorepo_root=None,
            timeout=60):
    """Verdict of one run from its outcome, git closure, plan check and item JSON."""
    plan_dir = Path(plan_dir)
    if monorepo_root is None:
        monorepo_root = find_monorepo_root(plan_dir.resolve())
        if monorepo_root is None:
            raise GateUnavailable(
                f"monorepo root not found from {plan_dir} — package `task` not available")

    check = _read_check_signals(plan_dir, monorepo_root, timeout=timeout)
    closure = _read_closure(before, timeout=timeout)
    item_after = _read_item_after(plan_dir, item_id, monorepo_root, timeout=timeout)

    signals = {
        "outcome_class": outcome.get("outcome"),
        "permission_denials": outcome.get("permission_denials"),
        "result_text": outcome.get("result_text"),
        "check_clean": check["clean"],
        "check_errors": check["errors"],
        "check_warnings": check["warnings"],
        "commit_count": closure["commit_count"],
        "dirty_remainder": closure["dirty_remainder"],
        "item_fields_available": item_after["available"],
        "item_status": item_after.get("status"),
        "pending_work_nonempty": item_after.get("pending_work_nonempty", False),
        "known_deviations_nonempty": item_after.get("known_deviations_nonempty", False),
        "escalation_needed_yes": item_after.get("escalation_needed_yes", False),
    }
    klass, matched = _classify(signals)
    return {
        "verdict": klass,
        "signals_matched": matched,
        "lint_class": check["lint_class"],
        "raw": {"outcome": outcome, "lint": check, "closure": closure, "item_after": item_after,
                "plan_id": plan_id, "item_id": item_id, "phase_id": phase_id},
    }
