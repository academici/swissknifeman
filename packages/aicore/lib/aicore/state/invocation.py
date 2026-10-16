"""The invocation context of a project-bound command and the checks of the project-local launcher.

A project runs swissknifeman through ``<project>/.swissknifeman/launcher.py``: the launcher derives the project root from
its own location, puts it into the ``SKM_LAUNCHER_*`` variables and replaces itself with the installed ``swissknifeman``
(the process id stays the same). The umbrella calls :func:`validate_launcher_env` before it routes anything; the modules
read the checked root through :func:`read_invocation_context` (or :func:`aicore.state.resolve_project`, which honours the
launcher first). :func:`require_project_path` keeps a write inside the project after symlinks are resolved.
stdlib only.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from .locations import (ENV_INVOCATION_CWD, ENV_LAUNCHER_ACTIVE, ENV_LAUNCHER_PATH, ENV_LAUNCHER_PID,
                        ENV_LAUNCHER_PROTOCOL, ENV_LAUNCHER_ROOT, ENV_PROJECT_ROOT, LAUNCHER_ENV, LAUNCHER_NAME,
                        PROJECT_DIRNAME, PathLike, ProjectContextRequired, launcher_root, resolve_project, same_path)

# The launcher protocol changes only with the environment contract, its checks or the managed file set; a hub release
# that keeps them keeps the protocol, so a project never needs a sync for an ordinary fix.
LAUNCHER_PROTOCOL = 1
MIN_LAUNCHER_PROTOCOL = 1
LOCK_NAME = "launcher.lock.json"
LOCK_SCHEMA = "urn:swissknifeman:aicore:project-launcher-lock:v1"
CONTEXT_SCHEMA = "urn:swissknifeman:aicore:invocation-context:v1"
ENV_STRICT = "SKM_LAUNCHER_STRICT"


class LauncherError(ValueError):
    """A refused launcher context: a stable ``code``, a message and machine-readable ``details``."""

    def __init__(self, code: str, message: str, details: Optional[Mapping[str, Any]] = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def envelope(self) -> Dict[str, Any]:
        """The JSON error envelope of the command line: ``{"ok": false, "error": {code, message, details}}``."""
        return {"ok": False, "error": {"code": self.code, "message": self.message, "details": self.details}}


class ProjectWriteError(LauncherError):
    """``PROJECT_WRITE_OUTSIDE_ROOT`` or ``PROJECT_WRITE_SYMLINK_ESCAPE``: a write target lies outside the project."""


@dataclass(frozen=True)
class InvocationContext:
    """Where a command runs: the project (the write, config and state boundary) and the folder it was called from (for
    relative arguments and diagnostics) are separate values. ``resolution`` is ``launcher``, ``flag``, ``environment``,
    ``git``, ``marker`` or ``none``."""

    project_root: Optional[Path]
    invocation_cwd: Path
    resolution: str
    marker: Optional[str] = None
    launcher_path: Optional[Path] = None
    launcher_protocol: Optional[int] = None

    def to_json(self) -> Dict[str, Any]:
        root = self.project_root
        return {
            "$schema": CONTEXT_SCHEMA,
            "project_root": str(root) if root else None,
            "invocation_cwd": str(self.invocation_cwd),
            "resolution": self.resolution,
            "marker": self.marker,
            "launcher": {"path": str(self.launcher_path), "protocol": self.launcher_protocol}
            if self.launcher_path else None,
            "config": str(root / PROJECT_DIRNAME / "config.toml") if root else None,
            "plans_root": str(root / "plans") if root else None,
        }


def launcher_file(root: PathLike) -> Path:
    return Path(root) / PROJECT_DIRNAME / LAUNCHER_NAME


def lock_file(root: PathLike) -> Path:
    return Path(root) / PROJECT_DIRNAME / LOCK_NAME


def _protocol(value: Any, label: str) -> int:
    text = str(value).strip()
    if not text.isdigit():
        raise LauncherError("LAUNCHER_PROTOCOL_INVALID", f"{label} must be a positive integer, got {value!r}")
    number = int(text)
    if number < MIN_LAUNCHER_PROTOCOL:
        raise LauncherError("LAUNCHER_PROTOCOL_TOO_OLD",
                            f"{label} {number} is older than the oldest supported {MIN_LAUNCHER_PROTOCOL}; run "
                            f"`swissknifeman project sync` in the project", {"protocol": number})
    if number > LAUNCHER_PROTOCOL:
        raise LauncherError("LAUNCHER_PROTOCOL_NEWER",
                            f"{label} {number} is newer than this hub ({LAUNCHER_PROTOCOL}); update swissknifeman",
                            {"protocol": number})
    return number


def read_lock(root: PathLike) -> Optional[Dict[str, Any]]:
    """The launcher lock of a project, ``None`` without one; ``LAUNCHER_LOCK_INVALID`` when it is unreadable."""
    path = lock_file(root)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise LauncherError("LAUNCHER_LOCK_INVALID", f"{path}: {exc.__class__.__name__}") from exc
    if not isinstance(doc, dict) or doc.get("$schema") != LOCK_SCHEMA:
        raise LauncherError("LAUNCHER_LOCK_INVALID", f"{path}: not a {LOCK_SCHEMA} document")
    return doc


def validate_launcher_env(env: Mapping[str, str], *, pid: Optional[int] = None) -> Tuple[Optional[InvocationContext],
                                                                                         Dict[str, str], list]:
    """Check the launcher context of this process before anything is routed: ``(context, environment, warnings)``.

    Without ``SKM_LAUNCHER_ACTIVE=1`` the context is ``None`` and the environment is returned as is. Variables inherited
    from another process (``SKM_LAUNCHER_PID`` differs) carry no authority: they are dropped and the context is ``None``.
    Otherwise every value is checked (protocol, root, launcher file, cwd, a second root source, the lock) and the
    environment comes back with canonical values; any failure raises :class:`LauncherError` before a module runs.
    """
    result = dict(env)
    warnings: list = []
    if result.get(ENV_LAUNCHER_ACTIVE) != "1":
        return None, result, warnings
    if result.get(ENV_LAUNCHER_PID) != str(os.getpid() if pid is None else pid):
        for name in LAUNCHER_ENV:
            result.pop(name, None)
        return None, result, warnings
    protocol = _protocol(result.get(ENV_LAUNCHER_PROTOCOL, ""), ENV_LAUNCHER_PROTOCOL)
    raw_root = result.get(ENV_LAUNCHER_ROOT, "")
    if not raw_root or not os.path.isabs(raw_root) or not os.path.isdir(raw_root):
        raise LauncherError("PROJECT_PATH_INVALID", f"{ENV_LAUNCHER_ROOT} {raw_root!r} is not an existing absolute folder")
    root = Path(os.path.realpath(raw_root))
    expected = launcher_file(root)
    raw_path = result.get(ENV_LAUNCHER_PATH, "")
    try:
        mode = os.lstat(raw_path).st_mode if raw_path else None
    except OSError:
        mode = None
    if mode is None:
        raise LauncherError("LAUNCHER_LOCATION_INVALID", f"{ENV_LAUNCHER_PATH} {raw_path!r} does not exist",
                            {"expected": str(expected)})
    if stat.S_ISLNK(mode):
        raise LauncherError("LAUNCHER_SYMLINK_FORBIDDEN", f"{raw_path} is a symlink")
    if not stat.S_ISREG(mode):
        raise LauncherError("LAUNCHER_NOT_REGULAR", f"{raw_path} is not a regular file")
    if os.path.realpath(raw_path) != str(expected) or raw_path != str(expected):
        raise LauncherError("LAUNCHER_LOCATION_INVALID", f"{raw_path} is not {expected}",
                            {"launcher": raw_path, "expected": str(expected)})
    other = result.get(ENV_PROJECT_ROOT, "")
    if other and not same_path(other, root):
        raise LauncherError("PROJECT_CONTEXT_CONFLICT", f"launcher project is {root}, but {ENV_PROJECT_ROOT} names {other}",
                            {"launcher_root": str(root), "environment_root": other})
    cwd = result.get(ENV_INVOCATION_CWD, "")
    if not cwd or not os.path.isabs(cwd) or not os.path.isdir(cwd):
        raise LauncherError("PROJECT_PATH_INVALID", f"{ENV_INVOCATION_CWD} {cwd!r} is not an existing absolute folder")
    lock = read_lock(root)
    if lock is None:
        if result.get(ENV_STRICT) == "1":
            raise LauncherError("LAUNCHER_LOCK_MISSING", f"{lock_file(root)} is missing; run `swissknifeman project sync`")
        warnings.append(f"LAUNCHER_LOCK_MISSING: {lock_file(root)} is missing; run `swissknifeman project sync`")
    else:
        locked = _protocol(lock.get("protocol", ""), f"{LOCK_NAME} protocol")
        if locked != protocol:
            raise LauncherError("LAUNCHER_LOCK_INVALID", f"the launcher speaks protocol {protocol}, its lock records "
                                f"{locked}; run `swissknifeman project sync`", {"launcher": protocol, "lock": locked})
    if protocol < LAUNCHER_PROTOCOL:
        warnings.append(f"LAUNCHER_UPDATE_AVAILABLE: launcher protocol {protocol}, hub {LAUNCHER_PROTOCOL}; run "
                        f"`swissknifeman project sync`")
    result.update({ENV_LAUNCHER_ROOT: str(root), ENV_LAUNCHER_PATH: str(expected),
                   ENV_INVOCATION_CWD: os.path.realpath(cwd), ENV_LAUNCHER_PROTOCOL: str(protocol)})
    result.pop(ENV_PROJECT_ROOT, None)
    context = InvocationContext(root, Path(result[ENV_INVOCATION_CWD]), "launcher", None, expected, protocol)
    return context, result, warnings


def read_invocation_context(start: Optional[PathLike] = None, *, explicit: Optional[PathLike] = None,
                            env: Optional[Mapping[str, str]] = None) -> InvocationContext:
    """The invocation context of this process: the launcher-bound project (checked by the umbrella), else the legacy
    resolution of :func:`resolve_project` from ``start`` (default: the working directory). A ``--project`` that differs
    from the launcher root raises ``PROJECT_CONTEXT_CONFLICT``."""
    environment = os.environ if env is None else env
    cwd = Path(start) if start is not None else Path.cwd()
    bound = launcher_root(environment)
    context = resolve_project(cwd, explicit=explicit, env=environment)
    if context is None:
        return InvocationContext(None, cwd, "none")
    if bound is not None:
        raw = environment.get(ENV_LAUNCHER_PROTOCOL, "")
        return InvocationContext(context.root, Path(environment.get(ENV_INVOCATION_CWD) or cwd), "launcher", None,
                                 launcher_file(context.root), int(raw) if raw.isdigit() else None)
    return InvocationContext(context.root, cwd, context.resolution, context.marker)


def require_project_path(root: PathLike, candidate: PathLike) -> Path:
    """``candidate`` resolved (symlinks of existing parts followed, ``..`` removed) when it stays inside the project root;
    else ``PROJECT_WRITE_SYMLINK_ESCAPE`` (a symlink inside the project leads out) or ``PROJECT_WRITE_OUTSIDE_ROOT``. A
    relative candidate is taken from the root. Check the final target of a write, not a string prefix."""
    try:
        base = Path(root).resolve(strict=True)
    except OSError as exc:
        raise ProjectContextRequired(root, f"project root {root} is not usable: {exc.__class__.__name__}") from exc
    path = Path(candidate)
    if not path.is_absolute():
        path = Path(root) / path
    target = path.resolve(strict=False)
    try:
        target.relative_to(base)
        return target
    except ValueError:
        pass
    # Lexically inside but resolved outside: a symlink in the project leads out.
    inside = Path(os.path.normpath(str(path))).is_relative_to(Path(os.path.normpath(str(Path(root).absolute()))))
    code = "PROJECT_WRITE_SYMLINK_ESCAPE" if inside else "PROJECT_WRITE_OUTSIDE_ROOT"
    raise ProjectWriteError(code, f"{candidate} resolves to {target}, outside the project {base}",
                            {"target": str(target), "root": str(base)})
