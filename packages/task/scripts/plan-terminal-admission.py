#!/usr/bin/env python3
"""Worktree-local CLI for Task terminal-admission leases."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "lib"))

from task.terminal_admission import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
