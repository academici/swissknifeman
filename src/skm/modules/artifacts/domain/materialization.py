"""The portable material plan (artifacts §4.4, ARTIFACT-03): one canonical version directory per file version.

The whole plan is validated before any byte is written: malformed metadata, a repeated version id with
different immutable metadata and any case/Unicode alias of a target path refuse the plan with
``INVALID_REFERENCE``. Archives stay ordinary bytes; nothing here looks inside them.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import FileVersionId

from .blob import ContentDigest

__all__ = ["MaterialEntry", "MaterialPlan", "MaterialSource", "plan_materialization", "safe_material_name"]

_MAX_NAME_BYTES = 120
_MAX_EXTENSION_BYTES = 16
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class MaterialEntry:
    file_version_id: FileVersionId
    relative_path: str
    size_bytes: int
    digest: ContentDigest


type MaterialPlan = tuple[MaterialEntry, ...]


class MaterialSource(Protocol):
    """The immutable metadata of one version to materialize (``FileVersionView`` has this shape)."""

    @property
    def file_version_id(self) -> UUID: ...
    @property
    def original_filename(self) -> str: ...
    @property
    def size_bytes(self) -> int: ...
    @property
    def digest(self) -> str | ContentDigest: ...


def _shorten(name: str) -> str:
    dot = name.rfind(".")
    extension = name[dot:][:_MAX_EXTENSION_BYTES] if dot > 0 else ""
    stem = name[:dot] if dot > 0 else name
    return stem[: _MAX_NAME_BYTES - len(extension)] + extension


def safe_material_name(original_filename: str) -> str:
    """A portable ASCII basename: ``[A-Za-z0-9._-]`` (others → ``_``), no trailing dot, no reserved
    Windows device name, at most 120 bytes with an extension of at most 16 bytes."""
    name = _UNSAFE.sub("_", unicodedata.normalize("NFC", original_filename)).rstrip(".")
    if _RESERVED.fullmatch(name.split(".", 1)[0]):
        name = "_" + name  # before shortening, so the prefix counts against the 120 bytes
    return _shorten(name).rstrip(".") or "content"


def _invalid(reason: str, version_id: str | None = None) -> ValidationFailed:
    details: dict[str, str] = {"reason": reason}
    if version_id is not None:
        details["file_version_id"] = version_id
    return ValidationFailed(ErrorCode.INVALID_REFERENCE, f"material plan refused: {reason}", details=details)


def _canonical_id(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)
    if type(value) is str:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    raise _invalid("malformed_version_id")


def _metadata(source: MaterialSource, version_id: str) -> tuple[str, int, ContentDigest]:
    name: object = source.original_filename
    size: object = source.size_bytes
    raw: object = source.digest
    if type(name) is not str or not name:
        raise _invalid("malformed_filename", version_id)
    if type(size) is not int or size < 0:
        raise _invalid("malformed_size", version_id)
    if isinstance(raw, ContentDigest):
        return name, size, raw
    if type(raw) is str:
        try:
            return name, size, ContentDigest(raw)
        except ValueError:
            pass
    raise _invalid("malformed_digest", version_id)


def _alias_keys(path: str) -> set[str]:
    return {unicodedata.normalize(form, path).casefold() for form in ("NFC", "NFD", "NFKC", "NFKD")}


def plan_materialization(versions: Sequence[MaterialSource]) -> MaterialPlan:
    """``<canonical lowercase version uuid>/<safe_material_name>`` per distinct version, in input order.

    A repeated version id with the same immutable metadata is one entry; with other metadata the plan is
    refused. Every target path is checked against every other under casefold and NFC/NFD/NFKC/NFKD.
    """
    entries: list[MaterialEntry] = []
    seen: dict[str, tuple[str, int, ContentDigest]] = {}
    aliases: set[str] = set()
    for source in versions:
        version_id = _canonical_id(source.file_version_id)
        metadata = _metadata(source, version_id)
        if version_id in seen:
            if seen[version_id] != metadata:
                raise _invalid("metadata_mismatch", version_id)
            continue
        seen[version_id] = metadata
        name, size, digest = metadata
        path = f"{version_id}/{safe_material_name(name)}"
        keys = _alias_keys(path)
        if keys & aliases:
            raise _invalid("path_alias", version_id)
        aliases |= keys
        entries.append(MaterialEntry(FileVersionId(UUID(version_id)), path, size, digest))
    return tuple(entries)
