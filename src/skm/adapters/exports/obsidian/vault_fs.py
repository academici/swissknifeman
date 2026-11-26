"""Descriptor-relative access to the vault and its private host state."""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Generator, Iterator
from contextlib import ExitStack, contextmanager, suppress
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from random import uniform
from time import monotonic, time
from typing import Literal, override
from uuid import UUID, uuid4

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, ValidationFailed
from skm.kernel.gateways import host_gateway
from skm.kernel.ids import HostId
from skm.modules.exports.domain.contracts import ScanBudget
from skm.modules.exports.domain.vault import VaultIdentity
from skm.modules.exports.ports import VaultFs
from skm.platform.fs.atomic_write import UnsafePathError
from skm.platform.fs.file_lock import FileLock, LockTimeout
from skm.platform.fs.safe_paths import safe_join

__all__ = ["LocalVaultFs"]

_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_READER = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
_TEMP = ".skm-tmp-"


def _unsafe() -> ValidationFailed:
    return ValidationFailed(ErrorCode.INTEGRATION_UNSAFE_TARGET, "Unsafe vault path")


def _open_dir(name: str, parent: int) -> int:
    try:
        return os.open(name, _DIRECTORY, dir_fd=parent)
    except NotADirectoryError as exc:
        if stat.S_ISLNK(os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode):
            raise _unsafe() from exc
        raise


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


class _PublicationUncertain(Exception):
    pass


def _fsync_chain(chain: list[int]) -> None:
    for directory in reversed(chain):
        os.fsync(directory)


@host_gateway
class LocalVaultFs(VaultFs):
    def __init__(self, root: Path, state_dir: Path | None = None) -> None:
        root = root.expanduser()
        if ".." in root.parts or "\x00" in str(root):
            raise _unsafe()
        self.root = root.absolute()
        self.state_dir = state_dir
        self._root_key: tuple[int, int] | None = None

    def at(self, root: str) -> LocalVaultFs:
        return LocalVaultFs(Path(root), self.state_dir)

    def state(self) -> LocalVaultFs:
        if self.state_dir is None:
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "Vault host state is unavailable")
        return self.at(str(self.state_dir / "exports"))

    def _parts(self, rel: str) -> tuple[str, ...]:
        if "\\" in rel or ".." in PurePosixPath(rel).parts:
            raise _unsafe()
        try:
            return safe_join(self.root, rel).relative_to(self.root).parts
        except (UnsafePathError, NotADirectoryError, RuntimeError, ValueError):
            raise _unsafe() from None

    @contextmanager
    def _chain(
        self, parts: tuple[str, ...], *, create: bool = False, create_root: bool = False
    ) -> Generator[list[int]]:
        """Hold ancestors through the durability barrier, starting with the OS root."""
        with ExitStack() as stack:
            chain: list[int] = []
            all_parts = (*self.root.parts[1:], *parts)
            try:
                directory = os.open(self.root.anchor, _DIRECTORY)
                stack.callback(os.close, directory)
                if len(self.root.parts) == 1:
                    chain.append(directory)
                for index, component in enumerate(all_parts, start=2):
                    in_vault = index > len(self.root.parts)
                    try:
                        child = _open_dir(component, directory)
                    except FileNotFoundError:
                        if not ((create and in_vault) or (create_root and index == len(self.root.parts))):
                            raise
                        with suppress(FileExistsError):
                            os.mkdir(component, 0o700, dir_fd=directory)
                        child = _open_dir(component, directory)
                    stack.callback(os.close, child)
                    if index >= len(self.root.parts) - int(create_root):
                        chain.append(child)
                    directory = child
                    if index == len(self.root.parts) and self._root_key is not None:
                        info = os.fstat(child)
                        if (info.st_dev, info.st_ino) != self._root_key:
                            raise _unsafe()
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    raise _unsafe() from None
                raise
            yield chain or [directory]

    def root_key(self) -> tuple[int, int]:
        with self._chain(()) as chain:
            info = os.fstat(chain[-1])
            self._root_key = (info.st_dev, info.st_ino)
            return self._root_key

    @override
    def ensure_identity(self) -> VaultIdentity:
        from .identity import ensure_identity

        return ensure_identity(self)

    def read_identity(self) -> VaultIdentity | None:
        from .identity import read_identity

        return read_identity(self)

    def require_writer(self, host_id: HostId) -> VaultIdentity:
        from .identity import require_writer

        return require_writer(self, host_id)

    def update_identity(self, host_id: HostId, *, fork: bool, deadline_seconds: float) -> VaultIdentity:
        from .identity import update_identity

        return update_identity(self, host_id, fork=fork, deadline_seconds=deadline_seconds)

    @override
    def is_dir(self, rel: str) -> bool:
        try:
            with self._chain(self._parts(rel)):
                return True
        except (FileNotFoundError, NotADirectoryError):
            return False

    def monotonic(self) -> float:
        return monotonic()

    def retry_time(self) -> float:
        return time()

    def retry_jitter(self) -> float:
        return uniform(0.8, 1.2)

    def normalize_locator(self, locator: str) -> str:
        return str(Path(locator).expanduser().resolve())

    def version(self, rel: str) -> tuple[int, ...] | None:
        parts = self._parts(rel)
        try:
            with self._chain(parts[:-1]) as chain:
                info = (
                    os.stat(parts[-1], dir_fd=chain[-1], follow_symlinks=False)
                    if parts
                    else os.fstat(chain[-1])
                )
                if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                    raise _unsafe()
                return _signature(info)
        except FileNotFoundError:
            return None

    def _read(self, rel: str, limit: int, *, head: bool, durable: bool) -> bytes | None:
        parts = self._parts(rel)
        if not parts or limit < 0:
            raise _unsafe()
        try:
            with self._chain(parts[:-1]) as chain:
                parent = chain[-1]
                fd = os.open(parts[-1], _READER, dir_fd=parent)
                with os.fdopen(fd, "rb") as stream:
                    before = os.fstat(fd)
                    if not stat.S_ISREG(before.st_mode):
                        raise _unsafe()
                    data = stream.read(limit if head else limit + 1)
                    if len(data) > limit:
                        raise ValidationFailed(
                            ErrorCode.INTEGRATION_UNSAFE_TARGET, "Vault file exceeds the read limit"
                        )
                    if durable:
                        os.fsync(fd)
                        _fsync_chain(chain)
                    current = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                    self._verify_parent(parts[:-1], parent)
                    if _signature(before) != _signature(current):
                        raise BackendUnavailable(
                            ErrorCode.BACKEND_UNAVAILABLE, "Vault file changed during read"
                        )
                    return data
        except FileNotFoundError:
            return None
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise _unsafe() from None
            raise

    @override
    def read_head(self, rel: str, *, limit: int = 8192) -> bytes | None:
        return self._read(rel, limit, head=True, durable=False)

    @override
    def read_bounded(self, rel: str, *, max_bytes: int, durable: bool = False) -> bytes | None:
        return self._read(rel, max_bytes, head=False, durable=durable)

    @override
    def glob(self, rel_dir: str, pattern: str, *, budget: ScanBudget) -> Iterator[str]:
        parts = self._parts(rel_dir)
        try:
            with self._chain(parts) as chain:
                yield from self._walk(chain[-1], "/".join(parts), pattern, budget)
        except FileNotFoundError:
            return

    def _walk(self, directory: int, rel: str, pattern: str, budget: ScanBudget) -> Iterator[str]:
        with os.scandir(directory) as entries:
            for entry in entries:
                remaining = int(str(budget.get("entries", 10000)))
                deadline = float(str(budget.get("deadline", float("inf"))))
                if remaining <= 0 or monotonic() >= deadline:
                    raise BackendUnavailable(
                        ErrorCode.BACKEND_UNAVAILABLE,
                        "Vault scan budget exceeded",
                        details={"reason": "budget_exceeded"},
                    )
                budget["entries"] = remaining - 1
                if entry.name.startswith(_TEMP):
                    continue
                path = f"{rel}/{entry.name}" if rel else entry.name
                if entry.is_symlink():
                    raise _unsafe()
                if entry.is_dir(follow_symlinks=False):
                    if path.count("/") >= 128:
                        raise _unsafe()
                    if budget.get("include_dirs"):
                        yield path + "/"
                    try:
                        child = os.open(entry.name, _DIRECTORY, dir_fd=directory)
                    except OSError as exc:
                        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                            raise _unsafe() from None
                        raise
                    try:
                        yield from self._walk(child, path, pattern, budget)
                    finally:
                        os.close(child)
                elif entry.is_file(follow_symlinks=False) and fnmatchcase(entry.name, pattern):
                    yield path

    def _verify_parent(self, parts: tuple[str, ...], parent: int) -> None:
        with self._chain(parts) as chain:
            if not os.path.samestat(os.fstat(chain[-1]), os.fstat(parent)):
                raise _unsafe()

    def _publish(self, rel: str, data: bytes, *, replace: bool) -> bool:
        try:
            return self._write(rel, data, replace=replace)
        except _PublicationUncertain as exc:
            outcome, cause = "outcome_unknown", exc.__cause__
        except ValidationFailed as exc:
            raise ValidationFailed(
                exc.code, exc.message, details={**exc.details, "outcome": "failed_without_effect"}
            ) from exc
        except OSError as exc:
            outcome, cause = "failed_without_effect", exc
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE, "Vault publication failed", details={"outcome": outcome}
        ) from cause

    def _write(self, rel: str, data: bytes, *, replace: bool) -> bool:
        parts = self._parts(rel)
        if not parts:
            raise _unsafe()
        with self._chain(parts[:-1], create=True) as chain:
            parent = chain[-1]
            name, temp = parts[-1], _TEMP + uuid4().hex
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            possible_effect = False
            try:
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                        written = os.fstat(stream.fileno())
                    self._verify_parent(parts[:-1], parent)
                    _fsync_chain(chain)
                    if replace:
                        self._check_target(parent, name)
                    possible_effect = True
                    if replace:
                        os.replace(temp, name, src_dir_fd=parent, dst_dir_fd=parent)
                    else:
                        try:
                            os.link(temp, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                        except FileExistsError:
                            possible_effect = False
                        except OSError as exc:
                            if exc.errno in (
                                errno.EXDEV,
                                errno.ENOTSUP,
                                errno.EPERM,
                                errno.EACCES,
                                errno.EROFS,
                            ):
                                possible_effect = False
                            raise
                    if possible_effect:
                        actual = os.stat(name, dir_fd=parent, follow_symlinks=False)
                        if not os.path.samestat(written, actual) or written.st_size != actual.st_size:
                            raise _unsafe()
                finally:
                    with suppress(FileNotFoundError):
                        os.unlink(temp, dir_fd=parent)
                _fsync_chain(chain)
                self._verify_parent(parts[:-1], parent)
            except (OSError, ValidationFailed) as exc:
                if possible_effect:
                    raise _PublicationUncertain from exc
                raise
            return possible_effect

    @staticmethod
    def _check_target(parent: int, name: str) -> None:
        with suppress(FileNotFoundError):
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise _unsafe()

    @override
    def create_new(self, rel: str, data: bytes) -> bool:
        return self._publish(rel, data, replace=False)

    @override
    def write_atomic(self, rel: str, data: bytes, *, replace: Literal[True]) -> None:
        if replace is not True:
            raise ValueError("Vault replacement requires explicit permission")
        self._publish(rel, data, replace=True)

    def prepare_state(self) -> None:
        with self._chain((), create_root=True) as chain:
            info = os.fstat(chain[-1])
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise _unsafe()
            _fsync_chain(chain)

    def validate_state(self) -> None:
        with self._chain(()) as chain:
            info = os.fstat(chain[-1])
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise _unsafe()

    @contextmanager
    def state_lock(self, name: str, deadline_seconds: float) -> Generator[None]:
        self.prepare_state()
        try:
            with FileLock(self.root / name).hold(timeout_seconds=deadline_seconds):
                yield
        except LockTimeout:
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "Vault lock timed out") from None

    @override
    def lock(self, vault_id: UUID, *, deadline_seconds: float):
        return self.state().state_lock(f"vault-{vault_id}.lock", deadline_seconds)

    def probe(self) -> None:
        """Verify exclusivity, durable reads and no-follow on this backend."""
        name = _TEMP + "probe-" + uuid4().hex
        symlink = name + "-link"
        with self._chain(()) as chain, ExitStack() as cleanup:
            parent = chain[-1]
            cleanup.callback(os.fsync, parent)
            try:
                if not self.create_new(name, b"probe"):
                    raise OSError("probe collision")
                cleanup.callback(os.unlink, name, dir_fd=parent)
                if (
                    self.create_new(name, b"collision")
                    or self.read_bounded(name, max_bytes=5, durable=True) != b"probe"
                ):
                    raise OSError("exclusive publication unavailable")
                os.symlink(name, symlink, dir_fd=parent)
                cleanup.callback(os.unlink, symlink, dir_fd=parent)
                try:
                    fd = os.open(symlink, _READER, dir_fd=parent)
                except OSError as exc:
                    if exc.errno != errno.ELOOP:
                        raise
                else:
                    os.close(fd)
                    raise OSError("no-follow unavailable")
            except (OSError, BackendUnavailable) as exc:
                raise BackendUnavailable(
                    ErrorCode.BACKEND_UNAVAILABLE, "Unsupported vault filesystem"
                ) from exc
