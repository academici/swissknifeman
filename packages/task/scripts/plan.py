#!/usr/bin/env python3
"""Thin launcher: Task plan (layout v3) authoring CLI.

Logic - in lib/task/plan/cli.py (thin launcher: sys.path -> lib).

Call:
    python3 packages/task/scripts/plan.py new --codename DEMO --title "Demo" --actor claude-code/claude-opus-5-5/high --message "..."
    python3 packages/task/scripts/plan.py check PLAN7
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from task.plan.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
