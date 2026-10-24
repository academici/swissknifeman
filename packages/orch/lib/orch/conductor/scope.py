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
import os
from pathlib import Path
import stat
from typing import Optional

from orch.conductor import checks as checks_mod


def sandbox_stub(project: Path, path: str) -> bool:
    """An empty read-only regular file: the placeholder a Claude Code sandbox (bwrap) mounts over a path it forbids
    (``.bashrc``, ``.claude/hooks``, ...) while a command runs. It is no work of a role and must never reach a commit."""
    try:
        mode = (project / path).lstat()
    except OSError:
        return False
    return stat.S_ISREG(mode.st_mode) and mode.st_size == 0 and not mode.st_mode & 0o222


# The paths of a project the Claude Code sandbox protects from the shell (its own configuration, fixed in the CLI, not
# chosen by --setting-sources): for one that does not exist it creates an empty read-only placeholder on the host while
# a command runs and removes it after; a command killed in between leaves it behind (seen 2026-10-24), and then an
# interactive Claude reads an empty settings.json and no tool can write it.
SANDBOX_STUB_PATHS = (".claude/settings.json", ".claude/settings.local.json", ".claude/commands", ".claude/agents",
                      ".claude/hooks", ".claude/skills", ".claude/workflows", ".claude/routines",
                      ".claude/scheduled_tasks.json", ".claude/loop.md", ".claude/launch.json", ".mcp.json")
STUB_MIN_AGE_S = 3600  # younger placeholders may belong to a sandboxed command still running (a session of the owner)


def leftover_stubs(project: Path, now: float, min_age_s: float = STUB_MIN_AGE_S) -> list:
    """The placeholders of :data:`SANDBOX_STUB_PATHS` a sandbox left behind: empty read-only regular files, not tracked
    by git, older than ``min_age_s``. Anything else at those paths (a real file, a tracked one) is never listed."""
    found = []
    for path in SANDBOX_STUB_PATHS:
        try:
            age = now - (project / path).lstat().st_mtime
        except OSError:
            continue
        if sandbox_stub(project, path) and age >= min_age_s:
            found.append(path)
    return sorted(set(found) - set(tracked(project, found))) if found else []


def remove_stubs(project: Path, paths) -> list:
    """Remove the placeholders ``paths`` (as :func:`leftover_stubs` gave them, checked again); the removed ones."""
    removed = []
    for path in paths:
        if path in SANDBOX_STUB_PATHS and sandbox_stub(project, path):
            try:
                (project / path).unlink()
            except OSError:
                continue
            removed.append(path)
    return removed


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


def tracked(project: Path, paths) -> list:
    """The ``paths`` git tracks (a tracked file that was deleted still is)."""
    paths = sorted(set(paths))
    if not paths:
        return []
    listing = checks_mod.git(project, "ls-files", "-z", "--", *[f":(literal){path}" for path in paths])
    return sorted(set(listing.split("\0")) - {""})


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


def under(path: str, patterns) -> bool:
    """Whether a repository-relative ``path`` is owned by one of ``patterns`` (the rules of ``write_set``)."""
    return any(matches(path, pattern) for pattern in patterns or [] if isinstance(pattern, str))


# Paths any piece may change whatever its module: the changelog and the documentation of the repository.
ALWAYS_ALLOWED = ("CHANGELOG.md", "docs/")
MODULE_ROOTS = ("packages", "bridges")  # ``<root>/<id>/...`` is the module ``<root>/<id>``; everything else is the hub


def module_of(path: str) -> str:
    """``packages/<id>``, ``bridges/<id>`` or ``hub`` (the scripts, configs and the rest of the repository root)."""
    parts = [part for part in str(path).split("/") if part and part != "."]
    if len(parts) > 1 and parts[0] in MODULE_ROOTS:
        return f"{parts[0]}/{parts[1]}"
    return "hub"


def _pattern_module(pattern: str) -> str:
    """The module a write-set pattern names, read up to its first ``*``, ``?`` or ``[``: ``packages/<root>/*`` when the
    id of the module is itself a pattern (``packages/*/lib/x.py``, ``packages/**``), ``hub`` for a pattern that starts
    with a glob."""
    parts = [part for part in str(pattern).split("/") if part and part != "."]
    if not parts or parts[0] not in MODULE_ROOTS:
        return "hub"
    if len(parts) == 1:
        return f"{parts[0]}/*" if str(pattern).endswith("/") else "hub"
    return f"{parts[0]}/{parts[1]}"


def _always_allowed(pattern: str) -> bool:
    normal = _normal(pattern)
    return normal == ALWAYS_ALLOWED[0] or normal.startswith(ALWAYS_ALLOWED[1])


def item_modules(write_set) -> set:
    """The modules the patterns of ``write_set`` name (``module_of`` of the pattern up to its first glob character); a
    pattern of ``ALWAYS_ALLOWED`` names none, so a documentation path does not make the hub a module of the piece. A
    module that is itself a pattern (``packages/or*``) stays a pattern: :func:`in_modules` matches it."""
    return {_pattern_module(pattern) for pattern in write_set or []
            if isinstance(pattern, str) and pattern and not _always_allowed(pattern)}


def in_modules(path: str, modules) -> bool:
    module = module_of(path)
    return any(fnmatchcase(module, wanted) for wanted in modules)


def in_directories(path: str, directories, project: Path) -> bool:
    """Whether ``path`` (relative to ``project``) lies in one of ``directories`` (``~`` expanded, a relative one read from
    the project): the granted ``scope.extra_paths`` that happen to be inside the project."""
    root = os.path.realpath(str(project))
    target = os.path.join(root, path)
    for directory in directories or []:
        base = os.path.realpath(os.path.join(root, os.path.expanduser(str(directory))))
        if target == base or target.startswith(base.rstrip("/") + "/"):
            return True
    return False


def foreign(paths, write_set, directories=(), project: Optional[Path] = None) -> list:
    """The ``paths`` (already outside the write set) that belong to another module than the ones the write set names:
    not the changelog or the documentation, not a granted extra directory. None when the input names no write set."""
    patterns = [pattern for pattern in write_set or [] if isinstance(pattern, str) and pattern]
    if not patterns:
        return []
    modules = item_modules(patterns)
    return sorted(path for path in paths
                  if not under(path, ALWAYS_ALLOWED) and not in_modules(path, modules)
                  and not (project is not None and in_directories(path, directories, project)))


def own(paths, excluded_prefixes) -> list:
    """``paths`` without those below one of ``excluded_prefixes`` (the artifact folder, the conductor reports)."""
    prefixes = [prefix.rstrip("/") + "/" for prefix in excluded_prefixes if prefix]
    return sorted(path for path in paths if not any(path.startswith(prefix) or path + "/" == prefix
                                                    for prefix in prefixes))
