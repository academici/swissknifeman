"""Git guard (policy §§5.4, 5.10; port of hooks/git-guardrails ``git_guard.py``).

Every simple command of the line (wrappers, assignments, ``sh -c``, ``eval`` and ``find -exec`` bodies are
unwrapped by ``shell_words``) whose program is ``git`` is judged after its global options; ``-c alias.x=…``
expands the alias, and a ``!`` alias body is judged as a shell line. ``check`` returns the first violation,
``violations`` all of them (the classifier needs every one). ``reset`` and ``clean`` read long options as
git does, abbreviations included; a spelling the guard cannot resolve is refused. ``REGEX_FALLBACK``
holds the eleven safety-net rules of ``lifecycle_git_guardrails_core``; they run on ``ShellScan.visible_text``
with collapsed whitespace, so a quoted ``echo "git push"`` is no longer a hit. A line outside the supported
shell subset is judged by the fallback rules only.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from .shell_scan import scan
from .shell_words import MAX_DEPTH, SEPARATORS, SHELLS, WRAPPER_VALUE_OPTS, WRAPPERS, parse

__all__ = [
    "GIT_VALUE_OPTS",
    "MAX_DEPTH",
    "REGEX_FALLBACK",
    "SEPARATORS",
    "SHELLS",
    "WRAPPERS",
    "WRAPPER_VALUE_OPTS",
    "FallbackRule",
    "GitViolation",
    "check",
    "fallback_hits",
    "judge",
    "split_globals",
    "violations",
]

GIT_VALUE_OPTS = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
)
_PUSH_FORCE = frozenset(
    {"-f", "--force", "--force-with-lease", "--force-if-includes", "--mirror", "--delete", "-d"}
)
_PUSH_FORCE_PREFIX = ("--force-with-lease=", "--force-if-includes=")
# long options of ``git reset``/``git clean`` (builtin/reset.c, builtin/clean.c) with their negations
_RESET_DISCARD = frozenset({"hard", "keep", "merge"})
_RESET_LONG = _RESET_DISCARD | frozenset(
    {
        "quiet",
        "no-quiet",
        "refresh",
        "no-refresh",
        "soft",
        "mixed",
        "recurse-submodules",
        "no-recurse-submodules",
        "patch",
        "no-patch",
        "intent-to-add",
        "no-intent-to-add",
        "pathspec-from-file",
        "pathspec-file-nul",
        "no-pathspec-file-nul",
    }
)
_CLEAN_LONG = frozenset(
    {
        "quiet",
        "no-quiet",
        "dry-run",
        "no-dry-run",
        "force",
        "no-force",
        "interactive",
        "no-interactive",
        "exclude",
        "no-exclude",
    }
)


@dataclass(frozen=True, slots=True)
class GitViolation:
    id: str
    severity: str  # high | critical
    command: str  # the judged git argv, joined


@dataclass(frozen=True, slots=True)
class FallbackRule:
    id: str
    pattern: re.Pattern[str]


def _short_flags(args: list[str]) -> set[str]:
    """Letters of clustered short options (``-fd`` → {f, d}); long options are not split."""
    letters: set[str] = set()
    for arg in args:
        if arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
            letters.update(arg[1:])
    return letters


def _push(args: list[str]) -> str:
    letters = _short_flags(args)
    if (
        any(arg in _PUSH_FORCE or arg.startswith(_PUSH_FORCE_PREFIX) for arg in args)
        or {"f", "d"} & letters
        or "--prune" in args
        or any(arg.startswith(("+", ":")) and len(arg) > 1 for arg in args if not arg.startswith("-"))
    ):
        return "push-force"
    return "git-push"


def _checkout(sub: str, args: list[str]) -> str | None:
    pathspec = any(arg in {".", ":/"} for arg in args)
    letters = _short_flags(args)
    staged_only = ("--staged" in args or "S" in letters) and "--worktree" not in args and "W" not in letters
    if sub == "restore" and pathspec and staged_only:
        return None
    if pathspec:
        return "git-checkout-dot"
    if sub == "checkout" and ("--force" in args or "f" in _short_flags(args)):
        return "git-checkout-force"
    return None


def _long_options(args: list[str], known: frozenset[str], destructive: frozenset[str]) -> set[str] | None:
    """Long options before ``--`` as git reads them: git accepts every unambiguous abbreviation
    (``--har`` is ``--hard``). A spelling that abbreviates a destructive option counts as it even when
    ambiguous; ``None``: a spelling the guard does not know (refused, never assumed harmless)."""
    names: set[str] = set()
    for arg in args:
        if arg in {"--", "--end-of-options"}:
            break
        if not arg.startswith("--"):
            continue
        name = arg[2:].split("=", 1)[0]
        dangerous = [option for option in sorted(destructive) if name and option.startswith(name)]
        matches = [option for option in sorted(known) if name and option.startswith(name)]
        if name in known:
            names.add(name)
        elif dangerous:
            names.update(dangerous)
        elif len(matches) == 1:
            names.add(matches[0])
        else:
            return None
    return names


def _reset(args: list[str]) -> str | None:
    names = _long_options(args, _RESET_LONG, _RESET_DISCARD)
    return "reset-hard" if names is None or names & _RESET_DISCARD else None


def _clean(args: list[str]) -> str | None:
    names = _long_options(args, _CLEAN_LONG, frozenset({"force"}))
    letters = _short_flags(args)
    if names is None:
        return "git-clean-f"
    if "force" not in names and "f" not in letters:
        return None
    dry = ("dry-run" in names or "n" in letters) and "no-dry-run" not in names
    return None if dry else "git-clean-f"


def _judge_table(sub: str, args: list[str]) -> str | None:  # noqa: PLR0911 - the §5.10 table, row by row
    letters = _short_flags(args)
    if sub == "push":
        return _push(args)
    if sub == "reset":
        return _reset(args)
    if sub == "clean":
        return _clean(args)
    if sub == "branch" and (
        "D" in letters or (("d" in letters or "--delete" in args) and ("f" in letters or "--force" in args))
    ):
        return "git-branch-delete"
    if sub in {"checkout", "restore"}:
        return _checkout(sub, args)
    if sub == "switch" and ("--discard-changes" in args or "--force" in args or "f" in letters):
        return "git-checkout-force"
    if sub == "stash" and args[:1] in (["drop"], ["clear"]):
        return "git-stash-drop"
    if sub == "reflog" and args[:1] in (["expire"], ["delete"]):
        return "git-reflog-expire"
    if sub == "update-ref" and ("-d" in args or "--delete" in args):
        return "git-update-ref-delete"
    if sub == "rebase" and any(arg == "--onto" or arg.startswith("--onto=") for arg in args):
        return "rebase-onto"
    if sub == "filter-branch":
        return "git-filter-branch"
    return None


_SEVERITY = {
    "push-force": "critical",
    "reset-hard": "critical",
    "git-clean-f": "critical",
    "rebase-onto": "critical",
    "git-filter-branch": "critical",
}


def split_globals(args: tuple[str, ...]) -> tuple[dict[str, str], str | None, list[str]]:
    """``git`` arguments → (``-c`` config values, subcommand, its arguments)."""
    config: dict[str, str] = {}
    index = 0
    while index < len(args):
        arg = args[index]
        if not arg.startswith("-"):
            return config, arg, list(args[index + 1 :])
        if arg in GIT_VALUE_OPTS:
            value = args[index + 1] if index + 1 < len(args) else ""
            if arg == "-c" and "=" in value:
                key, _, item = value.partition("=")
                config[key.lower()] = item
            index += 2
            continue
        if arg.startswith("-c") and "=" in arg[2:]:
            key, _, item = arg[2:].partition("=")
            config[key.lower()] = item
        index += 1
    return config, None, []


def judge(argv: tuple[str, ...], *, depth: int = 0) -> tuple[GitViolation, ...]:
    """Violations of one git argv (``argv[0]`` is the git program), aliases included."""
    config, sub, args = split_globals(argv[1:])
    if sub is None:
        return ()
    alias = config.get(f"alias.{sub.lower()}")
    if alias is not None and depth < MAX_DEPTH:
        if alias.startswith("!"):
            return violations(alias[1:], depth=depth + 1)
        try:
            expanded = shlex.split(alias)
        except ValueError:
            text = f"git {alias}"
            return tuple(
                GitViolation(rule.id, _SEVERITY.get(rule.id, "high"), text) for rule in fallback_hits(text)
            )
        if expanded:
            return judge(("git", *expanded, *args), depth=depth + 1)
    found = _judge_table(sub, args)
    if found is None:
        return ()
    return (GitViolation(found, _SEVERITY.get(found, "high"), " ".join(argv)),)


def violations(command: str, *, depth: int = 0) -> tuple[GitViolation, ...]:
    """All git violations of a shell line; an unsupported line falls back to ``REGEX_FALLBACK``."""
    parsed = parse(command)
    if not parsed.supported:
        return tuple(
            GitViolation(rule.id, _SEVERITY.get(rule.id, "high"), command) for rule in fallback_hits(command)
        )
    found: list[GitViolation] = []
    for simple in parsed.commands:
        if simple.head == "git":
            found.extend(judge(simple.argv, depth=depth))
    return tuple(found)


def check(command: str) -> GitViolation | None:
    """First violation of the line, or ``None``."""
    found = violations(command)
    return found[0] if found else None


_GIT = r"\bgit(?:\s+(?:-[Cc]\s+\S+|--?[A-Za-z][\w-]*(?:=\S*)?))*\s+"
_ARGS = r"(?:[^;&|]*\s)?"
_END = r"(?=\s|$|[;&|)])"  # a word ends at a blank, the line end or a separator


def _abbreviated(*names: str) -> str:
    """Every spelling git reads as one of the long options ``names`` (``--har`` is ``--hard``)."""
    spellings = sorted(
        {name[:end] for name in names for end in range(1, len(name) + 1)}, key=len, reverse=True
    )
    return "--(?:" + "|".join(spellings) + r")(?=\s|$|[=;&|)])"


REGEX_FALLBACK: tuple[FallbackRule, ...] = tuple(
    FallbackRule(rule_id, re.compile(pattern))
    for rule_id, pattern in (
        ("push-force-with-lease", _GIT + r"push\s" + _ARGS + r"--force-(?:with-lease|if-includes)\b"),
        (
            "push-force",
            _GIT
            + r"push\s"
            + _ARGS
            + r"(?:-[A-Za-z]*[fd][A-Za-z]*|--force|--mirror|--delete|--prune|\+\S+)"
            + _END,
        ),
        ("git-push", _GIT + r"push\b"),
        ("reset-hard", _GIT + r"reset\s" + _ARGS + _abbreviated("hard", "keep", "merge")),
        (
            "git-clean-f",
            _GIT + r"clean\s" + _ARGS + r"(?:-[A-Za-z]*f[A-Za-z]*" + _END + "|" + _abbreviated("force") + ")",
        ),
        ("git-checkout-dot", _GIT + r"(?:checkout|restore)\s" + _ARGS + r"(?:\.|:/)" + _END),
        (
            "git-checkout-force",
            _GIT + r"(?:checkout|switch)\s" + _ARGS + r"(?:-f|--force|--discard-changes)\b",
        ),
        ("git-stash-drop", _GIT + r"stash\s+(?:drop|clear)\b"),
        ("git-branch-delete", _GIT + r"branch\s" + _ARGS + r"(?:-[A-Za-z]*D[A-Za-z]*)" + _END),
        ("rebase-onto", _GIT + r"rebase\s" + _ARGS + r"--onto\b"),
        ("git-filter-branch", _GIT + r"filter-branch\b"),
    )
)


def fallback_hits(command: str) -> tuple[FallbackRule, ...]:
    """Rules of ``REGEX_FALLBACK`` matching the visible text of the line (whitespace collapsed)."""
    text = " ".join(scan(command).visible_text.split())
    return tuple(rule for rule in REGEX_FALLBACK if rule.pattern.search(text))
