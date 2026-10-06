"""Import fallback for direct test discovery: puts lib/ and the monorepo root on sys.path."""
import sys
from pathlib import Path

# In case of direct launch (`cd packages/task && python3 -m unittest discover -s tests`,
# without prior PYTHONPATH) — guarantee lib/ in the path
_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
_REPO_ROOT = Path(__file__).resolve().parents[3]
if (_REPO_ROOT / "core").is_dir() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
