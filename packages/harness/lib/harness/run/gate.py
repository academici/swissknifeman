"""Internal documentation."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from core import find_monorepo_root

GREEN = "GREEN"
ATTENTION = "ATTENTION"
RED = "RED"
_RANK = {RED: 0, ATTENTION: 1, GREEN: 2}

_BOOKKEEPING_ROOT_FILE = "plans/ACTIVE.md"


class GateUnavailable(RuntimeError):
    """Internal documentation."""




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
    proc = _git(["status", "--porcelain", "--", plan_rel], cwd=git_root, timeout=timeout)
    if proc.returncode != 0:
        raise GateUnavailable(f"git status --porcelain failed: {proc.stderr.strip()}")
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def snapshot_before(plan_dir, *, timeout=30):
    """Internal documentation."""
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


def _changed_paths(commit_hash, git_root, *, timeout=30):
    proc = _git(["show", "--name-only", "--pretty=format:", commit_hash],
               cwd=git_root, timeout=timeout)
    if proc.returncode != 0:
        raise GateUnavailable(
            f"git show --name-only {commit_hash} failed: {proc.stderr.strip()}")
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def _path_pattern(template):
    """Registry path template → full-match regex, without a second layout table."""
    parts = re.split(r"(<[^>]+>|\{[^}]+\}|\*\*)", template)
    escaped = "".join(
        r"[^/]+" if part.startswith(("<", "{")) else r".*" if part == "**"
        else re.escape(part).replace(r"\*", r"[^/]*")
        for part in parts
    )
    return re.compile(r"^" + escaped + r"$")


def _is_bookkeeping(rel_path, plan_rel, layout_data):
    """Classify a commit path from the resolver-projected carrier registry.

    The gate deliberately does not own a v2 path list: task's layout boundary
    returns patterns for volatile/index/history carriers, and the gate merely
    matches the path it was handed by git.
    """
    if rel_path == _BOOKKEEPING_ROOT_FILE:
        return True
    prefix = plan_rel + "/"
    if not rel_path.startswith(prefix):
        return False
    sub = rel_path[len(prefix):]
    return any(_path_pattern(template).match(sub)
               for template in layout_data["bookkeeping_patterns"])


def _call_plan_layout(plan_dir, phase_id, monorepo_root, *, timeout=30):
    """Read resolver addresses and bookkeeping patterns across the package boundary."""
    task_lib = str(Path(monorepo_root) / "packages" / "task" / "lib")
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = task_lib if not existing else task_lib + os.pathsep + existing
    code = (
        "import importlib,json,sys; m=importlib.import_module('task.plan_layout'); "
        "d,p=sys.argv[1:3]; v=m.layout_version(d); rows=m.registry().values(); "
        "patterns=[r['path'] for r in rows if v in r.get('layout_versions',[]) "
        "and (r.get('class') not in ('spec','evidence','research') or r.get('mutability')=='managed-block')]; "
        "x={'layout':v,'core':str(m.plan_core_path(d)),'phase':str(m.phase_path(d,p)),"
        "'handoff':str(m.carrier_path(d,'handoff')),'journal':str(m.carrier_path(d,'journal')),"
        "'bookkeeping_patterns':patterns}; print(json.dumps(x))"
    )
    try:
        proc = subprocess.run(["python3", "-c", code, str(plan_dir), phase_id],
                              capture_output=True, text=True, timeout=timeout,
                              check=False, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateUnavailable(f"layout resolver failed: {exc}") from exc
    if proc.returncode:
        raise GateUnavailable(f"layout resolver failed: {proc.stderr.strip()[-400:]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise GateUnavailable(f"layout resolver did not return JSON: {exc}") from exc


def _read_closure(before, phase_id, monorepo_root, *, timeout=30):
    """Internal documentation."""
    git_root = Path(before["git_root"])
    plan_rel = before["plan_rel"]
    layout = _call_plan_layout(git_root / plan_rel, phase_id, monorepo_root, timeout=timeout)

    log = _git(["log", "--format=%H", f"{before['sha']}..HEAD"], cwd=git_root, timeout=timeout)
    if log.returncode != 0:
        raise GateUnavailable(f"git log failed: {log.stderr.strip()}")
    commits = [ln for ln in log.stdout.splitlines() if ln.strip()]

    union_paths = set()
    bundle = False
    for commit in commits:
        paths = _changed_paths(commit, git_root, timeout=timeout)
        union_paths.update(paths)
        has_bookkeeping = any(_is_bookkeeping(p, plan_rel, layout) for p in paths)
        has_scope = any(not _is_bookkeeping(p, plan_rel, layout) for p in paths)
        if has_bookkeeping and has_scope:
            bundle = True

    phase_path = Path(layout["phase"]).relative_to(git_root).as_posix()
    core_path = Path(layout["core"]).relative_to(git_root).as_posix()
    handoff_path = Path(layout["handoff"]).relative_to(git_root).as_posix()
    journal_path = Path(layout["journal"]).relative_to(git_root).as_posix()
    required = ({core_path, phase_path, journal_path}
                if layout["layout"] == "v2" else {core_path, phase_path, handoff_path})
    missing = sorted(required - union_paths)

    return {
        "commit_count": len(commits),
        "commits": commits,
        "signature_complete": not missing,
        "missing_signature_paths": missing,
        "bundle": bundle,
        "dirty_remainder": sorted(
            set(_porcelain_lines(git_root, plan_rel, timeout=timeout)) - set(before["dirty"])),
    }




def _run_plan_lint(plan_dir, monorepo_root, extra_args, *, timeout=60):
    script = Path(monorepo_root) / "packages" / "task" / "scripts" / "plan-lint.py"
    try:
        return subprocess.run(["python3", str(script), str(plan_dir), *extra_args],
                              capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateUnavailable(f"plan-lint.py did not start: {exc}") from exc


def _read_lint_signals(plan_dir, monorepo_root, baseline_sha, *, timeout=60):
    """Internal documentation."""
    baseline = _run_plan_lint(plan_dir, monorepo_root,
                              ["--baseline", baseline_sha, "--gate", "new"], timeout=timeout)
    if "not available" in (baseline.stderr or ""):
        return {"degraded": True, "clean": False, "new_error_suspected": False,
                "new_warning_only": False, "lint_class": "degraded",
                "reason": baseline.stderr.strip()[-400:]}
    if baseline.returncode == 0:
        return {"degraded": False, "clean": True, "new_error_suspected": False,
                "new_warning_only": False, "lint_class": "clean", "reason": None}







    current = _run_plan_lint(plan_dir, monorepo_root, ["--gate", "all"], timeout=timeout)
    if current.returncode != 0:
        return {"degraded": False, "clean": False, "new_error_suspected": True,
                "new_warning_only": False, "lint_class": "new-error-suspected",
                "reason": ("there is a new diagnostic, and it is present in the tree ERROR — "
                          "doubt → strict verdict (IR6)")}
    return {"degraded": False, "clean": False, "new_error_suspected": False,
            "new_warning_only": True, "lint_class": "new-warning-only", "reason": None}


def _empty_field(value):
    v = (value or "").strip()
    return v in ("", "—")


def _read_item_fields_after(plan_dir, phase_id, item_id, monorepo_root, *, timeout=60):
    """Internal documentation."""
    try:
        proc = _run_plan_lint(plan_dir, monorepo_root, ["--json"], timeout=timeout)
    except GateUnavailable as exc:
        return {"available": False, "reason": str(exc)}
    if proc.returncode != 0:
        return {"available": False,
                "reason": (f"plan-lint.py --json ended with the code {proc.returncode} "
                          f"(circuit carries ERROR — S1 is not available for reading fields): "
                          f"{proc.stderr.strip()[-400:]}")}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"available": False, "reason": f"plan-lint.py --json: no output JSON: {exc}"}

    plan_key = Path(plan_dir).name
    phase_model = (((data.get("plans") or {}).get(plan_key) or {}).get("phases") or {}).get(phase_id) or {}
    item_model = (phase_model.get("items") or {}).get(item_id)
    if item_model is None:
        return {"available": False, "reason": f"item {item_id} not found in model S1 phases {phase_id}"}

    fields = item_model.get("fields") or {}
    return {
        "available": True,
        "status": fields.get("Status") or None,
        "pending_work_nonempty": not _empty_field(fields.get("Pending Work")),
        "known_deviations_nonempty": not _empty_field(fields.get("Known Deviations")),
        "escalation_needed_yes": (fields.get("Escalation Needed") or "").strip().lower().startswith("yes"),
    }




TABLE = (

    ("outcome-not-ok", RED, lambda s: s["outcome_class"] != "ok"),

    ("lint-new-error", RED, lambda s: s["lint_new_error_suspected"]),

    ("no-commits", RED, lambda s: s["commit_count"] == 0),

    ("closure-signature-incomplete", RED, lambda s: not s["signature_complete"]),

    ("dirty-remainder", RED, lambda s: bool(s["dirty_remainder"])),

    ("status-blocked", RED, lambda s: s["item_status"] == "🔴 Blocked"),
    # RED — Escalation Needed: yes
    ("escalation-needed-yes", RED, lambda s: s["escalation_needed_yes"]),

    ("escalation-in-report", RED, lambda s: "ESCALATION-REQUIRED:" in (s["result_text"] or "")),

    ("no-op", RED, lambda s: s["item_status"] in ("🟡 In progress", "⬜ Not started")),

    ("item-fields-unavailable", RED, lambda s: not s["item_fields_available"]),

    ("status-deviations", ATTENTION, lambda s: s["item_status"] == "🟠 Done with deviations"),

    ("permission-denials", ATTENTION, lambda s: bool(s["permission_denials"])),

    ("pending-work", ATTENTION, lambda s: s["pending_work_nonempty"]),

    ("known-deviations", ATTENTION, lambda s: s["known_deviations_nonempty"]),

    ("bundle", ATTENTION, lambda s: s["bundle"]),

    ("lint-new-warning-only", ATTENTION, lambda s: s["lint_new_warning_only"]),

    ("all-clear", GREEN, lambda s: (
        s["outcome_class"] == "ok" and s["lint_clean"] and s["signature_complete"]
        and not s["dirty_remainder"] and s["commit_count"] > 0
        and s["item_fields_available"] and s["item_status"] == "🟢 Done")),
)


def _classify(signals):
    """Internal documentation."""
    matched = [(name, klass) for name, klass, predicate in TABLE if predicate(signals)]
    if not matched:
        matched = [("no-signal-matched-default", RED)]
    _, worst_klass = min(matched, key=lambda m: _RANK[m[1]])
    return worst_klass, [name for name, _ in matched]




def pre_launch_verdict(queue_item):
    """Internal documentation."""
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
    """Internal documentation."""
    plan_dir = Path(plan_dir)
    if monorepo_root is None:
        monorepo_root = find_monorepo_root(plan_dir.resolve())
        if monorepo_root is None:
            raise GateUnavailable(
                f"monorepo root not found from {plan_dir} — package `task` not available")

    lint = _read_lint_signals(plan_dir, monorepo_root, before["sha"], timeout=timeout)
    closure = _read_closure(before, phase_id, monorepo_root, timeout=timeout)
    item_after = _read_item_fields_after(plan_dir, phase_id, item_id, monorepo_root,
                                        timeout=timeout)

    signals = {
        "outcome_class": outcome.get("outcome"),
        "permission_denials": outcome.get("permission_denials"),
        "result_text": outcome.get("result_text"),
        "lint_clean": lint["clean"],
        "lint_new_error_suspected": lint["new_error_suspected"],
        "lint_new_warning_only": lint["new_warning_only"],
        "commit_count": closure["commit_count"],
        "signature_complete": closure["signature_complete"],
        "bundle": closure["bundle"],
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
        "lint_class": lint["lint_class"],
        "raw": {"outcome": outcome, "lint": lint, "closure": closure, "item_after": item_after,
               "plan_id": plan_id, "item_id": item_id, "phase_id": phase_id},
    }
