"""``FilesystemPackReader``: filesystem and archive reader for extension packs (extensions §6, §7.1)."""

from __future__ import annotations

from pathlib import Path

from skm.adapters.resources.archive import safe_extract_to_payload
from skm.adapters.resources.compiled_pack import BLOB_DIR, LOCK_NAME, MANIFEST, enclosing_lock_root, read_lock
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

__all__ = ["FilesystemPackReader"]


def _walk_dir(
    folder: Path,
    prefix: str,
    *,
    files: dict[str, bytes],
    manifest_holder: list[bytes],
    counts: list[int],
    max_files: int,
    max_bytes: int,
) -> None:
    for entry in sorted(folder.iterdir(), key=lambda item: item.name):
        if not prefix and entry.name in {LOCK_NAME, BLOB_DIR}:
            continue
        rel = f"{prefix}{entry.name}"
        if entry.is_symlink():
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "symlinks are not allowed in pack directory",
                details={"reason": "unexpected_symlink", "path": rel},
            )
        validate_payload_path(rel)
        if entry.is_dir():
            _walk_dir(
                entry,
                f"{rel}/",
                files=files,
                manifest_holder=manifest_holder,
                counts=counts,
                max_files=max_files,
                max_bytes=max_bytes,
            )
            continue
        if not entry.is_file():
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "unsupported entry type in pack directory",
                details={"reason": "unsupported_entry", "path": rel},
            )
        stat_info = entry.stat(follow_symlinks=False)
        if rel != MANIFEST:
            counts[0] += 1
        check_payload_limits(
            counts[0],
            counts[1] + stat_info.st_size,
            max_files=max_files,
            max_bytes=max_bytes,
        )
        content = entry.read_bytes()
        counts[1] += len(content)
        check_payload_limits(counts[0], counts[1], max_files=max_files, max_bytes=max_bytes)
        if rel == MANIFEST:
            manifest_holder.append(content)
        else:
            files[rel] = content


class FilesystemPackReader:
    """Filesystem binding of ``PackReader`` enforcing symlink rejection and file/byte limits."""

    def __init__(
        self,
        *,
        max_files: int = DEFAULT_MAX_ARCHIVE_FILES,
        max_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    ) -> None:
        self._max_files = max_files
        self._max_bytes = max_bytes

    def read_dir(self, root: str) -> PackPayload:
        root_path = Path(root)
        if root_path.is_symlink():
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "pack directory cannot be a symlink",
                details={"reason": "unexpected_symlink", "path": root},
            )
        if not root_path.exists():
            raise NotFound(
                ErrorCode.NOT_FOUND,
                f"pack directory not found: {root}",
                details={"path": root},
            )
        if not root_path.is_dir():
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "pack path is not a directory",
                details={"reason": "not_a_directory", "path": root},
            )

        files: dict[str, bytes] = {}
        manifest_holder: list[bytes] = []
        counts = [0, 0]  # [file_count, total_bytes]
        try:
            _walk_dir(
                root_path,
                "",
                files=files,
                manifest_holder=manifest_holder,
                counts=counts,
                max_files=self._max_files,
                max_bytes=self._max_bytes,
            )
            compiled_root = enclosing_lock_root(root_path) if manifest_holder else None
            if compiled_root is not None and (current := read_lock(compiled_root)) is not None:
                relative = root_path.resolve().relative_to(compiled_root).as_posix()
                prefix = "" if relative == "." else relative + "/"
                for item in current[0].assets(compiled_root, prefix, files):
                    files[item.path] = item.content
                    counts[1] += len(item.content)
                    check_payload_limits(
                        len(files), counts[1], max_files=self._max_files, max_bytes=self._max_bytes
                    )
        except ValidationFailed:
            raise
        except OSError as exc:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                f"failed to read pack directory: {root}",
                details={"path": root},
            ) from exc

        if not manifest_holder:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "pack directory is missing pack.toml",
                details={"reason": "missing_pack_manifest", "path": root},
            )
        try:
            manifest_text = manifest_holder[0].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "pack.toml is not valid UTF-8",
                details={"reason": "not_utf8", "path": MANIFEST},
            ) from exc

        payload_files = tuple(PayloadFile(rel, files[rel]) for rel in sorted(files))
        return PackPayload(manifest_text=manifest_text, files=payload_files)

    def read_archive(self, path: str) -> PackPayload:
        return safe_extract_to_payload(path, max_files=self._max_files, max_bytes=self._max_bytes)
