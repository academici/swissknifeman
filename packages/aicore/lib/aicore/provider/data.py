"""Locate the provider data files shipped with the aicore package."""
from __future__ import annotations

from pathlib import Path

# lib/aicore/provider/data.py -> packages/aicore (the folder that holds ``configs/``).
CONFIG_DIR = Path(__file__).resolve().parents[3] / "configs"


def config_path(name: str) -> Path:
    """Return the path of the packaged config file *name* (a file name, no directories)."""
    if not name or Path(name).name != name:
        raise ValueError(f"config name must be a bare file name: {name!r}")
    return CONFIG_DIR / name
