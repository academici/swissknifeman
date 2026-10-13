"""Command line of the conductor: ``conduct.py run|resume|settle|status|observe``.

Exit codes: 0 the run finished (or the command succeeded), 1 the run stopped or a command was refused (``CODE:
message`` on stderr), 2 usage, 130 interrupted (resume continues).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from aicore.config import ConfigError

from orch import settings as settings_mod
from orch.conductor import engine, observer, progress


def _project() -> Path | None:
    from aicore.state import find_project_root
    root = find_project_root(Path.cwd())
    return root if (root / ".git").exists() else None


def _mode(args) -> str:
    return "quiet" if getattr(args, "quiet", False) else "json-lines" if getattr(args, "json_lines", False) else "text"


def _latest(project: Path) -> str | None:
    root = engine.runs_root(project)
    runs = sorted((path for path in root.glob("cnd-*") if (path / engine.RUN_FILE).is_file()),
                  key=lambda path: (path / progress.PROGRESS_FILE).stat().st_mtime
                  if (path / progress.PROGRESS_FILE).exists() else 0)
    return runs[-1].name if runs else None


def _preview(conductor: engine.Conductor, args) -> dict:
    """What a run would do, without the work source: the policy of the scenario, the merged options of the
    configuration, the pack and ``--options``, and the route and command line of every role."""
    conductor.run_id = "cnd-dry-run"
    claim = {"scenario": args.scenario or conductor.settings.default_profile, "options": []}
    item = engine.Item(ref="(preview)", orch_run="-", state={}, directory=Path(), claim=claim)
    conductor.run_doc = {"options_file": str(args.options) if args.options else None}
    conductor._resolve(item, persist=False)
    conductor._routes(item, persist=False)
    from orch.conductor import process
    available = {role: process.available(route["argv"]) for role, route in item.routes.items()}
    isolation = {role: conductor._role_argv(item, role, route)[len(route["argv"]):] for role, route in item.routes.items()}
    return {"plan": args.plan, "items": args.items or None, "batch": bool(args.batch),
            "scenario": claim["scenario"], "stages": [stage["id"] for stage in item.policy.get("stages", [])],
            "review": item.policy.get("review"), "options": item.options, "sources": item.sources,
            "routes": item.routes, "available": available, "isolation_args": isolation,
            "note": "the work source adds the scenario and the options of the plan, phase and item at claim time"}


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="conduct.py", description="Conduct pieces of work of a plan through "
                                     "the roles of their run-policy until green or an honest stop.")
    parser.add_argument("--config", type=Path, metavar="FILE", help="configuration file of the invocation layer")
    verbs = parser.add_subparsers(dest="verb", required=True)
    run = verbs.add_parser("run", help="claim and conduct pieces of work")
    run.add_argument("--plan", required=True, help="collection of the work source, such as a plan id")
    run.add_argument("--plans-root", dest="plans_root", metavar="DIR")
    which = run.add_mutually_exclusive_group(required=True)
    which.add_argument("--items", nargs="+", metavar="REF", help="these pieces of work, in order")
    which.add_argument("--batch", action="store_true", help="the next ready pieces of the source, one by one")
    run.add_argument("--max-items", dest="max_items", type=int, default=0, metavar="N",
                     help="with --batch: at most N pieces (default: until none is ready)")
    run.add_argument("--options", type=Path, metavar="FILE", help="run-options JSON: the most specific layer")
    run.add_argument("--scenario", help="with --dry-run: the scenario to preview (default: default_profile)")
    run.add_argument("--dry-run", action="store_true", help="print what would run; claims nothing, writes nothing")
    run.add_argument("--model-catalog", dest="model_catalog", type=Path, metavar="FILE")
    run.add_argument("--adopt", action="store_true",
                     help="take over the changes in the tree as an earlier attempt of the first piece (they must lie in "
                          "its write set): the executor checks and finishes them instead of starting over")
    resume = verbs.add_parser("resume", help="continue a stopped run; closed steps are not repeated")
    resume.add_argument("--run", required=True, metavar="RUN")
    resume.add_argument("--retry", nargs="+", default=[], metavar="ITEM",
                        help="also continue these blocked pieces: their steps from the blocked executor round on are "
                             "repeated (the source must have reopened them); finished steps are kept")
    resume.add_argument("--model-catalog", dest="model_catalog", type=Path, metavar="FILE")
    for sub in (run, resume):
        quiet = sub.add_mutually_exclusive_group()
        quiet.add_argument("--quiet", action="store_true", help="no progress lines on stderr")
        quiet.add_argument("--json-lines", dest="json_lines", action="store_true", help="progress lines as JSON")
    settle = verbs.add_parser("settle", help="set the outcome of a piece of a run by hand, after it was finished or "
                                             "given up outside the conductor")
    settle.add_argument("--run", required=True, metavar="RUN")
    settle.add_argument("--item", required=True, metavar="REF")
    settle.add_argument("--outcome", required=True, choices=["done", "done_with_deviations", "blocked"])
    settle.add_argument("--reason", required=True, help="why, for the journal")
    status = verbs.add_parser("status", help="state of a run from its journal (default: the latest run)")
    status.add_argument("--run", metavar="RUN")
    status.add_argument("--json", action="store_true")
    observe = verbs.add_parser("observe", help="write the observer report of a run, or --follow a running one")
    observe.add_argument("--run", metavar="RUN")
    observe.add_argument("--follow", action="store_true")
    args = parser.parse_args(argv)

    project = _project()
    if project is None:
        print("PROJECT_NOT_GIT: run the conductor inside a git repository", file=sys.stderr)
        return 1
    if args.verb in ("status", "observe"):
        run_id = args.run or _latest(project)
        directory = engine.runs_root(project) / (run_id or "-")
        if not run_id or not (directory / engine.RUN_FILE).is_file():
            print(f"RUN_UNKNOWN: no conductor run {args.run or ''} in {engine.runs_root(project)}".rstrip(),
                  file=sys.stderr)
            return 1
        if args.verb == "observe":
            if args.follow:
                return observer.follow(directory, stream=sys.stderr)
            written = observer.write_report(directory, project, project / engine.REPORTS / run_id)
            print(json.dumps(written, ensure_ascii=False))
            return 0
        found = progress.summarize(progress.read_lines(directory))
        found["run"] = run_id
        found["state"] = engine.read_json(directory / engine.STATE_FILE) or {}
        if args.json:
            print(json.dumps({key: value for key, value in found.items() if key != "state"} |
                             {"tokens": found["state"].get("tokens"), "stop": found["state"].get("stop")},
                             ensure_ascii=False, indent=2))
            return 0
        print(f"run {run_id}: {found['status']}" + (f" ({found['reason_code']})" if found["reason_code"] else "")
              + f", last line {found['last_ts']}")
        if found["current"]:
            current = found["current"]
            print(f"  now: {current['item']} {current['stage']} {current.get('role') or ''} "
                  f"{current.get('route') or ''} since {current['since']}".rstrip())
            if found.get("beacon"):
                beacon = found["beacon"]
                print(f"  beacon {beacon['ts']} {beacon['reason_code']}: {beacon.get('message', '')}")
        for row in found["items"]:
            last = row["last"] or {}
            print(f"  {row['item']}: {row['outcome'] or 'running'}"
                  + (f" ({row.get('reason_code')})" if row.get("reason_code") else "")
                  + f"; {row['stages']} step(s), last {last.get('stage', '-')} {last.get('verdict') or ''}".rstrip())
        tokens = found["state"].get("tokens") or {}
        print(f"  tokens: {tokens.get('input', 0)} in, {tokens.get('output', 0)} out")
        return 0

    try:
        current = settings_mod.load(project=project, config_file=args.config)
    except ConfigError as error:
        print(f"CONFIG_INVALID: {error}", file=sys.stderr)
        return 1
    except settings_mod.SettingsError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    conductor = engine.Conductor(project=project, settings=current, config_file=args.config, mode=_mode(args),
                                 model_catalog=getattr(args, "model_catalog", None))
    try:
        if args.verb == "run" and args.dry_run:
            print(json.dumps(_preview(conductor, args), ensure_ascii=False, indent=2))
            return 0
        if args.verb == "run":
            return conductor.run(plan=args.plan, plans_root=args.plans_root, items=args.items or [],
                                 batch=args.batch, max_items=args.max_items, options_file=args.options,
                                 adopt=args.adopt)
        if args.verb == "settle":
            return conductor.settle(args.run, args.item, args.outcome, args.reason)
        return conductor.resume(args.run, retry=args.retry)
    except engine.Stop as stop:
        print(f"{stop.code}: {stop.message}", file=sys.stderr)
        return 1
