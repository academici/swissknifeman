#!/usr/bin/env python3
"""Launch the internal orch CLI directly from the package checkout.

The aicore foundation is found by the locator below and its lib joins sys.path after the module's own lib.
"""
import os
from pathlib import Path
import sys

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
_lib = _aicore_lib(ROOT)
if _lib is None:
    raise SystemExit("AICORE_NOT_FOUND: orch needs aicore; set AICORE_ROOT or place aicore beside this module")
sys.path.insert(1, str(_lib))
os.environ.setdefault("AICORE_ROOT", str(_lib.parent))

from orch.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
