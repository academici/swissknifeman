#!/usr/bin/env python3
"""Thin launcher: planner plan (layout v4) authoring CLI.

Logic - in lib/planner/plan/cli.py (thin launcher: sys.path -> lib). The engine needs no aicore: when
the foundation is found (AICORE_ROOT, _vendor/aicore or the sibling aicore) its lib joins sys.path
after the module's own lib.

Call:
    python3 packages/planner/scripts/plan.py new --codename DEMO --title "Demo" --actor claude-code/claude-opus-5-5/high --message "..."
    python3 packages/planner/scripts/plan.py check PLAN7
"""
import os
import sys
from pathlib import Path

# --- aicore locator (python) ---
# Finds the aicore foundation: $AICORE_ROOT, then <module>/_vendor/aicore, then the sibling <module>/../aicore.
# Canonical copy: packages/aicore/scripts/aicore_locator.py; copies must stay identical.
def _aicore_lib(module_root):
    import json
    import os
    from pathlib import Path

    def _ok(root):
        try:
            return json.loads((root / "unit.json").read_text(encoding="utf-8")).get("id") == "aicore"
        except (OSError, ValueError):
            return False

    explicit = os.environ.get("AICORE_ROOT")
    if explicit:
        if not _ok(Path(explicit)):
            raise SystemExit(f"AICORE_NOT_FOUND: AICORE_ROOT={explicit} is not an aicore checkout")
        return Path(explicit).resolve() / "lib"
    for root in (Path(module_root) / "_vendor" / "aicore", Path(module_root).parent / "aicore"):
        if _ok(root):
            return root.resolve() / "lib"
    return None
# --- end aicore locator (python) ---

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
_lib = _aicore_lib(ROOT)
if _lib is not None:
    sys.path.insert(1, str(_lib))
    os.environ.setdefault("AICORE_ROOT", str(_lib.parent))

from planner.plan.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
