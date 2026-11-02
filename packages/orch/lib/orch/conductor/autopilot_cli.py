"""``orch conduct autopilot start|status|pause|resume|drain|stop|explain`` on the command line (the controller is
``application/autopilot.py``, its rules ``policies/autopilot.py``).

Exit codes: ``start`` 0 for AUTOPILOT_NO_WORK, AUTOPILOT_DRAINED, AUTOPILOT_STOPPED, AUTOPILOT_MAX_RUNS and AUTOPILOT_MAX_WALL, 1
for every other stop (``CODE: message`` on stderr); the other verbs 0, or 1 with ``CODE: message`` (``AUTOPILOT_NOT_RUNNING``,
``STATE_CORRUPT``, ``RECORD_INVALID``, ``PLAN_REQUIRED``); 2 usage.
"""
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import signal
import sys

from aicore.config import ConfigError

from orch import settings as settings_mod
from orch.conductor import contract, engine, records
from orch.conductor.application import autopilot, autopilot_status
from orch.conductor.infrastructure import clock, detach

REQUESTS = ("pause", "resume", "drain", "stop")


def add_parsers(verbs) -> None:
    """The ``autopilot`` group of the ``conduct`` verbs."""
    group = verbs.add_parser("autopilot", help="a controller that conducts the lanes of a plan one after another until a stop "
                                               "code, within [orch.autopilot] (the machine must allow it)")
    group.set_defaults(frozen=False, dry_run=False)
    commands = group.add_subparsers(dest="autopilot_verb", required=True)
    start = commands.add_parser("start", help="run the controller (in the foreground; --detach: in a session of its own)")
    start.add_argument("--plan", required=True, help="collection of the work source, such as a plan id")
    start.add_argument("--phase", help="restrict this session to the named phase")
    start.add_argument("--max-runs", dest="max_runs", type=int, default=None, metavar="N",
                       help="runs this session may start: it can only lower [orch.autopilot] max_runs")
    start.add_argument("--max-wall-s", dest="max_wall_s", type=int, default=None, metavar="S",
                       help="seconds this session may last: it can only lower [orch.autopilot] max_wall_s")
    start.add_argument("--run-tokens-hard-max", dest="run_tokens_hard_max", type=int, default=None, metavar="T",
                       help="run cap handed to every run (limits.run_tokens_hard_max of autopilot-options.json)")
    start.add_argument("--detach", action="store_true", help="start in a separate session; print JSON after startup is acknowledged")
    start.add_argument("--json-lines", dest="json_lines", action="store_true", help="progress lines as JSON on stdout")
    start.add_argument("--run-id", help=argparse.SUPPRESS)
    start.add_argument("--poll-s", dest="poll_s", type=float, default=None, help=argparse.SUPPRESS)  # tests: lowers poll_s
    state = commands.add_parser("status", help="the session of the project: mode, current run, waiting runs, stop")
    state.add_argument("--json", action="store_true", help="print an autopilot-status document")
    for name, text in (("pause", "take no new work after the current run"), ("resume", "take work again after a pause"),
                       ("drain", "finish the current run, then stop (AUTOPILOT_DRAINED)"),
                       ("stop", "interrupt the current run (SIGINT, resumable), then stop (AUTOPILOT_STOPPED)")):
        commands.add_parser(name, help=text)
    explain = commands.add_parser("explain", help="the effective policy with its sources, the readiness of the source and the "
                                                  "next action; starts nothing")
    explain.add_argument("--plan", help="collection (default: the plan of the session)")
    explain.add_argument("--json", action="store_true", help="print an autopilot-explain document")


def check(parser: argparse.ArgumentParser, args) -> None:
    """Usage errors of ``start`` (exit 2)."""
    if args.verb != "autopilot" or args.autopilot_verb != "start":
        return
    if args.phase is not None and not args.phase.strip():
        parser.error("--phase must not be empty")
    if any(value is not None and value < 1 for value in (args.max_runs, args.max_wall_s)) \
            or args.run_tokens_hard_max is not None and args.run_tokens_hard_max < 0 \
            or args.poll_s is not None and not args.poll_s >= 0.05:
        parser.error("--max-runs and --max-wall-s must be at least 1, --run-tokens-hard-max at least 0, --poll-s at least 0.05")


def _settings(args, project: Path) -> tuple:
    """``(settings, note)``. A project file that sets a machine-only ``[orch.autopilot]`` key is refused by aicore
    (``CONFIG_LAYER_FORBIDDEN``): the project layer is then left out, and ``note`` says so."""
    try:
        return settings_mod.load(project=project, config_file=args.config), ""
    except ConfigError as error:
        if getattr(error, "code", None) != "CONFIG_LAYER_FORBIDDEN" or "autopilot." not in str(getattr(error, "key", "")):
            raise
        return settings_mod.load(project=None, config_file=args.config), f"the project layer was ignored: {error}"


def run(args, project: Path, argv: list) -> int:
    """One ``autopilot`` verb; a refusal is ``CODE: message`` on stderr and exit 1."""
    if args.config:  # one absolute file for the settings, readiness and every child (they run in the project folder)
        args.config = Path(args.config).resolve()
    try:
        if args.autopilot_verb == "start" and args.detach:
            return detach.launch(argv, project=project, run_id=clock.new_run_id(), launcher="autopilot", new_run=True)
        if args.autopilot_verb == "start":
            return _start(args, project)
        if args.autopilot_verb == "status":
            return _status(args, project)
        if args.autopilot_verb in REQUESTS:
            doc = autopilot_status.request(project, args.autopilot_verb, getpass.getuser())
            print(f"requested {doc['action']}; the controller reads it at its next look (orch conduct autopilot status)")
            return 0
        return _explain(args, project)
    except (engine.Stop, settings_mod.SettingsError) as stop:
        detach.refuse(stop.code, getattr(stop, "message", str(stop)))
        print(f"{stop.code}: {getattr(stop, 'message', stop)}", file=sys.stderr)
        return 1
    except ConfigError as error:
        detach.refuse("CONFIG_INVALID", str(error))
        print(f"CONFIG_INVALID: {error}", file=sys.stderr)
        return 1


def _start(args, project: Path) -> int:
    current, note = _settings(args, project)
    flags = {"max_runs": args.max_runs, "max_wall_s": args.max_wall_s, "run_tokens_hard_max": args.run_tokens_hard_max,
             "poll_s": args.poll_s}

    def say(text: str) -> None:
        if args.json_lines:
            print(json.dumps({"ts": clock.utc_now(), "event": "autopilot", "message": text}, ensure_ascii=False), flush=True)
        else:
            print(f"[autopilot] {text}", file=sys.stderr, flush=True)

    def terminated(*_):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, terminated)
    try:
        return autopilot.Controller(project, args.plan, current, flags=flags, config_file=args.config, say=say,
                                    label=args.run_id, note=note, phase=args.phase).start()
    finally:
        signal.signal(signal.SIGTERM, previous)


def _checked(doc: dict, kind: str) -> dict:
    found = contract.problems(doc, kind)
    if found:
        raise engine.Stop("RECORD_INVALID", f"{kind}: {'; '.join(found[:3])}; {records.WRITER_HINT}")
    return doc


def _status(args, project: Path) -> int:
    doc = _checked(autopilot_status.status(project), "autopilot-status")
    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0
    state = doc["state"]
    if state is None:
        print("autopilot: no session in this project")
        return 0
    counters = state["counters"]
    print(f"autopilot {doc['status']}: plan {state['plan']}, {counters['runs']} run(s), {counters['items_closed']} piece(s) "
          f"closed, deadline {state['deadline_at']}" + (" (no controller holds the lock)" if doc["status"] == "dead" else ""))
    if state.get("phase"):
        print(f"  phase: {state['phase']}")
    if state["current"]:
        current = state["current"]
        print(f"  current: {current['kind']} {current['run_id']} ({current['state']}"
              + (f", pid {current['pid']}" if current.get("pid") else "") + f") since {current['since']}")
    for row in state["waiting_runs"]:
        print(f"  waiting: {row['run_id']} ({', '.join(row['items']) or '-'}) since {row['since']}")
    if state.get("quota_wait"):
        print(f"  quota: {state['quota_wait']['run_id']} resumes after {state['quota_wait']['until']}")
    if state["stop"]:
        print(f"  stop: {state['stop']['code']}: {state['stop']['message']}")
    if doc["request"]:
        print(f"  request: {doc['request']['action']} (not read yet)")
    return 0


def _explain(args, project: Path) -> int:
    current, note = _settings(args, project)
    doc = _checked(autopilot_status.explain(project, args.plan, current, config_file=args.config), "autopilot-explain")
    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0
    print(f"autopilot policy for {doc['plan']}" + (f" ({note})" if note else "") + ":")
    for key, value in doc["policy"].items():
        print(f"  {key} = {json.dumps(value)} ({doc['sources'][key]})")
    following = doc["readiness"].get("next") if doc["readiness"] else None
    if following:
        print(f"  source next: {following.get('kind')} {', '.join(following.get('items') or [])} "
              f"(phase {following.get('phase') or '-'})")
    step = doc["next"]
    print(f"next: {step['action']}" + (f" {step['code']}" if step.get("code") else "") + f": {step['message']}")
    return 0
