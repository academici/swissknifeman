"""Ownership modes, managed boundary descriptors, and empty-boundary digests (integrations §4.1)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from .merged_json import OwnedKeyPath

__all__ = [
    "ManagedBoundary",
    "Ownership",
    "empty_managed_digest",
    "sha256_tagged",
]


class Ownership(StrEnum):
    MANAGED_FILE = "managed_file"
    MANAGED_BLOCK = "managed_block"
    MERGED_JSON = "merged_json"
    MERGED_TOML = "merged_toml"


@dataclass(frozen=True, slots=True)
class ManagedBoundary:
    ownership: Ownership
    block_ids: tuple[str, ...] = ()
    owned_keys: tuple[OwnedKeyPath, ...] = ()


def sha256_tagged(data: bytes) -> str:
    """Return canonical ``sha256:<hex64>`` digest of raw ``data``."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def empty_managed_digest(boundary: ManagedBoundary) -> str:
    """Return canonical ``sha256:...`` digest of an empty managed part for ``boundary``."""
    if boundary.ownership is Ownership.MERGED_JSON:
        return sha256_tagged(b"{}\n")
    if boundary.ownership in (Ownership.MANAGED_BLOCK, Ownership.MERGED_TOML, Ownership.MANAGED_FILE):
        return sha256_tagged(b"")
    return sha256_tagged(b"")
