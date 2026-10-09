import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("AICORE_ROOT") or str(Path(__file__).resolve().parents[5]))
from tests.ext.fixtures.plugins._serve import serve  # noqa: E402

serve(Path(__file__).resolve().parent)
