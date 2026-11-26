"""Safe deletion check (policy §5.5; port of auto-approve ``lib/safedirs.py`` lines 168-349).

The line is split by ``shlex`` with ``punctuation_chars=";|&<>()"``. A line with a newline, an
``rm``/``rmdir``
word that is not the head of its segment (``git rm`` excepted; after a wrapper also ``/bin/rm``), an unknown
flag or an argument holding ``$``, a backtick, a brace or a ``..`` segment is unsafe. ``cd``/``pushd``/
``popd`` move the working directory; as a pipeline member, in the background, behind ``&&``/``||``, before
``||`` or behind a wrapper the directory is unknown and a relative target is unsafe. Every target,
resolved through the injected ``resolve``, must lie strictly inside one of ``write_roots`` (a glob may name
the root itself: the glob path is cut before its first glob character), outside ``excludes`` and, with
``protect_git``, outside any ``.git``. Roots come from the permission set, not from ``safe-dirs.json``.
"""

from __future__ import annotations

import posixpath
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass

from .shell_words import WRAPPERS

__all__ = ["DELETE_PROGRAMS", "RmTarget", "rm_is_safe", "rm_targets"]

type Resolve = Callable[[str, str], str]

DELETE_PROGRAMS = frozenset({"rm", "rmdir"})
_RM_FLAGS = frozenset(
    {"-r", "-R", "-f", "-v", "-d", "-i", "-I", "--recursive", "--force", "--verbose", "--dir"}
)
_RM_LETTERS = frozenset("rRfvdiI")
_RMDIR_FLAGS = frozenset({"-v", "--verbose", "--ignore-fail-on-non-empty"})
_GIT_RM_FLAGS = frozenset(
    {"-r", "-f", "-q", "-n", "--cached", "--force", "--quiet", "--dry-run", "--ignore-unmatch", "--sparse"}
)
_PUNCTUATION = ";|&<>()"
_MOVES = frozenset({"cd", "pushd", "popd"})
_CERTAIN_BEFORE = frozenset({"", ";", "&"})
_CERTAIN_AFTER = frozenset({"", ";", "&&"})
_GLOB = "*?["
# legacy ``safedirs_applicable``: only a line that mentions a deletion program is judged here
_MENTIONS_DELETE = re.compile(r"(?<![\w.-])(?:rm|rmdir)(?![\w.-])")


class _Unsafe(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RmTarget:
    argument: str  # as written
    cwd: str | None  # working directory at that point; None after a branch
    glob: bool
    cached: bool = False  # git rm --cached: the index entry only


def _tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=_PUNCTUATION)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError as error:
        raise _Unsafe(str(error)) from error


def _segments(tokens: list[str]) -> list[tuple[list[str], str, str]]:
    """``(words, separator before, separator after)``; a redirect and its target stay inside the command
    (``rm a > log b`` deletes ``a`` and ``b``)."""
    result: list[tuple[list[str], str, str]] = []
    words: list[str] = []
    before = ""
    target = False
    for token in tokens:
        if token and all(char in _PUNCTUATION for char in token):
            if any(char in "<>" for char in token) and "(" not in token and ")" not in token:
                target = True
                continue
            result.append((words, before, token))
            words, before, target = [], token, False
        elif target:
            target = False
        else:
            words.append(token)
    result.append((words, before, ""))
    return result


def _moves_parent(before: str, after: str) -> bool:
    """A ``cd``/``pushd``/``popd`` that surely runs in the parent shell: not a pipeline member (a subshell,
    or the current shell under ``lastpipe``), not in the background, not skipped by ``&&``/``||``."""
    return before in _CERTAIN_BEFORE and after in _CERTAIN_AFTER


def _operands(words: list[str], flags: frozenset[str], letters: frozenset[str]) -> tuple[list[str], bool]:
    operands: list[str] = []
    cached = False
    options = True
    for word in words:
        if options and word == "--":
            options = False
        elif options and word.startswith("-") and word != "-":
            if word == "--cached":
                cached = True
            if word not in flags and not (letters and not word.startswith("--") and set(word[1:]) <= letters):
                raise _Unsafe(f"unknown flag {word}")
        else:
            operands.append(word)
    return operands, cached


def _walk(command: str, cwd: str, resolve: Resolve, home: str | None) -> list[RmTarget]:
    if "\n" in command or "\r" in command:
        raise _Unsafe("newline")
    current: str | None = cwd
    stack: list[str | None] = []
    targets: list[RmTarget] = []
    for words, before, op in _segments(_tokens(command)):
        if not words:
            continue
        head = posixpath.basename(words[0])  # ``/bin/rm`` deletes like ``rm``
        wrapped = head in WRAPPERS  # ``env -C dir /bin/rm x``: the wrapper moves and deletes
        for index, word in enumerate(words[1:], start=1):
            name = posixpath.basename(word) if wrapped else word
            if name in DELETE_PROGRAMS and not (index == 1 and head == "git"):
                raise _Unsafe(f"{word} is not the head of its segment")
        if head in _MOVES and not _moves_parent(before, op):
            stack = list[str | None]([None] * (len(stack) + (head == "pushd")))
            current = None
        elif wrapped and any(posixpath.basename(word) in _MOVES for word in words[1:]):
            current = None  # ``command cd`` moves the shell, ``env cd`` does not: unknown
        elif head in {"cd", "pushd"}:
            if head == "pushd":
                stack.append(current)
            current = _cd(words[1:], current, resolve, home)
        elif head == "popd":
            current = stack.pop() if stack else None
        elif head in DELETE_PROGRAMS:
            flags, letters = (_RM_FLAGS, _RM_LETTERS) if head == "rm" else (_RMDIR_FLAGS, frozenset[str]())
            operands, _ = _operands(words[1:], flags, letters)
            targets.extend(RmTarget(arg, current, any(c in arg for c in _GLOB)) for arg in operands)
        elif head == "git" and words[1:2] == ["rm"]:
            operands, cached = _operands(words[2:], _GIT_RM_FLAGS, frozenset("rfqn"))
            targets.extend(RmTarget(arg, current, any(c in arg for c in _GLOB), cached) for arg in operands)
    return targets


def _cd(args: list[str], current: str | None, resolve: Resolve, home: str | None) -> str | None:
    target = args[0] if args else home
    if target is None or current is None or target == "-" or any(c in target for c in "$`{}"):
        return None
    expanded = _expand_home(target, home)
    return None if expanded is None else resolve(expanded, current)


def _expand_home(argument: str, home: str | None) -> str | None:
    if argument == "~" or argument.startswith("~/"):
        return None if home is None else home + argument[1:]
    if argument.startswith("~"):
        return None
    return argument


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _target_safe(
    target: RmTarget,
    write_roots: tuple[str, ...],
    excludes: tuple[str, ...],
    home: str | None,
    resolve: Resolve,
    *,
    allow_globs: bool,
    protect_git: bool,
) -> bool:
    argument = target.argument
    if any(char in argument for char in "$`{}") or ".." in argument.split("/"):
        return False
    expanded = _expand_home(argument, home)
    if expanded is None or target.cwd is None:
        return False
    if target.glob:
        if not allow_globs:
            return False
        hidden = any(part.startswith(".") and any(c in part for c in _GLOB) for part in expanded.split("/"))
        if protect_git and (".git" in expanded or hidden):
            return False
        cut = expanded[: min(expanded.index(c) for c in _GLOB if c in expanded)]
        expanded = cut.rsplit("/", 1)[0] if "/" in cut else "."
        if cut.startswith("/") and "/" not in cut[1:]:
            expanded = "/"
    path = resolve(expanded, target.cwd)
    if protect_git and ".git" in path.split("/"):
        return False
    if any(
        _inside(path, excluded)
        and not any(_inside(root, excluded) and _inside(path, root) for root in write_roots)
        for excluded in excludes
    ):
        return False
    return any(_inside(path, root) and (path != root.rstrip("/") or target.glob) for root in write_roots)


def rm_is_safe(
    command: str,
    cwd: str,
    write_roots: tuple[str, ...],
    excludes: tuple[str, ...],
    home: str | None,
    *,
    resolve: Resolve,
    allow_globs: bool = True,
    protect_git: bool = True,
) -> bool:
    """Every deletion of the line stays inside the write roots; a line that names no deletion program is
    safe here (its syntax is judged by the supported-shell gate, §5.2a)."""
    if _MENTIONS_DELETE.search(command) is None:
        return True
    try:
        targets = _walk(command, cwd, resolve, home)
    except _Unsafe:
        return False
    return all(
        _target_safe(
            target, write_roots, excludes, home, resolve, allow_globs=allow_globs, protect_git=protect_git
        )
        for target in targets
        if not target.cached
    )


def rm_targets(command: str, cwd: str, resolve: Resolve, *, home: str | None = None) -> tuple[str, ...]:
    """Absolute targets of ``rm``/``rmdir``/``git rm`` (globs joined with the directory, not expanded);
    ``()`` when the line cannot be parsed — ``rm_is_safe`` refuses such a line."""
    try:
        targets = _walk(command, cwd, resolve, home)
    except _Unsafe:
        return ()
    result: list[str] = []
    for target in targets:
        expanded = _expand_home(target.argument, home)
        if expanded is None or target.cwd is None or target.cached:
            continue
        if target.glob:
            result.append(posixpath.normpath(posixpath.join(target.cwd, expanded)))
        else:
            result.append(resolve(expanded, target.cwd))
    return tuple(result)
