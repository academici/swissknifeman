"""Managed project artifacts: the launcher written from the hub template and its lock.

:func:`plan_sync` compares a project with the template and returns the exact actions (create, update, unchanged,
refused); :func:`apply_sync` carries them out under the project sync lock, each file replaced crash-safely
(:func:`aicore.util.io.durable_replace`). User files (config, state, plans) and unknown files are never touched.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from aicore.state import backup, require_project_path
from aicore.state.invocation import (LAUNCHER_PROTOCOL, LOCK_NAME, LOCK_SCHEMA, LauncherError, launcher_file,
                                     lock_file, read_lock)
from aicore.state.locations import PROJECT_DIRNAME
from aicore.util.io import durable_replace

TEMPLATE = Path(__file__).resolve().parents[3] / "templates" / "project" / "launcher.py"
MANAGED = (f"{PROJECT_DIRNAME}/launcher.py",)
SYNC_LOCK = "project-sync.lock"
# Digests of earlier templates of the current protocol that `verify` still accepts without a warning; empty while the
# first template is the only one.
COMPATIBLE_DIGESTS: tuple = ()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def template_bytes() -> bytes:
    try:
        return TEMPLATE.read_bytes()
    except OSError as exc:
        raise LauncherError("LAUNCHER_TEMPLATE_MISSING", f"{TEMPLATE}: {exc.__class__.__name__}; reinstall swissknifeman") from exc


def lock_doc(digest: str) -> Dict[str, Any]:
    return {"$schema": LOCK_SCHEMA, "protocol": LAUNCHER_PROTOCOL, "template_sha256": digest,
            "managed_files": list(MANAGED)}


def lock_text(digest: str) -> bytes:
    return (json.dumps(lock_doc(digest), indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _file_digest(path: Path) -> Optional[str]:
    try:
        return sha256(path.read_bytes())
    except OSError:
        return None


def plan_sync(root: Path, *, adopt: bool = False) -> Dict[str, Any]:
    """What a sync of ``root`` would do: ``{template_sha256, actions: [{path, action, code?, reason?}]}``.

    The launcher is ours when its digest is the one the lock records (any older template) or a known template; then a
    different template replaces it. A file that matches neither is foreign (``FOREIGN_LAUNCHER``) and is replaced only
    with ``adopt`` (a backup is kept). A symlink in the place of a managed file is always refused.
    """
    data = template_bytes()
    digest = sha256(data)
    try:
        lock = read_lock(root)
    except LauncherError:
        lock = None  # an unreadable lock is rewritten; the launcher decides ownership by itself
    known = {digest, *COMPATIBLE_DIGESTS} | ({str(lock.get("template_sha256"))} if lock else set())
    actions: List[Dict[str, Any]] = []
    launcher = launcher_file(root)
    if launcher.is_symlink() or (launcher.exists() and not launcher.is_file()):
        actions.append({"path": MANAGED[0], "action": "refused", "code": "LAUNCHER_SYMLINK_FORBIDDEN"
                        if launcher.is_symlink() else "LAUNCHER_NOT_REGULAR", "reason": "not a regular file"})
    else:
        current = _file_digest(launcher) if launcher.exists() else None
        if current is None:
            actions.append({"path": MANAGED[0], "action": "create"})
        elif current == digest:
            actions.append({"path": MANAGED[0], "action": "unchanged"})
        elif current in known or adopt:
            actions.append({"path": MANAGED[0], "action": "update", "backup": current not in known})
        else:
            actions.append({"path": MANAGED[0], "action": "refused", "code": "FOREIGN_LAUNCHER",
                            "reason": "the file is not a launcher this hub wrote; pass --adopt to replace it (a backup "
                                      "is kept)"})
    lock_path = lock_file(root)
    wanted = lock_text(digest)
    if lock_path.is_symlink():
        actions.append({"path": f"{PROJECT_DIRNAME}/{LOCK_NAME}", "action": "refused",
                        "code": "LAUNCHER_SYMLINK_FORBIDDEN", "reason": "not a regular file"})
    elif not lock_path.exists():
        actions.append({"path": f"{PROJECT_DIRNAME}/{LOCK_NAME}", "action": "create"})
    else:
        try:
            same = lock_path.read_bytes() == wanted
        except OSError:
            same = False
        actions.append({"path": f"{PROJECT_DIRNAME}/{LOCK_NAME}", "action": "unchanged" if same else "update"})
    return {"template_sha256": digest, "actions": actions}


class _SyncLock:
    """``.swissknifeman/project-sync.lock``: created exclusively, holds pid, host, start and operation id; removed on
    exit. A lock of a dead process on this host is taken over; any other lock is ``PROJECT_SYNC_LOCKED``."""

    def __init__(self, root: Path):
        self.path = root / PROJECT_DIRNAME / SYNC_LOCK
        self.doc = {"pid": os.getpid(), "host": socket.gethostname(), "started": int(time.time()),
                    "operation": uuid.uuid4().hex}

    def _stale(self) -> bool:
        try:
            held = json.loads(self.path.read_text(encoding="utf-8"))
            pid, host = int(held["pid"]), str(held["host"])
        except (OSError, ValueError, KeyError, TypeError):
            return False  # unreadable: maybe being written right now; never removed by guess
        if host != socket.gethostname():
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def __enter__(self) -> "_SyncLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _attempt in range(2):
            try:
                handle = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            except FileExistsError:
                if _attempt == 0 and self._stale():
                    self.path.unlink(missing_ok=True)
                    continue
                raise LauncherError("PROJECT_SYNC_LOCKED", f"another project sync holds {self.path}") from None
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self.doc, stream)
            return self
        raise LauncherError("PROJECT_SYNC_LOCKED", f"another project sync holds {self.path}")

    def __exit__(self, *exc: Any) -> None:
        self.path.unlink(missing_ok=True)


def apply_sync(root: Path, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Carry out a :func:`plan_sync` result; the launcher first, the lock last (a lock never names a launcher that is
    not on disk). Refused actions stay refused; the result is the plan with ``applied`` set."""
    data = template_bytes()
    if sha256(data) != plan["template_sha256"]:
        raise LauncherError("LAUNCHER_TEMPLATE_CHANGED", "the hub template changed during the sync; run it again")
    by_path = {item["path"]: item for item in plan["actions"]}
    with _SyncLock(root):
        launcher = by_path.get(MANAGED[0])
        if launcher and launcher["action"] in ("create", "update"):
            target = require_project_path(root, launcher_file(root))
            if launcher.get("backup"):
                launcher["backup_path"] = str(backup(target, project=root))
            durable_replace(target, data, mode=0o755)
        lock = by_path.get(f"{PROJECT_DIRNAME}/{LOCK_NAME}")
        refused = any(item["action"] == "refused" for item in plan["actions"])
        if lock and lock["action"] in ("create", "update"):
            if refused:  # the launcher was not written: a new lock would claim a file this hub does not own
                lock.update(action="refused", code="LAUNCHER_NOT_SYNCED", reason="the launcher was refused")
            else:
                durable_replace(require_project_path(root, lock_file(root)), lock_text(plan["template_sha256"]), mode=0o644)
    return {**plan, "applied": True}
