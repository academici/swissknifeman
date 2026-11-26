"""Write-scope path patterns as the fence reads them (planning §5.7; fence: adapters §3.5).

Planning validates declared write scopes with this dialect and execution admits concurrent tasks with it,
so both must agree on what overlaps. The dialect is the fence's: ``*``, ``?`` and ``[..]`` stay inside one
segment, a whole ``**`` segment spans any number of segments (none included), a plain path or a trailing
``/`` names the path and everything under it. Two questions are asked of it:

* ``globs_overlap``: may two patterns share a path? ``False`` only when they provably cannot.
* ``covers``: does one pattern provably cover every path of another? ``False`` unless it provably does.

The two answers err in opposite directions on purpose: a missed overlap hides a write conflict, a missed cover
only raises a warning. ``covers`` follows the fence to the letter: a glob without a trailing ``/`` matches
whole paths and is not closed downwards, only a plain path or a trailing ``/`` names everything under it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

__all__ = ["bare", "covers", "globs_overlap"]

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

# One segment of a pattern is a tuple of tokens: a one-character literal, ``_ANY`` or ``_STAR``; ``_GLOBSTAR``
# is a whole ``**`` segment. None of them can equal a literal token.
_ANY: Final = "<?>"
_STAR: Final = "<*>"
_SET: Final = "<[]>"  # a bracket set read narrowly: no other token is proven to lie within it
_GLOBSTAR: Final[tuple[str, ...]] = ("**",)
_DRIVE: Final = re.compile(r"[A-Za-z]:")

type _Segment = tuple[str, ...]
type _Reading = tuple[_Segment, ...]


def bare(path: str) -> str:
    """``lib/x/``, ``./lib/x`` and ``lib//x`` name ``lib/x``: empty and ``.`` segments, a final ``/`` go."""
    parts = [part for part in path.split("/") if part not in ("", ".")]
    return "/".join(parts) if parts else path


def globs_overlap(left: str, right: str) -> bool:
    """May two write-scope patterns share a path (planning §5.7)? ``False`` only when they provably cannot.

    A path below one a pattern matches counts as well, so a directory overlaps the files in it. A pattern the
    fence rejects, or the root, may overlap anything.
    """
    mine, theirs = _readings(left), _readings(right)
    if mine is None or theirs is None:
        return True
    return any(
        _meet(a, b, _GLOBSTAR, lambda x, y: _meet(x, y, _STAR, _chars_meet)) for a in mine for b in theirs
    )


def covers(pattern: str, by: str) -> bool:
    """Is every path ``pattern`` names provably named by ``by`` as well, in the dialect of the fence?

    ``pattern`` is read in every way it may name paths (a trailing ``/`` after a glob literally and as a
    glob), each of which must be covered; ``by`` only in the fence's own way, and a bracket set of ``by`` is
    narrow: the same pattern always covers itself, nothing else is proven by a bracket. A pattern the fence
    rejects, or the root, is never covered and never covers: nothing is proven about it.
    """
    inner, outer = _covered_readings(pattern), _fence_reading(by)
    if inner is None or outer is None:
        return False
    if _parts(pattern) == _parts(by) and pattern.endswith("/") == by.endswith("/"):
        return True
    return all(_within(a, outer, _GLOBSTAR, lambda x, y: _within(x, y, _STAR, _char_within)) for a in inner)


def _parts(pattern: str) -> list[str] | None:
    """Normalised segments of ``pattern`` (empty and ``.`` removed); ``None`` when the fence rejects it."""
    if (
        not pattern
        or pattern.startswith(("/", "~"))
        or _DRIVE.match(pattern)
        or "\\" in pattern
        or "\x00" in pattern
    ):
        return None
    parts = [part for part in pattern.split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return parts


def _literal(parts: list[str], *, closed: bool = True) -> _Reading:
    """The literal reading of ``parts``; ``closed`` adds the final ``**``: it names what lies below it."""
    segments = tuple(tuple(part) for part in parts)
    return (*segments, _GLOBSTAR) if closed else segments


def _glob(parts: list[str], *, closed: bool = True, narrow: bool = False) -> _Reading:
    """The glob reading of ``parts``; ``closed`` adds the final ``**``: the path names what lies below it."""
    segments = tuple(_GLOBSTAR if part == "**" else _tokens(part, narrow=narrow) for part in parts)
    return (*segments, _GLOBSTAR) if closed else segments


def _has_glob(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def _readings(pattern: str) -> tuple[_Reading, ...] | None:
    """Every way the fence may read ``pattern``, each closed downwards by a final ``**``; ``None``: unknown.

    A trailing ``/`` after a glob is read literally, as the fence does, and as a glob: no wildcard narrows.
    """
    parts = _parts(pattern)
    if parts is None:
        return None
    if not _has_glob(pattern):
        return (_literal(parts),)
    glob = _glob(parts)
    return (_literal(parts), glob) if pattern.endswith("/") else (glob,)


def _fence_reading(pattern: str) -> _Reading | None:
    """The one way the fence reads ``pattern``: literally with a trailing ``/`` or without glob characters;
    a glob matches whole paths. Its bracket sets are narrow."""
    parts = _parts(pattern)
    if parts is None:
        return None
    if pattern.endswith("/") or not _has_glob(pattern):
        return _literal(parts)
    return _glob(parts, closed=False, narrow=True)


def _covered_readings(pattern: str) -> tuple[_Reading, ...] | None:
    """Every way ``pattern`` may name paths, for ``covers``; brackets read as any one character.

    A plain path or a trailing ``/`` names what lies below it, as at the fence (a ``/`` after a glob is read
    both ways); a glob without it matches whole paths only.
    """
    parts = _parts(pattern)
    if parts is None:
        return None
    if not _has_glob(pattern):
        return (_literal(parts),)
    if pattern.endswith("/"):
        return (_literal(parts), _glob(parts))
    return (_glob(parts, closed=False),)


def _tokens(segment: str, *, narrow: bool = False) -> _Segment:
    """Tokens of ``fnmatchcase`` over one segment; a bracket set reads as any one character (a superset), or,
    with ``narrow``, as ``_SET``, which no other token is proven to lie within.

    A ``[`` opens a set where ``fnmatch.translate`` finds its closing ``]``; an unclosed one is literal.
    """
    tokens: list[str] = []
    i, n = 0, len(segment)
    while i < n:
        char = segment[i]
        i += 1
        if char == "*":
            tokens.append(_STAR)
        elif char == "?":
            tokens.append(_ANY)
        elif char == "[":
            end = i + 1 if i < n and segment[i] == "!" else i
            end += 1 if end < n and segment[end] == "]" else 0
            end = segment.find("]", end)
            if end < 0:
                tokens.append(char)
            else:
                tokens.append(_SET if narrow else _ANY)
                i = end + 1
        else:
            tokens.append(char)
    return tuple(tokens)


def _chars_meet(left: str, right: str) -> bool:
    return left == right or _ANY in (left, right)


def _char_within(inner: str, outer: str) -> bool:
    """Is the one-character token ``inner`` matched by ``outer`` for every character it stands for?"""
    return outer == _ANY or (inner == outer and outer != _SET)


def _meet[T](left: Sequence[T], right: Sequence[T], star: T, meet: Callable[[T, T], bool]) -> bool:
    """Do two patterns share a word? ``star`` matches any run of units, any other element exactly one unit,
    and ``meet`` tells whether two such elements match a common unit (each matches at least one)."""
    seen = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        i, j = stack.pop()
        if i == len(left) and j == len(right):
            return True
        a = left[i] if i < len(left) else None
        b = right[j] if j < len(right) else None
        steps: list[tuple[int, int]] = []
        if a == star:
            steps.append((i + 1, j))
        if b == star:
            steps.append((i, j + 1))
        if a is not None and b is not None:
            if a == star and b != star:
                steps.append((i, j + 1))
            elif b == star and a != star:
                steps.append((i + 1, j))
            elif a != star and meet(a, b):
                steps.append((i + 1, j + 1))
        for step in steps:
            if step not in seen:
                seen.add(step)
                stack.append(step)
    return False


def _within[T](inner: Sequence[T], outer: Sequence[T], star: T, within: Callable[[T, T], bool]) -> bool:
    """Is every word of ``inner`` a word of ``outer``? Sound, not complete for exotic stars.

    ``star`` matches any run of units, any other element one unit. A ``star`` of ``inner`` stands for
    arbitrarily many units, so only a ``star`` of ``outer`` can take it; a ``star`` of ``outer`` takes any
    run, an ``inner`` ``star`` among them. ``within`` tells whether one ``inner`` element, as one unit, is
    matched by one ``outer`` element for everything it stands for.
    """
    known: dict[tuple[int, int], bool] = {}

    def covered(i: int, j: int) -> bool:
        if (i, j) in known:
            return known[i, j]
        if j == len(outer):
            result = i == len(inner)
        elif outer[j] == star:
            result = covered(i, j + 1) or (i < len(inner) and covered(i + 1, j))
        elif i == len(inner) or inner[i] == star:
            result = False
        else:
            result = within(inner[i], outer[j]) and covered(i + 1, j + 1)
        known[i, j] = result
        return result

    return covered(0, 0)
