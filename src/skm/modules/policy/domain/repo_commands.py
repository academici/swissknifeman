"""Git, forge and remote-copy command facts the operation classifier relies on (policy §5.2).

Which ``git`` subcommands change the repository configuration, which ``gh``/``glab``
calls write to a forge, whether ``gh api`` stays a read, and whether an ``rsync`` operand is remote.
Each predicate reads already parsed words only; ``classify`` decides what the answer means.
"""

from __future__ import annotations

import re

from . import command_classes as cc

__all__ = ["forge_write", "gh_api_read", "git_config_writes", "git_dir_change", "remote_operand"]

_RSYNC_HOST_RE = re.compile(r"(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9][A-Za-z0-9.-]*")


_GIT_CONFIG_READ = frozenset(
    {
        "--get",
        "--get-all",
        "--get-regexp",
        "--get-urlmatch",
        "--list",
        "-l",
        "--show-origin",
        "--show-scope",
        "--name-only",
        "get",
        "list",
    }
)


_GIT_CONFIG_WRITE = frozenset(
    {
        "--unset",
        "--unset-all",
        "--add",
        "--replace-all",
        "--rename-section",
        "--remove-section",
        "-e",
        "--edit",
        "set",
        "unset",
        "rename-section",
        "remove-section",
        "edit",
    }
)


_GIT_CONFIG_VALUE_OPTIONS = frozenset({"-f", "--file", "--blob", "-t", "--type", "--default", "--comment"})


_GIT_REMOTE_WRITE = frozenset(
    {"add", "set-url", "remove", "rm", "rename", "set-head", "set-branches", "prune"}
)


_GIT_WORKTREE_WRITE = frozenset({"add", "remove", "move", "prune", "repair", "lock", "unlock"})


_GIT_INDEX_FLAGS = frozenset({"--skip-worktree", "--no-skip-worktree", "--assume-unchanged"})


def forge_write(head: str, positionals: tuple[str, ...]) -> bool:
    nouns, verbs = {
        "gh": (cc.FORGE_GH_NOUNS, cc.FORGE_GH_VERBS),
        "glab": (cc.FORGE_GLAB_NOUNS, cc.FORGE_GLAB_VERBS),
    }.get(head, (frozenset[str](), frozenset[str]()))
    return len(positionals) > 1 and positionals[0] in nouns and positionals[1] in verbs


def remote_operand(value: str) -> bool:
    """``rsync://…``, ``[user@]host:path`` (also ``host:/abs``) and ``host::module``; a local path has a
    ``/`` before its first ``:``."""
    if value.startswith("rsync://"):
        return True
    head, sep, _ = value.partition(":")
    return bool(sep) and _RSYNC_HOST_RE.fullmatch(head) is not None


def gh_api_read(args: tuple[str, ...]) -> bool:
    for index, arg in enumerate(args):
        if arg in cc.GH_API_FIELD_FLAGS or any(arg.startswith(flag + "=") for flag in cc.GH_API_FIELD_FLAGS):
            return False
        method = None
        if arg in {"-X", "--method"}:
            method = args[index + 1] if index + 1 < len(args) else ""
        elif arg.startswith("--method="):
            method = arg.split("=", 1)[1]
        elif arg.startswith("-X") and len(arg) > 2:
            method = arg[2:]
        if method is not None and method.upper() not in cc.GH_API_READ_METHODS:
            return False
    return True


def git_dir_change(sub: str | None, args: list[str]) -> bool:
    if sub == "config":
        return git_config_writes(args)
    if sub == "remote":
        return bool(args) and args[0] in _GIT_REMOTE_WRITE
    if sub == "worktree":
        return bool(args) and args[0] in _GIT_WORKTREE_WRITE
    if sub == "update-index":
        return bool(_GIT_INDEX_FLAGS & set(args))
    return sub == "replace"


def git_config_writes(args: list[str]) -> bool:
    """``git config`` changes the configuration unless it is a read form: an explicit write form, else
    anything but exactly one key (``git config key`` reads, ``git config key value`` writes)."""
    names = {arg.split("=", 1)[0] for arg in args}
    positionals: list[str] = []
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in _GIT_CONFIG_VALUE_OPTIONS:
            skip = True
        elif not arg.startswith("-"):
            positionals.append(arg)
    first = positionals[0] if positionals else ""
    if names & _GIT_CONFIG_WRITE or first in _GIT_CONFIG_WRITE:
        return True
    if names & _GIT_CONFIG_READ or first in _GIT_CONFIG_READ:
        return False
    return len(positionals) != 1
