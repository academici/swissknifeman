"""The shell-profile snippet that exports the SKM environment variables, and its checks (stdlib only).

``SKM_HOME``, ``SKM_WORKSPACES`` and ``SKM_WORKSPACE`` (the table is :mod:`aicore.state.envtable`) are exported by a block
between two marker lines in the profile of the user's shell (``~/.bashrc`` for bash, ``~/.zshrc`` for zsh). The block is
the only thing this module writes: :func:`install` adds it or brings it up to date in place, :func:`uninstall` removes
it (and the blank line it added), both are idempotent, and nothing outside the markers is touched. A value already set in
the environment of the shell wins over the snippet (``SKM_WORKSPACE=other claude`` still works), so the snippet is a
default, not an override.

``SKM_HOME`` is exported only when that does not change how the machine is read: a set ``SKM_HOME`` is the home of a
sandbox and switches the lookup of the old XDG folders off, so a machine that still uses an old folder (``Locations.legacy``)
keeps it unexported until ``aicore config migrate-home`` moved the folders.
"""
from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from . import envtable
from .locations import (WorkspaceSelectionError, is_code, list_workspaces, machine_home, machine_locations,
                        selected_workspace, workspaces_root)

BEGIN = "# >>> swissknifeman environment (managed by swissknifeman: do not edit between the markers) >>>"
END = "# <<< swissknifeman environment <<<"
_BEGIN_PREFIX = "# >>> swissknifeman environment"
_END_PREFIX = "# <<< swissknifeman environment"
RESULT_SCHEMA = "urn:swissknifeman:aicore:check-result:v1"

# the shell (base name of $SHELL) -> the profile file below the user's home directory that every interactive shell reads
PROFILES = {"bash": ".bashrc", "zsh": ".zshrc"}

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]


class ShellEnvError(ValueError):
    """The snippet cannot be written or removed; ``code`` names why."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _environment(env: Env) -> Mapping[str, str]:
    return os.environ if env is None else env


def planned_values(env: Env = None, home: Optional[PathLike] = None) -> Tuple[Dict[str, str], List[str]]:
    """``(values, notes)``: what the snippet exports on this machine, by variable name, and why a variable is left out.

    ``SKM_HOME`` is the machine home, ``SKM_WORKSPACES`` the workspaces folder and ``SKM_WORKSPACE`` the workspace this
    shell works with (the one already named by the environment, else the only workspace of the machine)."""
    environment = _environment(env)
    values: Dict[str, str] = {}
    notes: List[str] = []
    try:
        base = machine_home(environment, home)
        where = machine_locations(environment, home)
        root = workspaces_root(environment, home)
    except ValueError as exc:
        raise ShellEnvError("SKM_ENV_INVALID", str(exc)) from None
    if where.legacy and not environment.get(envtable.ENV_HOME):
        notes.append(f"{envtable.ENV_HOME} is not exported: {', '.join(where.legacy)} still live in the old XDG folders and "
                     f"a set {envtable.ENV_HOME} would stop reading them; run `swissknifeman config migrate-home` first")
    else:
        values[envtable.ENV_HOME] = str(base)
    values[envtable.ENV_WORKSPACES] = str(root)
    try:
        values[envtable.ENV_WORKSPACE] = selected_workspace(environment, home)
    except WorkspaceSelectionError as exc:
        notes.append(f"{envtable.ENV_WORKSPACE} is not exported: {exc.message}")
    except ValueError as exc:
        raise ShellEnvError("SKM_ENV_INVALID", str(exc)) from None
    return values, notes


def profile_path(env: Env = None, home: Optional[PathLike] = None, explicit: Optional[PathLike] = None) -> Optional[Path]:
    """The profile file for the shell in ``$SHELL`` (``None`` for a shell this module does not support, such as fish)."""
    if explicit is not None:
        return Path(explicit)
    environment = _environment(env)
    shell = os.path.basename(environment.get("SHELL", "") or "bash")
    name = PROFILES.get(shell)
    if name is None:
        return None
    user = Path(home) if home is not None else Path(environment["HOME"]) if environment.get("HOME") else Path.home()
    return user / name


def render_block(values: Mapping[str, str]) -> str:
    """The managed block (ends with a newline). A variable already set in the shell keeps its value; both bash and zsh run it."""
    lines = [BEGIN]
    for name in envtable.NAMES:
        if name in values:
            lines.append(f"[ -n \"${{{name}-}}\" ] || {name}={shlex.quote(values[name])}")
            lines.append(f"export {name}")
    lines.append(END)
    return "\n".join(lines) + "\n"


def _blocks(lines: List[str]) -> List[Tuple[int, int]]:
    """Index ranges ``(begin, end)`` of the managed blocks; a begin without an end (or the reverse) is ``SHELL_PROFILE_BLOCK_BROKEN``."""
    found: List[Tuple[int, int]] = []
    start: Optional[int] = None
    for index, line in enumerate(lines):
        if line.startswith(_BEGIN_PREFIX):
            if start is not None:
                raise ShellEnvError("SHELL_PROFILE_BLOCK_BROKEN", f"two begin markers without an end (line {index + 1})")
            start = index
        elif line.startswith(_END_PREFIX):
            if start is None:
                raise ShellEnvError("SHELL_PROFILE_BLOCK_BROKEN", f"end marker without a begin (line {index + 1})")
            found.append((start, index))
            start = None
    if start is not None:
        raise ShellEnvError("SHELL_PROFILE_BLOCK_BROKEN", f"begin marker without an end (line {start + 1})")
    return found


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError) as exc:
        raise ShellEnvError("SHELL_PROFILE_UNREADABLE", f"{path}: {exc}") from None


def _target(path: Path) -> Path:
    """The file to write: a profile that is a symbolic link (a dotfiles manager) is written through, not replaced."""
    return Path(os.path.realpath(path))


def _write(path: Path, text: str) -> None:
    from aicore.util.io import atomic_write_text
    target = _target(path)
    mode = None
    try:
        mode = target.stat().st_mode & 0o777
    except OSError:
        pass
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, text, mode=mode)
    except OSError as exc:
        raise ShellEnvError("SHELL_PROFILE_UNWRITABLE", f"{path}: {exc}") from None


def block_values(text: str) -> Optional[Dict[str, str]]:
    """The variables the block of ``text`` exports (``None`` without a block)."""
    lines = text.splitlines()
    ranges = _blocks(lines)
    if not ranges:
        return None
    start, end = ranges[0]
    found: Dict[str, str] = {}
    for line in lines[start + 1:end]:
        for name in envtable.NAMES:
            prefix = f"[ -n \"${{{name}-}}\" ] || {name}="
            if line.startswith(prefix):
                try:
                    parts = shlex.split(line[len(prefix):])
                except ValueError:
                    parts = []
                if len(parts) == 1:
                    found[name] = parts[0]
    return found


def install(profile: PathLike, values: Mapping[str, str], dry_run: bool = False) -> Dict[str, Any]:
    """Add the block to ``profile`` or bring the existing one up to date in place; ``action`` is ``added``, ``updated`` or
    ``unchanged``. Every other line of the file stays as it is. A second run with the same values changes nothing."""
    path = Path(profile)
    text = _read(path)
    lines = text.splitlines()
    ranges = _blocks(lines)
    block = render_block(values).splitlines()
    if ranges:
        if len(ranges) > 1:
            raise ShellEnvError("SHELL_PROFILE_BLOCK_BROKEN", f"{path} holds {len(ranges)} managed blocks; remove them with "
                                f"`aicore shell-env uninstall` first")
        start, end = ranges[0]
        if lines[start:end + 1] == block:
            return {"profile": str(path), "action": "unchanged"}
        result = lines[:start] + block + lines[end + 1:]
        action = "updated"
    else:
        result = lines + ([""] if lines else []) + block
        action = "added"
    if not dry_run:
        _write(path, "\n".join(result) + "\n")
    return {"profile": str(path), "action": action}


def uninstall(profile: PathLike, dry_run: bool = False) -> Dict[str, Any]:
    """Remove the block (and the blank line :func:`install` put before it); ``action`` is ``removed`` or ``absent``. A file
    that becomes empty is deleted when it held nothing but the block."""
    path = Path(profile)
    text = _read(path)
    lines = text.splitlines()
    ranges = _blocks(lines)
    if not ranges:
        return {"profile": str(path), "action": "absent"}
    for start, end in reversed(ranges):
        first = start - 1 if start > 0 and lines[start - 1] == "" else start
        lines = lines[:first] + lines[end + 1:]
    if not dry_run:
        if not lines:
            try:
                _target(path).unlink()
            except OSError as exc:
                raise ShellEnvError("SHELL_PROFILE_UNWRITABLE", f"{path}: {exc}") from None
        else:
            _write(path, "\n".join(lines) + "\n")
    return {"profile": str(path), "action": "removed"}


def inspect(profile: Optional[PathLike], values: Mapping[str, str]) -> Dict[str, Any]:
    """``state`` of the snippet in ``profile``: ``absent``, ``current`` (the block is what :func:`install` would write),
    ``stale`` (a block with other values) or ``broken`` (markers that do not pair up, ``error`` says how)."""
    if profile is None:
        return {"state": "unsupported", "profile": None}
    path = Path(profile)
    try:
        lines = _read(path).splitlines()
        ranges = _blocks(lines)
    except ShellEnvError as exc:
        return {"state": "broken", "profile": str(path), "error": str(exc)}
    if not ranges:
        return {"state": "absent", "profile": str(path)}
    state = "current" if len(ranges) == 1 and lines[ranges[0][0]:ranges[0][1] + 1] == render_block(values).splitlines() else "stale"
    return {"state": state, "profile": str(path)}


def _result(check_id: str, status: str, observed: str, remediation: Optional[str] = None) -> Dict[str, Any]:
    doc: Dict[str, Any] = {"$schema": RESULT_SCHEMA, "check_id": check_id, "status": status, "category": "environment",
                           "observed": observed}
    if remediation and status in ("warn", "fail"):
        doc["remediation"] = remediation
    return doc


INSTALL_HINT = "run `aicore shell-env install` (or the installer again), then open a new shell"


def doctor_checks(prefix: str, env: Env = None, home: Optional[PathLike] = None,
                  profile: Optional[PathLike] = None) -> List[Dict[str, Any]]:
    """Two ``check-result/v1`` documents for the doctors: ``<prefix>.env-snippet`` (the profile snippet) and
    ``<prefix>.env-variables`` (the variables of this process). They read; they never repair."""
    environment = _environment(env)
    try:
        values, notes = planned_values(environment, home)
    except ShellEnvError as exc:
        return [_result(f"{prefix}.env-variables", "fail", str(exc)[:400], "set SKM_HOME to an absolute path")]
    target = profile_path(environment, home, profile)
    found = inspect(target, values)
    state = found["state"]
    snippet_id = f"{prefix}.env-snippet"
    if state == "unsupported":
        shell = os.path.basename(environment.get("SHELL", "")) or "?"
        checks = [_result(snippet_id, "skip", f"no profile snippet for the shell {shell} (supported: "
                          f"{', '.join(PROFILES)}); export {', '.join(envtable.NAMES)} yourself")]
    elif state == "current":
        checks = [_result(snippet_id, "ok", f"{found['profile']} exports {', '.join(sorted(values))}")]
    elif state == "stale":
        checks = [_result(snippet_id, "warn", f"{found['profile']} has a snippet with other values than this machine",
                          INSTALL_HINT)]
    elif state == "broken":
        checks = [_result(snippet_id, "fail", found["error"][:400], "fix or delete the lines between the markers "
                          f"of {found['profile']}, then {INSTALL_HINT}")]
    else:
        checks = [_result(snippet_id, "warn", f"{found['profile']} has no SKM environment snippet", INSTALL_HINT)]
    problems: List[str] = []
    missing = [name for name in envtable.NAMES if not environment.get(name)]
    exported = [name for name in missing if name in values]
    if exported and state in ("current", "stale"):
        problems.append(f"{', '.join(exported)} not set in this shell although the profile exports them: open a new shell")
    elif missing:
        problems.append(f"{', '.join(missing)} not set in this shell")
    home_value = environment.get(envtable.ENV_HOME)
    if home_value and not os.path.isdir(home_value):
        problems.append(f"{envtable.ENV_HOME}={home_value} is not a folder")
    folder = environment.get(envtable.ENV_WORKSPACES)
    if folder and not os.path.isdir(folder):
        problems.append(f"{envtable.ENV_WORKSPACES}={folder} is not a folder")
    code = environment.get(envtable.ENV_WORKSPACE)
    if code:
        if not is_code(code):
            problems.append(f"{envtable.ENV_WORKSPACE}={code!r} is not a workspace code")
        elif code not in list_workspaces(environment, home):
            problems.append(f"{envtable.ENV_WORKSPACE}={code} is not a workspace of {workspaces_root(environment, home)}")
    problems.extend(notes)
    variables_id = f"{prefix}.env-variables"
    if problems:
        checks.append(_result(variables_id, "warn", "; ".join(problems)[:600], INSTALL_HINT))
    else:
        checks.append(_result(variables_id, "ok", ", ".join(f"{name}={environment[name]}" for name in envtable.NAMES)[:600]))
    return checks
