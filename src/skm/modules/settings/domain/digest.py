"""CAS digest of the entries of one scope (settings §A.4, ``ImportConfig.expected_entries_digest``).

The digest is ``sha256:`` over canonical JSON v1 (``platform.jsonc``: sorted keys, compact separators, UTF-8)
of the list ``[key, op, value, locked]`` sorted by key; an empty scope digests ``[]``. Canonical JSON refuses
floats, and the ``repr`` string of §A.11 (effective config) would let ``1.5`` and ``"1.5"`` share a digest,
so the value is written in a type-tagged form: every JSON value becomes ``[tag, payload]`` (``["null"]``,
``["bool", b]``, ``["int", n]``, ``["float", repr]``, ``["str", s]``, ``["list", [...]]``,
``["object", {...}]``). The tag decides how the payload reads, so two values share a digest exactly when
``same_value`` holds. A value that cannot be stored (``value_issue``: a lone surrogate, more than 64 KiB)
is refused by ``ConfigEntry``; the digest checks it again and raises ``ValueError`` before encoding.
Domain code may not import ``platform``; the serialization is the same (``canonical_json``) and a test pins
it to ``skm.platform.jsonc.digest``. An integer of any width is written in full, whatever the interpreter's
int-to-text limit, so the digest of a stored value never depends on ``sys.set_int_max_str_digits``.
"""

import hashlib
import math
from collections.abc import Iterable, Mapping
from typing import cast

from skm.kernel.json_types import JsonValue

from .entry import ConfigEntry, canonical_json, value_issue

__all__ = ["entries_digest"]


def _encode(value: JsonValue | None) -> list[object]:
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite float is not JSON")
        return ["float", repr(value)]
    if isinstance(value, str):
        return ["str", value]
    if isinstance(value, list):
        return ["list", [_encode(item) for item in value]]
    return ["object", {key: _encode(item) for key, item in value.items()}]


def entries_digest(entries: Iterable[ConfigEntry] | Mapping[str, ConfigEntry]) -> str:
    """Digest of the entries of one scope; a mapping (``entries_of_scope``) is read by its values.

    Two entries with the same key are a ``ValueError``: the digest identifies the entries of a single scope.
    So is a value that cannot be stored: an entry has no digest it could be compared by.
    """
    rows = cast("Mapping[str, ConfigEntry]", entries).values() if isinstance(entries, Mapping) else entries
    document: list[list[object]] = []
    seen: set[str] = set()
    for entry in sorted(rows, key=lambda item: item.key):
        if entry.key in seen:
            raise ValueError(f"entries of one scope hold key {entry.key!r} twice")
        seen.add(entry.key)
        found = value_issue(entry.value)
        if found is not None:
            pointer, _code, message = found
            raise ValueError(
                f"entry {entry.key!r}: value at {pointer!r} is not storable canonical JSON: {message}"
            )
        document.append([entry.key, entry.op.value, _encode(entry.value), entry.locked])
    return "sha256:" + hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()
