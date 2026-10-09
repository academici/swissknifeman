#!/usr/bin/env python3
"""Thin launcher: planner plan (layout v4) authoring CLI.

Logic - in lib/planner/plan/cli.py (thin launcher: sys.path -> lib).

Call:
    python3 packages/planner/scripts/plan.py new --codename DEMO --title "Demo" --actor claude-code/claude-opus-5-5/high --message "..."
    python3 packages/planner/scripts/plan.py check PLAN7
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from planner.plan.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
