"""Tagged SHA-256 digests of bytes and canonical JSON v1 values."""

import hashlib
import re
from collections.abc import Iterable, Mapping
from typing import Final, cast

from skm.platform.jsonc.canonical import canonical_bytes

__all__ = ["TAG", "digest", "digest_bytes", "digest_json", "is_tagged_digest", "sha256_hex"]

TAG: Final = "sha256:"
_TAGGED_RE = re.compile(r"sha256:[0-9a-f]{64}")


def sha256_hex(data: bytes) -> str:
    """Return the bare lowercase SHA-256 hex digest; accept only bytes."""
    if not isinstance(cast(object, data), bytes):
        raise TypeError("data must be bytes")
    return hashlib.sha256(data).hexdigest()


def digest_bytes(data: bytes) -> str:
    """Hash bytes without JSON encoding and prefix the hash with its algorithm."""
    return TAG + sha256_hex(data)


def digest(value: object) -> str:
    """Return the tagged SHA-256 digest of any canonical JSON value."""
    return digest_bytes(canonical_bytes(value))


def digest_json(value: Mapping[str, object], *, exclude_keys: Iterable[str] = ()) -> str:
    """Digest a mapping, excluding only the explicitly named top-level keys."""
    if not isinstance(cast(object, value), Mapping):
        raise TypeError("value must be a mapping")
    skip = frozenset(exclude_keys)
    return digest({key: item for key, item in value.items() if key not in skip})


def is_tagged_digest(text: object) -> bool:
    """Recognize exactly sha256: followed by 64 lowercase hexadecimal digits."""
    return isinstance(text, str) and _TAGGED_RE.fullmatch(text) is not None
