"""Argument parser (cli §1, §2): global flags before the group, groups registered from ``GROUPS``.

Every group parser is built by ``CommandGroup.register``; the parser only adds the global flags and the
shared behaviour: no abbreviations, an unknown group is "unrecognized arguments" (exit 2), and a group of a
disabled optional module is hidden from help and answers ``MODULE_DISABLED`` when invoked.

A usage error is argparse's message, but it is written by ``parse_command_line`` and not by argparse: the
values of credential flags (``SECRET_FLAGS``) found anywhere on the command line are masked first, whatever
their position, spelling (``--as-token X``, ``--as-token=X``) or repetition, then the message is redacted and
escaped like any other untrusted text. The exit stays 2.
"""

import argparse
import re
import sys
from collections.abc import Callable, Sequence
from contextvars import ContextVar
from typing import Any, Final, NoReturn, Protocol, TextIO, cast, override

from skm import __version__
from skm.entrypoints.cli.commands import GROUPS, CommandGroup, SubParsers
from skm.entrypoints.cli.context import Cell, CliContext, CliOptions, CliRedactor, frame, seal, untrusted
from skm.entrypoints.cli.errors import EXIT_USAGE
from skm.entrypoints.cli.output import escape_terminal
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed

__all__ = [
    "GLOBAL_FLAGS",
    "SECRET_FLAGS",
    "build_parser",
    "options_from",
    "parse_command_line",
    "secret_values",
]

type _Flag = tuple[tuple[str, ...], dict[str, Any]]

# cli §2; ``--version`` prints the bare package version and is added separately.
GLOBAL_FLAGS: Final[tuple[_Flag, ...]] = (
    (("--json",), {"action": "store_true", "help": "machine-readable output: one JSON envelope on stdout"}),
    (("--quiet", "-q"), {"action": "store_true", "help": "print only the essential output"}),
    (("--verbose", "-v"), {"action": "count", "default": 0, "help": "-v debug logs, -vv also tracebacks"}),
    (("--bootstrap",), {"metavar": "PATH", "help": "explicit bootstrap file"}),
    (("--instance",), {"metavar": "NAME", "help": "instance profile of the bootstrap"}),
    (("--scope",), {"metavar": "SCOPE", "help": "scope for config commands and queries"}),
    (("--set",), {"action": "append", "default": [], "metavar": "KEY=VALUE", "help": "config override"}),
    (("--config",), {"metavar": "FILE", "help": "invocation config document (TOML/JSON)"}),
    (("--as-token",), {"metavar": "TOKEN", "help": "act as the principal of this token"}),
    (("--yes", "-y"), {"action": "store_true", "help": "do not ask for confirmation"}),
    (("--no-color",), {"action": "store_true", "help": "no ANSI colour"}),
)
# Global flags whose value is a credential; it never appears in any output, a usage error included.
SECRET_FLAGS: Final = ("--as-token",)
# An attempted abbreviation (refused: allow_abbrev=False) of at least this length still hides its value.
_SHORTEST_SPELLING: Final = len("--as")
_INVALID_CHOICE: Final = re.compile(r"invalid choice: '([^']*)'")
# Subparsers share the invocation's help sink without mutating parsers or process streams.
_HELP_OUTPUT: ContextVar[tuple[TextIO, CliRedactor] | None] = ContextVar("cli_help_output", default=None)


def _secret_flag(option: str) -> bool:
    return any(
        option == flag or (len(option) >= _SHORTEST_SPELLING and flag.startswith(option))
        for flag in SECRET_FLAGS
    )


def secret_values(argv: Sequence[str]) -> tuple[str, ...]:
    """Every value given to a ``SECRET_FLAGS`` flag anywhere in ``argv``, misplaced and repeated ones too."""
    found: list[str] = []
    for index, argument in enumerate(argv):
        option, equals, value = argument.partition("=")
        if not _secret_flag(option):
            continue
        if equals:
            found.append(value)
        elif index + 1 < len(argv):
            found.append(argv[index + 1])
    return tuple(value for value in found if value)


class _UsageError(Exception):
    """argparse's usage error, carried to ``parse_command_line`` instead of being printed by argparse."""

    def __init__(self, parser: argparse.ArgumentParser, message: str) -> None:
        super().__init__(message)
        self.parser = parser
        self.message = message


class _HelpWriter(Protocol):
    def write(self, text: str, /) -> object: ...


class _Parser(argparse.ArgumentParser):
    """No abbreviations, an unknown group reads like an unrecognized argument, errors are not printed."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("allow_abbrev", False)
        if sys.version_info >= (3, 14):
            # Help and usage text is escaped as data; argparse's own ANSI colouring (on under FORCE_COLOR)
            # would hide the ``usage:`` frame and surface as literal escape sequences.
            kwargs.setdefault("color", False)
        super().__init__(*args, **kwargs)

    @override
    def error(self, message: str) -> NoReturn:
        choice = _INVALID_CHOICE.search(message)
        if choice is not None:
            message = f"unrecognized arguments: {choice.group(1)}"
        raise _UsageError(self, message)

    @override
    def print_help(self, file: _HelpWriter | None = None) -> None:
        output = _HELP_OUTPUT.get()
        if output is None:
            super().print_help(file)
            return
        stream, redactor = output
        writer = stream if file is None else file
        writer.write(_help_text(self, redactor))
        if file is None:
            stream.flush()


def _program(redactor: CliRedactor, prog: str) -> list[Cell]:
    """The fixed executable name is framing; a selected group or a supplied program name is data."""
    own = "skm" if prog == "skm" or prog.startswith("skm ") else ""
    return [frame(own), *untrusted(redactor.text(prog[len(own) :]), escape_terminal)]


def _help_text(parser: argparse.ArgumentParser, redactor: CliRedactor) -> str:
    """Keep argparse's line structure; program names, group listings and help prose are data."""
    cells: list[Cell] = []
    prefix = f"usage: {parser.prog}"
    for line in parser.format_help().split("\n")[:-1]:
        remainder = line
        if line.startswith(prefix):
            cells.extend([frame("usage: "), *_program(redactor, parser.prog)])
            remainder = line[len(prefix) :]
        cells.extend([*untrusted(redactor.text(remainder), escape_terminal), frame("\n")])
    return seal(redactor, cells)


def _usage_text(parser: argparse.ArgumentParser, message: str, secrets: Sequence[str]) -> str:
    """Seal usage and its error together, protecting dynamic program names as well as the message."""
    redactor = CliRedactor()
    for value in secrets:
        redactor.register_secret(value)
    cells: list[Cell] = []
    usage = parser.format_usage()
    for index, part in enumerate(usage.split(parser.prog) if parser.prog else [usage]):
        if index:
            cells.extend(_program(redactor, parser.prog))
        cells.append(frame(part))
    cells.extend(_program(redactor, parser.prog))
    cells.extend([frame(": error: "), *untrusted(redactor.text(message), escape_terminal), frame("\n")])
    return seal(redactor, cells)


def _disabled_runner(group: CommandGroup) -> Callable[[argparse.Namespace, CliContext], int]:
    def run(args: argparse.Namespace, ctx: CliContext) -> int:  # noqa: ARG001 - the group contract
        raise PreconditionFailed(
            ErrorCode.MODULE_DISABLED,
            f"command group {group.name!r} belongs to module {group.module!r}, which is disabled",
            details={"module": group.module or "", "group": group.name},
        )

    return run


def _register_disabled(sub: SubParsers, group: CommandGroup) -> None:
    parser = sub.add_parser(group.name)  # no help= : argparse lists a verb only when it has help text
    parser.add_argument("rest", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    parser.set_defaults(run=_disabled_runner(group), command_name=group.name)


def parse_command_line(
    parser: argparse.ArgumentParser,
    argv: Sequence[str] | None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> argparse.Namespace:
    """``parse_args`` plus the group requirement, checked after stray arguments are reported.

    Stray arguments come first so that ``skm --ver`` is "unrecognized arguments", not
    a missing group. A usage error prints the usage of the parser that failed and the safe message on
    ``stderr`` (default: the process stream) and raises ``SystemExit(2)``. Automatic help is protected on
    ``stdout`` with the same credentials and terminal escaping, and still exits 0; ``--version`` retains
    argparse's bare-version output.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    redactor = CliRedactor()
    for value in secret_values(arguments):
        redactor.register_secret(value)
    help_output = _HELP_OUTPUT.set((sys.stdout if stdout is None else stdout, redactor))
    try:
        args = parser.parse_args(arguments)
        if args.group is None:
            parser.error("the following arguments are required: GROUP")
    except _UsageError as usage:
        stream = sys.stderr if stderr is None else stderr
        stream.write(_usage_text(usage.parser, usage.message, secret_values(arguments)))
        stream.flush()
        raise SystemExit(EXIT_USAGE) from None
    finally:
        _HELP_OUTPUT.reset(help_output)
    return args


def build_parser(
    groups: Sequence[CommandGroup] | None = None, *, disabled_modules: frozenset[str] = frozenset()
) -> argparse.ArgumentParser:
    """The ``skm`` parser over ``groups`` (default: the discovered ``GROUPS``)."""
    parser = _Parser(prog="skm", allow_abbrev=False, description="Swiss Knife Man command line")
    parser.add_argument("--version", action="version", version=__version__)
    for names, kwargs in GLOBAL_FLAGS:
        parser.add_argument(*names, **kwargs)
    sub = cast("SubParsers", parser.add_subparsers(dest="group", metavar="GROUP"))
    for group in GROUPS if groups is None else groups:
        if group.module is not None and group.module in disabled_modules:
            _register_disabled(sub, group)
        else:
            group.register(sub)
    return parser


def options_from(args: argparse.Namespace) -> CliOptions:
    """The global flags of a parsed command line."""
    return CliOptions(
        json=args.json,
        quiet=args.quiet,
        verbosity=args.verbose,
        assume_yes=args.yes,
        no_color=args.no_color,
        actor_hint=args.as_token,
        scope=args.scope,
        instance=args.instance,
        bootstrap=args.bootstrap,
        sets=tuple(args.set),
        config=args.config,
    )
