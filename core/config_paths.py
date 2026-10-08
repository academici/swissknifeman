"""Resolve shared config paths to their owning location in the monorepo."""
from __future__ import annotations

from pathlib import Path

from .repo import find_monorepo_root

# name -> repository-relative path of the single canonical copy (owner location).
_PATHS = {
    "command-routing": "packages/task/configs/command-routing.json",
    "profile-catalog": "packages/harness/configs/common/profile-catalog.json",
    "provider-capabilities": "packages/aicore/configs/provider-capabilities.json",
    "provider-distribution": "packages/aicore/configs/provider-distribution.json",
    "provider-projection": "packages/aicore/configs/provider-projection.json",
    "gitignore-policy": "configs/gitignore-policy.json",
}


def shared_config_path(name: str, *, repo_root: Path | None = None) -> Path:
    """Return the canonical path of a shared config (one copy, at its owner)."""
    if name not in _PATHS:
        raise KeyError(f"unknown shared config: {name!r}")
    root = repo_root or find_monorepo_root(Path(__file__))
    if root is None:
        raise FileNotFoundError(f"monorepo root not found for shared config {name!r}")
    return root / _PATHS[name]
