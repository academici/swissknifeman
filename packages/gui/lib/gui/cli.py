"""gui command line: ``python3 -m gui.cli <command>`` (the ``bin/gui`` wrapper runs it).

This module must stay importable on the hub Python (3.9) so that an old interpreter gets a clean
``PYTHON_TOO_OLD`` failure instead of a syntax error.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Sequence, Tuple

from . import MIN_PYTHON, __version__

PYTHON_TOO_OLD = "PYTHON_TOO_OLD"

EXIT_FAILURE = 1
EXIT_USAGE = 2


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"gui: usage: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="gui", description="Local control plane of Swiss Knife Man (desktop and browser mode).")
    parser.add_argument("--version", action="version", version=f"gui {__version__}")
    parser.add_subparsers(dest="command", parser_class=_Parser, metavar="<command>")
    return parser


def check_python(version_info: Optional[Sequence[int]] = None) -> Optional[str]:
    """The ``PYTHON_TOO_OLD`` message when the interpreter is older than ``MIN_PYTHON``, else ``None``."""
    current: Tuple[int, ...] = tuple(version_info if version_info is not None else sys.version_info)[:2]
    if current >= MIN_PYTHON:
        return None
    need = ".".join(str(part) for part in MIN_PYTHON)
    have = ".".join(str(part) for part in current)
    return f"{PYTHON_TOO_OLD}: gui requires Python >= {need}, found {have}"


def main(argv: Optional[List[str]] = None) -> int:
    problem = check_python()
    if problem:
        print(problem, file=sys.stderr)
        return EXIT_FAILURE
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
