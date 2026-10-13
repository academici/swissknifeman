"""What a role really changed, read from git, and which of it lies outside ``scope.write_set`` of the input.

The report of a role is not the source of the changed paths: a correction round lists only its own paths, and a role
can forget a file. The conductor reads the working tree after every executor round instead. Paths that were already
dirty before the first executor round (the work source writes its plan when it claims) are not the role's.

A write-set pattern is a repository-relative path or glob: ``*`` and ``?`` match inside one segment, ``**`` any
number of segments, and a pattern that ends with ``/`` owns everything below it (the planner's commit rules).
"""
from __future__ import annotations

from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import Path

from orch.conductor import checks as checks_mod


def dirty(project: Path) -> list:
    """Every changed, added, deleted or untracked path of the working tree (both names of a rename); ignored paths
    are not listed."""
    listing = checks_mod.git(project, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries, found, index = listing.split("\0"), [], 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        found.append(entry[3:])
        if entry[0] in "RC" and index < len(entries):  # the original name of a rename or copy follows
            found.append(entries[index])
            index += 1
    return sorted(set(found))


def _normal(pattern: str) -> str:
    parts = [part for part in str(pattern).split("/") if part and part != "."]
    return "/".join(parts) + ("/" if str(pattern).endswith("/") else "")


def matches(path: str, pattern: str) -> bool:
    pattern = _normal(pattern)
    if not pattern:
        return False
    if pattern.endswith("/"):
        return path.startswith(pattern)
    segments, wanted = path.split("/"), pattern.split("/")

    @lru_cache(None)
    def match(i: int, j: int) -> bool:
        if j == len(wanted):
            return i == len(segments)
        if wanted[j] == "**":
            return match(i, j + 1) or (i < len(segments) and match(i + 1, j))
        return i < len(segments) and fnmatchcase(segments[i], wanted[j]) and match(i + 1, j + 1)

    return match(0, 0)


def outside(paths, write_set) -> list:
    """The paths that no pattern of ``write_set`` owns; none when the input names no write set."""
    patterns = [pattern for pattern in write_set or [] if isinstance(pattern, str) and pattern]
    if not patterns:
        return []
    return sorted(path for path in paths if not any(matches(path, pattern) for pattern in patterns))


def own(paths, excluded_prefixes) -> list:
    """``paths`` without those below one of ``excluded_prefixes`` (the artifact folder, the conductor reports)."""
    prefixes = [prefix.rstrip("/") + "/" for prefix in excluded_prefixes if prefix]
    return sorted(path for path in paths if not any(path.startswith(prefix) or path + "/" == prefix
                                                    for prefix in prefixes))
