"""Find and run another module's public command as a child process. stdlib-only.

A module never imports a partner or guesses its folder: it asks for the partner's command line
here and reads the JSON the partner prints. Lookup order for ``name`` (``NAME`` is ``name`` upper-cased,
``-`` replaced by ``_``):

1. every variable in ``legacy_env`` (deprecated consumer-specific names), warned once per process;
2. ``SKM_<NAME>_BIN`` (an executable file);
3. ``SKM_<NAME>_ROOT/bin/<name>`` (an executable file);
4. ``name`` on ``PATH``.

``planner`` is the one exception: ``PLANNER_PLAN_PY``, ``PLANNER_ROOT/scripts/plan.py``, the
deprecated ``SKM_TASK_ROOT/scripts/plan.py`` and then ``planner`` on ``PATH``.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

_WARNED: set = set()


class PartnerError(RuntimeError):
    """A partner command failed or printed something that is not JSON."""


class PartnerUnavailable(RuntimeError):
    """No partner command line could be found."""


def _warn_once(var: str, hint: str) -> None:
    if var in _WARNED:
        return
    _WARNED.add(var)
    print(f"{var}_DEPRECATED: {var} is deprecated; {hint}", file=sys.stderr)


def _executable(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    path = Path(os.path.expanduser(value))
    if path.is_file() and os.access(path, os.X_OK):
        return str(path)
    return None


def _file(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    path = Path(os.path.expanduser(value))
    return str(path) if path.is_file() else None


def _planner_command(env: Mapping[str, str]) -> Optional[list]:
    plan_py = _file(env.get("PLANNER_PLAN_PY"))
    if plan_py:
        return [sys.executable, plan_py]
    if env.get("PLANNER_ROOT"):
        found = _file(str(Path(os.path.expanduser(env["PLANNER_ROOT"])) / "scripts" / "plan.py"))
        if found:
            return [sys.executable, found]
    if env.get("SKM_TASK_ROOT"):
        found = _file(str(Path(os.path.expanduser(env["SKM_TASK_ROOT"])) / "scripts" / "plan.py"))
        if found:
            _warn_once("SKM_TASK_ROOT", "set PLANNER_ROOT")
            return [sys.executable, found]
    # `install.sh` links the planner as `plan.py`; a `planner` launcher is the other accepted form.
    which = (shutil.which("planner", path=env.get("PATH", ""))
             or shutil.which("plan.py", path=env.get("PATH", "")))
    return [which] if which else None


def partner_command(name: str, *, env: Optional[Mapping[str, str]] = None,
                    legacy_env: Sequence[str] = ()) -> Optional[list]:
    """Return the argv prefix that runs ``name``, or ``None`` when it cannot be found."""
    env = os.environ if env is None else env
    key = name.upper().replace("-", "_")
    for var in legacy_env:
        found = _executable(env.get(var))
        if found:
            _warn_once(var, f"set SKM_{key}_BIN")
            return [found]
    if name == "planner":
        return _planner_command(env)
    found = _executable(env.get(f"SKM_{key}_BIN"))
    if found:
        return [found]
    root = env.get(f"SKM_{key}_ROOT")
    if root:
        found = _executable(str(Path(os.path.expanduser(root)) / "bin" / name))
        if found:
            return [found]
    which = shutil.which(name, path=env.get("PATH", ""))
    return [which] if which else None


def require_partner(name: str, **kw: Any) -> list:
    """Like :func:`partner_command`, raising :class:`PartnerUnavailable` when not found."""
    argv = partner_command(name, **kw)
    if argv is None:
        key = name.upper().replace("-", "_")
        raise PartnerUnavailable(
            f"PARTNER_UNAVAILABLE: {name} not found (set SKM_{key}_ROOT or put {name} on PATH)")
    return argv


def run_partner_json(name: str, args: Sequence[str], *, env: Optional[Mapping[str, str]] = None,
                     legacy_env: Sequence[str] = (), timeout: float = 120,
                     input: Optional[str] = None) -> Any:
    """Run ``name`` with ``args`` and return its decoded JSON stdout."""
    argv = require_partner(name, env=env, legacy_env=legacy_env)
    verb = args[0] if args else ""
    try:
        proc = subprocess.run(argv + list(args), capture_output=True, text=True,
                              timeout=timeout, env=None if env is None else dict(env), input=input)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PartnerError(f"PARTNER_FAILED: {name} {verb} could not run: {exc}") from exc
    if proc.returncode != 0:
        lines = (proc.stderr or "").strip().splitlines()
        raise PartnerError(
            f"PARTNER_FAILED: {name} {verb} exited {proc.returncode}: {lines[-1] if lines else ''}")
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise PartnerError(f"PARTNER_BAD_OUTPUT: {name} {verb} printed invalid JSON: {exc}") from exc
