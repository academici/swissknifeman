import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("AICORE_ROOT") or str(Path(__file__).resolve().parents[5]))
from tests.ext.fixtures.plugins._serve import serve  # noqa: E402

# A grandchild in a session of its own is out of reach of a process-group kill; it ends by itself after 3 s.
subprocess.Popen(["sleep", "3"], start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL)
serve(Path(__file__).resolve().parent)
