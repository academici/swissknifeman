"""Transitional: make the harness package importable in-process.

harness still imports the legacy ``core`` facade, which lives next to ``packages/`` in the
monorepo. Both go on ``sys.path`` here until the in-process harness link is replaced by its
public commands."""
import sys
from pathlib import Path


def ensure_harness_importable(harness_lib):
    lib = Path(harness_lib).resolve()
    candidates = [lib, lib.parents[2]] if len(lib.parents) > 2 else [lib]
    for candidate in reversed(candidates):
        if candidate is lib or (candidate / "core" / "__init__.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
