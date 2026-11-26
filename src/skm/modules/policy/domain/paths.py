"""Path scopes, rules and policies (policy §§4.2, 5.3 F1/F2, 5.11).

A path is judged after the host resolved it (``PathFacts.resolve``: absolute realpath, symlinks followed),
so a symlink inside the worktree that points elsewhere is classified by its target. ``classify_path`` picks
the longest matching root; a path under no root has scope ``any``. Patterns are POSIX globs relative to the
scope root: ``*`` and ``?`` stay inside one segment, ``**`` spans any number of segments (``**`` alone also
matches the root itself), ``[..]`` is a class. A rule matches only paths of its own scope.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "PathPolicy",
    "PathRule",
    "PathScope",
    "ScopeRoots",
    "ScopedPath",
    "classify_path",
    "glob_match",
    "inside",
    "is_protected",
    "own_roots",
    "subsumes",
    "unrestricted_policy",
]


class PathScope(StrEnum):
    WORKTREE = "worktree"
    MATERIALS = "materials"
    TMP = "tmp"
    HOME = "home"
    SAFE_DIR = "safe_dir"
    ANY = "any"


@dataclass(frozen=True, slots=True)
class PathRule:
    scope: PathScope
    pattern: str
    mount: str | None = None

    def matches(self, scoped: ScopedPath) -> bool:
        if self.scope is not scoped.scope:
            return False
        if self.mount is not None and self.mount != scoped.mount:
            return False
        return glob_match(self.pattern, scoped.relative)


@dataclass(frozen=True, slots=True)
class ScopedPath:
    scope: PathScope
    mount: str | None
    relative: str  # POSIX path inside the root ("" = the root itself)


@dataclass(frozen=True, slots=True)
class PathPolicy:
    allow: tuple[PathRule, ...]
    deny: tuple[PathRule, ...]

    def allows(self, scoped: ScopedPath) -> bool:
        return any(rule.matches(scoped) for rule in self.allow) and not any(
            rule.matches(scoped) for rule in self.deny
        )

    def allows_scope(self, scope: PathScope) -> bool:
        return any(rule.scope is scope for rule in self.allow)


def unrestricted_policy() -> PathPolicy:
    """Every path of every scope; used for a layer that only denies."""
    return PathPolicy(tuple(PathRule(scope, "**") for scope in PathScope), ())


@dataclass(frozen=True, slots=True)
class ScopeRoots:
    worktrees: Mapping[str, str]  # mount → realpath of the attempt worktree (hook: checkout root)
    materials: str | None
    tmp: str | None
    home: str | None
    safe_dirs: tuple[str, ...]
    protected: tuple[str, ...]  # state_dir, blobs, backups, worktrees_root, materialized_root
    remote_hosts: frozenset[str]


@lru_cache(maxsize=1024)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**", i):
            at_start = i == 0 or pattern[i - 1] == "/"
            rest = pattern[i + 2 :]
            if at_start and rest.startswith("/"):
                out.append("(?:[^/]+/)*")
                i += 3
                continue
            if at_start and not rest:
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 2
        elif char == "*":
            out.append("[^/]*")
            i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        elif char == "[":
            start = i + 1
            negate = pattern[start : start + 1] in {"!", "^"}
            start += 1 if negate else 0
            end = pattern.find("]", start + 1 if pattern[start : start + 1] == "]" else start)
            if end < 0:
                out.append(re.escape(char))
                i += 1
                continue
            body = "".join(c if c == "-" else re.escape(c) for c in pattern[start:end])
            out.append(f"[^/{body}]" if negate else f"(?!/)[{body}]")
            i = end + 1
        else:
            out.append(re.escape(char))
            i += 1
    return re.compile("".join(out), re.DOTALL)


def glob_match(pattern: str, relative: str) -> bool:
    """Whether ``relative`` (no leading ``/``; ``""`` is the root) matches the scope-relative glob."""
    if pattern == "**":
        return True
    return _glob_regex(pattern).fullmatch(relative) is not None


def _has_glob(text: str) -> bool:
    return any(char in text for char in "*?[")


def inside(path: str, root: str) -> bool:
    """``path`` is ``root`` or below it (both absolute, normalized)."""
    root = root.rstrip("/") or "/"
    return path == root or path.startswith(root if root == "/" else root + "/")


def _relative(path: str, root: str) -> str:
    root = root.rstrip("/") or "/"
    if path == root:
        return ""
    return path[len(root) :].lstrip("/")


def _roots(roots: ScopeRoots) -> Iterator[tuple[PathScope, str | None, str]]:
    for mount, root in roots.worktrees.items():
        yield PathScope.WORKTREE, mount, root
    if roots.materials is not None:
        yield PathScope.MATERIALS, None, roots.materials
    if roots.tmp is not None:
        yield PathScope.TMP, None, roots.tmp
    if roots.home is not None:
        yield PathScope.HOME, None, roots.home
    for root in roots.safe_dirs:
        yield PathScope.SAFE_DIR, None, root


def classify_path(path: str, roots: ScopeRoots) -> ScopedPath:
    """Scope of a resolved absolute path by the longest root containing it; ``any`` otherwise."""
    normalized = posixpath.normpath(path) if path else "/"
    best: tuple[int, PathScope, str | None, str] | None = None
    for scope, mount, root in _roots(roots):
        clean = posixpath.normpath(root)
        if inside(normalized, clean) and (best is None or len(clean) > best[0]):
            best = (len(clean), scope, mount, clean)
    if best is None:
        return ScopedPath(PathScope.ANY, None, normalized.lstrip("/"))
    _, scope, mount, root = best
    return ScopedPath(scope, mount, _relative(normalized, root))


def own_roots(roots: ScopeRoots) -> tuple[str, ...]:
    """Roots that belong to the attempt itself: its worktrees, materials and tmp."""
    own = [*roots.worktrees.values()]
    own.extend(root for root in (roots.materials, roots.tmp) if root is not None)
    return tuple(own)


def is_protected(path: str, roots: ScopeRoots) -> bool:
    """Inside an SKM state root and not inside one of the attempt's own roots (P0, any profile)."""
    normalized = posixpath.normpath(path)
    if any(inside(normalized, posixpath.normpath(root)) for root in own_roots(roots)):
        return False
    return any(inside(normalized, posixpath.normpath(root)) for root in roots.protected)


def subsumes(outer: PathRule, inner: PathRule) -> bool:
    """Provable ``inner ⊆ outer`` by prefix (§5.11); ``False`` means unproven, not disjoint. A rule matches
    only paths of its own scope, so an ``any`` rule never covers a rule of another scope."""
    if outer.scope is not inner.scope:
        return False
    if outer.mount is not None and outer.mount != inner.mount:
        return False
    if outer.pattern in {"**", inner.pattern}:
        return True
    if outer.pattern.endswith("/**") and not _has_glob(outer.pattern[:-3]):
        return inner.pattern.startswith(outer.pattern[:-2])
    return False
