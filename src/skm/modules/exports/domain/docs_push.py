"""Admission and destination naming for checkout document exports."""

from __future__ import annotations

from fnmatch import fnmatchcase
from unicodedata import normalize

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

from .note import validate_relative_path

_SENSITIVE = (
    ".git",
    ".skm",
    ".env*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_dsa*",
    "id_ed25519*",
    "credentials.json",
    "secrets.*",
)


def sensitive(component: str) -> bool:
    return any(fnmatchcase(component.casefold(), pattern) for pattern in _SENSITIVE)


def safe_pattern(pattern: str) -> tuple[str, ...]:
    parts = pattern.split("/")
    if (
        not 0 < len(pattern) <= 1024
        or pattern.startswith("~")
        or ":" in pattern
        or "\\" in pattern
        or any(ord(char) < 32 or ord(char) == 127 for char in pattern)
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Expected a safe checkout-relative glob")
    return tuple(parts)


def matches(path: str, pattern: tuple[str, ...], *, subtree: bool = False) -> bool:
    """Match whole POSIX components, including possible descendants of a pruned path."""
    parts = path.split("/")
    positions: set[int] = {0}
    for component in pattern:
        if subtree and len(parts) in positions:
            return True
        if not positions:
            return False
        if component == "**":
            positions = set(range(min(positions), len(parts) + 1))
        else:
            positions = {i + 1 for i in positions if i < len(parts) and fnmatchcase(parts[i], component)}
    return len(parts) in positions


def destination(folder: str, subfolder: str, source: str) -> str:
    path = normalize("NFC", "/".join((folder, subfolder, source)))
    validate_relative_path(path)
    if any(sensitive(part) for part in path.split("/")):
        raise ValidationFailed(ErrorCode.INTEGRATION_UNSAFE_TARGET, "Sensitive vault destination")
    return path
