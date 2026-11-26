"""Bounded document reads beneath a pinned local checkout descriptor."""

from __future__ import annotations

import errno
import os
import stat
from contextlib import ExitStack, contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.exports.domain.docs_push import sensitive

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator

__all__ = ["LocalDocsCheckoutFs"]

_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class _ReadBudget(Protocol):
    @property
    def remaining(self) -> int: ...

    def check(self, *, size: int = 0) -> None: ...


def _refused(reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.INTEGRATION_UNSAFE_TARGET, "Checkout document refused", details={"reason": reason}
    )


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _version(info: os.stat_result) -> tuple[int, ...]:
    return (*_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _directory(start: int, parts: tuple[str, ...], protected: set[tuple[int, int]]) -> Generator[int]:
    directory = os.dup(start)
    try:
        for part in parts:
            child = os.open(part, _DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = child
            if _identity(os.fstat(directory)) in protected:
                raise _refused("protected_path")
        yield directory
    finally:
        os.close(directory)


def _read_file(fd: int, before: os.stat_result, max_bytes: int, budget: _ReadBudget) -> bytes:
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise _refused("unsafe_path")
    if before.st_size > max_bytes:
        raise _refused("file_too_large")
    if before.st_size > budget.remaining:
        budget.check(size=before.st_size)
    limit = min(max_bytes + 1, budget.remaining)
    data = bytearray()
    while len(data) < limit:
        budget.check()
        block = os.read(fd, min(65536, limit - len(data)))
        budget.check(size=len(block))
        if not block:
            break
        data.extend(block)
    after = os.fstat(fd)
    if _version(after) != _version(before) or len(data) != before.st_size:
        raise _refused("source_changed")
    return bytes(data)


class _Tree:
    def __init__(self, fd: int, root: Path, protected: set[Path], identities: set[tuple[int, int]]) -> None:
        self.fd, self.root, self.protected, self.identities = fd, root, protected, identities

    def entries(
        self, visit: Callable[[], None], exclude: Callable[[str], bool]
    ) -> Iterator[tuple[str, str | None]]:
        pending: list[tuple[str, ...]] = [()]
        while pending:
            parts = pending.pop()
            try:
                with _directory(self.fd, parts, self.identities) as directory, os.scandir(directory) as scan:
                    for entry in scan:
                        visit()
                        child = (*parts, entry.name)
                        path = "/".join(child)
                        if exclude(entry.name):
                            yield path, "sensitive_path"
                        elif self.root.joinpath(*child) in self.protected:
                            yield path, "protected_path"
                        elif entry.is_dir(follow_symlinks=False):
                            if len(path) < 1024:
                                pending.append(child)
                        else:
                            yield path, None if entry.is_file(follow_symlinks=False) else "unsafe_path"
            except OSError:
                if not parts:
                    raise _refused("source_unavailable") from None
                yield "/".join(parts), "source_unavailable"
            except ValidationFailed as error:
                if error.code is not ErrorCode.INTEGRATION_UNSAFE_TARGET:
                    raise
                yield "/".join(parts), "protected_path"

    def read(self, path: str, max_bytes: int, budget: _ReadBudget) -> bytes:
        parts = tuple(path.split("/"))
        if any(part in {"", ".", ".."} or sensitive(part) for part in parts) or any(
            self.root.joinpath(*parts).is_relative_to(root) for root in self.protected
        ):
            raise _refused("unsafe_path")
        parents, leaf = parts[:-1], parts[-1]
        try:
            with _directory(self.fd, parents, self.identities) as parent:
                fd = os.open(leaf, _FILE, dir_fd=parent)
                try:
                    before = os.fstat(fd)
                    data = _read_file(fd, before, max_bytes, budget)
                    self._verify_path(parents, parent, leaf, before)
                    return data
                finally:
                    os.close(fd)
        except OSError as error:
            reason = "unsafe_path" if error.errno in {errno.ELOOP, errno.ENOTDIR} else "source_unavailable"
            raise _refused(reason) from None

    def _verify_path(self, parents: tuple[str, ...], parent: int, leaf: str, before: os.stat_result) -> None:
        with _directory(self.fd, parents, self.identities) as current:
            if not os.path.samestat(os.fstat(parent), os.fstat(current)) or _version(
                os.stat(leaf, dir_fd=current, follow_symlinks=False)
            ) != _version(before):
                raise _refused("source_changed")


class LocalDocsCheckoutFs:
    def __init__(self, protected_roots: tuple[Path, ...]) -> None:
        self.protected_roots = protected_roots

    @contextmanager
    def open_checkout(self, locator: str, *, vault_root: str) -> Generator[_Tree]:
        root = Path(locator)
        protected: set[Path] = set()
        identities: set[tuple[int, int]] = set()
        with ExitStack() as stack:
            try:
                for configured in (*self.protected_roots, Path(vault_root)):
                    resolved = configured.resolve()
                    protected.update((configured.absolute(), resolved))
                    with suppress(FileNotFoundError):
                        identities.add(_identity(resolved.stat()))
                if (
                    root.anchor != "/"
                    or any(part == ".." or sensitive(part) for part in root.parts[1:])
                    or any(root.is_relative_to(path) for path in protected)
                ):
                    raise _refused("unsafe_path")
                anchor = os.open(root.anchor, _DIRECTORY)
                stack.callback(os.close, anchor)
                directory = stack.enter_context(_directory(anchor, root.parts[1:], identities))
            except (OSError, ValueError):
                raise _refused("source_unavailable") from None
            yield _Tree(directory, root, protected, identities)
