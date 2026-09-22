#!/usr/bin/env python3
"""Compact Task work facade; callable only by an explicit Task invocation."""
import sys
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PACKAGE / "lib"))
if (_PACKAGE.parent.parent / "core").is_dir():
    sys.path.insert(0, str(_PACKAGE.parent.parent))

from task.plan_work import main

if __name__ == "__main__":
    raise SystemExit(main())
