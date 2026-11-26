"""Where the packaged schemas live: inside the ``skm`` package, never relative to the working directory."""

from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

import skm

__all__ = ["checkout_schema_root", "default_schema_root"]

_PACKAGE = "skm"
_DIRECTORY = "schemas"


def checkout_schema_root(start: Path) -> Path | None:
    """Walk up from ``start`` to the first directory holding ``src/skm/schemas`` (dev/editable checkout)."""
    for parent in start.parents:
        candidate = parent / "src" / _PACKAGE / _DIRECTORY
        if (parent / "src").is_dir() and candidate.is_dir():
            return candidate
    return None


def default_schema_root() -> Traversable:
    """``skm/schemas`` of the installed package; the checkout copy is the fallback; no environment is read."""
    packaged = resources.files(_PACKAGE) / _DIRECTORY
    if packaged.is_dir():
        return packaged
    package_file = getattr(skm, "__file__", None)
    if package_file is not None:
        found = checkout_schema_root(Path(package_file).absolute())
        if found is not None:
            return found
    raise RuntimeError("schemas not found")
