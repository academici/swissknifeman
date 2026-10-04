"""Deterministic Files expansion shared by evidence and review admission."""
from __future__ import annotations

import glob
from functools import lru_cache
from fnmatch import fnmatchcase
from pathlib import Path
import subprocess


class ManifestError(ValueError):
    pass


def _matches(relative: str, pattern: str) -> bool:
    """Path-component glob semantics: ** spans zero or more directories."""
    parts, patterns = tuple(relative.split("/")), tuple(pattern.split("/"))
    @lru_cache(None)
    def match(index, position):
        if position == len(patterns):
            return index == len(parts)
        if patterns[position] == "**":
            return match(index, position + 1) or index < len(parts) and match(index + 1, position)
        return (index < len(parts) and fnmatchcase(parts[index], patterns[position])
                and match(index + 1, position + 1))
    return match(0, 0)


def expand(root: Path, declarations, *, base: str | None = None,
           required: bool = False) -> tuple[str, ...]:
    # The existing bounded brace grammar is also used by phase fingerprints.
    from task.plan_gates import _expand_braces, _is_glob
    root = root.resolve()
    inventory = set()
    if base:
        result = subprocess.run(["git", "ls-tree", "-r", "--name-only", "-z", base],
                                cwd=root, capture_output=True, check=True)
        inventory = set(result.stdout.decode().rstrip("\0").split("\0")) - {""}
    rows = set()
    for declaration in declarations:
        for pattern in _expand_braces(declaration):
            path = root / pattern
            if _is_glob(pattern):
                matches = {Path(value).relative_to(root).as_posix()
                           for value in glob.glob(str(path), recursive=True, include_hidden=True)}
                # Git pathspecs bind tracked deletions as explicit tombstones too.
                matches.update(name for name in inventory if _matches(name, pattern))
            else:
                matches = {pattern} if path.exists() or path.is_symlink() or pattern in inventory else set()
                if not matches:
                    matches.update(name for name in inventory if name.startswith(pattern.rstrip("/") + "/"))
            if not matches:
                if required:
                    raise ManifestError(f"REVIEW_REQUIRED_PATH_MISSING: {pattern}")
                matches = {pattern}
            for relative in matches:
                candidate = root / relative
                if not candidate.resolve().is_relative_to(root):
                    raise ManifestError(f"REVIEW_PATH_INVALID: {relative}")
                rows.add(relative.rstrip("/"))
    return tuple(sorted(rows))
