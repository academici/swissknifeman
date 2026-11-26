"""Bind the offline pack compiler for the CLI."""

from pathlib import Path

from skm.adapters.resources.pack_compiler import compile_packs
from skm.kernel.json_types import JsonObject

__all__ = ["compile_pack_tree"]


def compile_pack_tree(path: Path, *, check: bool) -> JsonObject:
    return compile_packs(path, check=check)
