"""``aicore events``: emit and list.

``emit`` is for people and tests: it journals an event as if a module had emitted it, strictly (every
failure is an error). ``list`` prints the journal. Exit codes: 0 success, 1 refusal or failure, 2 usage.
``--json`` prints one JSON document on stdout; errors go to stderr as ``<CODE>: <message>``.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, TextIO

from ..state import find_project_root
from . import units as _units
from .errors import ExtError
from .events import DELIVERY_MODES, emit, read_events


class _Parser(argparse.ArgumentParser):
    """argparse with the documented exit code 2 and messages on stderr."""

    def error(self, message: str):  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="aicore events", description="The project event journal.")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser, metavar="COMMAND")

    emit_cmd = commands.add_parser("emit", help="journal an event as if a module had emitted it")
    emit_cmd.add_argument("--source", required=True, metavar="MODULE", help="id of the emitting module")
    emit_cmd.add_argument("--type", required=True, metavar="TYPE", help="<module>.<subject>.<verb>")
    emit_cmd.add_argument("--subject", metavar="TEXT")
    payload = emit_cmd.add_mutually_exclusive_group()
    payload.add_argument("--data", metavar="JSON", help="the payload, a JSON object")
    payload.add_argument("--data-file", metavar="FILE", help="read the payload (a JSON object) from FILE")
    emit_cmd.add_argument("--project", metavar="DIR", help="project root (default: the nearest project, "
                          "else the machine journal)")
    emit_cmd.add_argument("--delivery", choices=DELIVERY_MODES, help="delivery mode (journal only for now)")
    emit_cmd.add_argument("--strict-type", action="store_true",
                          help="refuse a type that no module declares in provides.events")
    emit_cmd.add_argument("--json", action="store_true", help="print the event as JSON")

    list_cmd = commands.add_parser("list", help="print the events of the journal")
    list_cmd.add_argument("--project", metavar="DIR", help="project root (default: the nearest project, "
                          "else the machine journal)")
    list_cmd.add_argument("--type", action="append", metavar="PATTERN", help="only types matching the "
                          "shell-style pattern (repeatable)")
    list_cmd.add_argument("--since", metavar="ID", help="only events after the event with this id")
    list_cmd.add_argument("--limit", type=int, metavar="N", help="only the last N events")
    list_cmd.add_argument("--json", action="store_true", help='print {"events": [...], "problems": [...]}')
    return parser


def _project(args: argparse.Namespace, env: Mapping[str, str], cwd: Path) -> Optional[Path]:
    if args.project:
        return Path(args.project)
    root = find_project_root(cwd, env=env)
    if (root / ".git").exists() or (root / ".swissknifeman").is_dir():
        return root
    return None


def _data(args: argparse.Namespace) -> Optional[dict]:
    if args.data is None and args.data_file is None:
        return None
    try:
        text = args.data if args.data is not None else Path(args.data_file).read_text(encoding="utf-8")
        value = json.loads(text)
    except (OSError, ValueError) as exc:
        raise ExtError("EVENT_INVALID", f"the payload is not readable JSON: {exc.__class__.__name__}") from None
    if not isinstance(value, dict):
        raise ExtError("EVENT_INVALID", "the payload must be a JSON object")
    return value


def _run_emit(args: argparse.Namespace, env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    data = _data(args)
    declared = _units.declared_events(_units.discover_units(env))
    if args.type not in declared:
        message = f"type {args.type} is not declared in provides.events by any module"
        if args.strict_type:
            raise ExtError("EVENT_TYPE_UNDECLARED", message)
        print(f"aicore events emit: EVENT_TYPE_UNDECLARED: {message}", file=err)
    event = emit(args.type, data, source=args.source, subject=args.subject, project=_project(args, env, cwd),
                 delivery=args.delivery, strict=True, env=env)
    assert event is not None  # strict emit raises instead of returning None
    if args.json:
        print(json.dumps(event.to_json(), ensure_ascii=False, sort_keys=True), file=out)
    else:
        print(event.id, file=out)
    return 0


def _printable(text: str) -> str:
    """``text`` with every non-printable character (a newline, U+2028, U+0085...) written as an escape, so a
    subject cannot add rows to the listing."""
    return "".join(char if char.isprintable() else char.encode("unicode_escape").decode("ascii")
                   for char in text)


def _run_list(args: argparse.Namespace, env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    events, problems = read_events(_project(args, env, cwd), types=args.type, since_id=args.since,
                                   limit=args.limit, env=env)
    if args.json:
        print(json.dumps({"events": [event.to_json() for event in events], "problems": problems},
                         ensure_ascii=False, sort_keys=True), file=out)
        return 0
    for event in events:
        print(f"{event.time} {event.type} {_printable(event.subject) if event.subject else '-'} {event.id}", file=out)
    for problem in problems:
        print(f"aicore events list: offset {problem['offset']}: {problem['code']}: {problem['message']}", file=err)
    return 0


_COMMANDS = {"emit": _run_emit, "list": _run_list}


def main(argv: Optional[Sequence[str]] = None, *, env: Optional[Mapping[str, str]] = None,
         cwd: Optional[Path] = None, out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    out = out or sys.stdout
    err = err or sys.stderr
    try:
        with contextlib.redirect_stderr(err):  # argparse writes its usage text to sys.stderr
            args = build_parser().parse_args(args_list)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    environment = os.environ if env is None else env
    try:
        return _COMMANDS[args.command](args, environment, cwd or Path.cwd(), out, err)
    except ExtError as exc:
        print(f"aicore events {args.command}: {exc}", file=err)
        return 1
    except (OSError, ValueError) as exc:
        print(f"aicore events {args.command}: {exc}", file=err)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
