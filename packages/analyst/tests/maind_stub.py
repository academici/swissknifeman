"""A stand-in `maind` executable that answers `projects list --json` for registry-based commands."""
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest import mock

_SCRIPT = """#!{python}
import sys
if sys.argv[1:4] == ["projects", "list", "--json"]:
    sys.stdout.write({payload!r})
    sys.exit(0)
sys.stderr.write("unexpected arguments: " + " ".join(sys.argv[1:]))
sys.exit(2)
"""


def install_maind_stub(testcase, projects):
    """Put a fake maind on SKM_MAIND_BIN for ``testcase``; ``projects`` is the registry list it prints."""
    tmp = tempfile.TemporaryDirectory()
    testcase.addCleanup(tmp.cleanup)
    path = Path(tmp.name) / "maind"
    path.write_text(_SCRIPT.format(python=sys.executable, payload=json.dumps(projects)), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    env = {k: v for k, v in os.environ.items() if k not in ("MAIND_BIN", "SKM_MAIND_ROOT")}
    env["SKM_MAIND_BIN"] = str(path)   # the legacy MAIND_BIN would be tried first, so it is dropped
    patcher = mock.patch.dict(os.environ, env, clear=True)
    patcher.start()
    testcase.addCleanup(patcher.stop)
    return path


def without_maind(testcase):
    """Hide every maind lookup step (legacy and SKM variables, PATH entries holding maind) for ``testcase``."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("MAIND_BIN", "SKM_MAIND_BIN", "SKM_MAIND_ROOT")}
    env["PATH"] = os.pathsep.join(d for d in env.get("PATH", "").split(os.pathsep)
                                  if d and not (Path(d) / "maind").exists())
    patcher = mock.patch.dict(os.environ, env, clear=True)
    patcher.start()
    testcase.addCleanup(patcher.stop)
