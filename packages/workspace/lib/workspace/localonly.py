"""Local-only files: the portable index ``projects/<id>/local-only.json`` and this machine's block in ``.git/info/exclude``.

A local-only file (too large, binary and large, or a migrated file with a secret pattern) stays out of git. The index records it for every device (path relative to
the project folder, size, SHA-256, owner device, reason); the exclude block keeps git from adding the files of *this* device.
The functions here do not take ``git.lock``: a caller that changes the repository (sync, migrate) holds it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

from aicore.util.io import atomic_write_text
from aicore.workspace import WorkspaceError, is_code, project_dir, read_workspace, validate_document

from . import gitutil
from .safety import Report

SCHEMA = "urn:swissknifeman:aicore:workspace-local-only:v1"
INDEX_FILE = "local-only.json"
BEGIN = "# skm:local-only begin"
END = "# skm:local-only end"

PathLike = Union[str, "os.PathLike[str]"]


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _safe(relative: str) -> str:
    """A POSIX path inside the project folder: not absolute, no ``..``, no empty or ``.`` segment."""
    pure = PurePosixPath(relative)
    if not relative or pure.is_absolute() or "\\" in relative or any(part in ("", ".", "..") for part in relative.split("/")):
        raise ValueError(f"not a path inside the project folder: {relative!r}")
    return str(pure)


def index_path(ws_root: PathLike, project_id: str) -> Path:
    return project_dir(ws_root, project_id) / INDEX_FILE


def read(ws_root: PathLike, project_id: str) -> Dict[str, Any]:
    """The index of a project (an empty one when there is none); a damaged index is ``WORKSPACE_LAYOUT_INVALID``."""
    path = index_path(ws_root, project_id)
    if not path.is_file():
        return {"$schema": SCHEMA, "files": []}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", f"projects/{project_id}/{INDEX_FILE} is not readable JSON") from None
    issues = validate_document("workspace-local-only", document) if isinstance(document, dict) else ["not an object"]
    if issues:
        raise WorkspaceError("WORKSPACE_LAYOUT_INVALID",
                             f"projects/{project_id}/{INDEX_FILE} does not match its contract: {issues[0]}")
    return document


def update(ws_root: PathLike, project_id: str, entries: Iterable[Mapping[str, Any]], device_id: str) -> Dict[str, Any]:
    """Replace the entries of ``device_id`` in the index of a project by ``entries`` and keep those of other devices.

    An entry is ``{"path": <relative to the project folder>, "reason": "size"|"binary"|"secret-pattern"}``; the size and the SHA-256 are read
    from the file. The index is sorted by path and written atomically only when it changes; with no entries and no index
    nothing is written. An entry whose file is missing, or whose path leaves the project folder, is a ``ValueError``.
    """
    folder = project_dir(ws_root, project_id)
    if not folder.is_dir():
        raise WorkspaceError("PROJECT_UNKNOWN", f"no project {project_id} in the workspace")
    current = read(ws_root, project_id)
    mine: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        relative = _safe(str(entry["path"]))
        target = folder / relative
        if not target.is_file() or target.is_symlink():
            raise ValueError(f"{relative}: the local-only file does not exist")
        mine[relative] = {"path": relative, "bytes": target.stat().st_size, "sha256": _digest(target),
                          "device_id": device_id, "reason": entry["reason"]}
    files: List[Dict[str, Any]] = [item for item in current["files"] if item["device_id"] != device_id]
    files.extend(mine.values())
    files.sort(key=lambda item: (item["path"], item["device_id"]))
    document = {"$schema": SCHEMA, "files": files}
    path = index_path(ws_root, project_id)
    if document == current and (path.exists() or not files):
        return document
    issues = validate_document("workspace-local-only", document)
    if issues:
        raise ValueError(f"invalid local-only index: {issues[0]}")
    atomic_write_text(path, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    return document


def entries_by_project(report: Report) -> Dict[str, List[Dict[str, Any]]]:
    """The local-only files of a scan grouped by project, with paths relative to the project folder, ready for
    :func:`update`. Files outside ``projects/<id>/`` have no index and are left out."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in report.local_only:
        parts = item["path"].split("/")
        if len(parts) >= 3 and parts[0] == "projects" and parts[2] != INDEX_FILE:
            grouped.setdefault(parts[1], []).append({"path": "/".join(parts[2:]), "reason": item["reason"]})
    return grouped


def device_paths(ws_root: PathLike, device_id: str) -> List[str]:
    """Workspace-relative paths of the local-only files that belong to ``device_id``, from every project index."""
    found: List[str] = []
    projects = Path(ws_root) / "projects"
    try:
        names = sorted(child.name for child in projects.iterdir() if child.is_dir() and is_code(child.name))
    except OSError:
        return found
    for project_id in names:
        for item in read(ws_root, project_id)["files"]:
            if item["device_id"] == device_id:
                found.append(f"projects/{project_id}/{item['path']}")
    return sorted(found)


def _pattern(relative: str) -> str:
    """A gitignore line that matches exactly one file, anchored at the workspace root."""
    escaped = "".join("\\" + char if char in "\\*?[]" else char for char in relative)
    if escaped.endswith(" "):
        escaped = escaped[:-1] + "\\ "
    return "/" + escaped


def exclude_file(ws_root: PathLike) -> Path:
    done = gitutil.git(["rev-parse", "--git-path", "info/exclude"], Path(ws_root))
    if done.returncode != 0:
        raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", f"{ws_root} is not a git repository")
    return (Path(ws_root) / done.stdout.strip()).resolve() if not os.path.isabs(done.stdout.strip()) \
        else Path(done.stdout.strip())


def rebuild_exclude(ws_root: PathLike, device_id: str) -> List[str]:
    """Rebuild the block between ``# skm:local-only begin`` and ``end`` in ``.git/info/exclude`` from the index entries of
    ``device_id``; every line outside the block is kept as it is. Returns the patterns of the block.

    Without entries and without a block the file is not touched. A block that has a begin line and no end line is refused
    (``WORKSPACE_LAYOUT_INVALID``) rather than guessed at.
    """
    read_workspace(ws_root)  # a damaged workspace.json stops here, before anything is written
    patterns = [_pattern(relative) for relative in device_paths(ws_root, device_id)]
    path = exclude_file(ws_root)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    kept: List[str] = []
    insert_at: Optional[int] = None
    inside = False
    for line in lines:
        if line.strip() == BEGIN:
            if inside:
                raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", f"{path.name} has a second begin line of the local-only block")
            inside = True
            if insert_at is None:
                insert_at = len(kept)
        elif line.strip() == END and inside:
            inside = False
        elif not inside:
            kept.append(line)
    if inside:
        raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", f"{path.name} has a local-only begin line without an end line")
    if insert_at is None:
        if not patterns:
            return []
        insert_at = len(kept)
    block = [BEGIN, *patterns, END]
    result = kept[:insert_at] + block + kept[insert_at:]
    text = "\n".join(result) + "\n"
    try:
        same = path.read_text(encoding="utf-8") == text
    except FileNotFoundError:
        same = False
    if not same:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, text)
    return patterns
