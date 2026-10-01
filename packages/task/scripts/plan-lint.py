#!/usr/bin/env python3
"""Thin launcher: adds `lib/` (and the root of the monorepo - for `core/`) in sys.path
and delegates to `task.plan_lint.main()`. Logic - in lib/task/plan_lint.py
(separate imported module: name scripts/plan-lint.py cannot be used with a hyphen
import directly, and tests need to pull the parser/checks individually, not only
via subprocess).

Called by protocol commands (`plan-design`/`plan-run`/`plan-close`):
    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-lint.py" plans/<PLAN-ID>
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

from task.plan_lint import main  # noqa: E402  (after editing sys.path)

if __name__ == "__main__":
    sys.exit(main())
