"""Swiss Knife Man package metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    __version__: str

__all__ = ["__version__"]


def __getattr__(name: str) -> str:
    if name == "__version__":
        from importlib.metadata import version

        value = version("skm")
        globals()["__version__"] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
