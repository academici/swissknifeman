"""Private durable process journals shared by host adapters; PID facts never prove containment."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from skm.platform.fs.atomic_write import atomic_write, fsync_dir
from skm.platform.fs.file_lock import FileLock
from skm.platform.process.identity import ProcessIdentity

__all__ = ["boot_id", "claim_marker", "create_marker", "read_marker", "remove_marker", "update_marker"]


def boot_id() -> str | None:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip() or None
    except FileNotFoundError:
        return None


def _document(ownership: Mapping[str, Any]) -> dict[str, Any]:
    # Adapters supply their admitted ownership record. The platform preserves its opaque identity;
    # it does not import or reconstruct any module's domain types.
    return cast("dict[str, Any]", json.loads(json.dumps(dict(ownership), default=str)))


def _target(identity_dir: Path, ownership: Mapping[str, Any]) -> Path:
    owner = ownership["owner"]
    if identity_dir.resolve() != Path(owner["identity_dir"]).resolve():
        raise ValueError("marker directory differs from admitted owner")
    identity_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = identity_dir.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError("ownership directory must be private and owned")
    return identity_dir / f"{UUID(str(owner['unit_id']))}.json"


def create_marker(identity_dir: Path, ownership: Mapping[str, Any]) -> Path:
    path = _target(identity_dir, ownership)
    data = {**_document(ownership), "boot_id": boot_id()}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as target:
        target.write(json.dumps(data, separators=(",", ":")))
        target.flush()
        os.fsync(target.fileno())
    fsync_dir(identity_dir)
    return path


def read_marker(path: Path) -> dict[str, Any]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("unsafe ownership marker")
        raw = source.read(16_385)
    if len(raw) > 16_384:
        raise ValueError("oversized ownership marker")
    data: object = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("ownership marker must be an object")
    return cast("dict[str, Any]", data)


def _require_binding(data: Mapping[str, Any], ownership: Mapping[str, Any]) -> dict[str, Any]:
    expected = _document(ownership)
    # Journal metadata (boot/process/launching) is separate from the complete ownership identity.
    if {key: data.get(key) for key in expected} != expected:
        raise ValueError("ownership marker belongs to another launch")
    return expected


def claim_marker(identity_dir: Path, ownership: Mapping[str, Any]) -> Path:
    """Accept only the admitted prepared identity and durably exclude a second launch."""
    path = _target(identity_dir, ownership)
    with FileLock(path.with_suffix(".launch.lock")).hold(timeout_seconds=1):
        try:
            create_marker(identity_dir, ownership)
        except FileExistsError:
            _require_binding(read_marker(path), ownership)
        data = read_marker(path)
        if data.get("launching") or data.get("process") is not None:
            raise ValueError("ownership marker already launched or uncertain")
        data["launching"] = True
        atomic_write(path, json.dumps(data).encode(), mode=0o600, private=True)
    return path


def update_marker(
    path: Path, identity: ProcessIdentity, *, pgid: int | None, ownership: Mapping[str, Any]
) -> None:
    bound = _require_binding(read_marker(path), ownership)
    data = {**bound, "boot_id": identity.boot_id, "process": {**asdict(identity), "pgid": pgid}}
    atomic_write(path, json.dumps(data).encode(), mode=0o600, private=True)


def remove_marker(path: Path) -> None:
    """Remove a confirmed stopped unit's record and launch lock; callers own the reap proof."""
    path.unlink()
    path.with_suffix(".launch.lock").unlink(missing_ok=True)
    fsync_dir(path.parent)
