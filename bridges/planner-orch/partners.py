"""Find the partners and the foundation of the planner-orch bridge.

The bridge reaches the planner and orch only as processes (``plan.py``, ``orch.py``), found by an explicit
environment variable, its own hub, or a command on PATH. The planner engine library and
the foundation (aicore) are located the same way and put on ``sys.path`` before they are imported.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


TIMEOUT_RETURNCODE = 124   # the exit status of coreutils `timeout`


def run_bounded(argv, *, timeout, **kwargs):
    """``subprocess.run`` with a mandatory ``timeout``; a child that hangs is killed and reported as exit status 124
    (stderr says so) instead of raising ``TimeoutExpired``, so the callers' return-code handling covers it."""
    try:
        return subprocess.run(argv, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired as expired:
        def text(value):
            return value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")
        note = f"timed out after {timeout}s: {argv[0] if argv else ''}"
        return subprocess.CompletedProcess(argv, TIMEOUT_RETURNCODE, text(expired.stdout),
                                           (text(expired.stderr) + "\n" + note).strip())

BRIDGE = Path(__file__).resolve().parent
UNAVAILABLE = "BRIDGE_PARTNER_UNAVAILABLE: {name} not found (set {var})"
AICORE_NOT_FOUND = "AICORE_NOT_FOUND: aicore library not found (set AICORE_ROOT)"


def _unavailable(name: str, var: str) -> SystemExit:
    print(UNAVAILABLE.format(name=name, var=var), file=sys.stderr)
    return SystemExit(3)


def _command_root(command: str, marker: str) -> Path | None:
    """Package root of the ``command`` found on PATH (``<root>/bin/<command>``), when it holds ``marker``."""
    found = shutil.which(command)
    if not found:
        return None
    candidate = Path(os.path.realpath(found)).parent.parent
    return candidate if (candidate / marker).is_file() else None


def _hub_partner(name: str, marker: str) -> Path | None:
    """Use a partner from this bridge's hub only when its unit identifies it."""
    root = BRIDGE.parent.parent / "packages" / name
    try:
        unit = json.loads((root / "unit.json").read_text(encoding="utf-8"))
        return root.resolve() if unit.get("id") == name and (root / marker).is_file() else None
    except (OSError, ValueError, AttributeError):
        return None


# ------------------------------------------------------------------------------------------------ planner

def planner_root() -> Path | None:
    """Explicit roots, this bridge's hub, then the root behind a ``planner`` command on PATH."""
    env = os.environ.get("PLANNER_ROOT")
    if env:
        root = Path(env)
        return root.resolve() if (root / "scripts" / "plan.py").is_file() else None
    script = os.environ.get("PLANNER_PLAN_PY")
    if script:
        root = Path(script).resolve().parent.parent
        return root if (root / "scripts" / "plan.py").is_file() else None
    return _hub_partner("planner", "scripts/plan.py") or _command_root("planner", "scripts/plan.py")


def plan_argv() -> list[str] | None:
    """Command line of ``plan.py`` from an explicit path, this hub, or PATH, in that order."""
    script = os.environ.get("PLANNER_PLAN_PY")
    if script:
        return [sys.executable, script] if Path(script).is_file() else None
    root = os.environ.get("PLANNER_ROOT")
    if root:
        plan = Path(root) / "scripts" / "plan.py"
        return [sys.executable, str(plan)] if plan.is_file() else None
    local = _hub_partner("planner", "scripts/plan.py")
    if local:
        return [sys.executable, str(local / "scripts/plan.py")]
    command = shutil.which("planner")
    return [command] if command else None


def require_plan_argv() -> list[str]:
    argv = plan_argv()
    if argv is None:
        raise _unavailable("planner", "PLANNER_PLAN_PY or PLANNER_ROOT")
    return argv


def require_planner_root() -> Path:
    root = planner_root()
    if root is None:
        raise _unavailable("planner", "PLANNER_ROOT")
    return root


def planner_engine(*modules: str):
    """Import planner engine modules (``plan.context`` ...) from the located planner library; a runtime dependency
    declared by ``requires`` of this bridge, resolved by name so that no neighbour path is ever read."""
    lib = str(require_planner_root() / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    loaded = [importlib.import_module(f"planner.{name}") for name in modules]
    return loaded[0] if len(loaded) == 1 else loaded


# ---------------------------------------------------------------------------------------------------- orch

def _is_orch_root(path: Path) -> bool:
    return (path / "scripts" / "orch.py").is_file()


def find_orch_root() -> Path | None:
    """``SKM_ORCH_ROOT``, this bridge's hub, then an ``orch`` command on PATH."""
    env = os.environ.get("SKM_ORCH_ROOT")
    if env:
        return Path(env).resolve() if _is_orch_root(Path(env)) else None
    return _hub_partner("orch", "scripts/orch.py") or _command_root("orch", "scripts/orch.py")


def require_orch() -> Path:
    root = find_orch_root()
    if root is None:
        raise _unavailable("orch", "SKM_ORCH_ROOT")
    return root


def orch_validate(kind: str, path: str | Path) -> tuple[int, str]:
    """Exit code and stdout of ``orch.py validate <kind> <path>``."""
    root = require_orch()
    done = run_bounded([sys.executable, str(root / "scripts" / "orch.py"), "validate", kind, str(path)],
                       timeout=60, capture_output=True, text=True, encoding="utf-8", check=False)
    return done.returncode, done.stdout


# --------------------------------------------------------------------------------------------------- aicore

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
