"""Find the orch partner. The bridge never imports orch; it calls ``scripts/orch.py`` as a process."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

TASK_ROOT = Path(__file__).resolve().parents[2]
UNAVAILABLE = "BRIDGE_PARTNER_UNAVAILABLE: orch not found (set SKM_ORCH_ROOT)"


def _is_root(path: Path) -> bool:
    return (path / "scripts" / "orch.py").is_file()


def find_orch_root() -> Path | None:
    """``SKM_ORCH_ROOT``, then an ``orch`` command on PATH, then the monorepo sibling ``<Task root>/../orch``."""
    env = os.environ.get("SKM_ORCH_ROOT")
    if env:
        return Path(env).resolve() if _is_root(Path(env)) else None
    command = shutil.which("orch")
    if command:
        candidate = Path(os.path.realpath(command)).parent.parent
        if _is_root(candidate):
            return candidate
    sibling = TASK_ROOT.parent / "orch"
    return sibling.resolve() if _is_root(sibling) else None


def require_orch() -> Path:
    root = find_orch_root()
    if root is None:
        print(UNAVAILABLE, file=sys.stderr)
        raise SystemExit(3)
    return root


def orch_validate(kind: str, path: str | Path) -> tuple[int, str]:
    """Exit code and stdout of ``orch.py validate <kind> <path>``."""
    root = require_orch()
    done = subprocess.run([sys.executable, str(root / "scripts" / "orch.py"), "validate", kind, str(path)],
                          capture_output=True, text=True, encoding="utf-8", check=False)
    return done.returncode, done.stdout
