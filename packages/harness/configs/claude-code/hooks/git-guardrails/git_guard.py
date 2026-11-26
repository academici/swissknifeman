#!/usr/bin/env python3
"""Argv-level check of destructive git commands (stdlib only, Python 3.9+).

One implementation for every provider: `block-dangerous-git.sh` (Claude Code) runs it as a script,
`harness.lifecycle_git_guardrails_core` (Codex, Cursor, Grok) imports it by path.

The command is split into simple commands, wrappers (`env`, `sudo`, `command`, `xargs`, ...) are
skipped, shell bodies (`bash -c`, `eval`, `$(...)`, backticks) are searched too, git's global
options (`-C dir`, `-c k=v`, `--git-dir=...`) are skipped, and the subcommand is judged with its flags.

CLI: JSON `{"tool_input": {"command": ...}}` on stdin; exit 2 and a message on stderr when blocked.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from typing import Iterator, List, NamedTuple, Optional, Sequence

SEPARATORS = {";", "&&", "||", "|", "&", "|&", "(", ")", "{", "}", "\n", ";;"}
WRAPPERS = {"env", "sudo", "doas", "command", "builtin", "exec", "nohup", "time", "nice", "ionice", "setsid",
            "xargs", "stdbuf", "timeout", "watch", "then", "do", "else", "!", "if", "while", "until"}
WRAPPER_VALUE_OPTS = {"timeout": 0, "nice": 0, "ionice": 0, "sudo": 0, "doas": 0, "env": 0}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "ash", "fish"}
# git global options that take a value in the next word.
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--exec-path",
                  "--config-env", "--attr-source", "--list-cmds"}
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
MAX_DEPTH = 6


class Violation(NamedTuple):
    id: str
    reason: str
    tier: str


def _flags(args: Sequence[str]) -> List[str]:
    return [a for a in args if a.startswith("-") and a != "--"]


def _has_short(args: Sequence[str], letters: str) -> bool:
    """True if a short-flag cluster (-fd, -xdf) holds one of `letters` (case-sensitive)."""
    for a in _flags(args):
        if not a.startswith("--") and any(ch in letters for ch in a[1:]):
            return True
    return False


def _has_long(args: Sequence[str], *names: str) -> bool:
    for a in args:
        for n in names:
            if a == n or a.startswith(n + "="):
                return True
    return False


def _positional(args: Sequence[str]) -> List[str]:
    out: List[str] = []
    for a in args:
        if a == "--":
            continue
        if not a.startswith("-"):
            out.append(a)
    return out


def _judge(sub: str, args: Sequence[str]) -> Optional[Violation]:
    if sub == "push":
        if (_has_short(args, "f") or _has_long(args, "--force", "--force-with-lease", "--force-if-includes",
                                              "--mirror", "--delete", "--prune")
                or any(p.startswith("+") for p in _positional(args)) or _has_short(args, "d")):
            return Violation("push-force", "git push that rewrites or deletes remote history", "critical")
        return Violation("git-push", "git push", "high")
    if sub == "reset" and (_has_long(args, "--hard", "--keep", "--merge")):
        return Violation("reset-hard", "git reset --hard/--keep/--merge discards local work", "critical")
    if sub == "clean" and (_has_short(args, "f") or _has_long(args, "--force")) \
            and not (_has_short(args, "n") or _has_long(args, "--dry-run")):
        return Violation("git-clean-f", "git clean with force deletes untracked files", "critical")
    if sub == "branch":
        if _has_short(args, "D") or (
                (_has_short(args, "d") or _has_long(args, "--delete")) and (_has_short(args, "f") or _has_long(args, "--force"))):
            return Violation("git-branch-delete", "forced branch deletion", "high")
    if sub in ("checkout", "restore", "switch"):
        positional = _positional(args)
        unstage_only = sub == "restore" and (_has_long(args, "--staged") or _has_short(args, "S")) \
            and not (_has_long(args, "--worktree") or _has_short(args, "W"))
        if sub != "switch" and ("." in positional or ":/" in positional) and not unstage_only:
            return Violation("git-checkout-dot", "git %s . discards working tree changes" % sub, "high")
        if sub == "checkout" and (_has_short(args, "f") or _has_long(args, "--force")):
            return Violation("git-checkout-force", "git checkout --force discards local changes", "high")
        if sub == "switch" and (_has_long(args, "--discard-changes") or _has_short(args, "f")):
            return Violation("git-checkout-force", "git switch --discard-changes discards local changes", "high")
    if sub == "stash" and any(p in ("clear", "drop") for p in _positional(args)[:1]):
        return Violation("git-stash-drop", "git stash drop/clear loses stashed work", "high")
    if sub == "reflog" and any(p in ("expire", "delete") for p in _positional(args)[:1]):
        return Violation("git-reflog-expire", "git reflog expire/delete removes recovery points", "high")
    if sub == "update-ref" and (_has_short(args, "d") or _has_long(args, "--delete")):
        return Violation("git-update-ref-delete", "git update-ref -d deletes a ref", "high")
    if sub == "rebase" and _has_long(args, "--onto"):
        return Violation("rebase-onto", "git rebase --onto rewrites history", "critical")
    if sub == "filter-branch":
        return Violation("git-filter-branch", "git filter-branch rewrites history", "critical")
    return None


def _split_git(words: Sequence[str]) -> Optional[tuple]:
    """(subcommand, args, aliases) of a git invocation whose first word is `git`."""
    aliases = {}
    i = 1
    while i < len(words):
        w = words[i]
        if w in ("--",):
            i += 1
            continue
        if w == "-c" and i + 1 < len(words):
            key, _, value = words[i + 1].partition("=")
            if key.lower().startswith("alias."):
                aliases[key[6:]] = value
            i += 2
            continue
        if w.startswith("-c") and len(w) > 2 and "=" in w:      # -cfoo=bar
            key, _, value = w[2:].partition("=")
            if key.lower().startswith("alias."):
                aliases[key[6:]] = value
            i += 1
            continue
        if w in GIT_VALUE_OPTS:
            i += 2
            continue
        if w.startswith("-"):
            i += 1
            continue
        return w, list(words[i + 1:]), aliases
    return None


def _is_git(word: str) -> bool:
    return os.path.basename(word) in ("git", "git.exe")


def _simple_commands(command: str) -> Iterator[List[str]]:
    text = command.replace("`", " ; ").replace("$(", " ( ").replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|(){}<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    current: List[str] = []
    try:
        for token in lexer:
            if token in SEPARATORS or (token and set(token) <= set(";&|(){}<>")):
                if current:
                    yield current
                current = []
            else:
                current.append(token)
    except ValueError:
        # Unbalanced quote: fall back to whitespace splitting so that nothing is skipped.
        current = [t for t in re.split(r"[\s;&|(){}]+", text) if t]
    if current:
        yield current


def _check(command: str, depth: int) -> Optional[Violation]:
    if depth > MAX_DEPTH or not command.strip():
        return None
    for words in _simple_commands(command):
        found = _check_words(words, depth)
        if found:
            return found
    return None


def _check_words(words: List[str], depth: int) -> Optional[Violation]:
    i = 0
    while i < len(words):
        w = words[i]
        base = os.path.basename(w)
        if _ASSIGN.match(w):
            i += 1
        elif base in WRAPPERS:
            i += 1
            # Skip the wrapper's own options and assignments (`env -i A=1`, `sudo -u root`, `timeout 5`).
            while i < len(words) and (words[i].startswith("-") or _ASSIGN.match(words[i])
                                      or (base in ("timeout", "nice", "ionice") and re.match(r"^[0-9.]+[smhd]?$", words[i]))):
                if base in ("sudo", "doas") and words[i] in ("-u", "-g", "-h", "-p", "-C", "-D", "-R", "-r", "-t"):
                    i += 1
                i += 1
        else:
            break
    if i >= len(words):
        return None
    head = words[i]
    base = os.path.basename(head)
    rest = words[i + 1:]
    if base in SHELLS:
        for j, arg in enumerate(rest):
            if arg.startswith("-") and "c" in arg[1:] and not arg.startswith("--") and j + 1 < len(rest):
                return _check(rest[j + 1], depth + 1)
        return None
    if base in ("eval",):
        return _check(" ".join(rest), depth + 1)
    if base == "find":
        for j, arg in enumerate(rest):
            if arg in ("-exec", "-execdir", "-ok", "-okdir"):
                found = _check_words(rest[j + 1:], depth + 1)
                if found:
                    return found
        return None
    if _is_git(head):
        split = _split_git(words[i:])
        if split is None:
            return None
        sub, args, aliases = split
        seen = set()
        while sub in aliases and sub not in seen:
            seen.add(sub)
            value = aliases[sub]
            if value.startswith("!"):
                return _check(value[1:] + " " + " ".join(args), depth + 1)
            try:
                expanded = shlex.split(value)
            except ValueError:
                expanded = value.split()
            if not expanded:
                break
            sub, args = expanded[0], expanded[1:] + args
        return _judge(sub, args)
    return None


def check(command: str) -> Optional[Violation]:
    """First destructive git invocation found in `command`, else None."""
    if not isinstance(command, str):
        return None
    return _check(command, 0)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = payload["tool_input"]["command"]
    except (ValueError, KeyError, TypeError):
        return 0
    found = check(command)
    if found is None:
        return 0
    sys.stderr.write("BLOCKED: '%s' - %s (rule %s). User has disabled this command.\n"
                     % (command, found.reason, found.id))
    return 2


if __name__ == "__main__":
    sys.exit(main())
