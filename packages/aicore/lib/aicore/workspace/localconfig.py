"""The project-local folder of a workspace: ``projects/<code>/local/`` (contract ``project-local-config/v1``).

``local/`` holds what belongs to one project on one machine and never enters the workspace repository (the workspace
``.gitignore`` lists it): ``config.toml`` (the project layer of the configuration plus ``[repo] path``, the code
repository of the project on this machine, which replaces the entry of ``bindings.json``), ``state/`` (module state),
``backups/`` (backups of the layer files) and ``stubs/`` (generated launcher stubs). Writers hold ``flock`` on
``config.toml.lock`` and replace the file atomically; readers take no lock and always see a whole file. Paths are stored
as real paths. The functions create nothing but what they are asked to write; :func:`ensure_local` makes the folders.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

from aicore.config import ConfigError, toml, toml_edit
from aicore.config.model import CONFIG_FILE_VERSION, layer_lock
from aicore.state.locations import LOCAL_DIRNAME, ensure_dir
from aicore.util.io import atomic_write_text

from . import WorkspaceError
from .documents import project_dir, validate_document

CONFIG_FILE = "config.toml"
LOCAL_FOLDERS = ("state", "backups", "stubs")
KIND = "project-local-config"
LOCK_TIMEOUT_S = 10.0

_EMPTY_REPO = re.compile(r"^\[repo\][ \t]*(?:#[^\n]*)?\n?", re.M)

PathLike = Union[str, "os.PathLike[str]"]


def local_dir(ws: PathLike, project_id: str) -> Path:
    """``<ws>/projects/<project_id>/local`` (nothing is created; ``ValueError`` for a project id that is not a code)."""
    return project_dir(ws, project_id) / LOCAL_DIRNAME


def local_config_file(ws: PathLike, project_id: str) -> Path:
    return local_dir(ws, project_id) / CONFIG_FILE


def local_state_dir(ws: PathLike, project_id: str, app: Optional[str] = None) -> Path:
    base = local_dir(ws, project_id) / "state"
    return base / app if app else base


def local_backups_dir(ws: PathLike, project_id: str) -> Path:
    return local_dir(ws, project_id) / "backups"


def local_stubs_dir(ws: PathLike, project_id: str) -> Path:
    return local_dir(ws, project_id) / "stubs"


def ensure_local(ws: PathLike, project_id: str) -> Path:
    """Create ``local/`` with ``state/``, ``backups/`` and ``stubs/`` (owner-only access) and return it. The project folder
    must exist: a project that is not in the workspace is ``WorkspaceError('PROJECT_UNKNOWN')``."""
    folder = local_dir(ws, project_id)
    if not folder.parent.is_dir():
        raise WorkspaceError("PROJECT_UNKNOWN", f"no project {project_id} in the workspace")
    ensure_dir(folder)
    for name in LOCAL_FOLDERS:
        ensure_dir(folder / name)
    return folder


def _real(path: PathLike) -> str:
    return os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))


def _invalid(project_id: str, detail: str) -> WorkspaceError:
    return WorkspaceError("PROJECT_LOCAL_CONFIG_INVALID",
                          f"projects/{project_id}/{LOCAL_DIRNAME}/{CONFIG_FILE} does not match the contract: {detail}")


def _parse(text: str, project_id: str, source: str) -> Dict[str, Any]:
    try:
        document = toml.loads(text, source=source)
    except ConfigError as exc:
        raise _invalid(project_id, exc.message) from None
    issues = validate_document(KIND, document)
    if issues:
        raise _invalid(project_id, issues[0])
    return document


def _failed(project_id: str, exc: ConfigError, timeout_s: float) -> WorkspaceError:
    if exc.code == "CONFIG_LOCKED":
        return WorkspaceError("PROJECT_LOCAL_CONFIG_LOCKED", f"another process holds the lock of the local config of "
                              f"{project_id} (waited {timeout_s:g} s); try again")
    return WorkspaceError("PROJECT_LOCAL_CONFIG_INVALID", exc.message)


def read_local_config(ws: PathLike, project_id: str) -> Optional[Dict[str, Any]]:
    """The parsed ``local/config.toml`` of the project, validated against ``project-local-config/v1``; ``None`` when there is no
    file; unreadable, not TOML or not matching the contract: ``WorkspaceError('PROJECT_LOCAL_CONFIG_INVALID')``."""
    path = local_config_file(ws, project_id)
    if not path.exists() and not path.is_symlink():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise _invalid(project_id, f"not readable: {exc.__class__.__name__}") from None
    return _parse(text, project_id, str(path))


def repo_path(ws: PathLike, project_id: str) -> Optional[str]:
    """``repo.path`` of the project (the code repository on this machine); ``None`` when the project has no local config
    or no ``[repo]`` table."""
    document = read_local_config(ws, project_id)
    return None if document is None else document.get("repo", {}).get("path")


def _write(project_id: str, path: Path, text: str) -> None:
    _parse(text, project_id, str(path))  # never write a file this module would refuse to read
    atomic_write_text(path, text, mode=0o600)


def set_repo_path(ws: PathLike, project_id: str, path: PathLike, timeout_s: float = LOCK_TIMEOUT_S) -> str:
    """Set ``repo.path`` of the project to the real path of ``path`` and return it. The folders of ``local/`` are created, the
    other tables of the file are kept as they are; the same path again changes nothing. ``PROJECT_UNKNOWN`` for a project
    that is not in the workspace, ``PROJECT_LOCAL_CONFIG_INVALID`` when the existing file is damaged (it is not touched)."""
    real = _real(path)
    folder = ensure_local(ws, project_id)
    target = folder / CONFIG_FILE
    try:
        with layer_lock(target, timeout_s=timeout_s):
            try:
                old = target.read_text(encoding="utf-8")
            except FileNotFoundError:
                old = f"schema_version = {CONFIG_FILE_VERSION}\n"
            except (OSError, UnicodeError) as exc:
                raise _invalid(project_id, f"not readable: {exc.__class__.__name__}") from None
            current = _parse(old, project_id, str(target))
            if current.get("repo", {}).get("path") == real and target.exists():
                return real
            try:
                new = toml_edit.set_value(old, ("repo", "path"), real, source=str(target))
            except (ConfigError, toml_edit.TomlEditError) as exc:
                raise _invalid(project_id, getattr(exc, "message", str(exc))) from None
            _write(project_id, target, new)
    except ConfigError as exc:
        raise _failed(project_id, exc, timeout_s) from None
    return real


def clear_repo_path(ws: PathLike, project_id: str, timeout_s: float = LOCK_TIMEOUT_S) -> bool:
    """Remove ``repo.path`` from the local config; ``True`` when something changed. The rest of the file stays."""
    target = local_config_file(ws, project_id)
    if not target.is_file():
        return False
    try:
        with layer_lock(target, timeout_s=timeout_s):
            old = target.read_text(encoding="utf-8")
            if "path" not in _parse(old, project_id, str(target)).get("repo", {}):
                return False
            new = toml_edit.unset_value(old, ("repo", "path"), source=str(target))
            if toml.loads(new, source=str(target)).get("repo") == {}:  # an empty [repo] would not match the contract
                new = _EMPTY_REPO.sub("", new, count=1)
            _write(project_id, target, new)
            return True
    except ConfigError as exc:
        raise _failed(project_id, exc, timeout_s) from None
