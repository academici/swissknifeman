"""Find the partners and the foundation of the workspace-planner bridge.

The bridge reaches the planner engine library and the foundation (aicore) by an explicit environment variable or a
command on PATH and puts them on ``sys.path`` before they are imported; it never looks at a neighbouring folder. The
workspace module is found the same way (``SKM_WORKSPACE_MODULE_ROOT``, then the ``swissknifeman`` command): the bridge
needs its location only to tell the caller where the port is filled, it never imports it.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Optional

BRIDGE = Path(__file__).resolve().parent
UNAVAILABLE = "BRIDGE_PARTNER_UNAVAILABLE: {name} not found (set {var})"
AICORE_NOT_FOUND = "AICORE_NOT_FOUND: aicore library not found (set AICORE_ROOT)"


def _unavailable(name: str, var: str) -> SystemExit:
    print(UNAVAILABLE.format(name=name, var=var), file=sys.stderr)
    return SystemExit(3)


def _command_root(command: str, marker: str) -> Optional[Path]:
    """Package root of the ``command`` found on PATH (``<root>/bin/<command>``), when it holds ``marker``."""
    found = shutil.which(command)
    if not found:
        return None
    candidate = Path(os.path.realpath(found)).parent.parent
    return candidate if (candidate / marker).is_file() else None


# ------------------------------------------------------------------------------------------------ planner

def planner_root() -> Optional[Path]:
    """``PLANNER_ROOT``, the root of ``PLANNER_PLAN_PY``, then the root behind a ``planner`` command on PATH."""
    env = os.environ.get("PLANNER_ROOT")
    if env:
        root = Path(env)
        return root.resolve() if (root / "scripts" / "plan.py").is_file() else None
    script = os.environ.get("PLANNER_PLAN_PY")
    if script:
        root = Path(script).resolve().parent.parent
        return root if (root / "scripts" / "plan.py").is_file() else None
    return _command_root("planner", "scripts/plan.py")


def require_planner_root() -> Path:
    root = planner_root()
    if root is None:
        raise _unavailable("planner", "PLANNER_ROOT")
    return root


def planner_engine(*modules: str):
    """Import planner engine modules (``plan.store`` ...) from the located planner library; a runtime dependency
    declared by ``requires`` of this bridge, resolved by name so that no neighbour path is ever read."""
    lib = str(require_planner_root() / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    loaded = [importlib.import_module(f"planner.{name}") for name in modules]
    return loaded[0] if len(loaded) == 1 else loaded


# ------------------------------------------------------------------------------------------------ workspace

def workspace_module_root() -> Optional[Path]:
    """``SKM_WORKSPACE_MODULE_ROOT``, then the root behind a ``swissknifeman`` command on PATH (the hub that holds the
    workspace module). The folder must hold the module's ``unit.json``."""
    env = os.environ.get("SKM_WORKSPACE_MODULE_ROOT")
    if env:
        root = Path(env)
        return root.resolve() if (root / "unit.json").is_file() else None
    found = shutil.which("swissknifeman")
    if not found:
        return None
    candidate = Path(os.path.realpath(found)).parent.parent / "packages" / "workspace"
    return candidate if (candidate / "unit.json").is_file() else None


def require_workspace_module_root() -> Path:
    root = workspace_module_root()
    if root is None:
        raise _unavailable("workspace", "SKM_WORKSPACE_MODULE_ROOT")
    return root


# --------------------------------------------------------------------------------------------------- aicore

def _is_aicore(path: Path) -> bool:
    try:
        return json.loads((path / "unit.json").read_text(encoding="utf-8")).get("id") == "aicore"
    except (OSError, ValueError, AttributeError):
        return False


def aicore_lib() -> Optional[Path]:
    """``AICORE_ROOT/lib``, ``<bridge>/_vendor/aicore/lib``, then the foundation of the hub that holds this bridge."""
    env = os.environ.get("AICORE_ROOT")
    if env:
        lib = Path(env) / "lib"
        return lib if (lib / "aicore").is_dir() else None
    vendored = BRIDGE / "_vendor" / "aicore"
    if (vendored / "lib" / "aicore").is_dir():
        return vendored / "lib"
    hub = BRIDGE.parent.parent
    foundation = hub / "packages" / "aicore"
    return foundation / "lib" if _is_aicore(foundation) and (foundation / "lib" / "aicore").is_dir() else None


def use_aicore() -> None:
    """Put the foundation library on ``sys.path`` before ``import aicore``; exit 2 when it cannot be found."""
    lib = aicore_lib()
    if lib is None:
        print(AICORE_NOT_FOUND, file=sys.stderr)
        raise SystemExit(2)
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
