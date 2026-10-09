"""Run ``plan.py`` and its ``bridge orch`` verbs on a copy of planner's demo plan (subprocess, as an executor would)."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

BRIDGE = Path(__file__).resolve().parents[1]
PLANNER = Path(__file__).resolve().parents[3]
DEMO = PLANNER / "tests/engine/fixtures/demo-plan"
PLAN_NAME = "2026.10.05-№7-DEMO"
PLAN_PY = PLANNER / "scripts/plan.py"

if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))


def demo_plan(tmpdir) -> Path:
    """Copy the demo plan to ``<tmpdir>/plans/2026.10.05-№7-DEMO`` and return its directory."""
    plan_dir = Path(tmpdir) / "plans" / PLAN_NAME
    shutil.copytree(DEMO, plan_dir)
    source = Path(tmpdir) / "lib/pkg/config.py"  # repo file the demo items list as a required read
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("DEFAULT = 1\n", encoding="utf-8")
    return plan_dir


def plan_py(tmpdir, *args: str) -> subprocess.CompletedProcess:
    """``plan.py <args>`` run in ``tmpdir``."""
    return subprocess.run([sys.executable, str(PLAN_PY), *args], cwd=tmpdir, capture_output=True, text=True,
                          encoding="utf-8", check=False)


def brief_of_demo_plan(tmpdir, item="P1.2", unit=None) -> dict:
    """Copy the demo plan into ``tmpdir`` and return the JSON of the bridge's ``brief``."""
    cmd = ["bridge", "orch", "brief", str(demo_plan(tmpdir)), item]
    if unit:
        cmd += ["--unit", unit]
    done = plan_py(tmpdir, *cmd)
    if done.returncode:
        raise RuntimeError(f"bridge orch brief failed ({done.returncode}): {done.stderr or done.stdout}")
    return json.loads(done.stdout)
