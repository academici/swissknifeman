"""Digests of resources and pack versions (extensions §4.14).

A resource digest is SHA-256 over its files in the order of their sorted relative POSIX paths; each file feeds
``path`` (UTF-8), a zero byte and its content. Legacy ``skill_content_hash`` is the source of this algorithm,
not of its file set: two digests compare only over the same files. The legacy hash also skips sidecars that a
v2 pack cannot hold (``kinds.validate_layout``), and a v2 skill hashes ``manifest.toml``, unknown to legacy,
so a migrated skill never repeats its legacy hash. A pack digest is the canonical JSON digest of the manifest
and the sorted ``[kind, key, version, digest]`` rows.

The stream of a resource digest has no length framing, and this algorithm is the normative external contract:
``{a.md: b"1b/two.md\\0" + b"2"}`` and ``{a.md: b"1", b/two.md: b"2"}`` hash alike. So an equal digest never
proves equal files; ``install_candidate`` compares the stored paths and bytes before it relies on one.
"""

import fnmatch
import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import cast

__all__ = ["file_digest", "is_excluded", "pack_digest", "resource_digest"]

_MAIN_SKILL_FILE = "SKILL.md"


def is_excluded(path: str) -> bool:
    """Never in a digest: ``__pycache__/**``, ``*.pyc``, ``SKILL.*.md`` except ``SKILL.md``, ``.DS_Store``."""
    parts = path.split("/")
    name = parts[-1]
    return (
        "__pycache__" in parts[:-1]
        or name.endswith(".pyc")
        or name == ".DS_Store"
        or (name != _MAIN_SKILL_FILE and fnmatch.fnmatchcase(name, "SKILL.*.md"))
    )


def file_digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def resource_digest(files: Mapping[str, bytes]) -> str:
    hasher = hashlib.sha256()
    for path in sorted(item for item in files if not is_excluded(item)):
        hasher.update(path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(files[path])
    return f"sha256:{hasher.hexdigest()}"


def _without_floats(value: object) -> object:
    """Canonical JSON refuses floats; a float of ``pack.toml`` enters as its ``repr`` (settings §A.11)."""
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, object]", value)
        return {key: _without_floats(item) for key, item in mapping.items()}
    if isinstance(value, list | tuple):
        return [_without_floats(item) for item in cast("Iterable[object]", value)]
    return value


def pack_digest(manifest_json: Mapping[str, object], resources: Iterable[tuple[str, str, str, str]]) -> str:
    document = {
        "manifest": _without_floats(manifest_json),
        "resources": [list(row) for row in sorted(resources)],
    }
    canonical = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return file_digest(canonical.encode("utf-8"))
