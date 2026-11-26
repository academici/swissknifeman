"""Local checkout filesystem adapter with symlink/containment/CAS guards (integrations §6.2)."""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, Conflict, SkmError, error_for
from skm.modules.integrations.domain.decisions import is_safe_relative_path
from skm.modules.integrations.domain.filesystem import FileStat
from skm.modules.integrations.domain.observed import FileKind
from skm.modules.integrations.domain.ownership import sha256_tagged
from skm.platform.fs.atomic_write import UnsafePathError, assert_safe_replace_target, atomic_write, fsync_dir
from skm.platform.fs.file_lock import FileLock, LockTimeout
from skm.platform.process import runner as process_runner

__all__ = ["LocalCheckoutFs"]


@dataclass(frozen=True, slots=True)
class _EntryState:
    safe: bool
    outside_root: bool
    file_kind: FileKind
    is_symlink: bool
    size: int
    leaf: Path | None
    mode: int | None


def _has_git_segment(relative_path: str) -> bool:
    return any(segment.lower() == ".git" for segment in relative_path.split("/"))


def _unsafe_error(relative_path: str, reason: str) -> SkmError:
    return error_for(
        ErrorCode.INTEGRATION_UNSAFE_TARGET,
        f"unsafe checkout target {relative_path!r} ({reason})",
        details={"relative_path": relative_path, "reason": reason},
    )


def _race_conflict(
    relative_path: str,
    *,
    expected_whole_digest: str | None,
    actual_whole_digest: str | None,
) -> Conflict:
    return Conflict(
        ErrorCode.PROJECTION_CONFLICT,
        f"concurrent modification detected at {relative_path!r}",
        details={
            "reason": "race",
            "relative_path": relative_path,
            "expected_whole_digest": expected_whole_digest,
            "actual_whole_digest": actual_whole_digest,
        },
    )


class LocalCheckoutFs:
    """``CheckoutFs`` bound to a checkout root with per-binding locks and crash journals."""

    root: Path

    def __init__(
        self,
        root: Path | str,
        *,
        state_dir: Path | str | None = None,
        git_binary: str = "git",
        lock_timeout_seconds: float | None = 30.0,
    ) -> None:
        self.root = Path(root)
        self._state_dir = None if state_dir is None else Path(state_dir)
        self._git_binary = git_binary
        self._lock_timeout_seconds = lock_timeout_seconds

    def for_checkout(self, local_locator: Path | str) -> LocalCheckoutFs:
        """Bind a fresh ``LocalCheckoutFs`` to ``local_locator`` preserving state/git settings."""
        return LocalCheckoutFs(
            Path(local_locator),
            state_dir=self._state_dir,
            git_binary=self._git_binary,
            lock_timeout_seconds=self._lock_timeout_seconds,
        )

    def _state_root(self) -> Path:
        if self._state_dir is None:
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "Checkout host state is unavailable")
        return self._state_dir / "integrations"

    def _inspect_root(self) -> Path | None:
        if self.root.parts[:2] == ("/", ".skm-checkout"):
            return None
        try:
            rst = self.root.lstat()
        except OSError:
            return None
        if stat.S_ISLNK(rst.st_mode) or not stat.S_ISDIR(rst.st_mode):
            return None
        try:
            return self.root.resolve(strict=True)
        except OSError:
            return None

    @staticmethod
    def _classify_leaf(leaf: Path) -> _EntryState:
        try:
            lst = leaf.lstat()
        except FileNotFoundError:
            return _EntryState(True, False, FileKind.MISSING, False, 0, leaf, None)
        except OSError:
            return _EntryState(False, False, FileKind.OTHER, False, 0, leaf, None)

        mode = lst.st_mode
        if stat.S_ISLNK(mode):
            return _EntryState(False, False, FileKind.SYMLINK, True, lst.st_size, leaf, None)
        if stat.S_ISDIR(mode):
            return _EntryState(False, False, FileKind.DIRECTORY, False, 0, leaf, None)
        if stat.S_ISFIFO(mode):
            return _EntryState(False, False, FileKind.FIFO, False, 0, leaf, None)
        if not stat.S_ISREG(mode) or lst.st_nlink > 1:
            return _EntryState(False, False, FileKind.OTHER, False, lst.st_size, leaf, None)
        return _EntryState(True, False, FileKind.REGULAR, False, lst.st_size, leaf, stat.S_IMODE(mode))

    def _inspect(self, relative_path: str) -> _EntryState:
        resolved_root = (
            None
            if not is_safe_relative_path(relative_path) or _has_git_segment(relative_path)
            else self._inspect_root()
        )
        if resolved_root is None:
            return _EntryState(False, True, FileKind.OTHER, False, 0, None, None)

        segments = relative_path.split("/")
        cur = self.root
        for seg in segments[:-1]:
            cur = cur / seg
            try:
                pst = cur.lstat()
            except FileNotFoundError:
                return _EntryState(
                    True, False, FileKind.MISSING, False, 0, self.root.joinpath(*segments), None
                )
            except OSError:
                return _EntryState(False, True, FileKind.OTHER, False, 0, None, None)
            if stat.S_ISLNK(pst.st_mode):
                return _EntryState(False, True, FileKind.SYMLINK, True, 0, None, None)
            if not stat.S_ISDIR(pst.st_mode):
                return _EntryState(False, False, FileKind.OTHER, False, 0, None, None)

        try:
            resolved_parent = cur.resolve(strict=True)
        except OSError:
            return _EntryState(False, True, FileKind.OTHER, False, 0, None, None)
        if not resolved_parent.is_relative_to(resolved_root):
            return _EntryState(False, True, FileKind.OTHER, False, 0, None, None)
        return self._classify_leaf(cur / segments[-1])

    def _read_regular_nofollow(self, leaf: Path, relative_path: str) -> tuple[bytes | None, int | None]:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            fd = os.open(leaf, flags)
        except FileNotFoundError:
            return None, None
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.EISDIR, errno.ENOTDIR):
                raise _unsafe_error(relative_path, "nofollow_rejected") from exc
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                f"failed opening checkout file {relative_path!r}",
                details={"relative_path": relative_path},
            ) from exc
        try:
            fst = os.fstat(fd)
            if not stat.S_ISREG(fst.st_mode) or fst.st_nlink > 1:
                raise _unsafe_error(relative_path, "not_single_regular_file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks), stat.S_IMODE(fst.st_mode)
        except OSError as exc:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                f"failed reading checkout file {relative_path!r}",
                details={"relative_path": relative_path},
            ) from exc
        finally:
            os.close(fd)

    def observe_entry(self, relative_path: str) -> tuple[FileKind, bytes | None, bool, bool]:
        """Inspect and read ``relative_path`` without following symlinks."""
        state = self._inspect(relative_path)
        if not state.safe:
            return state.file_kind, None, state.is_symlink, state.outside_root
        if state.file_kind is FileKind.MISSING or state.leaf is None:
            return FileKind.MISSING, None, False, False
        try:
            raw, _ = self._read_regular_nofollow(state.leaf, relative_path)
        except SkmError as exc:
            if exc.code is ErrorCode.INTEGRATION_UNSAFE_TARGET:
                return FileKind.SYMLINK, None, True, False
            raise
        if raw is None:
            return FileKind.MISSING, None, False, False
        return FileKind.REGULAR, raw, False, False

    def stat(self, relative_path: str) -> FileStat:
        state = self._inspect(relative_path)
        exists = state.file_kind is not FileKind.MISSING and not state.outside_root
        return FileStat(exists=exists, is_symlink=state.is_symlink, size=state.size)

    def read(self, relative_path: str) -> bytes | None:
        state = self._inspect(relative_path)
        if not state.safe:
            raise _unsafe_error(relative_path, "unsafe_read")
        if state.file_kind is FileKind.MISSING or state.leaf is None:
            return None
        raw, _ = self._read_regular_nofollow(state.leaf, relative_path)
        return raw

    def _ensure_safe_leaf(self, relative_path: str) -> Path:
        if not is_safe_relative_path(relative_path) or _has_git_segment(relative_path):
            raise _unsafe_error(relative_path, "invalid_relative_path")
        resolved_root = self._inspect_root()
        if resolved_root is None:
            raise _unsafe_error(relative_path, "invalid_checkout_root")

        segments = relative_path.split("/")
        cur = self.root
        for seg in segments[:-1]:
            cur = cur / seg
            try:
                pst = cur.lstat()
            except FileNotFoundError:
                try:
                    try:
                        cur.mkdir(mode=0o755)
                    except FileExistsError:
                        pass
                    else:
                        # Pruning is optional on filesystems without user extended attributes.
                        with suppress(AttributeError, OSError):
                            os.setxattr(
                                cur,
                                "user.skm.projection-dir",
                                self._directory_tag(cur),
                                follow_symlinks=False,
                            )
                    pst = cur.lstat()
                except OSError as exc:
                    raise BackendUnavailable(
                        ErrorCode.BACKEND_UNAVAILABLE,
                        f"failed creating parent directory for {relative_path!r}",
                        details={"relative_path": relative_path},
                    ) from exc
            if stat.S_ISLNK(pst.st_mode) or not stat.S_ISDIR(pst.st_mode):
                raise _unsafe_error(relative_path, "unsafe_ancestor")

        resolved_parent = cur.resolve(strict=True)
        if not resolved_parent.is_relative_to(resolved_root):
            raise _unsafe_error(relative_path, "escapes_root")
        return cur / segments[-1]

    def write_atomic(
        self,
        relative_path: str,
        data: bytes,
        *,
        expected_whole_digest: str | None,
        executable: bool | None = None,
    ) -> str:
        state = self._inspect(relative_path)
        if not state.safe:
            raise _unsafe_error(relative_path, "unsafe_target")
        leaf = self._ensure_safe_leaf(relative_path)
        current_bytes, current_mode = self._read_regular_nofollow(leaf, relative_path)
        actual_digest = None if current_bytes is None else sha256_tagged(current_bytes)
        if expected_whole_digest is None:
            if actual_digest is not None:
                raise _race_conflict(
                    relative_path,
                    expected_whole_digest=None,
                    actual_whole_digest=actual_digest,
                )
        elif actual_digest != expected_whole_digest:
            raise _race_conflict(
                relative_path,
                expected_whole_digest=expected_whole_digest,
                actual_whole_digest=actual_digest,
            )

        target_mode: int | None = current_mode
        if executable is True:
            target_mode = (current_mode if current_mode is not None else 0o644) | 0o111
        elif executable is False and current_mode is not None:
            target_mode = current_mode & ~0o111

        temp = leaf.with_name(f".{leaf.name}.skm-tmp.{os.getpid()}.{os.urandom(6).hex()}")
        try:
            assert_safe_replace_target(leaf)
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o666)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                if temp.exists():
                    with _suppress_oserror():
                        os.unlink(temp)
                raise
            if target_mode is not None:
                os.chmod(temp, target_mode)

            # Re-verify ancestor symlinks, leaf type, and whole-digest CAS right before rename.
            rechecked_leaf = self._ensure_safe_leaf(relative_path)
            assert_safe_replace_target(rechecked_leaf)
            latest_bytes, _ = self._read_regular_nofollow(rechecked_leaf, relative_path)
            latest_digest = None if latest_bytes is None else sha256_tagged(latest_bytes)
            if latest_digest != expected_whole_digest:
                raise _race_conflict(
                    relative_path,
                    expected_whole_digest=expected_whole_digest,
                    actual_whole_digest=latest_digest,
                )
            os.replace(temp, rechecked_leaf)
            fsync_dir(rechecked_leaf.parent)
        except SkmError:
            with _suppress_oserror():
                os.unlink(temp)
            raise
        except UnsafePathError as exc:
            with _suppress_oserror():
                os.unlink(temp)
            raise _unsafe_error(relative_path, exc.reason) from exc
        except OSError as exc:
            with _suppress_oserror():
                os.unlink(temp)
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                f"atomic write failed for {relative_path!r}",
                details={"relative_path": relative_path},
            ) from exc
        return sha256_tagged(data)

    def _directory_tag(self, path: Path) -> bytes:
        entry = path.lstat()
        return f"{entry.st_dev}:{entry.st_ino}:".encode() + os.fsencode(path.relative_to(self.root))

    def prune_created_parents(self, relative_path: str) -> None:
        """Prune empty directories with an ownership tag matching this exact directory."""
        if not self._inspect(relative_path).safe:
            return
        directory = (self.root / relative_path).parent
        while self.root in directory.parents:
            try:
                tag = os.getxattr(directory, "user.skm.projection-dir", follow_symlinks=False)
                if tag != self._directory_tag(directory):
                    return
                directory.rmdir()
            except (AttributeError, OSError):
                return
            fsync_dir(directory.parent)
            directory = directory.parent

    def remove(self, relative_path: str, *, expected_whole_digest: str) -> None:
        state = self._inspect(relative_path)
        if not state.safe or state.leaf is None:
            raise _unsafe_error(relative_path, "unsafe_remove")
        leaf = self._ensure_safe_leaf(relative_path)
        current_bytes, _ = self._read_regular_nofollow(leaf, relative_path)
        actual_digest = None if current_bytes is None else sha256_tagged(current_bytes)
        if actual_digest != expected_whole_digest:
            raise _race_conflict(
                relative_path,
                expected_whole_digest=expected_whole_digest,
                actual_whole_digest=actual_digest,
            )
        try:
            assert_safe_replace_target(leaf)
            os.unlink(leaf)
            fsync_dir(leaf.parent)
        except UnsafePathError as exc:
            raise _unsafe_error(relative_path, exc.reason) from exc
        except FileNotFoundError as exc:
            raise _race_conflict(
                relative_path,
                expected_whole_digest=expected_whole_digest,
                actual_whole_digest=None,
            ) from exc
        except OSError as exc:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                f"failed removing {relative_path!r}",
                details={"relative_path": relative_path},
            ) from exc

    def is_gitignored(self, relative_path: str) -> bool | None:
        if not is_safe_relative_path(relative_path) or _has_git_segment(relative_path):
            return None
        if self._inspect_root() is None or not (self.root / ".git").exists():
            return None
        exec_path = os.pathsep.join(d for d in os.get_exec_path() if d) or os.defpath
        argv = [
            self._git_binary,
            "-c",
            "protocol.allow=never",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(self.root),
            "check-ignore",
            "-q",
            "--",
            relative_path,
        ]
        env = {
            "PATH": exec_path,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_OPTIONAL_LOCKS": "0",
            "LC_ALL": "C",
        }
        try:
            proc = process_runner.run(argv, cwd=self.root, env=env, timeout_seconds=10.0)
        except (OSError, TimeoutError, SkmError):
            return None
        if proc.timed_out:
            return None
        if proc.exit_code == 0:
            return True
        if proc.exit_code == 1:
            return False
        return None

    @contextmanager
    def hold_binding_lock(self, binding_id: str) -> Generator[None]:
        """Acquire exclusive POSIX file lock for ``binding_id`` across host operations."""
        locks_dir = self._state_root() / "locks"
        locks_dir.mkdir(parents=True, exist_ok=True)
        safe_id = "".join(ch for ch in binding_id if ch.isalnum() or ch in ("-", "_"))
        lock = FileLock(locks_dir / f"{safe_id}.lock")
        try:
            with lock.hold(timeout_seconds=self._lock_timeout_seconds):
                yield
        except LockTimeout as exc:
            raise Conflict(
                ErrorCode.PROJECTION_CONFLICT,
                "checkout binding lock timed out",
                details={"reason": "binding_locked", "checkout_binding_id": binding_id},
            ) from exc

    def write_journal(self, binding_id: str, journal_id: str, payload: bytes) -> None:
        """Persist and fsync a crash-recovery journal entry for ``binding_id``."""
        journals_dir = self._state_root() / "journals"
        journals_dir.mkdir(parents=True, exist_ok=True)
        safe_binding = "".join(ch for ch in binding_id if ch.isalnum() or ch in ("-", "_"))
        safe_id = "".join(ch for ch in journal_id if ch.isalnum() or ch in ("-", "_"))
        atomic_write(journals_dir / f"{safe_binding}__{safe_id}.json", payload, private=True)

    def list_journals(self, binding_id: str) -> tuple[tuple[str, bytes], ...]:
        """Return ``(journal_id, raw_bytes)`` entries for ``binding_id`` in deterministic order."""
        journals_dir = self._state_root() / "journals"
        if not journals_dir.is_dir():
            return ()
        safe_binding = "".join(ch for ch in binding_id if ch.isalnum() or ch in ("-", "_"))
        prefix = f"{safe_binding}__"
        items: list[tuple[str, bytes]] = []
        for entry in sorted(journals_dir.iterdir(), key=lambda p: p.name):
            if not entry.name.startswith(prefix) or not entry.name.endswith(".json"):
                continue
            journal_id = entry.name[len(prefix) : -5]
            try:
                items.append((journal_id, entry.read_bytes()))
            except FileNotFoundError:
                continue
        return tuple(items)

    def remove_journal(self, binding_id: str, journal_id: str) -> None:
        """Delete a completed crash-recovery journal entry and fsync its parent directory."""
        journals_dir = self._state_root() / "journals"
        safe_binding = "".join(ch for ch in binding_id if ch.isalnum() or ch in ("-", "_"))
        safe_id = "".join(ch for ch in journal_id if ch.isalnum() or ch in ("-", "_"))
        target = journals_dir / f"{safe_binding}__{safe_id}.json"
        try:
            os.unlink(target)
        except FileNotFoundError:
            return
        fsync_dir(journals_dir)


@contextmanager
def _suppress_oserror() -> Generator[None]:
    try:
        yield
    except OSError:
        return
