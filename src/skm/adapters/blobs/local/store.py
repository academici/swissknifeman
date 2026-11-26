"""Local content-addressed ``BlobStore`` (adapters §4; artifacts §6, §6.1; lifecycle §8).

``stage`` streams chunks into ``<root>/staging/<instance_id>/<staging_id>.part`` through a ``StorageBudget``
reservation of the whole effective upload ceiling and returns a ``StagingHandle`` whose ``staging_id`` is that
uuid4, never a path; ``promote`` hard-links the staged inode to the immutable final
``<root>/<workspace_id>/objects/<aa>/<hex>``. A final is never overwritten, renamed or repaired here: an
existing final is accepted only after a full SHA-256 and size check of its own regular-file descriptor.
Only ``delete_unreferenced`` (janitor/prune under the digest guard, after the reference recheck) removes one.
The root comes from bootstrap and must stay closed to runtime/check writers; ``0444`` is no trust boundary.

A handle is ephemeral: it lives in this store instance between ``stage`` and ``promote``/``discard`` of one
upload and never survives a restart. It is honoured only by the store that issued it and only exactly as
issued; promote publishes the issued workspace, digest and size and rehashes the staging inode itself first.
A changed field is ``ValueError`` before any IO and leaves the staging alone; an id this store does not hold
(consumed, recovered or issued elsewhere) is ``NotFound``. Every directory ensure, made here or found, syncs
its parent, and a new store first syncs every entry on its root's path up to ``/``, so no promote succeeds on
an ancestor a racing creator left unsynced. Every directory sync here fails closed: an error is never taken as
"nothing to sync", so a location is returned only when each sync it depends on succeeded.

Each store writes only into its own ``staging/<instance_id>/``, held by an exclusive ``flock`` for the
store's lifetime. Recovery removes only staging proven abandoned: a handle this store claims itself (never
both with a promote or discard) or files in a directory whose lock is free, so the store that wrote them has
ended. A locked directory belongs to a live store and is never touched, whatever its age. Entries outside
this layout (such as a flat ``staging/<id>.part`` of an older layout) are left alone.

A store belongs to the process that created it. A forked child shares its lock and copies its issued handles
and its thread lock, but its copy acts on none of them: the process is checked before any of that state is
used, inherited handles are ``NotFound`` (discard is a no-op) and stage and recovery are ``staging_changed``.
The child keeps the parent's directory locked while it holds the inherited descriptor and needs a fresh store
of its own, which claims its own directory. The object methods use none of that state: in the child they act
on the finals under the shared root, as a fresh store would.
"""

import errno
import hashlib
import os
import re
import threading
import uuid
import weakref
from collections.abc import Iterable, Iterator
from contextlib import suppress
from datetime import UTC, datetime
from fcntl import LOCK_EX, LOCK_NB, flock
from pathlib import Path
from stat import S_ISDIR, S_ISLNK, S_ISREG
from typing import BinaryIO, ClassVar, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, NotFound, ValidationFailed
from skm.kernel.ids import WorkspaceId
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.ports import BlobLocationRef, BlobObjectStat, StagingHandle
from skm.platform.fs.atomic_write import UnsafePathError
from skm.platform.fs.safe_paths import safe_join
from skm.platform.fs.storage_budget import BudgetedFile, StorageBudget, WriteReservation

__all__ = ["LocalBlobStore"]

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_ID = re.compile(_UUID)  # workspace ids and staging ids
_PART = re.compile(_UUID + r"\.part")
_KEY = re.compile(rf"{_UUID}/objects/(?P<shard>[0-9a-f]{{2}})/(?P<hex>[0-9a-f]{{64}})")
_SHARD = re.compile(r"[0-9a-f]{2}")
_HEX = re.compile(r"[0-9a-f]{64}")
# O_NONBLOCK: a FIFO planted under the root cannot hang open(); it fails the regular-file check instead.
_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
# The instance lock descriptor: never inherited by a spawned program, never a symlinked directory.
_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_CLAIM_ATTEMPTS = 8
_OWNER = "artifacts.blob_stage"


def _workspace_name(workspace_id: WorkspaceId) -> str:
    name = str(workspace_id)
    if not _ID.fullmatch(name):
        raise UnsafePathError(name, "escapes_root")
    return name


def _storage_key(workspace_id: WorkspaceId, digest: str) -> str:
    hex_digest = ContentDigest(digest).value.removeprefix("sha256:")
    return f"{_workspace_name(workspace_id)}/objects/{hex_digest[:2]}/{hex_digest}"


def _require_private_dir(path: Path) -> None:
    info = os.lstat(path)
    if S_ISLNK(info.st_mode):
        raise UnsafePathError(path, "symlink")
    if not S_ISDIR(info.st_mode):
        raise UnsafePathError(path, "not_regular")
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError(f"{path}: blob storage directories must be private (0700) and owned by this user")


def _make_dirs(path: Path, mode: int) -> None:
    """``mkdir -p`` for the root; durability is ``_sync_path``'s, nothing here is taken as synced."""
    try:
        os.mkdir(path, mode)
    except FileNotFoundError:
        _make_dirs(path.parent, 0o777)  # missing parents get the mode Path.mkdir(parents=True) gives them
        with suppress(FileExistsError):
            os.mkdir(path, mode)
    except FileExistsError:
        pass


def _sync_path(path: Path) -> None:
    """Sync the entry of ``path`` and every entry above it, from ``/`` down.

    Nothing visible proves an entry on the path durable. An existing ancestor may be a racing creator's that
    it has not synced yet, or failed to sync, with others' entries inside; and its parent's permissions may
    have changed since, so a directory this user cannot write now may still hold an entry a store of this user
    made then. So each store syncs the whole chain itself, made here or found, and a retry syncs it all again.
    A directory on the path this user cannot open or sync fails the store: what cannot be synced is not
    assumed durable.
    """
    for parent in reversed(path.parents):
        _sync_dir(parent)


def _sync_dir(directory: Path) -> None:
    """``fsync`` a directory or raise; unlike ``fsync_dir`` no errno is taken as "nothing to sync".

    ``fsync_dir`` returns on ``EINVAL``, ``ENOTSUP``, ``EPERM``, ``EISDIR`` and ``EBADF``; a durable location
    built on that return would claim a sync that never happened. Here every failure, ``EACCES`` on a directory
    this user cannot read included, propagates as it came.
    """
    fd = os.open(directory, _DIR)
    try:
        os.fsync(fd)
    except BaseException as primary:
        try:
            os.close(fd)
        except OSError as error:
            primary.add_note(f"directory close failed for {directory}: {error}")
        raise
    os.close(fd)


def _ensure_dir(path: Path) -> None:
    """A private real directory whose entry is durable in its parent before anything goes below it.

    The parent is synced on every success, not only after our own mkdir: a racing creator may not have synced
    it yet, and an earlier attempt may have failed in that fsync after its mkdir.
    """
    with suppress(FileExistsError):
        os.mkdir(path, 0o700)
    _require_private_dir(path)
    _sync_dir(path.parent)


def _present(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _staging_changed(message: str) -> InternalError:
    return InternalError(ErrorCode.INTERNAL_ERROR, message, details={"reason": "staging_changed"})


def _claim_instance(staging: Path) -> tuple[Path, int]:
    """A fresh private ``staging/<uuid4>/`` and the descriptor holding its exclusive lock.

    The kernel drops the lock when the last descriptor closes (process exit included): a free lock proves the
    store ended. A recovery may win the empty new directory before the lock and remove it; the identity check
    after locking sees that and takes another id.
    """
    for _ in range(_CLAIM_ATTEMPTS):
        path = staging / str(uuid.uuid4())
        os.mkdir(path, 0o700)
        try:
            fd = os.open(path, _DIR)
        except FileNotFoundError:
            continue
        try:
            try:
                flock(fd, LOCK_EX | LOCK_NB)
                held = os.path.samestat(os.fstat(fd), os.lstat(path))
            except (BlockingIOError, FileNotFoundError):
                held = False
            if held:
                _sync_dir(staging)
                return path, fd
        except BaseException:
            os.close(fd)
            raise
        os.close(fd)
    raise _staging_changed("blob staging directory could not be claimed")


def _remove_owned(path: Path, created: os.stat_result, primary: BaseException) -> None:
    """Remove our staging inode only; a foreign entry that replaced it is left alone."""
    try:
        if os.path.samestat(os.lstat(path), created):
            os.unlink(path)
    except FileNotFoundError:
        return
    except OSError as error:
        primary.add_note(f"staging cleanup failed for {path}: {error}")


class LocalBlobStore:
    BACKEND_ID: ClassVar[str] = "local-primary"

    def __init__(
        self,
        root: Path,
        *,
        max_bytes: int,
        min_free_bytes: int,
        storage_budget: StorageBudget,
        chunk_size: int = 1 << 20,
    ) -> None:
        for name, value, minimum in (
            ("max_bytes", max_bytes, 0),
            ("min_free_bytes", min_free_bytes, 0),
            ("chunk_size", chunk_size, 1),
        ):
            if isinstance(value, bool) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        _make_dirs(root, 0o700)
        self._root = root.resolve(strict=True)
        _require_private_dir(self._root)
        _sync_path(self._root)
        self._staging = self._root / "staging"
        _ensure_dir(self._staging)
        self._pid = os.getpid()
        self._own, own_fd = _claim_instance(self._staging)
        # Closed (never unlocked: a forked child shares the lock) when the store goes or the process ends; a
        # child closing its inherited copy drops only its own reference, the parent keeps the lock.
        weakref.finalize(self, os.close, own_fd)
        self._own_stat = os.fstat(own_fd)
        self._max_bytes, self._min_free_bytes, self._chunk_size = max_bytes, min_free_bytes, chunk_size
        self._budget = storage_budget
        self._lock = threading.Lock()
        self._issued: dict[str, tuple[StagingHandle, os.stat_result]] = {}  # staging_id -> handle, inode

    # -- staging -------------------------------------------------------------------------------------------

    def stage(self, workspace_id: WorkspaceId, chunks: Iterable[bytes]) -> StagingHandle:
        _workspace_name(workspace_id)
        self._require_own()
        # The whole ceiling is reserved before the file exists and held until fsync/close (lifecycle §8).
        reservation = self._budget.reserve(
            self._root, owner_id=_OWNER, max_bytes=self._max_bytes, min_free_bytes=self._min_free_bytes
        )
        staging_id = str(uuid.uuid4())
        path = self._own / f"{staging_id}.part"
        writer: BudgetedFile | None = None
        created: os.stat_result | None = None
        try:
            writer = reservation.open_file(path)  # O_CREAT|O_EXCL|O_NOFOLLOW, 0600, registered in the ledger
            created = os.lstat(path)
            digest, size = self._write(writer, chunks)
            # fsync, close and the budget's staging directory fsync, which may skip an unsupported errno: no
            # final relies on it, promote fsyncs the inode itself and syncs the final's directory strictly.
            writer.close()
        except BaseException as primary:
            self._abort_stage(reservation, writer, path, created, primary)
            raise
        try:
            reservation.close()
        except BaseException as primary:
            _remove_owned(path, created, primary)
            raise
        handle = StagingHandle(workspace_id, f"sha256:{digest}", size, staging_id)
        with self._lock:
            self._issued[staging_id] = (handle, created)
        return handle

    def _require_creator(self) -> None:
        """Before any inherited state is used: a forked copy shares the lock but is not this store."""
        if os.getpid() != self._pid:
            raise _staging_changed("blob store belongs to the process that created it; create a fresh one")

    def _require_own(self) -> None:
        """Write only under the locked directory: staging anywhere else would look abandoned to recovery."""
        self._require_creator()
        try:
            current = os.path.samestat(os.lstat(self._own), self._own_stat)
        except FileNotFoundError:
            current = False
        if not current:
            raise _staging_changed("blob staging directory changed")

    def _write(self, writer: BudgetedFile, chunks: Iterable[bytes]) -> tuple[str, int]:
        hasher = hashlib.sha256()
        size = 0
        for chunk in chunks:
            # memoryview rejects int/str producers instead of writing zero bytes or a repr.
            data = chunk if type(chunk) is bytes else memoryview(chunk).tobytes()
            if len(data) > self._max_bytes - size:
                raise ValidationFailed(
                    ErrorCode.BLOB_TOO_LARGE,
                    "blob exceeds artifacts.upload.max_bytes",
                    details={"limit": self._max_bytes, "received_at_least": size + len(data)},
                )
            if data:
                writer.write(data)
                hasher.update(data)
                size += len(data)
        return hasher.hexdigest(), size

    @staticmethod
    def _abort_stage(
        reservation: WriteReservation,
        writer: BudgetedFile | None,
        path: Path,
        created: os.stat_result | None,
        primary: BaseException,
    ) -> None:
        # Confirmed close first, then the staging file, then the reserve: a failed close keeps the reserve.
        if writer is not None:
            try:
                writer.close()
            except BaseException as error:  # noqa: BLE001 - keep the primary error
                if error is not primary:
                    primary.add_note(f"staging close failed for {path}: {error}")
        if created is not None:
            _remove_owned(path, created, primary)
        try:
            reservation.close()
        except BaseException as error:  # noqa: BLE001 - keep the primary error
            if error is not primary:
                primary.add_note(f"staging reservation close failed: {error}")

    def discard(self, staged: StagingHandle) -> None:
        path = self._staging_path(staged)
        claimed = self._claim(staged)
        if claimed is None:
            return  # consumed, recovered or issued elsewhere: nothing of this store's to drop
        with suppress(FileNotFoundError):
            if os.path.samestat(os.lstat(path), claimed[1]):
                os.unlink(path)

    def _staging_path(self, staged: StagingHandle) -> Path:
        """Only a uuid4 issued here names a staging file: no separator, ``..`` or absolute path passes."""
        staging_id = staged.staging_id
        if not (isinstance(cast(object, staging_id), str) and _ID.fullmatch(staging_id)):
            raise UnsafePathError(str(staging_id), "escapes_root")
        return self._own / f"{staging_id}.part"

    def _claim(self, staged: StagingHandle) -> tuple[StagingHandle, os.stat_result] | None:
        """Take the handle issued as exactly ``staged`` and its inode; ``None`` when this store holds none.

        A changed workspace, digest or size would publish the staged bytes under a claim nobody verified:
        it is refused before any IO and the issued staging stays for its real handle. Promote, discard and
        recovery all claim here, so only one of them ever acts on a staging. A forked copy holds no handle: it
        never reads the inherited map nor waits on the inherited lock, which a parent thread may have held.
        """
        if os.getpid() != self._pid:
            return None
        with self._lock:
            found = self._issued.get(staged.staging_id)
            if found is None:
                return None
            if found[0] != staged:
                raise ValueError("staging handle was not issued by this store")
            del self._issued[staged.staging_id]
        return found

    # -- promote -------------------------------------------------------------------------------------------

    def promote(self, staged: StagingHandle, *, expected_digest: str | None = None) -> BlobLocationRef:
        """Caller holds the digest guard (artifacts §6.1); staging is consumed whatever the outcome.

        What is published comes from the issued handle, never from the caller's copy.
        """
        staging = self._staging_path(staged)
        claimed = self._claim(staged)
        if claimed is None:
            raise NotFound(ErrorCode.NOT_FOUND, "staged blob not found", details={"kind": "staged_blob"})
        issued, created = claimed
        try:
            key = _storage_key(issued.workspace_id, issued.digest)
            if expected_digest is not None and expected_digest != issued.digest:
                raise ValidationFailed(
                    ErrorCode.BLOB_DIGEST_MISMATCH,
                    "received bytes do not match the expected digest",
                    details={"expected": expected_digest, "actual": issued.digest},
                )
            final = self._final_path(key)
            if not self._link(staging, final, issued, created):
                self._require_match(final, issued, key)
                _sync_dir(final.parent)
        except BaseException as primary:
            _remove_owned(staging, created, primary)
            raise
        with suppress(FileNotFoundError):
            os.unlink(staging)
        return self._location(key)

    def _final_path(self, key: str) -> Path:
        *parents, name = key.split("/")
        directory = self._root
        for part in parents:
            directory /= part
            _ensure_dir(directory)  # private, real directories: no symlink between root and the final
        # Whatever already holds the final name is judged by _link/_require_match, never followed.
        return directory / name

    def _link(self, staging: Path, final: Path, staged: StagingHandle, created: os.stat_result) -> bool:
        """Link the staged inode as a new final; ``False`` when a final already holds the name."""
        try:
            fd = os.open(staging, _READ)
        except FileNotFoundError as error:  # recovered by another store over this root
            raise NotFound(
                ErrorCode.NOT_FOUND, "staged blob not found", details={"kind": "staged_blob"}
            ) from error
        try:
            info = os.fstat(fd)
            # Only the inode stage wrote and hashed: a file put in its place never reaches a final.
            issued = S_ISREG(info.st_mode) and os.path.samestat(info, created)
            if not issued or info.st_size != staged.size_bytes:
                raise _staging_changed("staged bytes changed before promote")
            if _present(final):
                return False
            os.fchmod(fd, 0o444)  # the final is born read-only: mode belongs to the shared inode
            # The stage hash is not trusted across the wait for the guard: these bytes are what is published.
            if not self._matches(fd, staged.digest, staged.size_bytes):
                raise _staging_changed("staged bytes changed before promote")
            os.fsync(fd)
            try:
                os.link(staging, final, follow_symlinks=False)  # never replaces an existing name
            except FileExistsError:
                return False  # a concurrent promote won the name: verify it like any existing final
            except FileNotFoundError as error:
                raise _staging_changed("staged inode changed during promote") from error
            if not os.path.samestat(os.lstat(final), info):
                raise _staging_changed("staged inode changed during promote")
        finally:
            os.close(fd)
        _sync_dir(final.parent)
        return True

    def _require_match(self, final: Path, staged: StagingHandle, key: str) -> None:
        try:
            fd = os.open(final, _READ)
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise self._corrupt(key) from error  # a symlink at the final name is never followed
            raise
        try:
            matches = self._matches(fd, staged.digest, staged.size_bytes)
        finally:
            os.close(fd)
        if not matches:
            raise self._corrupt(key)

    def _matches(self, fd: int, digest: str, size: int | None) -> bool:
        """Full SHA-256 and size of this descriptor; never trusts the name, a size or an earlier verify."""
        info = os.fstat(fd)
        if not S_ISREG(info.st_mode) or (size is not None and info.st_size != size):
            return False
        hasher = hashlib.sha256()
        total = 0
        while block := os.read(fd, self._chunk_size):
            hasher.update(block)
            total += len(block)
        return (size is None or total == size) and f"sha256:{hasher.hexdigest()}" == digest

    def _corrupt(self, key: str) -> InternalError:
        return InternalError(
            ErrorCode.INTERNAL_ERROR,
            "stored blob object does not match its digest",
            details={"reason": "blob_corrupt", "backend_id": self.BACKEND_ID, "storage_key": key},
        )

    # -- objects -------------------------------------------------------------------------------------------

    def _location(self, key: str) -> BlobLocationRef:
        return {"backend_id": self.BACKEND_ID, "storage_key": key, "storage_version": None}

    def _key(self, location: BlobLocationRef) -> str:
        if location.get("backend_id") != self.BACKEND_ID:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "blob location belongs to another backend",
                details={"field": "backend_id"},
            )
        key = location.get("storage_key")
        match = _KEY.fullmatch(key) if isinstance(key, str) else None
        if match is None or match["shard"] != match["hex"][:2]:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "blob storage key is not a workspace object key",
                details={"field": "storage_key", "reason": "unsafe"},
            )
        return match.string

    def _object_path(self, key: str) -> Path:
        try:
            return safe_join(self._root, key)
        except (UnsafePathError, NotADirectoryError) as error:
            raise self._corrupt(key) from error

    def _open_object(self, key: str) -> int:
        path = self._object_path(key)
        try:
            return os.open(path, _READ)
        except FileNotFoundError as error:
            raise NotFound(
                ErrorCode.NOT_FOUND, "blob object not found", details={"kind": "blob_location"}
            ) from error
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.ENOTDIR):
                raise self._corrupt(key) from error
            raise

    def _lstat_object(self, key: str) -> os.stat_result | None:
        try:
            info = os.lstat(self._object_path(key))
        except FileNotFoundError:
            return None
        except NotADirectoryError as error:
            raise self._corrupt(key) from error
        if not S_ISREG(info.st_mode):
            raise self._corrupt(key)
        return info

    def open(self, location: BlobLocationRef) -> BinaryIO:
        key = self._key(location)
        fd = self._open_object(key)
        try:
            if not S_ISREG(os.fstat(fd).st_mode):
                raise self._corrupt(key)
        except BaseException:
            os.close(fd)
            raise
        return os.fdopen(fd, "rb")

    def exists(self, location: BlobLocationRef) -> bool:
        return self._lstat_object(self._key(location)) is not None

    def verify(self, location: BlobLocationRef, digest: str) -> bool:
        """Diagnostic full-content check: ``NotFound`` when missing, ``False`` when not a matching file."""
        key = self._key(location)
        try:
            fd = self._open_object(key)
        except InternalError:
            return False
        try:
            matches = self._matches(fd, digest, None)
        finally:
            os.close(fd)
        return matches

    def stat(self, location: BlobLocationRef) -> BlobObjectStat:
        """Size and ``created_at`` = later of mtime/ctime: no birth time is claimed, age is not overstated."""
        key = self._key(location)
        info = self._lstat_object(key)
        if info is None:
            raise NotFound(ErrorCode.NOT_FOUND, "blob object not found", details={"kind": "blob_location"})
        created = datetime.fromtimestamp(max(info.st_mtime_ns, info.st_ctime_ns) / 1e9, tz=UTC)
        return BlobObjectStat(info.st_size, created)

    def iter_objects(self, workspace_id: WorkspaceId) -> Iterator[BlobLocationRef]:
        workspace = _workspace_name(workspace_id)
        objects = safe_join(self._root, f"{workspace}/objects")
        try:
            shards = sorted(
                entry.name
                for entry in os.scandir(objects)
                if _SHARD.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False)
            )
        except FileNotFoundError:
            return
        for shard in shards:
            names = sorted(
                entry.name
                for entry in os.scandir(objects / shard)
                if _HEX.fullmatch(entry.name)
                and entry.name[:2] == shard
                and entry.is_file(follow_symlinks=False)
            )
            for name in names:
                yield self._location(f"{workspace}/objects/{shard}/{name}")

    def delete_unreferenced(self, location: BlobLocationRef) -> None:
        """Only janitor/prune under the digest guard after the reference recheck (artifacts §6.1, §11.1)."""
        key = self._key(location)
        if self._lstat_object(key) is None:
            return
        path = self._object_path(key)
        with suppress(FileNotFoundError):
            os.unlink(path)
        _sync_dir(path.parent)

    # -- recovery ------------------------------------------------------------------------------------------

    def recover_staging(self, *, stale_before: datetime) -> int:
        """Startup/``staging_gc``: settle dead ledger owners, then drop staging proven abandoned and stale.

        Dead writers' reserves are released only after their files are settled and counted by the filesystem;
        live or unknown owners keep theirs, whatever happens to the files. A file goes only when it was last
        written before the cutoff and either this store claims its handle (as promote would) or the store
        that wrote it has ended (its directory lock is free). In-flight stages and live stores' staging stay;
        finals are never touched here. A forked copy recovers nothing: its parent may still claim each handle.
        """
        self._require_creator()
        self._budget.reconcile(self._root)
        removed = self._recover_issued(stale_before)
        with os.scandir(self._staging) as entries:
            others = [
                entry.name
                for entry in entries
                if _ID.fullmatch(entry.name)
                and entry.name != self._own.name
                and entry.is_dir(follow_symlinks=False)
            ]
        for name in sorted(others):
            removed += self._recover_instance(self._staging / name, stale_before)
        return removed

    def _recover_issued(self, stale_before: datetime) -> int:
        """Handles this store issued that nobody promoted or discarded; an in-flight stage holds none yet."""
        with self._lock:
            issued = list(self._issued.items())
        removed = 0
        for staging_id, (_, created) in issued:
            path = self._own / f"{staging_id}.part"
            try:
                info = os.lstat(path)
            except FileNotFoundError:
                ours = False
            else:
                ours = os.path.samestat(info, created)
                if ours and datetime.fromtimestamp(info.st_mtime, tz=UTC) >= stale_before:
                    continue
            with self._lock:
                if self._issued.pop(staging_id, None) is None:
                    continue  # promoted or discarded since the listing: theirs, not ours
            if not ours:
                continue  # gone or replaced: the handle can never promote, a foreign entry is left alone
            with suppress(FileNotFoundError):
                os.unlink(path)
                removed += 1
        return removed

    def _recover_instance(self, directory: Path, stale_before: datetime) -> int:
        """Another store's directory: stale files only once its lock is free, the directory once empty."""
        try:
            fd = os.open(directory, _DIR)
        except OSError as error:
            if error.errno in (errno.ENOENT, errno.ENOTDIR, errno.ELOOP):
                return 0  # removed by another recovery, or nothing this layout made
            raise
        try:
            try:
                flock(fd, LOCK_EX | LOCK_NB)
            except BlockingIOError:
                return 0  # a live store holds it: age alone proves nothing
            try:
                if not os.path.samestat(os.fstat(fd), os.lstat(directory)):
                    return 0
            except FileNotFoundError:
                return 0
            removed = 0
            with os.scandir(fd) as entries:
                names = sorted(entry.name for entry in entries if _PART.fullmatch(entry.name))
            for name in names:
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    written = datetime.fromtimestamp(info.st_mtime, tz=UTC)
                    if not S_ISREG(info.st_mode) or written >= stale_before:
                        continue
                    os.unlink(name, dir_fd=fd)
                except FileNotFoundError:
                    continue  # removed by someone else since the listing
                removed += 1
            try:
                os.rmdir(directory)  # under the lock: a new store never adopts it, it claims a fresh id
            except OSError as error:
                if error.errno not in (errno.ENOENT, errno.ENOTEMPTY, errno.EEXIST):
                    raise
            return removed
        finally:
            os.close(fd)
