"""``orch conduct supervise`` and ``orch conduct reap`` on the command line (the logic is ``application/supervisor.py``).

Exit codes: 0 a pass was made (or another supervisor holds the project: ``busy``), 1 a refusal (``CODE: message`` on stderr:
``RUN_UNKNOWN``, ``RUN_BUSY``, ``STATE_CORRUPT``), 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
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
    supervise.add_argument("--print-systemd-unit", action="store_true", help="print a user service and timer; install nothing")
    supervise.add_argument("--check-systemd-unit", action="store_true", help="verify the user service and timer in a temporary folder")
    reap = verbs.add_parser("reap", help="stop the role processes an orphaned run left behind and close their agent records "
                                         "(under the checkout lock and the run lease; RUN_BUSY while a conductor holds the run)")
    reap.add_argument("--run", required=True, metavar="RUN")


def check(parser: argparse.ArgumentParser, args) -> None:
    """Usage errors of the numbers of ``supervise`` (exit 2)."""
    if args.verb == "supervise" and (args.interval is not None and args.interval < 1
                                     or args.max_recoveries is not None and args.max_recoveries < 0):
        parser.error("--interval must be at least 1 and --max-recoveries at least 0")
    if args.verb == "supervise" and args.json and (args.print_systemd_unit or args.check_systemd_unit):
        parser.error("--json is incompatible with systemd unit text")


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
    if args.print_systemd_unit or args.check_systemd_unit:
        return systemd_units(project, policy.interval_s, check=args.check_systemd_unit)
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


def _unit_arg(value: str) -> str:
    """Escape systemd specifiers and ExecStart expansion; quote paths with spaces (there is no shell)."""
    value = value.replace("%", "%%").replace("$", "$$")
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"' if any(c in value for c in ' \t"\\') else value


def systemd_units(project: Path, interval: int, *, check: bool = False) -> int:
    """Print both user units; verification only writes inside TemporaryDirectory, never the user's unit folder."""
    executable = shutil.which("swissknifeman")
    if executable is None:
        print("SUPERVISE_UNIT_UNAVAILABLE: swissknifeman not found on PATH", file=sys.stderr)
        return 1
    project = project.resolve()
    if any(c in str(project) + executable for c in "\r\n\x00"):
        print("SUPERVISE_UNIT_UNAVAILABLE: unit paths contain control characters", file=sys.stderr)
        return 1
    key = hashlib.sha256(os.fsencode(project)).hexdigest()[:12]
    name = f"skm-supervise-{key}"
    label = str(project).replace("%", "%%")
    service = (f"[Unit]\nDescription=Swiss Knife Man conductor supervisor for {label}\n"
               f"[Service]\nType=oneshot\nExecStart={_unit_arg(str(Path(executable).absolute()))} orch conduct --project "
               f"{_unit_arg(str(project))} supervise --once\nEnvironment=SKM_ORCH_LAUNCHER=supervisor\n")
    timer = (f"[Unit]\nDescription=Run the SKM supervisor every {interval} s for {label}\n"
             f"[Timer]\nOnBootSec=120\nOnUnitActiveSec={interval}\nUnit={name}.service\n"
             "[Install]\nWantedBy=timers.target\n")
    units = {f"{name}.service": service, f"{name}.timer": timer}
    for filename, content in units.items():
        print(f"# file: ~/.config/systemd/user/{filename}\n{content}", flush=True)
    if check:
        analyze = shutil.which("systemd-analyze")
        if analyze is None:
            print("systemd-analyze not found: unit text printed only")
            return 0
        with tempfile.TemporaryDirectory(prefix="skm-supervise-") as temporary:
            paths = []
            for filename, content in units.items():
                path = Path(temporary) / filename
                path.write_text(content, encoding="utf-8")
                paths.append(str(path))
            try:
                return subprocess.run([analyze, "--user", "verify", *paths], timeout=30, check=False).returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                print(f"SUPERVISE_UNIT_UNAVAILABLE: {error}", file=sys.stderr)
                return 1
    return 0
