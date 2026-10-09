"""``aicore events`` (emit, list, deliver, replay, status) and ``aicore ext`` (plugins, status).

``emit`` is for people and tests: it journals an event as if a module had emitted it, strictly (every
failure is an error). ``list`` prints the journal. ``deliver`` runs a deliverer (it is also the background
deliverer started by ``emit``, through the hidden ``--journal`` and ``--trigger-offset``), ``replay``
delivers again and ``status`` shows the subscriptions. Exit codes: 0 success, 1 refusal or failure (for
``deliver`` and ``replay``: a delivery failed), 2 usage. ``--json`` prints one JSON document on stdout;
errors go to stderr as ``<CODE>: <message>``.

``aicore ext plugins list|describe|invoke`` and ``aicore ext status`` work on the plugins of the machine
configuration: ``describe`` and ``invoke`` start plugins (after the manifest check and the handshake),
``list`` and ``status`` never do; ``status`` always exits 0, it is a diagnosis.
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
from . import delivery as _delivery
from . import journal
from . import plugins as _plugins
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
    emit_cmd.add_argument("--delivery", choices=DELIVERY_MODES, help="delivery mode (default: events.delivery "
                          "of the configuration)")
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

    deliver_cmd = commands.add_parser("deliver", help="deliver pending events to the subscribers")
    deliver_cmd.add_argument("--project", metavar="DIR", help="project root (default: the nearest project, "
                             "else the machine journal)")
    deliver_cmd.add_argument("--journal", metavar="DIR", help=argparse.SUPPRESS)
    deliver_cmd.add_argument("--trigger-offset", type=int, metavar="N", help=argparse.SUPPRESS)
    deliver_cmd.add_argument("--config-file", metavar="FILE", help=argparse.SUPPRESS)
    deliver_cmd.add_argument("--json", action="store_true", help="print the delivery report as JSON")

    replay_cmd = commands.add_parser("replay", help="deliver events to one subscription again")
    replay_cmd.add_argument("subscription", metavar="SUBSCRIPTION", help="subscription id")
    start = replay_cmd.add_mutually_exclusive_group(required=True)
    start.add_argument("--from-start", action="store_true", help="rewind the cursor to the first event")
    start.add_argument("--from-event", metavar="ID", help="rewind the cursor to the event with this id")
    start.add_argument("--event", metavar="ID", help="deliver this one event (for example a dead letter)")
    replay_cmd.add_argument("--project", metavar="DIR", help="project root (default: the nearest project, "
                            "else the machine journal)")
    replay_cmd.add_argument("--json", action="store_true", help="print the delivery report as JSON")

    status_cmd = commands.add_parser("status", help="show the subscriptions and their delivery state")
    status_cmd.add_argument("--project", metavar="DIR", help="project root (default: the nearest project, "
                            "else the machine journal)")
    status_cmd.add_argument("--json", action="store_true", help="print the status as JSON")
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


def _report(command: str, report: "_delivery.DeliveryReport", args: argparse.Namespace, out: TextIO,
            err: TextIO) -> int:
    if args.json:
        print(json.dumps(report.to_json(), ensure_ascii=False, sort_keys=True), file=out)
    else:
        busy = " (another deliverer is running)" if report.busy else ""
        print(f"delivered {report.delivered}, failed {report.failed}, dead-lettered {report.dead_lettered}"
              f"{busy}", file=out)
    for problem in report.problems:
        print(f"aicore events {command}: {problem['code']}: {problem['message']}", file=err)
    for attempt in report.attempts:
        if attempt["outcome"] not in ("ok", "skipped"):
            print(f"aicore events {command}: {attempt['code']}: {attempt['subscription']} {attempt['event_id']} "
                  f"attempt {attempt['attempt']}: {attempt['outcome']}", file=err)
    return 0 if report.ok else 1


def _run_deliver(args: argparse.Namespace, env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    if args.journal:  # an explicit journal: the project is only what the caller names, never guessed from cwd
        project = Path(args.project) if args.project else None
        jdir = Path(args.journal)
    else:
        project = _project(args, env, cwd)
        jdir = journal.journal_dir(project, env=env)
    automatic = args.trigger_offset is not None  # the deliverer started by emit gives way to a running one
    report = _delivery.deliver(jdir, trigger_offset=args.trigger_offset, project=project, env=env,
                               config_file=args.config_file, wait=not automatic)
    return _report("deliver", report, args, out, err)


def _run_replay(args: argparse.Namespace, env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    project = _project(args, env, cwd)
    report = _delivery.replay(journal.journal_dir(project, env=env), args.subscription,
                              from_start=args.from_start, from_event=args.from_event, event_id=args.event,
                              project=project, env=env)
    return _report("replay", report, args, out, err)


def _run_status(args: argparse.Namespace, env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    project = _project(args, env, cwd)
    status = _delivery.delivery_status(journal.journal_dir(project, env=env), project=project, env=env)
    if args.json:
        print(json.dumps(status, ensure_ascii=False, sort_keys=True), file=out)
        return 0
    for row in status["subscriptions"]:
        state = "on" if row["enabled"] and row["active"] else ("off" if not row["enabled"] else "inactive")
        pending = f" pending {row['pending']['attempts']}x {row['pending']['last_error']}" if row["pending"] else ""
        print(f"{row['id']} {row['origin']} {state} lag {row['lag']} dead-letters {row['dead_letters']}{pending}",
              file=out)
    if status["malformed"] or status["resets"]:
        print(f"journal: {status['malformed']} broken line(s), {status['resets']} cursor reset(s)", file=out)
    for problem in status["problems"]:
        print(f"aicore events status: {problem['code']}: {problem['message']}", file=err)
    return 0


_COMMANDS = {"emit": _run_emit, "list": _run_list, "deliver": _run_deliver, "replay": _run_replay,
             "status": _run_status}


# --- aicore ext ----------------------------------------------------------------------------------------------


def build_ext_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="aicore ext", description="Extensions: external plugins.")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser, metavar="COMMAND")

    plugins_cmd = commands.add_parser("plugins", help="list, describe and call the registered plugins")
    plugin_commands = plugins_cmd.add_subparsers(dest="plugins_command", required=True, parser_class=_Parser,
                                                 metavar="COMMAND")
    list_cmd = plugin_commands.add_parser("list", help="list the plugins of [aicore.plugins] (starts nothing)")
    list_cmd.add_argument("--project", metavar="DIR", help="project root (default: the nearest project)")
    list_cmd.add_argument("--json", action="store_true", help="print the list as JSON")

    describe_cmd = plugin_commands.add_parser("describe", help="start a plugin with op describe and compare the "
                                              "answer with its manifest")
    describe_cmd.add_argument("plugin", metavar="ID", help="plugin id")
    describe_cmd.add_argument("--project", metavar="DIR", help="project root (default: the nearest project)")
    describe_cmd.add_argument("--json", action="store_true", help="print the description as JSON")

    invoke_cmd = plugin_commands.add_parser("invoke", help="call an extension point as a module would")
    invoke_cmd.add_argument("point", metavar="POINT", help="<module>:<id> declared in provides.extension_points")
    source = invoke_cmd.add_mutually_exclusive_group()
    source.add_argument("--input", metavar="JSON", help="the input, a JSON object (default: {})")
    source.add_argument("--input-file", metavar="FILE", help="read the input (a JSON object) from FILE")
    invoke_cmd.add_argument("--project", metavar="DIR", help="project root (default: the nearest project)")
    invoke_cmd.add_argument("--json", action="store_true", help='print {"point": ..., "results": [...]}')

    status_cmd = commands.add_parser("status", help="show the plugins and the subscriptions (always exits 0)")
    status_cmd.add_argument("--project", metavar="DIR", help="project root (default: the nearest project)")
    status_cmd.add_argument("--json", action="store_true", help="print the status as JSON")
    return parser


def _input(args: argparse.Namespace) -> dict:
    if args.input is None and args.input_file is None:
        return {}
    try:
        text = args.input if args.input is not None else Path(args.input_file).read_text(encoding="utf-8")
        value = json.loads(text)
    except (OSError, ValueError) as exc:
        raise ExtError("EVENT_INVALID", f"the input is not readable JSON: {exc.__class__.__name__}") from None
    if not isinstance(value, dict):
        raise ExtError("EVENT_INVALID", "the input must be a JSON object")
    return value


def _flag(value: bool, yes: str, no: str) -> str:
    return yes if value else no


def _plugin_lines(row: dict) -> List[str]:
    state = f"{_flag(row['trusted'], 'trusted', 'untrusted')} {_flag(row['enabled'], 'enabled', 'disabled')}"
    lines = [f"{row['id']} {row['kind'] or '-'} {row['version'] or '-'} {state}",
             f"  manifest: {row['manifest'] or '-'}",
             f"  profile: {row['profile']['profile']}, enforced: {_flag(row['profile']['enforced'], 'true', 'false')}"]
    if row["points"]:
        lines.append(f"  points: {', '.join(row['points'])}")
    if row["events"]:
        lines.append(f"  events: {', '.join(row['events'])}")
    lines.extend(f"  note: {_plugins.safe_text(item)}" for item in row["ignored"])
    lines.extend(f"  problem: PLUGIN_POINT_UNKNOWN: no module declares point {point}"
                 for point in row["unknown_points"])
    if row["problem"]:
        lines.append(f"  problem: {row['problem']['code']}: {_plugins.safe_text(row['problem']['message'])}")
    return lines


def _run_plugins_list(args: argparse.Namespace, env: Mapping[str, str], cwd: Path, out: TextIO) -> int:
    listing = _plugins.list_plugins(_project(args, env, cwd), env=env)
    if args.json:
        print(json.dumps(listing, ensure_ascii=False, sort_keys=True), file=out)
        return 0
    for row in listing["plugins"]:
        print("\n".join(_plugin_lines(row)), file=out)
    if not listing["plugins"]:
        print("no plugins registered", file=out)
    return 0


def _run_plugins_describe(args: argparse.Namespace, env: Mapping[str, str], cwd: Path, out: TextIO) -> int:
    project = _project(args, env, cwd)
    registration = _plugins.find_registration(args.plugin, project, env=env)
    described = _plugins.describe_plugin(registration, env=env, project=project)
    if args.json:
        print(json.dumps(described.to_json(), ensure_ascii=False, sort_keys=True), file=out)
    else:
        print(f"{described.id} {described.kind} {described.version} protocol {described.protocol} "
              f"{described.transport} {described.capabilities_digest} ({described.duration_ms} ms)", file=out)
    return 0


def _run_plugins_invoke(args: argparse.Namespace, env: Mapping[str, str], cwd: Path, out: TextIO) -> int:
    results = _plugins.invoke_point(args.point, _input(args), project=_project(args, env, cwd), env=env)
    if args.json:
        print(json.dumps({"point": args.point, "results": [item.to_json() for item in results]},
                         ensure_ascii=False, sort_keys=True), file=out)
    else:
        for item in results:
            detail = f" {item.code}: {item.error}" if item.status == "error" else ""
            print(f"{item.plugin} {item.status}{detail} ({item.duration_ms} ms)", file=out)
            if item.output is not None:
                print(json.dumps(item.output, ensure_ascii=False, sort_keys=True), file=out)
        if not results:
            print(f"no plugin handles {args.point}", file=out)
    return 1 if any(item.status == "error" for item in results) else 0


_PLUGIN_COMMANDS = {"list": _run_plugins_list, "describe": _run_plugins_describe, "invoke": _run_plugins_invoke}


def _run_ext_plugins(args: argparse.Namespace, env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    return _PLUGIN_COMMANDS[args.plugins_command](args, env, cwd, out)


def _run_ext_status(args: argparse.Namespace, env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    project = _project(args, env, cwd)
    document: dict = {"plugins": [], "subscriptions": [], "problems": []}
    try:
        listing = _plugins.list_plugins(project, env=env)
        document["plugins"], document["problems"] = listing["plugins"], list(listing["problems"])
    except ExtError as exc:
        document["problems"].append({"code": exc.code, "plugin": None, "message": exc.message})
    status = _delivery.delivery_status(journal.journal_dir(project, env=env), project=project, env=env)
    document["subscriptions"] = status["subscriptions"]
    reported = any(item["code"] == "CONFIG_INVALID" for item in document["problems"])
    for problem in status["problems"]:
        if problem["code"] == "CONFIG_INVALID" and reported:
            continue
        document["problems"].append({"code": problem["code"], "plugin": None,
                                     "subscription": problem.get("subscription"), "message": problem["message"]})
    if args.json:
        print(json.dumps(document, ensure_ascii=False, sort_keys=True), file=out)
        return 0
    print("plugins:" if document["plugins"] else "plugins: none", file=out)
    for row in document["plugins"]:
        print("\n".join(_plugin_lines(row)), file=out)
    print("subscriptions:" if document["subscriptions"] else "subscriptions: none", file=out)
    for row in document["subscriptions"]:
        state = "on" if row["enabled"] and row["active"] else ("off" if not row["enabled"] else "inactive")
        via = f" plugin {row['plugin']}" if row["plugin"] else ""
        print(f"  {row['id']} {row['origin']}{via} {state} lag {row['lag']} dead-letters {row['dead_letters']}",
              file=out)
    for problem in document["problems"]:
        subject = problem.get("subscription") or problem.get("plugin")
        where = f" [{subject}]" if subject else ""
        print(f"problem: {problem['code']}: {_plugins.safe_text(problem['message'])}{where}", file=out)
    return 0


_EXT_COMMANDS = {"plugins": _run_ext_plugins, "status": _run_ext_status}


def _dispatch(prog: str, parser: argparse.ArgumentParser, commands: Mapping[str, Any],
              argv: Optional[Sequence[str]], env: Optional[Mapping[str, str]], cwd: Optional[Path],
              out: Optional[TextIO], err: Optional[TextIO]) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    out = out or sys.stdout
    err = err or sys.stderr
    try:
        with contextlib.redirect_stderr(err):  # argparse writes its usage text to sys.stderr
            args = parser.parse_args(args_list)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    environment = os.environ if env is None else env
    try:
        return commands[args.command](args, environment, cwd or Path.cwd(), out, err)
    except ExtError as exc:
        print(f"aicore {prog} {args.command}: {exc}", file=err)
        return 1
    except (OSError, ValueError) as exc:
        print(f"aicore {prog} {args.command}: {exc}", file=err)
        return 1


def main(argv: Optional[Sequence[str]] = None, *, env: Optional[Mapping[str, str]] = None,
         cwd: Optional[Path] = None, out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    """``aicore events``."""
    return _dispatch("events", build_parser(), _COMMANDS, argv, env, cwd, out, err)


def ext_main(argv: Optional[Sequence[str]] = None, *, env: Optional[Mapping[str, str]] = None,
             cwd: Optional[Path] = None, out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    """``aicore ext``."""
    return _dispatch("ext", build_ext_parser(), _EXT_COMMANDS, argv, env, cwd, out, err)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
