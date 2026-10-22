"""``aicore schema <command>``: picks the command (compat, codegen) and hands the rest over."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Mapping, Optional, Sequence, TextIO

from .schemacompat import USAGE

# command -> (module, function)
COMMANDS = {
    "compat": ("aicore.util.schemacompat", "main"),
    "codegen": ("aicore.util.schemacodegen", "main"),
}


def main(argv: Optional[Sequence[str]] = None, *, env: Optional[Mapping[str, str]] = None,
         cwd: Optional[Path] = None, out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    """``aicore schema <command>``; the exit code is the one of the command, 2 for an unknown command."""
    args = list(sys.argv[1:] if argv is None else argv)
    out = out or sys.stdout
    err = err or sys.stderr
    if not args:
        err.write(USAGE)
        return 2
    if args[0] in ("-h", "--help", "help"):
        out.write(USAGE)
        return 0
    command = COMMANDS.get(args[0])
    if command is None:
        err.write(f"SCHEMA_COMPAT_USAGE: unknown command {args[0]!r}\n{USAGE}")
        return 2
    module, function = command
    handler = getattr(importlib.import_module(module), function)  # lazy: only the chosen command is imported
    if args[0] == "compat":  # schemacompat.main reads the command name itself
        return handler(args, env=env, cwd=cwd, out=out, err=err)
    return handler(args[1:], env=env, cwd=cwd, out=out, err=err)
