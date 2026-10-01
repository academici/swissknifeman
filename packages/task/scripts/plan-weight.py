#!/usr/bin/env python3
"""Thin launcher: adds `lib/` (and the root of the monorepo - for `core/`) in sys.path
and delegates to `task.plan_weight.main()`. Logic - in lib/task/plan_weight.py
(separate imported module: name scripts/plan-weight.py cannot be used with a hyphen
import directly, and tests need to pull the resolver/measured individually, not only
via subprocess). Same template as scripts/plan-lint.py.

Call:
    python3 packages/task/scripts/plan-weight.py plan plans/<PLAN-ID>
    python3 packages/task/scripts/plan-weight.py item plans/<PLAN-ID> Pn.m --json
    python3 packages/task/scripts/plan-weight.py sweep plans/
"""
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent       # packages/task
_MONOREPO_ROOT = _PKG_ROOT.parent.parent                 # root monorepo (…/packages/task -> …)
sys.path.insert(0, str(_PKG_ROOT / "lib"))
if (_MONOREPO_ROOT / "core").is_dir():
    # core/ optional (standalone-package layout - no monorepo parent - too
    # working: task.plan_lint itself falls back without core.term).
    sys.path.insert(0, str(_MONOREPO_ROOT))

from task.plan_weight import main  # noqa: E402  (after editing sys.path)

if __name__ == "__main__":
    sys.exit(main())
