"""Find the partners of the orch-harness bridge: the orch role manifests and the harness agent-pack role catalog.

Both are found by an explicit environment variable (``SKM_ORCH_ROOT``, ``SKM_HARNESS_ROOT``); the orch root may also
come from an ``orch`` command on PATH. The bridge never looks at a neighbouring folder.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil

CATALOG = Path("configs") / "common" / "agent-packs" / "roles.json"


def find_orch_root() -> Path | None:
    """``SKM_ORCH_ROOT``, then the root behind an ``orch`` command on PATH (a folder with ``scripts/orch.py``)."""
    env = os.environ.get("SKM_ORCH_ROOT")
    if env:
        root = Path(env).resolve()
        return root if (root / "scripts" / "orch.py").is_file() else None
    command = shutil.which("orch")
    if command:
        root = Path(os.path.realpath(command)).parent.parent
        return root if (root / "scripts" / "orch.py").is_file() else None
    return None


def agent_pack_roles() -> Path | None:
    """The harness role catalog under ``SKM_HARNESS_ROOT``; None when the variable is unset or the file is absent."""
    env = os.environ.get("SKM_HARNESS_ROOT")
    path = Path(env) / CATALOG if env else None
    return path if path is not None and path.is_file() else None
