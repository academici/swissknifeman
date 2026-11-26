"""Layout-v3 plan fixtures for Harness black-box tests, built only through `plan.py`."""
import json
import os
import subprocess
import unittest
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

from aicore.util.partners import partner_command

ACTOR = "claude-code/claude-opus-5-5/high"
DATE = "2026.10.05"

_DETAIL = {
    "summary": "Harness fixture item", "why": "Exercises the run driver",
    "scope": {"include": ["fixture.py"]}, "deliverables": ["fixture"],
    "task_files": [{"path": "lib/fixture.py", "change": "any"}],
    "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}],
    "review": {"mode": "none", "reason": "synthetic fixture item"},
}


def planner_argv():
    """argv prefix of the planner partner; the calling test is skipped when it is not found."""
    argv = partner_command("planner")
    if argv is None:
        raise unittest.SkipTest("planner partner not found (set PLANNER_ROOT or PLANNER_PLAN_PY)")
    return argv


def require_planner_root():
    """Skip the calling test when the driver cannot find the planner root either."""
    from harness.run import task_paths
    try:
        task_paths.planner_root()
    except task_paths.PlannerUnavailable as exc:
        raise unittest.SkipTest(str(exc)) from exc


def run_plan(*args, plans_root=None, expect=0):
    """Run one `plan.py` verb; `plans_root` is appended as `--plans-root`."""
    argv = [*planner_argv(), *args]
    if plans_root is not None:
        argv += ["--plans-root", str(plans_root)]
    # Fixture plans must not start event delivery: it runs after the call and would move journal cursors the test
    # compares or commits.
    env = {**os.environ, "SKM_AICORE_EVENTS__DELIVERY": "off"}
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False, env=env)
    if result.returncode != expect:
        raise RuntimeError(f"plan.py {args} exited {result.returncode}: {result.stderr}")
    return result


def _build_plan(root, *, codename="FIXTURE", items, design="detailed", phase="P1"):
    """Create `<root>/plans/<ID>` with one phase and items, return `(plan_dir, item_ids)`.

    `items` is a list of `(status, route)`; status is one of `todo, in_progress, done,
    done_with_deviations, blocked`, route is `(class, effort)` or None to keep the default.
    """
    require_planner_root()
    plans = Path(root) / "plans"
    run_plan("new", "--codename", codename, "--title", "Harness fixture", "--actor", ACTOR,
             "--message", "Fixture for harness tests.", "--date", DATE, plans_root=plans)
    plan_dir = next(plans.iterdir())
    run_plan("set", "PLAN1", "plan", "--json", json.dumps(
        {"goal": "Exercise the run driver.", "context": "Synthetic plan for Harness tests."}),
        plans_root=plans)
    run_plan("add-phase", "PLAN1", "--title", "Fixture phase", plans_root=plans)
    item_ids = []
    for index, (_status, route) in enumerate(items, start=1):
        item_id = f"{phase}.{index}"
        item_ids.append(item_id)
        run_plan("add-item", "PLAN1", phase, "--title", f"Fixture item {index}", plans_root=plans)
        detail = dict(_DETAIL)
        if route is not None:
            detail["route"] = {"class": route[0], "effort": route[1]}
        run_plan("set", "PLAN1", item_id, "--json", json.dumps(detail), plans_root=plans)
    if design == "detailed":
        run_plan("design-done", "PLAN1", phase, plans_root=plans)
        for item_id, (status, _route) in zip(item_ids, items):
            if status == "todo":
                continue
            run_plan("start", "PLAN1", item_id, "--actor", ACTOR, plans_root=plans)
            if status == "done":
                run_plan("finish", "PLAN1", item_id, "--status", "done", "--check", "V1=0",
                         "--notes", "fixture", plans_root=plans)
            elif status == "done_with_deviations":
                run_plan("finish", "PLAN1", item_id, "--status", "done_with_deviations",
                         "--check", "V1=0", "--deviation", "fixture deviation", plans_root=plans)
            elif status == "blocked":
                run_plan("finish", "PLAN1", item_id, "--status", "blocked",
                         "--escalation", "fixture escalation", plans_root=plans)
    return plan_dir, item_ids


@lru_cache(maxsize=32)
def _seed(codename, items, design, phase, argv, environment):
    """One private immutable seed per fixture variant and worker, built only by plan.py."""
    temporary = tempfile.TemporaryDirectory(prefix="harness-plan-seed-")
    try:
        plan, ids = _build_plan(temporary.name, codename=codename, items=items, design=design, phase=phase)
        for path in Path(temporary.name).rglob("*"):
            path.chmod(path.stat().st_mode & ~0o222)
        return temporary, plan.name, tuple(ids)
    except BaseException:
        temporary.cleanup()
        raise


def write_plan(root, *, codename="FIXTURE", items, design="detailed", phase="P1"):
    """Give every case an independent writable copy of its worker's CLI-built seed."""
    require_planner_root()
    plans = Path(root) / "plans"
    if plans.exists() or (Path(root) / ".swissknifeman").exists():
        return _build_plan(root, codename=codename, items=items, design=design, phase=phase)
    immutable_items = tuple((status, tuple(route) if route is not None else None) for status, route in items)
    temporary, name, ids = _seed(codename, immutable_items, design, phase, tuple(planner_argv()),
                                 tuple(sorted(os.environ.items())))
    seed = Path(temporary.name)
    shutil.copytree(seed, root, dirs_exist_ok=True)
    # Include CLI event/journal side effects as well as plans, without touching the case's git repository.
    for original in seed.rglob("*"):
        path = Path(root) / original.relative_to(seed)
        path.chmod(path.stat().st_mode | (0o700 if path.is_dir() else 0o200))
    return plans / name, list(ids)
