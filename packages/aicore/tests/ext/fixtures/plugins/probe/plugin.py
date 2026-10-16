import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("AICORE_ROOT") or str(Path(__file__).resolve().parents[5]))
from tests.ext.fixtures.plugins._serve import serve  # noqa: E402


def invoke(request):
    names = request["input"].get("names", [])
    return {"present": {name: name in os.environ for name in names}, "trusted": os.environ.get("SKM_EXT_TRUSTED")}


serve(Path(__file__).resolve().parent, invoke=invoke)
