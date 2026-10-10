"""Layout-v3 plan fixtures for Harness black-box tests, built only through `plan.py`."""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PLAN_SCRIPT = REPO_ROOT / "packages" / "planner" / "scripts" / "plan.py"
ACTOR = "claude-code/claude-opus-5-5/high"
DATE = "2026.10.05"

_DETAIL = {
    "summary": "Harness fixture item", "why": "Exercises the run driver",
    "scope": {"include": ["fixture.py"]}, "deliverables": ["fixture"],
    "task_files": [{"path": "lib/fixture.py", "change": "any"}],
    "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}],
}


def run_plan(*args, plans_root=None, expect=0):
    """Run one `plan.py` verb; `plans_root` is appended as `--plans-root`."""
    argv = [sys.executable, str(PLAN_SCRIPT), *args]
    if plans_root is not None:
        argv += ["--plans-root", str(plans_root)]
    # Fixture plans must not start event delivery: it runs after the call and would move journal cursors the test
    # compares or commits.
    env = {**os.environ, "SKM_AICORE_EVENTS__DELIVERY": "off"}
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False, env=env)
    if result.returncode != expect:
        raise RuntimeError(f"plan.py {args} exited {result.returncode}: {result.stderr}")
    return result


def write_plan(root, *, codename="FIXTURE", items, design="detailed", phase="P1"):
    """Create `<root>/plans/<ID>` with one phase and items, return `(plan_dir, item_ids)`.

    `items` is a list of `(status, route)`; status is one of `todo, in_progress, done,
    done_with_deviations, blocked`, route is `(class, effort)` or None to keep the default.
    """
    plans = Path(root) / "plans"
    run_plan("new", "--codename", codename, "--title", "Harness fixture", "--actor", ACTOR,
             "--message", "Fixture for harness tests.", "--date", DATE, plans_root=plans)
    plan_dir = next(plans.iterdir())
    run_plan("set", "PLAN1", "plan", "--json", json.dumps(
        {"goal": "Exercise the run driver.", "context": "Synthetic plan for Harness tests."}),
        plans_root=plans)
    run_plan("add-phase", "PLAN1", "--title", "Fixture phase", plans_root=plans)
    item_ids = []
    for index, (status, route) in enumerate(items, start=1):
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
