"""The git remote of the workspace: ``connect`` (classify a remote, then only add ``origin``) and ``clone`` (make the
workspace of this machine from a remote). Neither commits or pushes. Every URL shown or recorded in a message is
redacted (no user information); git never asks for a password (``gitutil.network_env``)."""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from aicore.workspace import WorkspaceError, read_workspace, redact_remote

from . import gitutil, layout

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]

EMPTY, SAME = "empty", "same"
NEXT_PUSH = "swissknifeman workspace sync --push"
NEXT_SCAN = "swissknifeman workspace project scan ~/projects"


def _check_url(url: str) -> str:
    text = (url or "").strip()
    if not text or text.startswith("-") or any(ch in text for ch in "\n\r\0"):
        raise ValueError("a remote URL is required and must not start with '-'")
    return text


def _heads(url: str, cwd: Path, env: Env) -> List[str]:
    done = gitutil.network(["ls-remote", "--heads", "--", url], cwd, "ls-remote", env)
    names = []
    for line in done.stdout.splitlines():
        _, _, ref = line.partition("\t")
        if ref.startswith("refs/heads/"):
            names.append(ref[len("refs/heads/"):])
    return names


def _read_remote_workspace(path: Path, shown: str, branch: str) -> Dict[str, Any]:
    """``workspace.json`` of a checkout of the remote; ``REMOTE_FOREIGN`` when it is missing or invalid."""
    try:
        document = read_workspace(path)
    except WorkspaceError:
        document = None
    if document is None:
        raise WorkspaceError("REMOTE_FOREIGN", f"{shown} branch {branch} holds no valid workspace.json; it is not a "
                             f"workspace repository and is not connected")
    return document


def classify(url: str, branch: str, root: Path, env: Env = None) -> Dict[str, Any]:
    """What ``url`` holds relative to the workspace at ``root``: ``{"kind": "empty"|"same", "branch"}``.

    ``REMOTE_FOREIGN`` (no ``workspace.json``, or the branch is absent), ``REMOTE_OTHER_WORKSPACE`` (another
    ``workspace_id``), ``REMOTE_UNREACHABLE`` (network or authentication). The temporary shallow clone lives in
    ``.staging/connect-<id>`` and is removed in every case."""
    url = _check_url(url)
    shown = redact_remote(url)
    local = layout.require_initialized(root)
    heads = _heads(url, root, env)
    if not heads:
        return {"kind": EMPTY, "branch": branch}
    if branch not in heads:
        raise WorkspaceError("REMOTE_FOREIGN", f"{shown} has no branch {branch} (it has: {', '.join(sorted(heads))}); "
                             f"choose it with --branch")
    staging = root / ".staging"
    staging.mkdir(exist_ok=True)
    scratch = staging / f"connect-{uuid.uuid4().hex[:12]}"
    try:
        gitutil.network(["clone", "-q", "--depth", "1", "--branch", branch, "--no-tags", "--", url, str(scratch)],
                        root, "clone", env)
        remote = _read_remote_workspace(scratch, shown, branch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if remote["workspace_id"] != local["workspace_id"]:
        raise WorkspaceError("REMOTE_OTHER_WORKSPACE", f"{shown} holds another workspace ({remote['workspace_id']}, this "
                             f"one is {local['workspace_id']}); to use it on this machine run `swissknifeman workspace "
                             f"clone <URL>` into an empty folder")
    return {"kind": SAME, "branch": branch}


def connect(url: str, branch: Optional[str] = None, root: Optional[PathLike] = None, env: Env = None,
            home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Classify ``url`` and, only when it is ``empty`` or ``same``, add it as ``origin``. Nothing else in the git
    configuration changes; nothing is committed or pushed."""
    target = layout.root_of(root, env, home)
    layout.require_initialized(target)
    url = _check_url(url)
    gitutil.require_version()
    current = gitutil.git(["symbolic-ref", "--short", "-q", "HEAD"], target).stdout.strip() or "main"
    wanted = branch or current
    if wanted != current:
        raise ValueError(f"--branch {wanted} differs from the workspace branch {current}; the workspace pushes its own "
                         f"branch")
    if gitutil.remote_of(target) is not None or gitutil.git(["remote", "get-url", "origin"], target).returncode == 0:
        raise WorkspaceError("REMOTE_ALREADY_SET", f"this workspace already has a remote ({gitutil.remote_of(target)})")
    found = classify(url, wanted, target, env)
    with gitutil.git_lock(env, home):
        if gitutil.git(["remote", "get-url", "origin"], target).returncode == 0:
            raise WorkspaceError("REMOTE_ALREADY_SET", "this workspace already has a remote")
        gitutil.require(gitutil.git(["remote", "add", "origin", "--", url], target), "remote add")
    return {"root": str(target), "remote": redact_remote(url), "branch": wanted, "classification": found["kind"],
            "next": NEXT_PUSH}


def clone(url: str, root: Optional[PathLike] = None, env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Make the workspace of this machine from ``url``: the target is absent or empty (else
    ``WORKSPACE_ROOT_NOT_EMPTY``), the clone must hold a valid ``workspace.json`` (else ``REMOTE_FOREIGN`` and nothing is
    left behind), the device is created when this machine has none and never overwritten."""
    target = layout.root_of(root, env, home)
    url = _check_url(url)
    shown = redact_remote(url)
    if target.exists() or target.is_symlink():
        if not target.is_dir() or target.is_symlink() or any(target.iterdir()):
            raise WorkspaceError("WORKSPACE_ROOT_NOT_EMPTY", f"{target} is not empty; choose an absent or empty folder "
                                 f"(SKM_WORKSPACE_ROOT or --root)")
    gitutil.require_version()
    existed = target.exists()
    with gitutil.git_lock(env, home):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            gitutil.network(["clone", "-q", "--", url, str(target)], target.parent, "clone", env)
            document = _read_remote_workspace(target, shown, "HEAD")
            device = layout._ensure_device(env, home)
            (target / ".staging").mkdir(exist_ok=True)
        except BaseException:
            layout._clean_partial(target, existed)
            raise
    branch = gitutil.git(["symbolic-ref", "--short", "-q", "HEAD"], target).stdout.strip() or None
    return {"root": str(target), "workspace_id": document["workspace_id"], "device_id": device["device_id"],
            "remote": shown, "branch": branch, "next": NEXT_SCAN}
