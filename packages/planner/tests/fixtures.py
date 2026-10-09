"""Import fallback for direct test discovery: puts lib/ and, when it sits next to the module, the aicore lib on sys.path."""
import sys
import unittest
from pathlib import Path

# In case of direct launch (`cd packages/planner && python3 -m unittest discover -s tests`,
# without prior PYTHONPATH) — guarantee lib/ in the path
_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
_AICORE_LIB = Path(__file__).resolve().parents[2] / "aicore" / "lib"
if (_AICORE_LIB / "aicore" / "__init__.py").is_file() and str(_AICORE_LIB) not in sys.path:
    sys.path.insert(1, str(_AICORE_LIB))

MODULE_ROOT = Path(__file__).resolve().parents[1]
_HUB = Path(__file__).resolve().parents[3]
# The repository root when this module sits at packages/planner of it; None in a vendored or standalone copy.
HUB_ROOT = _HUB if (_HUB / "packages" / "planner").resolve() == MODULE_ROOT.resolve() else None
hub_only = unittest.skipUnless(HUB_ROOT is not None, "needs the repository layout (packages/planner in the hub)")
