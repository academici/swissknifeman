"""Canonical JSON and tagged SHA-256 digests (the ``digest/v1`` contract).

Canonical form of a JSON value: object keys are strings sorted by code point, separators are ``,`` and
``:`` without spaces, strings are UTF-8 with only the JSON-mandatory escapes (non-ASCII text is written
as is), and only null, booleans, integers, strings, arrays and objects are allowed. Floats are rejected
because their text form differs between languages. A digest is ``sha256:`` plus the lowercase hex of the
SHA-256 of the canonical bytes. ``schemas/digest/v1/vectors.json`` lists language-neutral test vectors.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable, Mapping

TAG = "sha256:"
_TAGGED_RE = re.compile(r"sha256:[0-9a-f]{64}")


def canonical_value(value: object) -> object:
    """Return ``value`` with objects key-sorted and sequences as tuples; reject anything non-canonical."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        raise TypeError("canonical JSON values must not use floats")
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        return {key: canonical_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return tuple(canonical_value(item) for item in value)
    raise TypeError("value is not canonical JSON data")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a JSON value to its canonical UTF-8 bytes."""
    return json.dumps(canonical_value(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Return the bare lowercase hex SHA-256 of ``data``."""
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return hashlib.sha256(data).hexdigest()


def sha256_tagged(data: bytes) -> str:
    """Return the tagged digest ``sha256:<hex>`` of ``data``."""
    return TAG + sha256_hex(data)


def digest_json(value: object, *, exclude_keys: Iterable[str] = ()) -> str:
    """Return the tagged digest of a JSON object without the given top-level keys."""
    if not isinstance(value, Mapping):
        raise TypeError("value must be a mapping")
    skip = frozenset(exclude_keys)
    return sha256_tagged(canonical_json_bytes({key: item for key, item in value.items() if key not in skip}))


def is_tagged_digest(text: object) -> bool:
    """Whether ``text`` is a well-formed tagged digest."""
    return isinstance(text, str) and _TAGGED_RE.fullmatch(text) is not None
