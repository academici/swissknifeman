"""Find the Skiller partner. The bridge never imports it; it calls ``bin/skiller`` as a process."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys

ORCH_ROOT = Path(__file__).resolve().parents[2]
UNAVAILABLE = "BRIDGE_PARTNER_UNAVAILABLE: skiller not found (set SKM_SKILLER_ROOT)"


def _launcher(path: Path) -> Path | None:
    launcher = path / "bin" / "skiller"
    return launcher if launcher.is_file() else None


def find_skiller() -> Path | None:
    """``SKM_SKILLER_ROOT``, then a ``skiller`` command on PATH, then the monorepo sibling ``<orch root>/../skiller``."""
    env = os.environ.get("SKM_SKILLER_ROOT")
    if env:
        return _launcher(Path(env).resolve())
    command = shutil.which("skiller")
    if command:
        return Path(os.path.realpath(command))
    return _launcher((ORCH_ROOT.parent / "skiller").resolve())


def require_skiller() -> Path:
    launcher = find_skiller()
    if launcher is None:
        print(UNAVAILABLE, file=sys.stderr)
        raise SystemExit(3)
    return launcher
