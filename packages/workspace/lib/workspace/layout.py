"""The layout of the workspace (contract: ``workspace.json``, ``projects/<project_id>/…``): ``init`` creates it, ``status``
reads it. Machine files (bindings, device, sync state) live in ``workspace_state_dir()``, never in the git tree."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from aicore.state import is_code, workspace_root, workspace_state_dir
from aicore.workspace import (WorkspaceError, new_id, read_bindings, read_device, read_marker,
                              read_project, read_workspace, utc_now, write_device, write_workspace)

from . import gitutil, policy

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]

BASELINE_IGNORE = """/.staging/
**/.lock
**/views/
**/context/
*.pid
*.tmp
.env
.env.*
*.pem
*.key
*.p12
*.pfx
.DS_Store
Thumbs.db
*.swp
"""

GITIGNORE = BASELINE_IGNORE + policy.block()  # the tracking policy: see policy.py

GITATTRIBUTES = """*.json text=auto eol=lf
*.md text=auto eol=lf
*.toml text=auto eol=lf
*.yaml text=auto eol=lf
*.yml text=auto eol=lf
*.jsonl text=auto eol=lf
**/log.jsonl merge=union
**/views/** linguist-generated=true
"""

README = """# SwissKnifeMan workspace

This folder is a portable workspace: the plans of all your projects in one git repository.
It is created and kept by `swissknifeman workspace`; do not move it by hand.

- `workspace.json` names this workspace (its code is the name of this folder); `projects/<code>/` holds the plans of one project.
- `swissknifeman workspace status` shows the state of this repository and of the projects bound on this machine.
- `swissknifeman workspace sync` commits, pulls and pushes it between machines.
- Files that are too large for git stay on the machine that made them and are listed in `projects/<code>/local-only.json`.
- `projects/<code>/local/` is the machine-local folder of a project (its `config.toml` with `repo.path`, state, backups, stubs): git ignores it.

Machine-specific files (bindings of checkouts, the device id) are kept outside this folder and never enter git.
"""

TOP_LEVEL = (".git", ".gitignore", ".gitattributes", "workspace.json", "README.md", ".staging", "projects")
GIT_MIN_TEXT = "2.38"


def scoped_env(code: str, env: Env = None) -> Dict[str, str]:
    """A copy of the environment that selects the workspace ``code`` (``SKM_WORKSPACE``) for the machine files."""
    if not is_code(code):
        raise WorkspaceError("WORKSPACE_CODE_INVALID", f"{code!r} is not a code: lowercase letters, digits and single "
                             f"hyphens, starting with a letter, at most 40 characters")
    scoped = dict(os.environ if env is None else env)
    scoped["SKM_WORKSPACE"] = code
    return scoped


def root_of(root: Optional[PathLike], env: Env = None, home: Optional[PathLike] = None) -> Path:
    """``--root`` (made absolute) or ``workspace_root()`` of the selected workspace."""
    if root is not None and str(root) != "":
        return Path(os.path.abspath(os.path.expanduser(str(root))))
    return workspace_root(env, home)


def _ensure_device(env: Env, home: Optional[PathLike]) -> Dict[str, Any]:
    device = read_device(env, home)
    if device is not None:
        return device
    import socket
    name = socket.gethostname() or "device"
    return write_device(new_id("dev"), name, env=env, home=home)


def _clean_partial(root: Path, existed: bool) -> None:
    """Undo a failed init in a root that was empty or absent before it started."""
    if not root.exists():
        return
    if not existed:
        shutil.rmtree(root, ignore_errors=True)
        return
    for child in root.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                pass


def _refuse_foreign(target: Path) -> None:
    """``WORKSPACE_ROOT_NOT_EMPTY`` for an existing root that is not an empty folder and holds no ``workspace.json``."""
    if (target / "workspace.json").is_file():
        return
    if (target.exists() or target.is_symlink()) and (not target.is_dir() or any(target.iterdir())):
        raise WorkspaceError("WORKSPACE_ROOT_NOT_EMPTY",
                             f"{target} is not empty and holds no workspace.json; choose an empty folder "
                             f"(another --code or --root)")


def init(code: str, root: Optional[PathLike] = None, env: Env = None,
         home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Create the workspace ``code`` at ``root`` (default ``workspaces/<code>``). Returns ``{code, root, workspace_id,
    device_id, created, already_initialized}``.

    A root that holds ``workspace.json`` is left alone (``already_initialized``; another code in it is
    ``WORKSPACE_CODE_MISMATCH``); a non-empty root without it is ``WORKSPACE_ROOT_NOT_EMPTY`` and nothing is written.
    A failure part way removes what this call created.
    """
    env = scoped_env(code, env)
    target = root_of(root, env, home)
    _refuse_foreign(target)  # before the lock: a refusal writes nothing, not even the lock file
    with gitutil.git_lock(env, home):
        if (target / "workspace.json").is_file():
            document = read_workspace(target)
            if document["code"] != code:
                raise WorkspaceError("WORKSPACE_CODE_MISMATCH", f"{target} holds the workspace {document['code']!r}, "
                                     f"not {code!r}")
            device = _ensure_device(env, home)
            return {"code": code, "root": str(target), "workspace_id": document["workspace_id"],
                    "device_id": device["device_id"], "created": False, "already_initialized": True}
        existed = target.exists() or target.is_symlink()
        _refuse_foreign(target)
        version = gitutil.git_version()
        if version is None or version < gitutil.MIN_GIT_INIT:
            raise WorkspaceError("WORKSPACE_GIT_TOO_OLD", "git 2.28 or newer is required (git init -b main)")
        device = _ensure_device(env, home)
        try:
            target.mkdir(parents=True, exist_ok=True)
            workspace_id = new_id("ws")
            write_workspace(target, code, workspace_id, device["device_id"])
            (target / "projects").mkdir()
            (target / "projects" / ".gitkeep").write_text("", encoding="utf-8")
            (target / ".staging").mkdir()
            (target / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
            (target / ".gitattributes").write_text(GITATTRIBUTES, encoding="utf-8")
            (target / "README.md").write_text(README, encoding="utf-8")
            gitutil.require(gitutil.git(["init", "-q", "-b", "main"], target), "init")
            gitutil.require(gitutil.git(["add", "-A"], target), "add")
            gitutil.require(gitutil.git([*gitutil.identity_args(target), "commit", "-q", "-m", "skm(workspace): init",
                                         "-m", f"Workspace-Device: {device['device_id']}"], target), "commit")
        except BaseException:
            _clean_partial(target, existed)
            raise
    return {"code": code, "root": str(target), "workspace_id": workspace_id, "device_id": device["device_id"],
            "created": True, "already_initialized": False}


def require_initialized(target: Path) -> Dict[str, Any]:
    """The ``workspace.json`` of ``target``; ``WORKSPACE_NOT_INITIALIZED`` when there is none."""
    document = read_workspace(target) if target.is_dir() else None
    if document is None:
        raise WorkspaceError("WORKSPACE_NOT_INITIALIZED",
                             f"no workspace at {target}; run `swissknifeman workspace init --code CODE`")
    return document


def project_ids(target: Path) -> List[str]:
    """Folder names under ``projects/`` that are project codes, sorted."""
    folder = target / "projects"
    try:
        return sorted(child.name for child in folder.iterdir() if child.is_dir() and is_code(child.name))
    except OSError:
        return []


def count_plans(target: Path, project_id: str) -> int:
    """Plan folders (not ``archive``) of a project in the workspace."""
    folder = target / "projects" / project_id / "plans"
    try:
        return sum(1 for child in folder.iterdir() if child.is_dir() and child.name != "archive")
    except OSError:
        return 0


def _git_state(target: Path, fetch: bool, env: Env, home: Optional[PathLike]) -> Dict[str, Any]:
    branch = gitutil.git(["symbolic-ref", "--short", "-q", "HEAD"], target).stdout.strip() or None
    porcelain = gitutil.git(["status", "--porcelain", "--untracked-files=all"], target)
    dirty = len([line for line in porcelain.stdout.splitlines() if line.strip()]) if porcelain.returncode == 0 else 0
    remote = gitutil.remote_of(target)
    fetched_at: Optional[str] = None
    if fetch and remote is not None:
        with gitutil.git_lock(env, home):
            gitutil.fetch(target, "origin", env)
        fetched_at = utc_now()
    elif (target / ".git" / "FETCH_HEAD").is_file():
        stamp = (target / ".git" / "FETCH_HEAD").stat().st_mtime
        fetched_at = datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ahead: Optional[int] = None
    behind: Optional[int] = None
    if branch is not None and remote is not None:
        counts = gitutil.ahead_behind(target, branch)
        if counts is not None:
            ahead, behind = counts
    return {"branch": branch, "dirty": dirty, "remote": remote, "ahead": ahead, "behind": behind,
            "diverged": bool(ahead and behind), "fetched_at": fetched_at}


def _last_sync(env: Env, home: Optional[PathLike]) -> Optional[Dict[str, Any]]:
    path = workspace_state_dir(env, home) / "sync.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def project_rows(target: Path, env: Env, home: Optional[PathLike]) -> List[Dict[str, Any]]:
    """One row per project of the workspace with its binding on this machine."""
    bound = read_bindings(env, home)["projects"]
    rows = []
    for project_id in project_ids(target):
        try:
            record = read_project(target, project_id)
        except WorkspaceError as exc:
            rows.append({"project_id": project_id, "name": None, "status": "invalid", "error": exc.code,
                         "bound": project_id in bound, "paths": list(bound.get(project_id, {}).get("paths", [])),
                         "plans": count_plans(target, project_id), "plans_store": None})
            continue
        if record is None:
            continue
        entry = bound.get(project_id)
        store = None
        if entry is not None:
            try:
                marker = read_marker(entry["primary"]) if os.path.isdir(entry["primary"]) else None
            except WorkspaceError:
                marker = None
            store = marker["plans_store"] if marker else None
        rows.append({"project_id": project_id, "name": record["name"], "status": record["status"],
                     "bound": entry is not None, "paths": list(entry["paths"]) if entry else [],
                     "plans": count_plans(target, project_id), "plans_store": store})
    return rows


def list_rows(env: Env = None, home: Optional[PathLike] = None) -> List[Dict[str, Any]]:
    """One row per workspace of this machine: code, id, root, remote and the number of projects."""
    from aicore.state import list_workspaces, workspaces_root
    rows = []
    for code in list_workspaces(env, home):
        target = workspaces_root(env, home) / code
        try:
            document = read_workspace(target)
        except WorkspaceError:
            document = None
        rows.append({"code": code, "workspace_id": document["workspace_id"] if document else None, "root": str(target),
                     "remote": gitutil.remote_of(target) if (target / ".git").exists() else None,
                     "projects": len(project_ids(target))})
    return rows


def status(root: Optional[PathLike] = None, fetch: bool = False, env: Env = None,
           home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Layout, git state (no network unless ``fetch``), projects and the last sync of the workspace."""
    target = root_of(root, env, home)
    document = require_initialized(target)
    state = _git_state(target, fetch, env, home) if (target / ".git").exists() else None
    return {"code": document["code"], "root": str(target), "workspace_id": document["workspace_id"], "git": state,
            "projects": project_rows(target, env, home), "last_sync": _last_sync(env, home)}
