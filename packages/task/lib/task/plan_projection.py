"""Shared deterministic writer and freshness check for plan projections."""
from __future__ import annotations

import hashlib
import fcntl
import os
import secrets
import stat
from pathlib import Path


class ProjectionError(ValueError):
    """A projection cannot be built or is not fresh."""


METADATA_FIELDS = (
    "projection",
    "projection_version",
    "source_scope",
    "through",
    "inputs_sha256",
    "generated_by",
)


def inputs_sha256(paths, *, root) -> str:
    """Hash named inputs, including relative paths, in deterministic order."""
    root = Path(root)
    digest = hashlib.sha256()
    for path in sorted((Path(path) for path in paths), key=lambda value: str(value)):
        try:
            relative = path.relative_to(root).as_posix()
            payload = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise ProjectionError(f"projection input not available: {path}") from exc
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def metadata_block(*, projection, projection_version, source_scope, through,
                   inputs_sha256_value, generated_by) -> str:
    """Render the canonical metadata block shared by every projection."""
    values = {
        "projection": projection,
        "projection_version": projection_version,
        "source_scope": source_scope,
        "through": through,
        "inputs_sha256": inputs_sha256_value,
        "generated_by": generated_by,
    }
    if set(values) != set(METADATA_FIELDS) or any(not str(value) for value in values.values()):
        raise ProjectionError("projection metadata is incomplete")
    lines = ["<!-- plan-projection"]
    lines.extend(f"{field}: {values[field]}" for field in METADATA_FIELDS)
    lines.append("-->")
    return "\n".join(lines)


def rendered_file(*, metadata: str, title: str, body: str) -> str:
    """Build one complete generated Markdown file without wall-clock state."""
    if not metadata.startswith("<!-- plan-projection\n"):
        raise ProjectionError("projection metadata is non-canonical")
    return f"{metadata}\n\n# {title}\n\n> Do not manipulate by hand: this is a generated view.\n\n{body.rstrip()}\n"


def write_or_check(target, expected: str, *, check: bool) -> bool:
    """Publish/check a regular projection under one no-follow durable lock domain."""
    target = Path(target)
    encoded = expected.encode("utf-8")
    if not check:
        target.parent.mkdir(parents=True, exist_ok=True)
    if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
            or target.parent.is_symlink()):
        raise ProjectionError(f"view cannot guarantee no-follow durability: {target}")
    try:
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise ProjectionError(f"view directory not available: {target.parent}") from exc
    temporary = None
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        current = None
        try:
            descriptor = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except FileNotFoundError:
            descriptor = None
        except OSError as exc:
            raise ProjectionError(f"view is not secure regular file: {target}") from exc
        if descriptor is not None:
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise ProjectionError(f"view not regular file: {target}")
                with os.fdopen(descriptor, "rb", closefd=False) as stream:
                    current = stream.read()
                if check:
                    if current != encoded:
                        raise ProjectionError(f"view is obsolete: {target}")
                    return False
                if current == encoded:
                    os.fsync(descriptor)
                    os.fsync(directory)
                    return False
            finally:
                os.close(descriptor)
        elif check:
            raise ProjectionError(f"view is missing or unreadable: {target}")

        for _attempt in range(32):
            temporary = f".{target.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
            try:
                descriptor = os.open(
                    temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600, dir_fd=directory)
                break
            except FileExistsError:
                continue
        else:
            raise ProjectionError(f"could not be created temporary view: {target}")
        try:
            cursor = 0
            while cursor < len(encoded):
                written = os.write(descriptor, encoded[cursor:])
                if written <= 0:
                    raise OSError("short projection write")
                cursor += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, target.name, src_dir_fd=directory, dst_dir_fd=directory)
        temporary = None
        os.fsync(directory)
        return True
    except ProjectionError:
        raise
    except OSError as exc:
        raise ProjectionError(f"record of the type did not reach durable boundary: {target}: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
        os.close(directory)
