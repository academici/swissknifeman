"""Resolve shared monorepo config paths from repository root ``configs/``."""
from __future__ import annotations

from pathlib import Path

from .repo import find_monorepo_root

_SHARED = {
    "command-routing": "command-routing.json",
    "profile-catalog": "profile-catalog.json",
    "provider-capabilities": "provider-capabilities.json",
    "provider-distribution": "provider-distribution.json",
    "provider-projection": "provider-projection.json",
    "gitignore-policy": "gitignore-policy.json",
}

_PACKAGE_FALLBACKS = {
    "command-routing": "packages/task/configs/command-routing.json",
    "profile-catalog": "packages/harness/configs/common/profile-catalog.json",
}


def shared_config_path(name: str, *, repo_root: Path | None = None) -> Path:
    """Return the canonical path for a shared config under ``configs/``.

    Falls back to the legacy package-local path when the root copy is absent.
    """
    if name not in _SHARED:
        raise KeyError(f"unknown shared config: {name!r}")
    root = repo_root or find_monorepo_root(Path(__file__))
    if root is None:
        raise FileNotFoundError(f"monorepo root not found for shared config {name!r}")
    primary = root / "configs" / _SHARED[name]
    if primary.is_file():
        return primary
    fallback_rel = _PACKAGE_FALLBACKS.get(name)
    if fallback_rel is None:
        return primary
    fallback = root / fallback_rel
    if fallback.is_file():
        return fallback
    return primary
