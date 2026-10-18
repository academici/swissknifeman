"""The documents of the workspace: the project marker, ``workspace.json``, ``project.json`` and the device file.

Every document is validated against its contract (``schemas/<kind>/v1``) when it is read and before it is written.
A portable document (everything but the machine files ``bindings.json``, ``device.json`` and ``local/config.toml``) must hold no absolute path:
the schemas reject the fields that could carry one and :func:`validate_document` rejects any string that starts with
``/``, ``~`` or ``X:\\`` anywhere in the document.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Union

from aicore.state.locations import device_file, ensure_dir, is_code
from aicore.util import schema
from aicore.util.io import atomic_write_text

from . import WorkspaceError

MARKER_RELPATH = ".swissknifeman/project.json"
WORKSPACE_FILE = "workspace.json"
PROJECT_FILE = "project.json"
DEVICE_FILE = "device.json"
SCHEMA_PREFIX = "urn:swissknifeman:aicore:"
MACHINE_KINDS = ("workspace-bindings", "workspace-device", "project-local-config")
_SCHEMAS = Path(__file__).resolve().parents[3] / "schemas"
_ABSOLUTE = re.compile(r"^(?:[/~]|[A-Za-z]:[\\/])")

PathLike = Union[str, "os.PathLike[str]"]


def utc_now() -> str:
    """The current time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _absolute_strings(node: Any, pointer: str = "") -> List[str]:
    found: List[str] = []
    if isinstance(node, str):
        if _ABSOLUTE.match(node):
            found.append(pointer or "/")
    elif isinstance(node, Mapping):
        for key, value in node.items():
            found.extend(_absolute_strings(value, f"{pointer}/{key}"))
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            found.extend(_absolute_strings(value, f"{pointer}/{index}"))
    return found


def validate_document(kind: str, document: object) -> List[str]:
    """Issues of ``document`` against the contract ``kind`` (empty when valid); for a portable kind also every string that
    looks like an absolute path (``PORTABLE_ABSOLUTE_PATH`` at its pointer)."""
    registry, _kind = schema.load_contract(_SCHEMAS / kind / "v1")
    issues = [f"{issue.code}: {issue.message}" for issue in schema.validate(document, kind, registry)]
    if kind not in MACHINE_KINDS:
        issues.extend(f"PORTABLE_ABSOLUTE_PATH: {pointer}: a portable document holds no absolute path"
                      for pointer in _absolute_strings(document))
    return issues


def _read(path: Path, kind: str, code: str) -> Optional[dict]:
    """The validated document at ``path``; ``None`` when there is no file; ``WorkspaceError(code)`` otherwise."""
    if not path.exists() and not path.is_symlink():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise WorkspaceError(code, f"{path.name} is not readable JSON: {exc.__class__.__name__}") from None
    if not isinstance(document, dict):
        raise WorkspaceError(code, f"{path.name} must hold a JSON object")
    issues = validate_document(kind, document)
    if issues:
        raise WorkspaceError(code, f"{path.name} does not match {SCHEMA_PREFIX}{kind}:v1: {issues[0]}")
    return document


def _write(path: Path, kind: str, document: dict) -> dict:
    issues = validate_document(kind, document)
    if issues:
        raise ValueError(f"invalid {kind} document: {issues[0]}")
    atomic_write_text(path, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    return document


def _doc(kind: str, **fields: Any) -> dict:
    return dict({"$schema": f"{SCHEMA_PREFIX}{kind}:v1"}, **fields)


def read_marker(root: PathLike) -> Optional[dict]:
    """The project marker ``<root>/.swissknifeman/project.json``; ``None`` when there is no file; not JSON, not an object
    or not matching the contract: ``WorkspaceError('PROJECT_MARKER_INVALID')``."""
    return _read(Path(root) / MARKER_RELPATH, "project-marker", "PROJECT_MARKER_INVALID")


def write_marker(root: PathLike, workspace: str, project_id: str, plans_store: str) -> dict:
    """Write the marker atomically; the caller commits it. ``workspace`` and ``project_id`` are codes. ``ValueError`` for
    an invalid code or store."""
    return _write(Path(root) / MARKER_RELPATH, "project-marker",
                  _doc("project-marker", workspace=workspace, project_id=project_id, plans_store=plans_store))


def read_workspace(ws: PathLike) -> Optional[dict]:
    """``<ws>/workspace.json``; ``None`` when absent; invalid: ``WorkspaceError('WORKSPACE_LAYOUT_INVALID')``."""
    return _read(Path(ws) / WORKSPACE_FILE, "workspace", "WORKSPACE_LAYOUT_INVALID")


def write_workspace(ws: PathLike, code: str, workspace_id: str, created_by: str,
                    created_at: Optional[str] = None) -> dict:
    return _write(Path(ws) / WORKSPACE_FILE, "workspace",
                  _doc("workspace", code=code, workspace_id=workspace_id, layout=2, created_at=created_at or utc_now(),
                       created_by=created_by))


def project_dir(ws: PathLike, project_id: str) -> Path:
    """``<ws>/projects/<project_id>`` (nothing is created; the id is the project code)."""
    if not is_code(project_id):
        raise ValueError(f"invalid project code {project_id!r}")
    return Path(ws) / "projects" / project_id


def read_project(ws: PathLike, project_id: str) -> Optional[dict]:
    """``<ws>/projects/<id>/project.json``; ``None`` when absent; invalid: ``WORKSPACE_LAYOUT_INVALID``."""
    return _read(project_dir(ws, project_id) / PROJECT_FILE, "workspace-project", "WORKSPACE_LAYOUT_INVALID")


def write_project(ws: PathLike, project_id: str, name: str, remotes: Sequence[str] = (),
                  aliases: Sequence[str] = (), status: str = "active", created_at: Optional[str] = None) -> dict:
    return _write(project_dir(ws, project_id) / PROJECT_FILE, "workspace-project",
                  _doc("workspace-project", project_id=project_id, name=name, created_at=created_at or utc_now(),
                       identity={"remotes": list(remotes)}, aliases=list(aliases), status=status))


def _device_path(env: Optional[Mapping[str, str]], home: Optional[PathLike]) -> Path:
    return device_file(env, home)


def read_device(env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None) -> Optional[dict]:
    """The device file of this machine (``state/workspaces/device.json``, shared by every workspace); ``None`` when absent."""
    return _read(_device_path(env, home), "workspace-device", "WORKSPACE_LAYOUT_INVALID")


def write_device(device_id: str, name: str, created_at: Optional[str] = None,
                 env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None) -> dict:
    path = _device_path(env, home)
    ensure_dir(path.parent)
    return _write(path, "workspace-device", _doc("workspace-device", device_id=device_id, name=name,
                                                  created_at=created_at or utc_now()))
