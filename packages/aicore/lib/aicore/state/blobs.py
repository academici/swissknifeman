"""A content-addressed store for the data an ``artifact-ref/v1`` document points at.

A blob is a file named by the SHA-256 of its bytes: ``<project>/.swissknifeman/state/artifacts/sha256/<hex>``
inside a project, or ``<machine state>/artifacts/sha256/<hex>`` without one. Writing the same bytes again changes
nothing; reading checks the digest and the size, so a damaged file is reported and never returned. There is no
garbage collection: the store only grows, and the project folder is in ``.gitignore``.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

from ..util.digest import canonical_json_bytes, is_tagged_digest, sha256_tagged
from .locations import PathLike, ensure_dir, project_state_dir, state_dir

SCHEMA = "urn:swissknifeman:aicore:artifact-ref:v1"
SENSITIVITIES = ("normal", "sensitive")
BLOB_MODE = 0o600
_MEDIA_TYPE = re.compile(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+\Z")
_NAME = re.compile(r"[^\x00-\x1f]{1,255}\Z")

Ref = Union[Mapping[str, Any], str]


def _store(project: Optional[PathLike], env: Optional[Mapping[str, str]],
           home: Optional[PathLike]) -> "tuple[Path, str]":
    if project is not None:
        return project_state_dir(project, "artifacts") / "sha256", "project"
    return state_dir("artifacts", env=env, home=home) / "sha256", "machine"


def _digest_of(ref: Ref) -> str:
    digest = ref if isinstance(ref, str) else ref.get("digest")
    if not is_tagged_digest(digest):
        raise ValueError("BLOB_REF_INVALID: the reference needs a tagged sha256 digest")
    return digest


def blob_path(ref: Ref, *, project: Optional[PathLike] = None, env: Optional[Mapping[str, str]] = None,
              home: Optional[PathLike] = None) -> Path:
    """Where the blob of ``ref`` (an artifact-ref document or a tagged digest) lives; it may not exist."""
    store, _location = _store(project, env, home)
    return store / _digest_of(ref)[len("sha256:"):]


def put_bytes(data: bytes, *, media_type: str, sensitivity: str = "normal", name: Optional[str] = None,
              project: Optional[PathLike] = None, env: Optional[Mapping[str, str]] = None,
              home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Store ``data`` and return its ``artifact-ref/v1`` document (``location`` says which store holds it)."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes")
    data = bytes(data)
    if not _MEDIA_TYPE.match(media_type or ""):
        raise ValueError(f"BLOB_ARGUMENT: invalid media type {media_type!r}")
    if sensitivity not in SENSITIVITIES:
        raise ValueError(f"BLOB_ARGUMENT: sensitivity must be one of {', '.join(SENSITIVITIES)}")
    if name is not None and not _NAME.match(name):
        raise ValueError("BLOB_ARGUMENT: the name must be 1-255 characters without control characters")
    digest = sha256_tagged(data)
    store, location = _store(project, env, home)
    target = store / digest[len("sha256:"):]
    if not _holds(target, data):
        _write(target, data)
    ref: Dict[str, Any] = {"$schema": SCHEMA, "digest": digest, "size": len(data), "media_type": media_type,
                           "sensitivity": sensitivity}
    if name is not None:
        ref["name"] = name
    ref["location"] = location
    return ref


def put_json(value: object, *, sensitivity: str = "normal", name: Optional[str] = None,
             project: Optional[PathLike] = None, env: Optional[Mapping[str, str]] = None,
             home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Store ``value`` as canonical JSON (see :mod:`aicore.util.digest`) with the media type ``application/json``."""
    return put_bytes(canonical_json_bytes(value), media_type="application/json", sensitivity=sensitivity,
                     name=name, project=project, env=env, home=home)


def read_bytes(ref: Ref, *, project: Optional[PathLike] = None, env: Optional[Mapping[str, str]] = None,
               home: Optional[PathLike] = None) -> bytes:
    """The bytes of a blob. ``FileNotFoundError`` if absent; ``ValueError('BLOB_CORRUPT ...')`` if the digest
    (or the size, when ``ref`` states one) does not match."""
    digest = _digest_of(ref)
    path = blob_path(digest, project=project, env=env, home=home)
    data = path.read_bytes()
    size = ref.get("size") if isinstance(ref, Mapping) else None
    if size is not None and size != len(data):
        raise ValueError(f"BLOB_CORRUPT {digest}: the file has {len(data)} bytes, the reference says {size}")
    if sha256_tagged(data) != digest:
        raise ValueError(f"BLOB_CORRUPT {digest}: the content does not match its digest")
    return data


def _holds(path: Path, data: bytes) -> bool:
    try:
        return path.is_file() and path.stat().st_size == len(data) and path.read_bytes() == data
    except OSError:
        return False


def _write(path: Path, data: bytes) -> None:
    """Atomic write through a private temporary file in the same folder; the result has mode 0o600."""
    ensure_dir(path.parent)
    descriptor, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".blob-")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, BLOB_MODE)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
