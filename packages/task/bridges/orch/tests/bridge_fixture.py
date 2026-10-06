"""Run ``plan.py bridge orch brief`` on a copy of Task's demo plan (subprocess, as an executor would)."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

BRIDGE = Path(__file__).resolve().parents[1]
TASK = Path(__file__).resolve().parents[3]
DEMO = TASK / "tests/engine/fixtures/demo-plan"
PLAN_NAME = "2026.10.05-№7-DEMO"

if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))


def brief_of_demo_plan(tmpdir, item="P1.2", unit=None) -> dict:
    """Copy the demo plan to ``<tmpdir>/plans/2026.10.05-№7-DEMO`` and return the JSON of the bridge's ``brief``."""
    plan_dir = Path(tmpdir) / "plans" / PLAN_NAME
    shutil.copytree(DEMO, plan_dir)
    source = Path(tmpdir) / "lib/pkg/config.py"  # repo file the demo items list as a required read
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("DEFAULT = 1\n", encoding="utf-8")
    cmd = [sys.executable, str(TASK / "scripts/plan.py"), "bridge", "orch", "brief", str(plan_dir), item]
    if unit:
        cmd += ["--unit", unit]
    done = subprocess.run(cmd, cwd=tmpdir, capture_output=True, text=True, encoding="utf-8", check=False)
    if done.returncode:
        raise RuntimeError(f"bridge orch brief failed ({done.returncode}): {done.stderr or done.stdout}")
    return json.loads(done.stdout)
