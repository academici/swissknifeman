"""Raw byte snapshots and typed v2 candidate/output identity (adapters §3.6)."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution.domain.output import ChangedPath, OutputMount, output_tree_digest

from .host_inputs import CheckoutDescriptor, capture_checkout, read_metadata
from .status import encode_path, tree_entries, validate_path

if TYPE_CHECKING:
    from .runner import GitRunner

__all__ = ["candidate", "inventory", "output_digest", "path_fingerprint", "raw_entry", "snapshot_entries"]


def digest(payload: object) -> str:
    raw = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def busy() -> None:
    raise error_for(ErrorCode.CHECKOUT_BUSY, "checkout changed during raw snapshot")


def _stamp(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def raw_entry(root: Path, path: bytes) -> tuple[str, bytes] | None:
    """Open every parent without following symlinks and verify bytes/metadata after reading."""
    parts = validate_path(path).split(b"/")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for part in parts[:-1]:
            try:
                following = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory
                )
            except FileNotFoundError:
                return None
            os.close(directory)
            directory = following
        name = parts[-1]
        try:
            before = os.stat(name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(before.st_mode):
            data = os.readlink(name, dir_fd=directory)
            mode = "120000"
        elif stat.S_ISREG(before.st_mode):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            with os.fdopen(fd, "rb") as stream:
                if _stamp(os.fstat(stream.fileno())) != _stamp(before):
                    busy()
                data = stream.read()
                if _stamp(os.fstat(stream.fileno())) != _stamp(before):
                    busy()
            mode = "100755" if before.st_mode & 0o111 else "100644"
        else:
            raise ValueError("unsupported file type or nested repository")
        if _stamp(before) != _stamp(os.stat(name, dir_fd=directory, follow_symlinks=False)):
            busy()
        return mode, data
    finally:
        os.close(directory)


def object_format(git: GitRunner, root: Path) -> Literal["sha1", "sha256"]:
    value = git.run(root, ["rev-parse", "--show-object-format"]).stdout.strip()
    if value not in {"sha1", "sha256"}:
        raise ValueError("unsupported Git object format")
    return cast("Literal['sha1', 'sha256']", value)


def path_fingerprint(root: Path, path: bytes, *, git: GitRunner | None = None, write: bool = False) -> str:
    from .runner import GitRunner

    runner = git if git is not None else GitRunner()
    entry = raw_entry(root, path)
    if entry is None:
        return "absent"
    mode, data = entry
    argv = ["hash-object", "--no-filters", "--stdin"]
    if write:
        argv.append("-w")
    oid = runner.run_bytes(root, argv, stdin=data).stdout.strip().decode("ascii")
    return mode + " " + oid


def inventory(git: GitRunner, root: Path) -> tuple[bytes, ...]:
    # Reject nested repositories, including ones hidden by ignore rules, before object writes.
    for directory, dirs, files in os.walk(root, followlinks=False):
        if Path(directory) != root and (".git" in dirs or ".git" in files):
            raise ValueError("nested repositories are unsupported")
        if ".git" in dirs:
            dirs.remove(".git")
    tree_entries(git, root, "HEAD")  # rejects gitlinks before taking the snapshot
    raw = git.run_bytes(root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]).stdout
    return tuple(sorted({validate_path(path) for path in raw.split(b"\0") if path}))


@dataclass(frozen=True)
class Candidate:
    head: str
    object_format: str
    entries: tuple[tuple[bytes, str], ...]
    digest: str


def candidate(root: Path, paths: Iterable[bytes], *, git: GitRunner | None = None) -> Candidate:
    from .runner import GitRunner

    runner = git if git is not None else GitRunner()
    binding = capture_checkout(root)
    head = runner.run(root, ["rev-parse", "--verify", "HEAD"]).stdout.strip()
    fmt = object_format(runner, root)
    entries = tuple((p, path_fingerprint(root, p, git=runner)) for p in sorted(set(paths)))
    binding.verify()
    return Candidate(
        head, fmt, entries, digest(["skm-candidate-v2", fmt, [[encode_path(p), f] for p, f in entries]])
    )


@dataclass(frozen=True)
class CheckoutGuard:
    binding: CheckoutDescriptor
    head: bytes
    index: bytes | None

    def verify(self, git: GitRunner) -> None:
        self.binding.verify()
        if checkout_guard(git, Path(self.binding.root)) != self:
            busy()


def checkout_guard(git: GitRunner, root: Path) -> CheckoutGuard:
    binding = capture_checkout(root)
    index = Path(binding.git_dir) / "index"
    head = git.run_bytes(root, ["rev-parse", "--verify", "HEAD"]).stdout
    index_bytes = read_metadata(index) if index.exists() else None
    return CheckoutGuard(binding, head, index_bytes)


def snapshot_entries(git: GitRunner, root: Path) -> tuple[CheckoutGuard, dict[bytes, str]]:
    guard = checkout_guard(git, root)
    paths = inventory(git, root)
    entries = {p: path_fingerprint(root, p, git=git, write=True) for p in paths}
    guard.verify(git)
    if paths != inventory(git, root) or any(
        path_fingerprint(root, p, git=git) != f for p, f in entries.items()
    ):
        busy()
    guard.verify(git)
    return guard, entries


def output_digest(
    mounts: Iterable[OutputMount], paths: Iterable[ChangedPath], *, algorithm: str = "skm-output-v2"
) -> str:
    return output_tree_digest(mounts, paths, algorithm=algorithm)


def verify_entries(git: GitRunner, root: Path, guard: CheckoutGuard, entries: Mapping[bytes, str]) -> None:
    guard.verify(git)
    if set(inventory(git, root)) != set(entries) or any(
        path_fingerprint(root, p, git=git) != f for p, f in entries.items()
    ):
        busy()
    guard.verify(git)
