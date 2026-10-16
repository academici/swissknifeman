import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.environ.get("AICORE_ROOT") or str(Path(__file__).resolve().parents[5]))
from tests.ext.fixtures.plugins._serve import serve  # noqa: E402

time.sleep(30)  # longer than the 1 s deadline of the manifest
serve(Path(__file__).resolve().parent)
