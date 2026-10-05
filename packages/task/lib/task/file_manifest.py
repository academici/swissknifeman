"""Deterministic Files expansion shared by evidence and review admission."""
from __future__ import annotations

import os
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


def _walk_inventory(root: Path, prefix: str) -> set[str]:
    """Enumerate concrete members without following directory symlinks."""
    start = root / prefix
    if start.is_symlink() or start.is_file():
        return {start.relative_to(root).as_posix()}
    members = set()
    for directory, children, files in os.walk(start, followlinks=False):
        for name in files + [name for name in children if (Path(directory) / name).is_symlink()]:
            members.add((Path(directory) / name).relative_to(root).as_posix())
    return members


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
    working_inventory = None
    for declaration in declarations:
        for pattern in _expand_braces(declaration):
            path = root / pattern
            if _is_glob(pattern):
                if working_inventory is None:
                    result = subprocess.run(
                        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                        cwd=root, capture_output=True)
                    working_inventory = (set(result.stdout.decode().rstrip("\0").split("\0")) - {""}
                                         if result.returncode == 0 else None)
                prefix = []
                for component in pattern.split("/"):
                    if _is_glob(component):
                        break
                    prefix.append(component)
                literal_prefix = "/".join(prefix)
                # An explicitly named ignored subtree remains a valid input. Broad
                # source globs do not absorb generated dependencies hidden below it.
                ignored_prefix = (literal_prefix and subprocess.run(
                    ["git", "check-ignore", "-q", "--", literal_prefix],
                    cwd=root, capture_output=True).returncode == 0)
                candidates = (_walk_inventory(root, literal_prefix)
                              if working_inventory is None or ignored_prefix else working_inventory)
                matches = {name for name in candidates if _matches(name, pattern)}
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
