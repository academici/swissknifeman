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
import hashlib
from pathlib import Path
import stat

from orch.conductor import checks as checks_mod


def sandbox_stub(project: Path, path: str) -> bool:
    """An empty read-only regular file: the placeholder a Claude Code sandbox (bwrap) mounts over a path it forbids
    (``.bashrc``, ``.claude/hooks``, ...) while a command runs. It is no work of a role and must never reach a commit."""
    try:
        mode = (project / path).lstat()
    except OSError:
        return False
    return stat.S_ISREG(mode.st_mode) and mode.st_size == 0 and not mode.st_mode & 0o222


def dirty(project: Path) -> list:
    """Every changed, added, deleted or untracked path of the working tree (both names of a rename); ignored paths
    and the placeholders of a sandbox (:func:`sandbox_stub`, untracked only) are not listed."""
    listing = checks_mod.git(project, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries, found, index = listing.split("\0"), [], 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        if not (entry[:2] == "??" and sandbox_stub(project, entry[3:])):
            found.append(entry[3:])
        if entry[0] in "RC" and index < len(entries):  # the original name of a rename or copy follows
            found.append(entries[index])
            index += 1
    return sorted(set(found))


def fingerprint(project: Path, paths) -> dict:
    """``{path: sha256 of its bytes}`` (``""`` for a path that is not a readable file): a path whose fingerprint is
    unchanged was not touched."""
    found = {}
    for path in paths:
        try:
            found[path] = hashlib.sha256((project / path).read_bytes()).hexdigest()
        except OSError:
            found[path] = ""
    return found


def untouched(project: Path, kept: dict) -> set:
    """The paths of ``kept`` (a :func:`fingerprint`) whose content is still the same."""
    now = fingerprint(project, kept)
    return {path for path, digest in kept.items() if now.get(path) == digest}


def diff_lines(project: Path, paths) -> int:
    """Lines added and deleted in ``paths`` against HEAD, an untracked file counting all its lines."""
    paths = sorted(set(paths))
    if not paths:
        return 0
    total = 0
    for row in checks_mod.git(project, "diff", "--numstat", "HEAD", "--", *paths).splitlines():
        added, deleted = row.split("\t")[:2]
        total += (int(added) if added.isdigit() else 0) + (int(deleted) if deleted.isdigit() else 0)  # "-": binary
    for path in set(paths) & set(checks_mod.untracked(project)):
        # like numstat of the staged file: a symlink is one line, a binary file none
        file = project / path
        if file.is_symlink():
            total += 1
            continue
        try:
            data = file.read_bytes()
        except OSError:
            continue
        if b"\0" not in data[:8000]:
            total += len(data.decode("utf-8", errors="replace").splitlines())
    return total


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
