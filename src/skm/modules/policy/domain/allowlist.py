"""Allowlist engine for one simple command (policy §5.7; port of auto-approve ``analyze.sh`` 109-226).

A segment is allowlisted when its assignments are harmless, every wrapper and the head are listed programs
written without a path, and the arguments do not turn a reader into a writer (``_args_ok``,
``_git_branch_ok``,
``_gh_api_ok``). A head written with a path (``./ls``, ``bin/git``) never gains auto-allow from its basename.
"""

from __future__ import annotations

import re

from .command_classes import GH_API_FIELD_FLAGS, GH_API_READ_METHODS
from .commands import CommandPolicy, subcommand_allowed
from .shell_words import SimpleCommand

__all__ = ["SAFE_PREFIX_VAR_RE", "SHELL_KEYWORDS", "UNSAFE_VAR_RE", "segment_allowlisted"]

SAFE_PREFIX_VAR_RE = re.compile(
    r"(LANG|LANGUAGE|LC_[A-Z_]+|TZ|NO_COLOR|CLICOLOR|FORCE_COLOR|COLUMNS|LINES|TERM"
    r"|GIT_OPTIONAL_LOCKS|GIT_TERMINAL_PROMPT)"
)
UNSAFE_VAR_RE = re.compile(
    r"(PATH|IFS|HOME|SHELL|ENV|BASH_ENV|BASHOPTS|SHELLOPTS|PS[0-9]|PROMPT_COMMAND|GLOBIGNORE|CDPATH|FUNCNEST"
    r"|LD_.*|DYLD_.*|GIT_.*|PAGER|EDITOR|VISUAL|LESS.*|PYTHON.*|NODE_.*|PERL.*|RUBY.*)"
)
SHELL_KEYWORDS = frozenset(
    {"return", "break", "continue", "exit", "set", "unset", "read", "shift", "wait", "true", "false", ":"}
)
_DECLARERS = frozenset({"export", "declare", "typeset", "readonly", "local"})
_GIT_FORBIDDEN_ARGS = ("--output", "--ext-diff", "--upload-pack", "--receive-pack", "--exec")
_GIT_FORBIDDEN_GLOBALS = ("-c", "--config-env", "--exec-path", "--git-dir", "--work-tree")
_GIT_BRANCH_LETTERS = frozenset("dDmMcCfutU")
_GIT_BRANCH_LONG = (
    "--delete",
    "--move",
    "--copy",
    "--force",
    "--set-upstream",
    "--unset-upstream",
    "--track",
    "--no-track",
    "--edit-description",
    "--create-reflog",
)
# Arguments that make a listed reader write or run code (``_args_ok``).
_WRITER_ARGS: dict[str, tuple[str, ...]] = {
    "find": ("-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"),
    "sort": ("-o", "--output", "--compress-program"),
    "tree": ("-o", "--output", "-R"),  # -R reruns tree with `-o 00Tree.html` in every directory
    "yq": ("-i", "-s", "--inplace", "--split-exp"),
    "file": ("-C", "--compile"),
    "date": ("-s", "--set"),
    "rg": ("--pre", "--hostname-bin", "--pager"),
    "ag": ("--pre", "--hostname-bin", "--pager"),
    "hostname": ("-F", "--file"),  # sets the host name from a file, like a positional name does
}

# Builtins that assign the variables they name: (options taking a value, those whose value is a name).
_ASSIGNING_BUILTINS: dict[str, tuple[str, str]] = {"read": ("adinNptu", "a"), "printf": ("v", "v")}

# xxd value options by letter, with the long-name tails after which the value is the next word (vim's xxd.c).
_XXD_VALUE_OPTIONS: dict[str, tuple[str, ...]] = {
    "c": ("ols",),
    "g": ("roup",),
    "l": ("en",),
    "n": ("ame",),
    "o": ("ffset",),
    "s": ("kip", "eek"),
    "R": (),
}


def _name(assignment: str) -> str:
    """The variable an assignment sets: ``PATH[0]=x`` and ``PATH+=x`` set ``PATH`` like ``PATH=x`` does."""
    return assignment.split("=", 1)[0].rstrip("+").split("[", 1)[0]


def _assigned_names(program: str, args: tuple[str, ...]) -> list[str]:
    """Variables ``read`` (its operands and ``-a``) or ``printf -v`` assign, parsed like bash's getopt:
    clustered letters, a value attached or in the next word, options ending at ``--`` or an operand."""
    values, names = _ASSIGNING_BUILTINS[program]
    assigned: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            index += 1
            break
        if arg == "-" or not arg.startswith("-"):
            break
        for position, letter in enumerate(arg[1:], start=2):
            if letter in values:
                value = arg[position:]
                if not value and index + 1 < len(args):
                    index += 1  # the value is the next word
                    value = args[index]
                if letter in names:
                    assigned.append(value)
                break
        index += 1
    if program == "read":
        assigned.extend(args[index:])
    return assigned


def _long_hits(arg: str, flag: str) -> bool:
    """``arg`` names the long option ``flag``, possibly abbreviated as getopt_long accepts (``--out=x``)."""
    name = arg.split("=", 1)[0]
    return name.startswith("--") and len(name) > 2 and flag.startswith(name)


def _flag_hits(arg: str, flags: tuple[str, ...]) -> bool:
    """``arg`` is one of ``flags``: exact, an abbreviated ``--long[=value]`` or a short letter inside a
    cluster (``-no``)."""
    short = arg.startswith("-") and not arg.startswith("--")
    return any(
        arg == flag
        or (flag.startswith("--") and _long_hits(arg, flag))
        or (short and len(flag) == 2 and flag[1] in arg[1:])
        for flag in flags
    )


def _xxd_writes(args: tuple[str, ...]) -> bool:
    """``xxd [options] [infile [outfile]]`` reverts or writes ``outfile``. xxd names an option by the letter
    after its first one or two dashes (``-r``, ``-revert`` and ``--r`` all revert; ``-groupsize`` is ``-g``)
    and stops at the first operand; a value is attached (``-c8``) or, after the bare letter or long name,
    the next word."""
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            index += 1
            break
        option = arg[1:] if arg.startswith("--") else arg
        if not option.startswith("-") or option == "-":
            break
        letter, rest = option[1:2], option[2:]
        if letter == "r":
            return True
        tails = _XXD_VALUE_OPTIONS.get(letter)
        capitalize = letter == "c" and rest.startswith("apitalize")
        if tails is not None and not capitalize and (not rest or rest.startswith(tails)):
            index += 1  # the next word is the value, even when it starts with "-"
        index += 1
    operands = args[index:]
    return len(operands) > 1 and operands[1] != "-"


def _args_ok(head: str, args: tuple[str, ...]) -> bool:
    if head == "xxd" and _xxd_writes(args):
        return False
    if any(_flag_hits(arg, _WRITER_ARGS.get(head, ())) for arg in args):
        return False
    positionals = [arg for arg in args if not arg.startswith("-")]
    if head == "hostname":
        return not positionals
    if head == "uniq":
        return len(positionals) <= 1
    if head == "env":
        return all(arg in {"-0", "--null"} for arg in args)
    return True


def _git_branch_ok(args: list[str]) -> bool:
    for arg in args:
        if arg.startswith("--"):
            if any(_long_hits(arg, flag) for flag in _GIT_BRANCH_LONG) or arg.startswith("--set-upstream"):
                return False
        elif arg.startswith("-"):
            if _GIT_BRANCH_LETTERS & set(arg[1:]):
                return False
        else:
            return False  # a bare name creates a branch
    return True


def _gh_api_ok(args: tuple[str, ...]) -> bool:
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in GH_API_FIELD_FLAGS or any(arg.startswith(flag + "=") for flag in GH_API_FIELD_FLAGS):
            return False
        if arg in {"-X", "--method"}:
            method = args[index + 1] if index + 1 < len(args) else ""
            if method.upper() not in GH_API_READ_METHODS:
                return False
            index += 1
        elif arg.startswith(("-X", "--method=")):
            method = arg[2:] if arg.startswith("-X") else arg.split("=", 1)[1]
            if method.upper() not in GH_API_READ_METHODS:
                return False
        index += 1
    return True


def _git_ok(args: tuple[str, ...], policy: CommandPolicy) -> bool:
    rule = policy.rule("git")
    index = 0
    while index < len(args) and args[index].startswith("-"):
        arg = args[index]
        if arg.split("=", 1)[0] in _GIT_FORBIDDEN_GLOBALS:
            return False
        index += 2 if arg == "-C" else 1
    rest = args[index:]
    if rule is None or not rest or not subcommand_allowed(rule, rest[:1]):
        return False
    sub, sub_args = rest[0], list(rest[1:])
    if any(arg.split("=", 1)[0] in _GIT_FORBIDDEN_ARGS for arg in sub_args):
        return False
    if sub == "branch" and not _git_branch_ok(sub_args):
        return False
    return not (sub == "reflog" and sub_args[:1] in (["expire"], ["delete"]))


def _gh_ok(args: tuple[str, ...], policy: CommandPolicy) -> bool:
    rule = policy.rule("gh")
    positionals = tuple(arg for arg in args if not arg.startswith("-"))
    if rule is None or not positionals:
        return False
    if positionals[0] == "api":
        return subcommand_allowed(rule, positionals[:1]) and _gh_api_ok(args)
    return subcommand_allowed(rule, positionals[:2])


def _assignments_ok(segment: SimpleCommand) -> bool:
    if not segment.words:
        return not any(UNSAFE_VAR_RE.fullmatch(_name(item)) for item in segment.assignments)
    return all(SAFE_PREFIX_VAR_RE.fullmatch(_name(item)) for item in segment.assignments)


def segment_allowlisted(segment: SimpleCommand, commands: CommandPolicy) -> bool:  # noqa: PLR0911
    """Whether one simple command may run without asking under ``commands`` (§5.7 rules 1-7)."""
    if not _assignments_ok(segment):
        return False
    if not segment.words:
        return True
    for wrapper in segment.wrappers:
        rule = commands.rule(wrapper)
        if "/" in wrapper or rule is None or rule.subcommands is not None:
            return False
    program, args = segment.program, segment.argv[1:]
    if "/" in program:
        return False
    if program in _DECLARERS:
        return all(not UNSAFE_VAR_RE.fullmatch(_name(arg)) for arg in args if not arg.startswith("-"))
    if program in _ASSIGNING_BUILTINS and any(
        UNSAFE_VAR_RE.fullmatch(_name(name)) for name in _assigned_names(program, args)
    ):
        return False
    if program in SHELL_KEYWORDS:
        return True
    if program == "git":
        return _git_ok(args, commands)
    if program == "gh":
        return _gh_ok(args, commands)
    rule = commands.rule(program)
    if rule is None or rule.subcommands is not None:
        return False
    return _args_ok(program, args)
