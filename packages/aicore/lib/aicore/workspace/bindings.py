"""Machine bindings (``bindings.json`` in ``workspace_state_dir()``): which checkouts of this machine belong to which
project. Writers hold ``flock(LOCK_EX)`` on ``bindings.json.lock`` and replace the file atomically; readers take no
lock and always see a whole file. Paths are stored as real paths.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Mapping, Optional, Sequence, Union

from aicore.state.locations import ensure_dir, workspace_state_dir
from aicore.util.io import atomic_write_text
from aicore.util.lock import FileLock

from . import WorkspaceError
from .documents import SCHEMA_PREFIX, utc_now, validate_document
from .ids import is_code

BINDINGS_FILE = "bindings.json"
LOCK_TIMEOUT_S = 10.0
_POLL_S = 0.05

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]


def bindings_path(env: Env = None, home: Optional[PathLike] = None) -> Path:
    return workspace_state_dir(env, home) / BINDINGS_FILE


def _empty() -> dict:
    return {"$schema": f"{SCHEMA_PREFIX}workspace-bindings:v1", "projects": {}}


def read_bindings(env: Env = None, home: Optional[PathLike] = None) -> dict:
    """The bindings document (no lock); an empty one when the file is absent; a damaged file is
    ``WorkspaceError('WORKSPACE_LAYOUT_INVALID')``."""
    path = bindings_path(env, home)
    if not path.exists():
        return _empty()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", f"{BINDINGS_FILE} is not readable JSON: "
                             f"{exc.__class__.__name__}") from None
    issues = validate_document("workspace-bindings", document) if isinstance(document, dict) else ["not an object"]
    if issues:
        raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", f"{BINDINGS_FILE} does not match the contract: {issues[0]}")
    return document


@contextmanager
def _locked(env: Env, home: Optional[PathLike], timeout_s: float) -> Iterator[None]:
    folder = workspace_state_dir(env, home)
    ensure_dir(folder)
    lock = FileLock(folder / (BINDINGS_FILE + ".lock"))
    if not lock.acquire(blocking=True, timeout=max(timeout_s, 0.0), poll=_POLL_S):
        raise WorkspaceError("WORKSPACE_BINDINGS_LOCKED", f"another process holds the bindings lock "
                             f"(waited {timeout_s:g} s); try again")
    try:
        yield
    finally:
        lock.release()


def _real(path: PathLike) -> str:
    return os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))


def _check_id(project_id: str) -> None:
    if not is_code(project_id):
        raise ValueError(f"invalid project code {project_id!r}")


def _save(document: dict, env: Env, home: Optional[PathLike]) -> None:
    issues = validate_document("workspace-bindings", document)
    if issues:
        raise ValueError(f"invalid bindings document: {issues[0]}")
    atomic_write_text(bindings_path(env, home), json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def _first_existing(paths: Sequence[str]) -> str:
    return next((path for path in paths if os.path.isdir(path)), paths[0])


def bind(project_id: str, path: PathLike, env: Env = None, home: Optional[PathLike] = None,
         timeout_s: float = LOCK_TIMEOUT_S) -> dict:
    """Add the checkout ``path`` to the project and return its entry. The primary stays the first bound checkout while it
    exists, else it becomes this one. Binding a bound path again changes nothing."""
    _check_id(project_id)
    real = _real(path)
    with _locked(env, home, timeout_s):
        document = read_bindings(env, home)
        entry = document["projects"].get(project_id)
        if entry is None:
            entry = {"paths": [real], "primary": real, "bound_at": utc_now()}
        else:
            if real not in entry["paths"]:
                entry["paths"].append(real)
            if not os.path.isdir(entry["primary"]) and os.path.isdir(real):
                entry["primary"] = real
        document["projects"][project_id] = entry
        _save(document, env, home)
        return entry


def unbind(project_id: str, path: Optional[PathLike] = None, env: Env = None, home: Optional[PathLike] = None,
           timeout_s: float = LOCK_TIMEOUT_S) -> bool:
    """Drop the checkout ``path`` of the project, or the whole project without ``path``; the last path takes the project
    with it and a removed primary is replaced by the first remaining existing path. ``True`` when something changed."""
    _check_id(project_id)
    with _locked(env, home, timeout_s):
        document = read_bindings(env, home)
        entry = document["projects"].get(project_id)
        if entry is None:
            return False
        if path is None:
            del document["projects"][project_id]
        else:
            real = _real(path)
            if real not in entry["paths"]:
                return False
            entry["paths"].remove(real)
            if not entry["paths"]:
                del document["projects"][project_id]
            elif entry["primary"] == real:
                entry["primary"] = _first_existing(entry["paths"])
        _save(document, env, home)
        return True


def set_paths(project_id: str, paths: Sequence[PathLike], env: Env = None, home: Optional[PathLike] = None,
              timeout_s: float = LOCK_TIMEOUT_S, *, preserve: bool = False,
              primary: Optional[PathLike] = None) -> Optional[dict]:
    """Replace the paths of the project; the primary stays when it is among them, else the first existing one is used.
    No paths removes the project. Returns the entry (``None`` when removed).

    ``preserve=True`` keeps all previous paths in order (including missing directories), appending only new paths.
    ``primary`` explicitly selects a path in the resulting list; a non-member raises ``ValueError`` without writing.
    Reading the previous entry, merging paths and selecting primary share one lock and one atomic write; an existing
    ``bound_at`` is retained in either mode.
    """
    _check_id(project_id)
    real: List[str] = []
    for item in paths:
        converted = _real(item)
        if converted not in real:
            real.append(converted)
    requested_primary = _real(primary) if primary is not None else None
    with _locked(env, home, timeout_s):
        document = read_bindings(env, home)
        previous = document["projects"].get(project_id)
        if preserve and previous:
            real = previous["paths"] + [path for path in real if path not in previous["paths"]]
        if requested_primary is not None and requested_primary not in real:
            raise ValueError("primary must be among the resulting binding paths")
        if not real:
            document["projects"].pop(project_id, None)
            entry = None
        else:
            chosen_primary = requested_primary if requested_primary is not None else (
                previous["primary"] if previous and previous["primary"] in real else _first_existing(real))
            entry = {"paths": real, "primary": chosen_primary, "bound_at": previous["bound_at"] if previous else utc_now()}
            document["projects"][project_id] = entry
        _save(document, env, home)
        return entry
