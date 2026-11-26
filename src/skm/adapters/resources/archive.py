"""Safe in-memory archive extraction for extension packs (extensions §6, §7.1).

Extracts ``.tar.gz``, ``.tgz``, ``.tar``, and ``.zip`` archives directly into a ``PackPayload`` in memory
without writing to the filesystem. Rejects path traversal (``..``, leading ``/``, ``\\``), symlinks,
hardlinks, special files, and archives exceeding ``max_files`` or ``max_bytes``.
"""

from __future__ import annotations

import io
import stat
import tarfile
import zipfile
import zlib
from pathlib import Path
from typing import IO, Final

from skm.adapters.resources.compiled_pack import BLOB_DIR, LOCK_NAME, PackLock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, NotFound, ValidationFailed
from skm.modules.extensions.domain.payload import (
    DEFAULT_MAX_ARCHIVE_BYTES,
    DEFAULT_MAX_ARCHIVE_FILES,
    PackPayload,
    PayloadFile,
    check_payload_limits,
    validate_payload_path,
)

__all__ = ["safe_extract_to_payload"]

_MANIFEST: Final = "pack.toml"
_CHUNK_SIZE: Final = 65_536
_ZIP_MAGIC_PREFIXES: Final = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _validate_dir_entry(raw_name: str) -> None:
    stripped = raw_name.rstrip("/")
    if not stripped or stripped == ".":
        return
    validate_payload_path(stripped)


def _read_bounded_stream(
    reader: IO[bytes],
    *,
    file_count: int,
    total_bytes: int,
    max_files: int,
    max_bytes: int,
) -> tuple[bytes, int]:
    chunks: list[bytes] = []
    while True:
        chunk = reader.read(_CHUNK_SIZE)
        if not chunk:
            break
        total_bytes += len(chunk)
        check_payload_limits(file_count, total_bytes, max_files=max_files, max_bytes=max_bytes)
        chunks.append(chunk)
    return b"".join(chunks), total_bytes


def _decode_manifest(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "pack.toml is not valid UTF-8",
            details={"reason": "not_utf8", "path": _MANIFEST},
        ) from exc


def _extract_zip(
    source: Path | IO[bytes], *, max_files: int, max_bytes: int
) -> tuple[bytes | None, dict[str, bytes]]:
    manifest_bytes: bytes | None = None
    files: dict[str, bytes] = {}
    total_bytes = 0
    file_count = 0

    with zipfile.ZipFile(source, "r") as zf:
        for info in zf.infolist():
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID,
                    "symlinks are not allowed in pack archives",
                    details={"reason": "unexpected_symlink", "path": info.filename},
                )
            if info.is_dir() or info.filename.endswith("/"):
                _validate_dir_entry(info.filename)
                continue
            rel_path = validate_payload_path(info.filename)
            if rel_path in files or (rel_path == _MANIFEST and manifest_bytes is not None):
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID,
                    "duplicate path in archive",
                    details={"reason": "duplicate_path", "path": rel_path},
                )
            if rel_path != _MANIFEST:
                file_count += 1
            check_payload_limits(
                file_count,
                total_bytes + max(info.file_size, 0),
                max_files=max_files,
                max_bytes=max_bytes,
            )
            with zf.open(info, "r") as stream:
                content, total_bytes = _read_bounded_stream(
                    stream,
                    file_count=file_count,
                    total_bytes=total_bytes,
                    max_files=max_files,
                    max_bytes=max_bytes,
                )
            if rel_path == _MANIFEST:
                manifest_bytes = content
            else:
                files[rel_path] = content

    return manifest_bytes, files


def _extract_tar_members(
    tf: tarfile.TarFile, *, max_files: int, max_bytes: int
) -> tuple[bytes | None, dict[str, bytes]]:
    manifest_bytes: bytes | None = None
    files: dict[str, bytes] = {}
    total_bytes = 0
    file_count = 0

    for member in tf:
        if member.issym() or member.islnk():
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "symlinks and hardlinks are not allowed in pack archives",
                details={"reason": "unexpected_symlink", "path": member.name},
            )
        if member.isdir():
            _validate_dir_entry(member.name)
            continue
        if not member.isfile():
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "unsupported entry type in pack archive",
                details={"reason": "unsupported_entry", "path": member.name},
            )
        rel_path = validate_payload_path(member.name)
        if rel_path in files or (rel_path == _MANIFEST and manifest_bytes is not None):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "duplicate path in archive",
                details={"reason": "duplicate_path", "path": rel_path},
            )
        if rel_path != _MANIFEST:
            file_count += 1
        check_payload_limits(
            file_count,
            total_bytes + max(member.size, 0),
            max_files=max_files,
            max_bytes=max_bytes,
        )
        extracted = tf.extractfile(member)
        if extracted is None:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "unable to read archive entry",
                details={"reason": "archive_invalid", "path": rel_path},
            )
        with extracted:
            content, total_bytes = _read_bounded_stream(
                extracted,
                file_count=file_count,
                total_bytes=total_bytes,
                max_files=max_files,
                max_bytes=max_bytes,
            )
        if rel_path == _MANIFEST:
            manifest_bytes = content
        else:
            files[rel_path] = content

    return manifest_bytes, files


def _extract_tar(
    source: Path | IO[bytes], *, max_files: int, max_bytes: int
) -> tuple[bytes | None, dict[str, bytes]]:
    if isinstance(source, Path):
        with tarfile.open(source, "r:*") as tf:
            return _extract_tar_members(tf, max_files=max_files, max_bytes=max_bytes)
    with tarfile.open(fileobj=source, mode="r:*") as tf:
        return _extract_tar_members(tf, max_files=max_files, max_bytes=max_bytes)


def _extract_stream(
    stream: IO[bytes], *, max_files: int, max_bytes: int
) -> tuple[bytes | None, dict[str, bytes]]:
    seekable = stream if stream.seekable() else io.BytesIO(stream.read())
    pos = seekable.tell()
    magic = seekable.read(4)
    seekable.seek(pos)
    if magic.startswith(_ZIP_MAGIC_PREFIXES):
        return _extract_zip(seekable, max_files=max_files, max_bytes=max_bytes)
    return _extract_tar(seekable, max_files=max_files, max_bytes=max_bytes)


def _extract_path(
    path: Path, *, display_path: str, max_files: int, max_bytes: int
) -> tuple[bytes | None, dict[str, bytes]]:
    if path.is_symlink():
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "archive path cannot be a symlink",
            details={"reason": "unexpected_symlink", "path": display_path},
        )
    if not path.exists():
        raise NotFound(
            ErrorCode.NOT_FOUND,
            f"archive not found: {display_path}",
            details={"path": display_path},
        )
    if not path.is_file():
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "archive path is not a regular file",
            details={"reason": "archive_invalid", "path": display_path},
        )
    name_lower = path.name.lower()
    if name_lower.endswith(".zip") or zipfile.is_zipfile(path):
        return _extract_zip(path, max_files=max_files, max_bytes=max_bytes)
    if name_lower.endswith((".tar.gz", ".tgz", ".tar")) or tarfile.is_tarfile(path):
        return _extract_tar(path, max_files=max_files, max_bytes=max_bytes)
    raise ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "unsupported archive format",
        details={"reason": "archive_invalid", "path": display_path},
    )


def safe_extract_to_payload(
    archive_source: str | Path | bytes | IO[bytes],
    *,
    max_files: int = DEFAULT_MAX_ARCHIVE_FILES,
    max_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
) -> PackPayload:
    """Safely extract a ``.tar.gz``, ``.tgz``, ``.tar``, or ``.zip`` archive into a ``PackPayload``."""
    if isinstance(archive_source, (bytes, bytearray, memoryview)):
        display_path = "<bytes>"
        stream: IO[bytes] | None = io.BytesIO(bytes(archive_source))
    elif isinstance(archive_source, (str, Path)):
        display_path = str(archive_source)
        stream = None
    else:
        display_path = getattr(archive_source, "name", "<stream>")
        stream = archive_source

    try:
        if stream is not None:
            manifest_bytes, files = _extract_stream(stream, max_files=max_files, max_bytes=max_bytes)
        else:
            manifest_bytes, files = _extract_path(
                Path(archive_source),  # type: ignore[arg-type]
                display_path=display_path,
                max_files=max_files,
                max_bytes=max_bytes,
            )
    except (ValidationFailed, NotFound):
        raise
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, zlib.error) as exc:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid or corrupted archive",
            details={"reason": "archive_invalid", "path": display_path},
        ) from exc
    except OSError as exc:
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE,
            f"failed to read archive: {display_path}",
            details={"path": display_path},
        ) from exc

    if manifest_bytes is None:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "pack archive is missing pack.toml",
            details={"reason": "missing_pack_manifest", "path": display_path},
        )

    if (lock_bytes := files.pop(LOCK_NAME, None)) is not None:
        aliases = PackLock.decode(lock_bytes).assets(files, "", files)
        files = {path: content for path, content in files.items() if not path.startswith(BLOB_DIR + "/")}
        files.update((item.path, item.content) for item in aliases)
        check_payload_limits(
            len(files),
            len(manifest_bytes) + sum(map(len, files.values())),
            max_files=max_files,
            max_bytes=max_bytes,
        )
    payload_files = tuple(PayloadFile(rel, files[rel]) for rel in sorted(files))
    return PackPayload(manifest_text=_decode_manifest(manifest_bytes), files=payload_files)
