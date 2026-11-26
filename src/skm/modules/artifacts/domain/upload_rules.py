"""Upload limits of v2.0 (G21, artifacts §4.5): file names, media signatures and executable formats.

SKM never executes or interprets stored bytes; these rules only name what the bytes look like so that
content safety can raise a finding and the classification floor.
"""

import codecs
import re
import unicodedata
from dataclasses import dataclass

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

__all__ = [
    "EXECUTABLE_TYPES",
    "MEDIA_SIGNATURES",
    "OCTET_STREAM",
    "MediaSignature",
    "detect_media_type",
    "media_type_consistent",
    "normalize_media_type",
    "validate_filename",
]

OCTET_STREAM = "application/octet-stream"
HEAD_BYTES = 4096
_MAX_FILENAME_BYTES = 255
_MAX_MEDIA_TYPE = 200


def _invalid(field: str, reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID, f"{field} is invalid", details={"field": field, "reason": reason}
    )


def _forbidden_char(char: str) -> bool:
    code = ord(char)
    return (
        code <= 0x1F
        or 0x7F <= code <= 0x9F
        or 0x202A <= code <= 0x202E
        or 0x2066 <= code <= 0x2069
        or 0xD800 <= code <= 0xDFFF  # a lone surrogate (an undecodable OS name) is not UTF-8 text
    )


def validate_filename(name: str) -> str:
    """The NFC form of a display basename; raises ``SCHEMA_INVALID`` with ``details.reason``."""
    if type(name) is not str:
        raise _invalid("original_filename", "not_basename")
    if any(_forbidden_char(char) for char in name):
        raise _invalid("original_filename", "control_char")
    normal = unicodedata.normalize("NFC", name)
    if "/" in normal or "\\" in normal:
        raise _invalid("original_filename", "not_basename")
    if normal in {".", ".."}:
        raise _invalid("original_filename", "dot_name")
    if not 1 <= len(normal.encode("utf-8")) <= _MAX_FILENAME_BYTES:
        raise _invalid("original_filename", "too_long")
    return normal


@dataclass(frozen=True, slots=True)
class MediaSignature:
    """One row of ``MEDIA_SIGNATURES``: any of ``patterns`` matches; a pattern is ``(offset, bytes)`` parts.

    ``text`` rows also need the rest of the head to be text (``#!`` scripts).
    """

    media_type: str
    patterns: tuple[tuple[tuple[int, bytes], ...], ...]
    text: bool = False


def _one(*parts: tuple[int, bytes]) -> tuple[tuple[int, bytes], ...]:
    return parts


MEDIA_SIGNATURES: tuple[MediaSignature, ...] = (
    MediaSignature("image/png", (_one((0, b"\x89PNG\r\n\x1a\n")),)),
    MediaSignature("image/jpeg", (_one((0, b"\xff\xd8\xff")),)),
    MediaSignature("image/gif", (_one((0, b"GIF87a")), _one((0, b"GIF89a")))),
    MediaSignature("image/webp", (_one((0, b"RIFF"), (8, b"WEBP")),)),
    MediaSignature("application/pdf", (_one((0, b"%PDF-")),)),
    MediaSignature("application/zip", (_one((0, b"PK\x03\x04")), _one((0, b"PK\x05\x06")))),
    MediaSignature("application/gzip", (_one((0, b"\x1f\x8b")),)),
    MediaSignature("application/x-7z-compressed", (_one((0, b"7z\xbc\xaf\x27\x1c")),)),
    MediaSignature("application/x-tar", (_one((257, b"ustar")),)),
    MediaSignature("application/vnd.sqlite3", (_one((0, b"SQLite format 3\x00")),)),
    MediaSignature("application/wasm", (_one((0, b"\x00asm")),)),
    MediaSignature("application/x-elf", (_one((0, b"\x7fELF")),)),
    MediaSignature("application/vnd.microsoft.portable-executable", (_one((0, b"MZ")),)),
    MediaSignature(
        "application/x-mach-binary",
        tuple(
            _one((0, magic))
            for magic in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe")
        ),
    ),
    MediaSignature("video/mp4", (_one((4, b"ftyp")),)),
    MediaSignature("text/x-script", (_one((0, b"#!")),), text=True),
)

EXECUTABLE_TYPES = frozenset(
    {
        "application/x-elf",
        "application/vnd.microsoft.portable-executable",
        "application/x-mach-binary",
        "application/wasm",
        "text/x-script",
    }
)

_TEXT_DETECTED = frozenset({"text/plain", "text/x-script"})
_TEXT_COMPATIBLE = frozenset(
    {
        "application/json",
        "application/x-ndjson",
        "application/xml",
        "application/yaml",
        "application/x-yaml",
        "application/toml",
        "application/javascript",
        "application/x-sh",
        "application/sql",
        "image/svg+xml",
    }
)
_ZIP_COMPATIBLE = frozenset({"application/zip", "application/java-archive", "application/epub+zip"})
_ZIP_PREFIXES = ("application/vnd.openxmlformats-officedocument.", "application/vnd.oasis.opendocument.")
_ALIASES = {
    "image/jpg": "image/jpeg",
    "application/x-gzip": "application/gzip",
    "application/x-zip-compressed": "application/zip",
    "application/x-pdf": "application/pdf",
}
# RFC 6838 §4.2 restricted-name for type and subtype.
_NAME = r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}"
_MEDIA_TYPE = re.compile(rf"{_NAME}/{_NAME}")


def _is_text(head: bytes) -> bool:
    """No NUL and valid UTF-8; an incomplete last character (the head was cut) is accepted."""
    if b"\x00" in head:
        return False
    try:
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
    except UnicodeDecodeError:
        return False
    return True


def _matches(head: bytes, signature: MediaSignature) -> bool:
    return any(
        all(head[offset : offset + len(magic)] == magic for offset, magic in pattern)
        for pattern in signature.patterns
    )


def detect_media_type(head: bytes) -> str:
    """The first ``MEDIA_SIGNATURES`` row matching the first 4096 bytes; then text or octet-stream."""
    window = bytes(head[:HEAD_BYTES])
    for signature in MEDIA_SIGNATURES:
        if _matches(window, signature) and (not signature.text or _is_text(window)):
            return signature.media_type
    return "text/plain" if _is_text(window) else OCTET_STREAM


def _clean(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def normalize_media_type(value: str | None) -> str | None:
    """A declared ``type/subtype`` without parameters, lower case, ≤ 200; ``SCHEMA_INVALID`` otherwise."""
    if value is None:
        return None
    if type(value) is not str or len(value) > _MAX_MEDIA_TYPE:
        raise _invalid("declared_media_type", "invalid_media_type")
    clean = _clean(value)
    if not _MEDIA_TYPE.fullmatch(clean):
        raise _invalid("declared_media_type", "invalid_media_type")
    return clean


def media_type_consistent(declared: str | None, detected: str) -> bool:
    if declared is None or detected == OCTET_STREAM:
        return True
    clean = _clean(declared)
    if not _MEDIA_TYPE.fullmatch(clean):
        return False
    clean = _ALIASES.get(clean, clean)
    if detected in _TEXT_DETECTED:
        return clean.startswith("text/") or clean in _TEXT_COMPATIBLE
    if detected == "application/zip":
        return clean in _ZIP_COMPATIBLE or clean.startswith(_ZIP_PREFIXES)
    return clean == detected
