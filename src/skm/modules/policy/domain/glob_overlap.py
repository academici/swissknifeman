"""Whether a shell glob can name a path a policy glob matches (secret paths of K12).

A shell word such as ``~/.netr?`` is expanded by bash before the program runs, so matching the word
literally against ``.netrc`` misses the file it reads. ``glob_overlap`` decides whether some path matches
both patterns. The shell side follows bash without ``dotglob``/``globstar``: ``*``, ``?`` and brackets
never match ``/`` and never match the leading ``.`` of a component (``**`` is ``*`` twice). The policy side
follows ``paths.glob_match``; its ``**`` is widened to match anything, so a doubt counts as an overlap.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["glob_overlap"]


@dataclass(frozen=True, slots=True)
class _Token:
    chars: frozenset[str] = frozenset()
    ranges: tuple[tuple[str, str], ...] = ()
    negate: bool = False  # matches the characters outside chars/ranges
    repeat: bool = False  # zero or more characters (``*``, ``**``)
    slash: bool = False  # may match ``/``
    wildcard: bool = False  # cannot match the leading ``.`` of a component (shell side)

    def accepts(self, char: str) -> bool:
        if char == "/" and not self.slash:
            return False
        inside = char in self.chars or any(low <= char <= high for low, high in self.ranges)
        return inside != self.negate


def _literal(char: str) -> _Token:
    return _Token(chars=frozenset(char), slash=char == "/")


def _bracket(pattern: str, i: int, *, bash: bool) -> tuple[_Token, int] | None:
    start = i + 1
    negate = pattern[start : start + 1] in {"!", "^"}
    if negate:
        start += 1
    end = pattern.find("]", start + 1 if pattern[start : start + 1] == "]" else start)
    if end < 0:
        return None
    body = pattern[start:end]
    chars: set[str] = set()
    ranges: list[tuple[str, str]] = []
    k = 0
    while k < len(body):
        if k + 2 < len(body) and body[k + 1] == "-":
            ranges.append((body[k], body[k + 2]))
            k += 3
        else:
            chars.add(body[k])
            k += 1
    return _Token(frozenset(chars), tuple(ranges), negate, wildcard=bash), end + 1


def _tokens(pattern: str, *, bash: bool) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            double = not bash and pattern.startswith("**", i)
            tokens.append(_Token(negate=True, repeat=True, slash=double, wildcard=bash))
            i += 2 if double else 1
        elif char == "?":
            tokens.append(_Token(negate=True, wildcard=bash))
            i += 1
        elif char == "[" and (parsed := _bracket(pattern, i, bash=bash)) is not None:
            token, i = parsed
            tokens.append(token)
        else:
            tokens.append(_literal(char))
            i += 1
    return tokens


def _alphabet(tokens: list[_Token]) -> tuple[str, ...]:
    """One character of every region the token classes split the characters into."""
    points = {"/", ".", "\x01"}
    for token in tokens:
        points.update(token.chars)
        for low, high in token.ranges:
            points.update((low, high))
    near = {
        chr(code)
        for point in points
        for code in (ord(point) - 1, ord(point), ord(point) + 1)
        if 0 < code <= 0x10FFFF
    }
    return tuple(sorted(near))


def glob_overlap(word: str, glob: str, *, prefix: str = "") -> bool:
    """Whether a path matches both the shell glob ``word`` and ``prefix`` (literal) + the policy ``glob``."""
    shell = _tokens(word, bash=True)
    policy = [_literal(char) for char in prefix] + _tokens(glob, bash=False)
    alphabet = _alphabet(shell + policy)
    pending = [(0, 0, True)]
    seen: set[tuple[int, int, bool]] = set()
    while pending:
        state = pending.pop()
        if state in seen:
            continue
        seen.add(state)
        i, j, leading = state
        if i == len(shell) and j == len(policy):
            return True
        if i < len(shell) and shell[i].repeat:
            pending.append((i + 1, j, leading))
        if j < len(policy) and policy[j].repeat:
            pending.append((i, j + 1, leading))
        if i == len(shell) or j == len(policy):
            continue
        left, right = shell[i], policy[j]
        for char in alphabet:
            if not (left.accepts(char) and right.accepts(char)):
                continue
            if leading and char == "." and left.wildcard:
                continue
            pending.append((i if left.repeat else i + 1, j if right.repeat else j + 1, char == "/"))
    return False
