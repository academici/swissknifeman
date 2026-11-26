"""Descriptor-relative read-only materializer and symlink-safe upload source reader (artifacts §4.4, §5)."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
from collections.abc import Callable, Generator, Iterable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Final, cast, override
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import FileVersionId
from skm.kernel.json_types import JsonValue
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.materialization import MaterialEntry, safe_material_name
from skm.modules.artifacts.ports import MaterialWriter
from skm.platform.fs.safe_paths import UnsafePathError

__all__ = ["READY_MANIFEST_NAME", "LocalMaterialWriter", "LocalUploadSourceReader"]

READY_MANIFEST_NAME: Final = ".skm-materials-ready.json"
_READY_MANIFEST_SCHEMA: Final = "urn:skm:artifacts:materials-ready:v1"
_CHUNK_BYTES: Final = 65536
_O_NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY: Final = getattr(os, "O_DIRECTORY", 0)
_O_CLOEXEC: Final = getattr(os, "O_CLOEXEC", 0)
_O_NONBLOCK: Final = getattr(os, "O_NONBLOCK", 0)


@dataclass(slots=True)
class _TargetSession:
    entries: dict[str, MaterialEntry] = field(default_factory=dict[str, MaterialEntry])
    version_dirs: set[str] = field(default_factory=set[str])
    failed: bool = False


def _iter_fd_chunks(fd: int) -> Iterator[bytes]:
    while chunk := os.read(fd, _CHUNK_BYTES):
        yield chunk


def _invalid_ref(message: str, **details: JsonValue) -> ValidationFailed:
    return ValidationFailed(ErrorCode.INVALID_REFERENCE, message, details=details)


def _digest_str(digest: ContentDigest | str) -> str:
    return digest.value if isinstance(digest, ContentDigest) else str(digest)


def _lstat_or_not_found(target: Path, raw_path: str) -> os.stat_result:
    try:
        return os.lstat(target)
    except FileNotFoundError as exc:
        raise NotFound(
            ErrorCode.NOT_FOUND, f"upload source not found: {raw_path}", details={"path": raw_path}
        ) from exc


class LocalUploadSourceReader:
    """Descriptor-safe reader for ``UploadSourceReader`` rejecting symbolic links before reading."""

    @contextmanager
    def open_source(self, path: str) -> Generator[tuple[tuple[str, int, bool, bool], Iterable[bytes]]]:
        if "\x00" in path:
            raise UnsafePathError(Path(path.replace("\x00", "")), "nul")
        raw_path = Path(path)
        raw_name = os.path.basename(path.rstrip("/\\")) or raw_path.name or path
        anchor_path = raw_path if raw_path.is_absolute() else Path.cwd() / raw_path

        cur = Path(anchor_path.anchor)
        for part in anchor_path.parts[1:-1]:
            cur = cur / part
            if stat.S_ISLNK(_lstat_or_not_found(cur, path).st_mode):
                yield ((raw_name, 0, True, False), ())
                return

        lst = _lstat_or_not_found(anchor_path, path)
        if stat.S_ISLNK(lst.st_mode):
            yield ((raw_name, 0, True, False), ())
            return
        if not stat.S_ISREG(lst.st_mode):
            yield ((raw_name, 0, False, False), ())
            return

        fd: int | None = None
        try:
            try:
                fd = os.open(anchor_path, os.O_RDONLY | _O_CLOEXEC | _O_NOFOLLOW | _O_NONBLOCK)
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    yield ((raw_name, 0, True, False), ())
                    return
                raise
            fst = os.fstat(fd)
            if not os.path.samestat(lst, fst) or not stat.S_ISREG(fst.st_mode):
                yield ((raw_name, 0, False, False), ())
                return
            yield ((raw_name, fst.st_size, False, True), _iter_fd_chunks(fd))
        finally:
            if fd is not None:
                os.close(fd)


def _validate_entry_contract(entry: MaterialEntry) -> tuple[str, str]:
    rel = entry.relative_path
    if "\x00" in rel:
        raise UnsafePathError(Path(rel.replace("\x00", "")), "nul")
    if not rel:
        raise UnsafePathError(Path("."), "empty")
    if rel.startswith(("/", "\\")) or "\\" in rel or (len(rel) >= 2 and rel[1] == ":"):
        raise UnsafePathError(Path(rel), "absolute")
    parts = rel.split("/")
    if any(part == ".." for part in parts):
        raise UnsafePathError(Path(rel), "escapes_root")
    if len(parts) != 2 or any(not part or part == "." for part in parts):
        raise UnsafePathError(Path(rel), "escapes_root")
    ver_dir, file_name = parts
    try:
        canonical_vid = str(UUID(str(entry.file_version_id)))
    except ValueError as exc:
        raise _invalid_ref("file_version_id must be a valid UUID") from exc
    if (
        ver_dir != canonical_vid
        or safe_material_name(file_name) != file_name
        or file_name == READY_MANIFEST_NAME
    ):
        raise UnsafePathError(Path(rel), "escapes_root")
    if isinstance(entry.size_bytes, bool) or entry.size_bytes < 0:
        raise _invalid_ref("size_bytes must be non-negative", size_bytes=entry.size_bytes)
    try:
        ContentDigest(_digest_str(entry.digest))
    except ValueError as exc:
        raise _invalid_ref("entry digest is invalid", digest=_digest_str(entry.digest)) from exc
    return ver_dir, file_name


def _check_not_checkout_dir(dir_fd: int, display_path: Path) -> None:
    if display_path.name == ".git":
        raise _invalid_ref(
            "target is inside a Git repository", reason="inside_checkout", target_dir=str(display_path)
        )
    try:
        os.stat(".git", dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise _invalid_ref(
            "target is inside a Git checkout", reason="inside_checkout", target_dir=str(display_path)
        )
    try:
        head_st = os.stat("HEAD", dir_fd=dir_fd, follow_symlinks=False)
        obj_st = os.stat("objects", dir_fd=dir_fd, follow_symlinks=False)
        refs_st = os.stat("refs", dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISREG(head_st.st_mode) and stat.S_ISDIR(obj_st.st_mode) and stat.S_ISDIR(refs_st.st_mode):
        raise _invalid_ref(
            "target is inside a bare Git repository", reason="inside_checkout", target_dir=str(display_path)
        )


def _open_subdir_nofollow(parent_fd: int, name: str, display_path: Path, *, create: bool) -> int:
    try:
        lst = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        if not create:
            raise
        with suppress(FileExistsError):
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        lst = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)

    if stat.S_ISLNK(lst.st_mode):
        raise UnsafePathError(display_path, "symlink")
    if not stat.S_ISDIR(lst.st_mode):
        raise UnsafePathError(display_path, "not_regular")

    try:
        fd = os.open(name, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise UnsafePathError(display_path, "symlink") from exc
        raise
    fst = os.fstat(fd)
    if not os.path.samestat(lst, fst) or not stat.S_ISDIR(fst.st_mode):
        os.close(fd)
        raise UnsafePathError(display_path, "symlink")
    return fd


def _anchor_target(target_dir: Path | str) -> Path:
    raw = str(target_dir)
    if "\x00" in raw:
        raise UnsafePathError(Path(raw.replace("\x00", "")), "nul")
    candidate = Path(target_dir)
    if ".." in candidate.parts:
        raise UnsafePathError(candidate, "escapes_root")
    return candidate if candidate.is_absolute() else Path.cwd() / candidate


def _open_root_fd(anchored: Path, *, create: bool) -> int:
    cur_fd = os.open(anchored.anchor, os.O_RDONLY | _O_DIRECTORY | _O_CLOEXEC)
    cur_path = Path(anchored.anchor)
    try:
        _check_not_checkout_dir(cur_fd, cur_path)
        for part in anchored.parts[1:]:
            if part in {"", "."}:
                continue
            if part == "..":
                raise UnsafePathError(anchored, "escapes_root")
            next_path = cur_path / part
            next_fd = _open_subdir_nofollow(cur_fd, part, next_path, create=create)
            os.close(cur_fd)
            cur_fd, cur_path = next_fd, next_path
            _check_not_checkout_dir(cur_fd, cur_path)
        if os.fstat(cur_fd).st_uid != os.geteuid():
            raise UnsafePathError(anchored, "escapes_root")
    except BaseException:
        os.close(cur_fd)
        raise
    else:
        return cur_fd


def _check_regular_stat(st: os.stat_result, path: Path) -> None:
    if stat.S_ISLNK(st.st_mode):
        raise UnsafePathError(path, "symlink")
    if not stat.S_ISREG(st.st_mode):
        raise UnsafePathError(path, "not_regular")
    if st.st_nlink != 1:
        raise UnsafePathError(path, "hard_link")
    if st.st_uid != os.geteuid() or (st.st_mode & 0o333) != 0:
        raise UnsafePathError(path, "not_regular")


def _read_own_manifest(root_fd: int, root_path: Path) -> dict[str, MaterialEntry] | None:
    manifest_path = root_path / READY_MANIFEST_NAME
    try:
        lst = os.stat(READY_MANIFEST_NAME, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    _check_regular_stat(lst, manifest_path)

    fd = os.open(READY_MANIFEST_NAME, os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK | _O_CLOEXEC, dir_fd=root_fd)
    try:
        fst = os.fstat(fd)
        if not os.path.samestat(lst, fst):
            raise UnsafePathError(manifest_path, "not_regular")
        _check_regular_stat(fst, manifest_path)
        raw = b"".join(_iter_fd_chunks(fd))
    finally:
        os.close(fd)

    try:
        loaded: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise _invalid_ref("existing ready manifest is malformed", reason="malformed_manifest") from exc
    if not isinstance(loaded, dict):
        raise _invalid_ref("existing ready manifest schema is unrecognized", reason="foreign_manifest")
    doc = cast("dict[str, object]", loaded)
    if doc.get("schema") != _READY_MANIFEST_SCHEMA:
        raise _invalid_ref("existing ready manifest schema is unrecognized", reason="foreign_manifest")
    raw_entries = doc.get("entries")
    if not isinstance(raw_entries, list):
        raise _invalid_ref("existing ready manifest entries must be a list", reason="malformed_manifest")
    parsed: dict[str, MaterialEntry] = {}
    for raw_item in cast("list[object]", raw_entries):
        if not isinstance(raw_item, dict):
            raise _invalid_ref("invalid manifest entry")
        item = cast("dict[str, object]", raw_item)
        size_val = item.get("size_bytes")
        if isinstance(size_val, bool) or not isinstance(size_val, int):
            raise _invalid_ref("invalid manifest entry size")
        entry = MaterialEntry(
            file_version_id=FileVersionId(UUID(str(item.get("file_version_id")))),
            relative_path=str(item.get("relative_path")),
            size_bytes=size_val,
            digest=ContentDigest(str(item.get("digest"))),
        )
        _validate_entry_contract(entry)
        parsed[str(entry.file_version_id)] = entry
    return parsed


def _verify_existing_file(
    ver_fd: int, file_name: str, entry: MaterialEntry, file_path: Path, *, check_hash: bool
) -> None:
    try:
        lst = os.stat(file_name, dir_fd=ver_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise _invalid_ref("manifest entry is missing", relative_path=entry.relative_path) from exc
    _check_regular_stat(lst, file_path)

    try:
        fd = os.open(file_name, os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK | _O_CLOEXEC, dir_fd=ver_fd)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise UnsafePathError(file_path, "symlink") from exc
        raise
    try:
        fst = os.fstat(fd)
        if not os.path.samestat(lst, fst):
            raise UnsafePathError(file_path, "not_regular")
        _check_regular_stat(fst, file_path)
        if fst.st_size != entry.size_bytes:
            raise ValidationFailed(
                ErrorCode.BLOB_DIGEST_MISMATCH,
                "existing materialized file size does not match manifest",
                details={"expected": entry.size_bytes, "actual": fst.st_size},
            )
        if check_hash:
            hasher = hashlib.sha256()
            for chunk in _iter_fd_chunks(fd):
                hasher.update(chunk)
            actual = f"sha256:{hasher.hexdigest()}"
            expected_digest = _digest_str(entry.digest)
            if actual != expected_digest:
                raise ValidationFailed(
                    ErrorCode.BLOB_DIGEST_MISMATCH,
                    "existing materialized file digest does not match manifest",
                    details={"expected": expected_digest, "actual": actual},
                )
    finally:
        os.close(fd)


def _raise_for_preexisting(ver_fd: int, file_name: str, file_path: Path, rel_path: str) -> None:
    lst = os.stat(file_name, dir_fd=ver_fd, follow_symlinks=False)
    if stat.S_ISLNK(lst.st_mode):
        raise UnsafePathError(file_path, "symlink")
    if not stat.S_ISREG(lst.st_mode):
        raise UnsafePathError(file_path, "not_regular")
    if lst.st_nlink != 1:
        raise UnsafePathError(file_path, "hard_link")
    raise _invalid_ref(
        "refusing to overwrite preexisting file", reason="target_exists", relative_path=rel_path
    )


def _stream_into_temp(tmp_fd: int, stream: BinaryIO, entry: MaterialEntry) -> None:
    hasher = hashlib.sha256()
    written = 0
    while chunk := stream.read(_CHUNK_BYTES):
        view = memoryview(chunk)
        offset = 0
        while offset < len(view):
            offset += os.write(tmp_fd, view[offset:])
        hasher.update(view)
        written += len(view)
    actual_digest = f"sha256:{hasher.hexdigest()}"
    if written != entry.size_bytes or actual_digest != _digest_str(entry.digest):
        raise ValidationFailed(
            ErrorCode.BLOB_DIGEST_MISMATCH,
            "materialized stream bytes do not match expected size or digest",
            details={
                "expected_size": entry.size_bytes,
                "actual_size": written,
                "actual_digest": actual_digest,
            },
        )
    os.fchmod(tmp_fd, 0o444)
    os.fsync(tmp_fd)


def _publish_manifest(root_fd: int, entries: Iterable[MaterialEntry]) -> None:
    doc = {
        "schema": _READY_MANIFEST_SCHEMA,
        "entries": [
            {
                "file_version_id": str(item.file_version_id),
                "relative_path": item.relative_path,
                "size_bytes": item.size_bytes,
                "digest": _digest_str(item.digest),
            }
            for item in sorted(entries, key=lambda e: str(e.file_version_id))
        ],
    }
    payload = (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    tmp_manifest = f".manifest.{os.getpid()}.{os.urandom(6).hex()}"
    m_fd = os.open(
        tmp_manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_CLOEXEC, 0o600, dir_fd=root_fd
    )
    try:
        try:
            os.write(m_fd, payload)
            os.fchmod(m_fd, 0o444)
            os.fsync(m_fd)
        finally:
            os.close(m_fd)
        os.link(
            tmp_manifest, READY_MANIFEST_NAME, src_dir_fd=root_fd, dst_dir_fd=root_fd, follow_symlinks=False
        )
    finally:
        with suppress(FileNotFoundError):
            os.unlink(tmp_manifest, dir_fd=root_fd)


class LocalMaterialWriter(MaterialWriter):
    """Concrete descriptor-relative ``MaterialWriter`` publishing ``0444`` files and ``0555`` dirs."""

    def __init__(
        self,
        *,
        before_open: Callable[[Path, MaterialEntry], None] | None = None,
        before_publish: Callable[[Path, MaterialEntry], None] | None = None,
    ) -> None:
        self._before_open = before_open
        self._before_publish = before_publish
        self._sessions: dict[str, _TargetSession] = {}

    def _session(self, anchored: Path) -> _TargetSession:
        return self._sessions.setdefault(str(anchored), _TargetSession())

    def _reuse_manifest_entry(
        self,
        root_fd: int,
        anchored: Path,
        ver_dir: str,
        file_name: str,
        entry: MaterialEntry,
        manifest: dict[str, MaterialEntry],
        session: _TargetSession,
    ) -> None:
        recorded = manifest.get(str(entry.file_version_id))
        if recorded is None:
            raise _invalid_ref("target sealed with a different manifest", reason="manifest_mismatch")
        if (
            recorded.relative_path != entry.relative_path
            or recorded.size_bytes != entry.size_bytes
            or _digest_str(recorded.digest) != _digest_str(entry.digest)
        ):
            raise _invalid_ref("retry metadata mismatches manifest", reason="metadata_mismatch")
        ver_fd = _open_subdir_nofollow(root_fd, ver_dir, anchored / ver_dir, create=False)
        try:
            _verify_existing_file(ver_fd, file_name, entry, anchored / ver_dir / file_name, check_hash=True)
        finally:
            os.close(ver_fd)
        session.entries[entry.relative_path] = entry
        session.version_dirs.add(ver_dir)

    def _write_new_entry(
        self,
        root_fd: int,
        anchored: Path,
        ver_dir: str,
        file_name: str,
        entry: MaterialEntry,
        stream: BinaryIO,
    ) -> None:
        ver_fd = _open_subdir_nofollow(root_fd, ver_dir, anchored / ver_dir, create=True)
        try:
            ver_fstat = os.fstat(ver_fd)
            if ver_fstat.st_uid != os.geteuid():
                raise UnsafePathError(anchored / ver_dir, "escapes_root")
            file_path = anchored / ver_dir / file_name
            try:
                os.stat(file_name, dir_fd=ver_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                _raise_for_preexisting(ver_fd, file_name, file_path, entry.relative_path)

            tmp_name = f".tmp.{os.getpid()}.{os.urandom(6).hex()}"
            tmp_fd = os.open(
                tmp_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_CLOEXEC,
                0o600,
                dir_fd=ver_fd,
            )
            published = False
            try:
                try:
                    _stream_into_temp(tmp_fd, stream, entry)
                finally:
                    os.close(tmp_fd)
                if self._before_publish is not None:
                    self._before_publish(anchored, entry)
                try:
                    cur_ver = os.stat(ver_dir, dir_fd=root_fd, follow_symlinks=False)
                except FileNotFoundError as exc:
                    raise UnsafePathError(anchored / ver_dir, "not_regular") from exc
                if stat.S_ISLNK(cur_ver.st_mode) or not os.path.samestat(cur_ver, ver_fstat):
                    raise UnsafePathError(anchored / ver_dir, "symlink")
                try:
                    os.link(tmp_name, file_name, src_dir_fd=ver_fd, dst_dir_fd=ver_fd, follow_symlinks=False)
                    published = True
                except FileExistsError:
                    _raise_for_preexisting(ver_fd, file_name, file_path, entry.relative_path)
            finally:
                with suppress(FileNotFoundError):
                    os.unlink(tmp_name, dir_fd=ver_fd)
            if published:
                os.fsync(ver_fd)
        finally:
            os.close(ver_fd)

    @override
    def write(self, target_dir: Path | str, entry: MaterialEntry, stream: BinaryIO) -> None:
        anchored = _anchor_target(target_dir)
        session = self._session(anchored)
        try:
            ver_dir, file_name = _validate_entry_contract(entry)
            root_fd = _open_root_fd(anchored, create=True)
            try:
                manifest = _read_own_manifest(root_fd, anchored)
                if self._before_open is not None:
                    self._before_open(anchored, entry)
                if manifest is not None:
                    self._reuse_manifest_entry(
                        root_fd, anchored, ver_dir, file_name, entry, manifest, session
                    )
                    return
                self._write_new_entry(root_fd, anchored, ver_dir, file_name, entry, stream)
                session.entries[entry.relative_path] = entry
                session.version_dirs.add(ver_dir)
            finally:
                os.close(root_fd)
        except BaseException:
            session.failed = True
            raise

    @override
    def seal(self, target_dir: Path | str) -> None:
        anchored = _anchor_target(target_dir)
        session = self._session(anchored)
        if session.failed:
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                "cannot seal a materialization target after a failed write",
                details={"target_dir": str(anchored)},
            )
        root_fd = _open_root_fd(anchored, create=True)
        try:
            manifest = _read_own_manifest(root_fd, anchored)
            for _rel, entry in sorted(session.entries.items()):
                ver_dir, file_name = _validate_entry_contract(entry)
                ver_fd = _open_subdir_nofollow(root_fd, ver_dir, anchored / ver_dir, create=False)
                try:
                    _verify_existing_file(
                        ver_fd, file_name, entry, anchored / ver_dir / file_name, check_hash=False
                    )
                    with os.scandir(ver_fd) as it:
                        names = {de.name for de in it}
                    if names != {file_name}:
                        raise UnsafePathError(anchored / ver_dir, "escapes_root")
                    os.fchmod(ver_fd, 0o555)
                    os.fsync(ver_fd)
                finally:
                    os.close(ver_fd)

            with os.scandir(root_fd) as root_it:
                root_names = {de.name for de in root_it}
            allowed_root: set[str] = set(session.version_dirs) | (
                {READY_MANIFEST_NAME} if manifest is not None else set()
            )
            if root_names != allowed_root:
                raise _invalid_ref(
                    "unexpected preexisting entries in target",
                    unexpected=list[JsonValue](sorted(root_names - allowed_root)),
                )
            if manifest is None:
                _publish_manifest(root_fd, session.entries.values())
            os.fsync(root_fd)
            os.fchmod(root_fd, 0o555)
        except BaseException:
            session.failed = True
            raise
        finally:
            os.close(root_fd)
