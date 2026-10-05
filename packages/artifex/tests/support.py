"""Fixture helpers intentionally keep process payloads independent of compiler logic."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path


FIXTURE_PLAN = Path(__file__).resolve().parent / "fixtures_data" / "2026.10.05-№1-DEMO"
PLAN_CLI = Path(__file__).resolve().parents[2] / "task" / "scripts" / "plan.py"
ITEM_SPEC = {
    "route": {"class": "implementation", "effort": "high"},
    "task_files": [{"path": "src/out.py", "change": "create"}],
    "reads": [{"path": "docs/read.md", "why": "required read", "required": True}],
    "validation": [{"id": "V1", "cmd": "check one", "expect": "exit 0", "kind": "acceptance"}],
    "deliverables": ["Deliverable text"],
}


def plan_cli(cwd, *args):
    """Run the Task plan CLI; fixtures are written only through it."""
    done = subprocess.run([sys.executable, str(PLAN_CLI), *args], cwd=cwd, capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(f"plan.py {' '.join(args)}: {done.stderr or done.stdout}")
    return done.stdout


def make_plan(plans_root, *, repository="fixture"):
    """Create a v3 plan with phases P1, P2 and item P2.1 under ``plans_root``; return its directory."""
    plans_root = Path(plans_root)
    plans_root.mkdir(parents=True, exist_ok=True)
    plan_cli(plans_root.parent, "new", "--plans-root", str(plans_root), "--codename", "DEMO",
             "--title", "Demo plan", "--actor", "claude-code/claude-opus-5-5/high",
             "--message", "Synthetic plan used only as a package test fixture.")
    plan = next(plans_root.iterdir())
    plan_cli(plans_root.parent, "set", str(plan), "plan", "--json", json.dumps({"repository": repository}))
    for title in ("Foundation", "Slice phase"):
        plan_cli(plans_root.parent, "add-phase", str(plan), "--title", title)
    plan_cli(plans_root.parent, "add-item", str(plan), "P2", "--title", "Demo item",
             "--json", json.dumps(ITEM_SPEC))
    return plan


def load_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def clone(value):
    return copy.deepcopy(value)


def p2_1_pending_s3_fixture():
    """Independent expected Harness source for compiler conformance tests."""
    return {
        "degraded": False,
        "items": [{
            "item_id": "P2.1",
            "status": "todo",
            "route": {"model_class": "implementation", "effort": "high"},
            "route_error": None,
            "exec": "run",
            "exec_error": None,
            "drivable": True,
            "refusal": None,
            "refusal_detail": None,
            "argv": None,
            "argv_error": None,
        }],
        "excluded_terminal": [],
    }
