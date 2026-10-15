"""Command line of the conductor: ``conduct.py run|resume|settle|release|status|observe|answer|questions|prompt|gates``.

Exit codes: 0 the run finished (or the command succeeded), 1 the run stopped or a command was refused (``CODE:
message`` on stderr), 2 usage, 130 interrupted (resume continues).
"""
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import sys
import time

from aicore.config import ConfigError
from aicore.state import ProjectContextRequired

from orch import project as project_mod, sandbox, settings as settings_mod
from orch.conductor import agents, engine, gates, observer, progress, prompts, questions


def _project(args):
    """The project context (``--project``, ``SKM_PROJECT_ROOT`` or the nearest marker), or ``None`` after the refusal was
    printed: ``PROJECT_CONTEXT_REQUIRED`` without a project, ``PROJECT_NOT_GIT`` when it is not a git repository."""
    try:
        context = project_mod.require(args.project)
    except ProjectContextRequired as error:
        print(str(error), file=sys.stderr)
        return None
    if not (context.root / ".git").exists():
        print(f"PROJECT_NOT_GIT: {context.root} is not a git repository; the conductor needs one", file=sys.stderr)
        return None
    return context


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
    problems = {role: conductor.route_problem(route) for role, route in item.routes.items()}
    available = {role: problem is None for role, problem in problems.items()}
    unavailable = {role: problem for role, problem in problems.items() if problem}
    isolation = {role: conductor._role_argv(item, role, route)[len(route["argv"]):] for role, route in item.routes.items()}
    probed = sandbox.probe()
    network, warnings = {}, []
    for role, route in item.routes.items():
        network[role] = _network(conductor, role, route, isolation[role], probed)
        if network[role]["declared"] == "none" and not network[role]["enforced"]:
            warnings.append(f"{role}: network is declared none, but nothing enforces it "
                            f"({route['provider']} has no sandbox for its commands here)")
    if conductor._sandbox_mode(item) == "require" and not probed["available"] \
            and any(conductor._claude_bash(route) for route in item.routes.values()):
        warnings.append(f"instructions.sandbox is require and the sandbox cannot start ({probed['reason']}): "
                        "a run stops with SANDBOX_UNAVAILABLE")
    return {"plan": args.plan or str(args.input), "items": args.items or None, "batch": bool(args.batch),
            "scenario": claim["scenario"], "stages": [stage["id"] for stage in item.policy.get("stages", [])],
            "review": item.policy.get("review"), "options": item.options, "sources": item.sources,
            "reviewer": {"selector": item.options["reviewer"], "source": item.sources.get("reviewer", "default")},
            "fallback_routes": item.options["fallback_routes"], "route_notes": item.route_notes,
            "gates": [{"provider": name, **entry} for name, entry in sorted(gates.active(time.time()).items())],
            "routes": item.routes, "available": available, "unavailable": unavailable,
            "isolation_args": isolation, "sandbox": {"available": probed["available"], "reason": probed["reason"]},
            "network": network, "warnings": warnings,
            "note": "the work source adds the scenario and the options of the plan, phase and item at claim time"}


def _network(conductor, role: str, route: dict, isolation: list, probed: dict) -> dict:
    """What a role may reach (``declared``, from its manifest) and whether a provider sandbox confines its commands
    (``enforced``). The agent process itself is never confined: its model API stays reachable."""
    declared = conductor.declared_network(role)
    by = None
    if "--settings" in isolation:
        by = "claude-sandbox"
    elif conductor._codex_sandboxed(route) and probed["available"]:
        by = "codex-sandbox"
    elif route.get("provider") == "claude-code" and not conductor._claude_bash(route):
        by = "claude-tools"  # no shell tool: its commands cannot reach anything
    return {"declared": declared, "enforced": by is not None, "by": by}


def _questions(args, project: Path) -> int:
    """``answer``: write a resolution into ``questions.json`` of the piece (nothing else: the run is not touched);
    ``questions``: the open questions with their age."""
    run_id = args.run or _latest(project)
    directory = engine.runs_root(project) / (run_id or "-")
    if not run_id or not (directory / engine.RUN_FILE).is_file():
        print(f"RUN_UNKNOWN: no conductor run {args.run or ''} in {engine.runs_root(project)}".rstrip(), file=sys.stderr)
        return 1
    if args.verb == "questions":
        rows = questions.listing(directory, time.time())
        if args.json:
            print(json.dumps({"run": run_id, "questions": rows}, ensure_ascii=False, indent=2))
            return 0
        for row in rows:
            print(f"{row['item']} {row['id']} (revision {row['revision']}, {row['kind']}): {row['text']} — "
                  + ("answered, waits for resume; " if row["answered"] else "") + f"{row['age_s']} s"
                  + (" OVERDUE" if row["overdue"] else ""))
        if not rows:
            print("no open questions")
        return 0
    folder = directory / engine.safe(args.item)
    doc = questions.read(folder)
    if doc is None:
        print(f"QUESTION_UNKNOWN: {args.item} has no questions in run {run_id}", file=sys.stderr)
        return 1
    try:
        entry = questions.answer(doc, args.question, option=args.option, text=args.text,
                                 by=args.by or getpass.getuser(), now=engine.utc_now())
    except questions.QuestionError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    engine.write_json(questions.path(folder), doc)
    print(json.dumps({"run": run_id, "item": args.item, "question": entry["id"], "revision": entry["revision"],
                      "resolution": entry["resolution"],
                      "next": f"conduct.py resume --run {run_id} --retry {args.item}"}, ensure_ascii=False))
    return 0


def _prompt(args, project: Path) -> int:
    """``prompt explain``: the blocks of the prompt a role step was given (``prompts/<step>.manifest.json``), their
    origin, size and digest, and what was left out."""
    run_id = args.run or _latest(project)
    directory = engine.runs_root(project) / (run_id or "-")
    if not run_id or not (directory / engine.RUN_FILE).is_file():
        print(f"RUN_UNKNOWN: no conductor run {args.run or ''} in {engine.runs_root(project)}".rstrip(), file=sys.stderr)
        return 1
    file = directory / engine.safe(args.item) / "prompts" / f"{args.step}.manifest.json"
    doc = engine.read_json(file) if file.is_file() else None
    if not isinstance(doc, dict):
        print(f"MANIFEST_UNKNOWN: no prompt manifest for {args.item} {args.step} in run {run_id} ({file})", file=sys.stderr)
        return 1
    print(json.dumps(doc, ensure_ascii=False, indent=2) if args.json else prompts.explain_table(doc))
    return 0


def _gates(args) -> int:
    """List or clear the machine gates of providers; the gates do not depend on a project."""
    try:
        if args.clear is not None:
            removed = gates.clear(args.clear or None)
            if args.clear and not removed:
                print(f"GATE_UNKNOWN: no gate for {args.clear}", file=sys.stderr)
                return 1
            print(json.dumps({"cleared": removed}) if args.json else
                  ("cleared: " + ", ".join(removed) if removed else "no gates"))
            return 0
        found = gates.active(time.time())
    except gates.GateError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    rows = [{"provider": name, **entry} for name, entry in sorted(found.items())]
    if args.json:
        print(json.dumps({"path": str(gates.path()), "gates": rows}, ensure_ascii=False, indent=2))
    elif not rows:
        print("no gates")
    for row in rows:
        if not args.json:
            print(f"{row['provider']}: until {row['until']} ({row['class']} {row['code']}, set by {row['set_by']})")
    return 0


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="conduct.py", description="Conduct pieces of work of a plan through "
                                     "the roles of their run-policy until green or an honest stop.")
    parser.add_argument("--config", type=Path, metavar="FILE", help="configuration file of the invocation layer")
    parser.add_argument("--project", type=Path, metavar="DIR",
                        help="the project (a git repository); default: SKM_PROJECT_ROOT, else the nearest .git or "
                             ".swissknifeman above the working directory")
    verbs = parser.add_subparsers(dest="verb", required=True)
    run = verbs.add_parser("run", help="claim and conduct pieces of work")
    where = run.add_mutually_exclusive_group(required=True)
    where.add_argument("--plan", help="collection of the work source, such as a plan id")
    where.add_argument("--input", type=Path, metavar="FILE",
                       help="work outside a plan: one execution-input document (orch.py input adhoc), served by the "
                            "built-in file source; its artifacts go to .swissknifeman/orch-artifacts")
    run.add_argument("--commit", action="store_true",
                     help="with --input: commit the changed paths of the work (default: they stay in the tree)")
    run.add_argument("--plans-root", dest="plans_root", metavar="DIR")
    which = run.add_mutually_exclusive_group()
    which.add_argument("--items", nargs="+", metavar="REF", help="these pieces of work, in order")
    which.add_argument("--batch", action="store_true", help="the next ready pieces of the source, one by one")
    run.add_argument("--max-items", dest="max_items", type=int, default=0, metavar="N",
                     help="with --batch: at most N pieces (default: until none is ready)")
    run.add_argument("--options", type=Path, metavar="FILE", help="run-options JSON: the most specific layer")
    run.add_argument("--single-session", dest="single_session", action=argparse.BooleanOptionalAction, default=None,
                     help="one executor session for all pieces of the run (default on: `session.executor: shared`); "
                          "--no-single-session starts a fresh executor session per step")
    run.add_argument("--scenario", help="the scenario to preview with --dry-run, or the scenario of a --input run "
                                        "(default: default_profile)")
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
    release = verbs.add_parser("release", help="give a claimed piece of a run back to the work source, when the run stopped "
                                                "before any work began (so that a later run can claim it)")
    release.add_argument("--run", required=True, metavar="RUN")
    release.add_argument("--item", required=True, metavar="REF")
    release.add_argument("--reason", default="released by hand", help="why, for the journal of the source")
    status = verbs.add_parser("status", help="state of a run from its journal (default: the latest run)")
    status.add_argument("--run", metavar="RUN")
    status.add_argument("--json", action="store_true")
    observe = verbs.add_parser("observe", help="write the observer report of a run, or --follow a running one")
    observe.add_argument("--run", metavar="RUN")
    observe.add_argument("--follow", action="store_true")
    answer = verbs.add_parser("answer", help="answer a question of the executor of a blocked piece (written into its "
                                              "questions.json); resume --retry ITEM then gives the answer to the executor")
    answer.add_argument("--run", required=True, metavar="RUN")
    answer.add_argument("--item", required=True, metavar="REF")
    answer.add_argument("--question", required=True, metavar="ID")
    chosen = answer.add_mutually_exclusive_group(required=True)
    chosen.add_argument("--option", metavar="ID", help="one of the options of the question")
    chosen.add_argument("--text", help="a free answer (for a question without options, or a clarification)")
    answer.add_argument("--by", metavar="WHO", help="who answers (default: the user of the shell)")
    listed = verbs.add_parser("questions", help="open questions of a run and their age (default: the latest run)")
    listed.add_argument("--run", metavar="RUN")
    listed.add_argument("--json", action="store_true")
    prompt = verbs.add_parser("prompt", help="what a prompt of a role step was made of")
    prompt_verbs = prompt.add_subparsers(dest="prompt_verb", required=True)
    explain = prompt_verbs.add_parser("explain", help="the blocks of the prompt of one step: kind, origin, tokens, digest, "
                                                      "and the skills left out (default run: the latest)")
    explain.add_argument("--run", metavar="RUN")
    explain.add_argument("--item", required=True, metavar="REF")
    explain.add_argument("--step", required=True, metavar="STEP", help="such as scout, executor.1, review.1, triage.1, close")
    explain.add_argument("--json", action="store_true")
    gate_list = verbs.add_parser("gates", help="provider capacity gates of this machine (exhausted account quotas); "
                                               "--clear removes them")
    gate_list.add_argument("--json", action="store_true")
    gate_list.add_argument("--clear", nargs="?", const="", default=None, metavar="PROVIDER",
                           help="remove the gate of PROVIDER, or every gate when no provider is given")
    args = parser.parse_args(argv)
    if args.verb == "run":
        if args.input and (args.items or args.batch or args.max_items or args.adopt):
            parser.error("--input is one piece of work: it takes no --items, --batch, --max-items or --adopt")
        if not args.input and not (args.items or args.batch):
            parser.error("one of --items or --batch is required with --plan")
        if args.commit and not args.input:
            parser.error("--commit belongs to --input: a plan source commits as its own policy says")
    if args.verb == "gates":
        return _gates(args)

    context = _project(args)
    if context is None:
        return 1
    project = context.root
    if args.verb in ("answer", "questions"):
        return _questions(args, project)
    if args.verb == "prompt":
        return _prompt(args, project)
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
        here = (found["current"] or {}).get("item") or (found["items"][-1]["item"] if found["items"] else None)
        listed = agents.read(directory / engine.safe(here)) if here else []
        if args.json:
            print(json.dumps({key: value for key, value in found.items() if key != "state"} |
                             {"tokens": found["state"].get("tokens"), "stop": found["state"].get("stop"),
                              "agents": listed}, ensure_ascii=False, indent=2))
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
        for row in listed:
            print(f"  agent {row['agent_run_id']}: {row['role']} {row['step']} {row['status']}, "
                  f"{row['tokens']['input']} in, {row['tokens']['output']} out")
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
                                 model_catalog=getattr(args, "model_catalog", None),
                                 project_resolution=context.resolution)
    try:
        if args.verb == "run" and args.dry_run:
            print(json.dumps(_preview(conductor, args), ensure_ascii=False, indent=2))
            return 0
        if args.verb == "run":
            return conductor.run(plan=args.plan, plans_root=args.plans_root, items=args.items or [],
                                 batch=args.batch, max_items=args.max_items, options_file=args.options,
                                 adopt=args.adopt, input_file=args.input, commit=args.commit, scenario=args.scenario,
                                 session=None if args.single_session is None else ("shared" if args.single_session else "per-item"))
        if args.verb == "release":
            return conductor.release(args.run, args.item, args.reason)
        if args.verb == "settle":
            return conductor.settle(args.run, args.item, args.outcome, args.reason)
        return conductor.resume(args.run, retry=args.retry)
    except engine.Stop as stop:
        print(f"{stop.code}: {stop.message}", file=sys.stderr)
        return 1
