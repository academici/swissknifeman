"""``orch conduct supervise`` and ``orch conduct reap`` on the command line (the logic is ``application/supervisor.py``).

Exit codes: 0 a pass was made (or another supervisor holds the project: ``busy``), 1 a refusal (``CODE: message`` on stderr:
``RUN_UNKNOWN``, ``RUN_BUSY``, ``STATE_CORRUPT``), 2 usage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sys
import threading

from orch import settings as settings_mod
from orch.conductor import contract, engine, records
from orch.conductor.application import supervisor


def add_parsers(verbs) -> None:
    """The verbs ``supervise`` and ``reap`` of the ``conduct`` group."""
    supervise = verbs.add_parser("supervise", help="look at the runs of the project and act on a hung or dead conductor "
                                                   "within [orch.supervisor] recover (default: notify only)")
    supervise.add_argument("--run", metavar="RUN", help="only this run")
    supervise.add_argument("--once", action="store_true", help="one pass, then exit (default: a pass every --interval seconds)")
    supervise.add_argument("--interval", type=int, default=None, metavar="S", help="seconds between passes ([orch.supervisor] interval_s)")
    supervise.add_argument("--recover", choices=("notify", "stop-only", "resume"), default=None,
                           help="what to do about a run in trouble: it can only lower the policy of the machine")
    supervise.add_argument("--max-recoveries", dest="max_recoveries", type=int, default=None, metavar="N",
                           help="resumes per run within the window: it can only lower the policy of the machine")
    supervise.add_argument("--json", action="store_true", help="print the pass as a supervise-result document")
    supervise.add_argument("--notify-send", dest="notify_send", action="store_true", help="also call notify-send")
    reap = verbs.add_parser("reap", help="stop the role processes an orphaned run left behind and close their agent records "
                                         "(under the checkout lock and the run lease; RUN_BUSY while a conductor holds the run)")
    reap.add_argument("--run", required=True, metavar="RUN")


def check(parser: argparse.ArgumentParser, args) -> None:
    """Usage errors of the numbers of ``supervise`` (exit 2)."""
    if args.verb == "supervise" and (args.interval is not None and args.interval < 1
                                     or args.max_recoveries is not None and args.max_recoveries < 0):
        parser.error("--interval must be at least 1 and --max-recoveries at least 0")


def run(args, project: Path, current) -> int:
    """``supervise`` or ``reap`` with the settings ``current``; a refusal is ``CODE: message`` on stderr and exit 1."""
    try:
        return _supervise(args, project, current) if args.verb == "supervise" else _reap(args, project, current)
    except (engine.Stop, settings_mod.SettingsError) as stop:
        print(f"{stop.code}: {getattr(stop, 'message', stop)}", file=sys.stderr)
        return 1


def _supervise_document(policy, actions: list, busy: bool = False) -> dict:
    """The ``supervise-result`` a pass prints with ``--json``."""
    doc = {"$schema": "urn:swissknifeman:orch:conductor:supervise-result:v1", "busy": busy, "recover": policy.recover,
           "actions": actions}
    found = contract.problems(doc, "supervise-result")
    if found:
        raise engine.Stop("RECORD_INVALID", f"supervise-result: {'; '.join(found[:3])}; {records.WRITER_HINT}")
    return doc


def _supervise(args, project: Path, current) -> int:
    """``supervise``: one pass over the runs of the project (``--once``) or a pass every ``--interval`` seconds until SIGINT or
    SIGTERM. Another supervisor of the project holds ``supervisor.lock``: ``busy``, exit 0, nothing done."""
    policy = supervisor.Policy.build(current, recover=args.recover, max_recoveries=args.max_recoveries,
                                     interval_s=args.interval, notify_send=args.notify_send, config_file=args.config)
    if args.run and not (engine.runs_root(project) / args.run / engine.RUN_FILE).is_file():
        print(f"RUN_UNKNOWN: no conductor run {args.run} in {engine.runs_root(project)}", file=sys.stderr)
        return 1

    def report(actions: list) -> None:
        if args.json:
            print(json.dumps(_supervise_document(policy, actions), ensure_ascii=False), flush=True)
        else:
            for action in actions:
                print(supervisor.text(action), flush=True)
            if args.once and not actions:
                print(f"no action (recover {policy.recover})", flush=True)

    try:
        if args.once:
            report(supervisor.supervise_once(project, policy, run=args.run))
            return 0
        stopped = threading.Event()
        handlers = {number: signal.signal(number, lambda *_: stopped.set()) for number in (signal.SIGINT, signal.SIGTERM)}
        try:
            supervisor.supervise(project, policy, run=args.run, stop=stopped.is_set, wait=stopped.wait, report=report)
        finally:
            for number, handler in handlers.items():
                signal.signal(number, handler)
        return 0
    except supervisor.SupervisorBusy:
        print(json.dumps(_supervise_document(policy, [], busy=True)) if args.json
              else "busy: another supervisor holds this project", flush=True)
        return 0


def _reap(args, project: Path, current) -> int:
    """``reap``: stop the role processes an orphaned run left and close their agent records; nothing else, no loop."""
    done = supervisor.reap_recorded(project, args.run, supervisor.Policy.build(current, config_file=args.config))
    print(f"run {args.run}: stopped {done['killed']} orphaned role group(s), closed {done['closed']} agent record(s)"
          + (f" ({done['skipped']})" if done.get("skipped") else ""))
    return 0
