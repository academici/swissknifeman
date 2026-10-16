"""Find the partners and the foundation of the orch-skiller bridge.

The bridge reaches skiller only as a process (``bin/skiller``) and reads the data of orch (role manifests, capability
seeds) from the orch root. Both are found by an explicit environment variable or a command on PATH; the bridge never
looks at a neighbouring folder.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

BRIDGE = Path(__file__).resolve().parent
AICORE_NOT_FOUND = "AICORE_NOT_FOUND: aicore library not found (set AICORE_ROOT)"
SKILLER_UNAVAILABLE = "BRIDGE_PARTNER_UNAVAILABLE: skiller not found (set SKM_SKILLER_ROOT)"
ORCH_UNAVAILABLE = "BRIDGE_PARTNER_UNAVAILABLE: orch not found (set SKM_ORCH_ROOT)"


def _launcher(path: Path) -> Path | None:
    launcher = path / "bin" / "skiller"
    return launcher if launcher.is_file() else None


def find_skiller() -> Path | None:
    """``SKM_SKILLER_ROOT``, then a ``skiller`` command on PATH."""
    env = os.environ.get("SKM_SKILLER_ROOT")
    if env:
        return _launcher(Path(env).resolve())
    command = shutil.which("skiller")
    return Path(os.path.realpath(command)) if command else None


def require_skiller() -> Path:
    launcher = find_skiller()
    if launcher is None:
        print(SKILLER_UNAVAILABLE, file=sys.stderr)
        raise SystemExit(3)
    return launcher


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


def require_orch_root() -> Path:
    root = find_orch_root()
    if root is None:
        print(ORCH_UNAVAILABLE, file=sys.stderr)
        raise SystemExit(3)
    return root


def _is_aicore(path: Path) -> bool:
    try:
        return json.loads((path / "unit.json").read_text(encoding="utf-8")).get("id") == "aicore"
    except (OSError, ValueError, AttributeError):
        return False


def aicore_lib() -> Path | None:
    """``AICORE_ROOT/lib``, ``<bridge>/_vendor/aicore/lib``, then the foundation of the hub that holds this bridge."""
    env = os.environ.get("AICORE_ROOT")
    if env:
        lib = Path(env) / "lib"
        return lib if (lib / "aicore").is_dir() else None
    vendored = BRIDGE / "_vendor" / "aicore"
    if (vendored / "lib" / "aicore").is_dir():
        return vendored / "lib"
    foundation = BRIDGE.parent.parent / "packages" / "aicore"
    return foundation / "lib" if _is_aicore(foundation) and (foundation / "lib" / "aicore").is_dir() else None


def use_aicore() -> None:
    """Put the foundation library on ``sys.path`` before ``import aicore``; exit 2 when it cannot be found."""
    lib = aicore_lib()
    if lib is None:
        print(AICORE_NOT_FOUND, file=sys.stderr)
        raise SystemExit(2)
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
