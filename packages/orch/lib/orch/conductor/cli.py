"""Command line of the conductor: ``swissknifeman orch conduct run|resume|settle|release|status|runs|observe|answer|questions|prompt|timeline|gates``.

Exit codes: 0 the run finished (or the command succeeded), 1 the run stopped or a command was refused (``CODE:
message`` on stderr), 2 usage, 130 interrupted (resume continues).
"""
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import re
import sys
import time
from typing import Optional

from aicore.config import ConfigError
from aicore.state import ProjectContextRequired

from orch import project as project_mod, sandbox, settings as settings_mod
from orch.conductor import agents, engine, frozen, gates, observer, options as opts, progress, prompts, questions, runs
from orch.conductor.application import run_service
from orch.conductor.infrastructure import roles


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
    return runs.latest_run_id(project)


def _preview(conductor: engine.Conductor, args) -> dict:
    """What a run would do, without the work source: the policy of the scenario, the merged options of the
    configuration, the pack and ``--options``, and the route and command line of every role."""
    conductor.run_id = "cnd-dry-run"
    claim = {"scenario": args.scenario or conductor.settings.default_profile, "options": []}
    item = engine.Item(ref="(preview)", orch_run="-", state={}, directory=Path(), claim=claim)
    conductor.run_doc = {"options_file": str(args.options) if args.options else None,
                         "fence": getattr(args, "fence", None), "extra_paths": getattr(args, "allow_path", [])}
    conductor._resolve(item, persist=False)
    unavailable = conductor._routes(item, persist=False, preview=True) or {}
    problems = {**{role: conductor.route_problem(route) for role, route in item.routes.items()}, **unavailable}
    available = {role: problem is None for role, problem in problems.items()}
    unavailable = {role: problem for role, problem in problems.items() if problem}
    isolation = {}
    for role, route in item.routes.items():
        built = conductor._role_argv(item, role, route)
        guarded = any(arg.endswith("ro-run.py") for arg in built[:2])
        base = route["argv"] if guarded else roles.strip_guard(route["argv"])
        isolation[role] = built[len(base):]
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
    claim_actor, gap = _claim_actor_of(conductor, item.routes.get("executor"))
    warnings += [gap] if gap else []
    return {"plan": args.plan or str(args.input), "items": args.items or None, "ready": bool(args.ready),
            "batch": args.batch is not False and (len(args.items or []) > 1 or bool(args.ready)),
            "scenario": claim["scenario"], "stages": [stage["id"] for stage in item.policy.get("stages", [])],
            "review": item.policy.get("review"), "options": item.options, "sources": item.sources,
            "reviewer": {"selector": item.options["reviewer"], "source": item.sources.get("reviewer", "default")},
            "fallback_routes": item.options["fallback_routes"], "route_notes": item.route_notes,
            "gates": [{"provider": name, **entry} for name, entry in sorted(gates.active(time.time()).items())],
            "routes": item.routes, "available": available, "unavailable": unavailable,
            "isolation_args": isolation, "sandbox": {"available": probed["available"], "reason": probed["reason"]},
            "claim_actor": claim_actor, "network": network, "warnings": warnings,
            "note": "the work source adds the scenario and the options of the plan, phase and item at claim time"}


def _claim_actor_of(conductor, route: dict | None) -> tuple:
    """``(actor, warning)``: the actor a real run hands to ``source claim --actor`` (the source checks the route of the
    piece against it), and a warning when it is not the executor the preview routes, which the claim would refuse
    (``ROUTE_MISMATCH``, ``ROUTE_UNDERSHOOT``) while this preview is green."""
    try:
        actor = conductor._claim_actor()
    except engine.Stop as stop:
        return None, f"claim actor: {stop.code}: {stop.message}"
    if route is None:
        return actor, None
    claimed = opts.parse_actor(actor)
    differs = [name for name in ("provider", "model", "effort")
               if claimed.get(name) and claimed[name] != route.get(name)]
    if not differs:
        return actor, None
    routed = "/".join(part for part in (route["provider"], route["model"], route["effort"]) if part)
    return actor, (f"executor: the claim names {actor}, but the route is {routed} ({', '.join(differs)} differ): "
                   "a piece whose route pins the executor is refused at the claim")


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
    try:
        entry = questions.answer_file(folder, args.question, item=args.item, option=args.option, text=args.text,
                                      by=args.by or getpass.getuser(), now=engine.utc_now())
    except (questions.QuestionError, engine.Stop) as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    print(json.dumps({"run": run_id, "item": args.item, "question": entry["id"], "revision": entry["revision"],
                      "resolution": entry["resolution"],
                      "next": f"orch conduct resume --run {run_id} --retry {args.item}"}, ensure_ascii=False))
    return 0


STEP_PATTERN = r"[a-z][a-z0-9-]*(\.[0-9]+(-q[0-9]+)?)?"


class _PromptError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


def _manifest(project: Path, run: Optional[str], item: str, step: str, missing: str = "MANIFEST_UNKNOWN") -> tuple:
    """``(run_id, manifest)`` of ``prompts/<step>.manifest.json`` of ``item`` in ``run`` (default: the latest run), the
    paths checked to stay inside the run; ``_PromptError`` otherwise (``missing`` names a manifest that is not there)."""
    if re.fullmatch(STEP_PATTERN, step) is None:
        raise _PromptError("PROMPT_PATH_INVALID", "step must be a role step such as executor.1")
    run_id = run or _latest(project)
    if run_id and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id) is None:
        raise _PromptError("PROMPT_PATH_INVALID", "invalid run id")
    directory = engine.runs_root(project) / (run_id or "-")
    if not run_id or not (directory / engine.RUN_FILE).is_file():
        raise _PromptError("RUN_UNKNOWN", f"no conductor run {run or ''} in {engine.runs_root(project)}")
    item_dir = directory / engine.safe(item)
    file = item_dir / "prompts" / f"{step}.manifest.json"
    try:
        item_dir.resolve().relative_to(directory.resolve())
        file.resolve().relative_to(item_dir.resolve())
    except (ValueError, OSError, RuntimeError):
        raise _PromptError("PROMPT_PATH_INVALID", "manifest must resolve inside the item directory") from None
    doc = engine.read_json(file) if file.is_file() else None
    if not isinstance(doc, dict):
        raise _PromptError(missing, f"no prompt manifest for {item} {step} in run {run_id} ({file})")
    return run_id, doc


def _baseline(step: str) -> Optional[str]:
    """The previous attempt of the same step (``executor.2`` -> ``executor.1``), None for a first one."""
    found = re.fullmatch(r"([a-z][a-z0-9-]*)\.([0-9]+)(-q[0-9]+)?", step)
    if found is None or int(found.group(2)) <= 1:
        return None
    return f"{found.group(1)}.{int(found.group(2)) - 1}{found.group(3) or ''}"


def _prompt(args, project: Path) -> int:
    """``prompt explain``: the blocks of the prompt a role step was given (``prompts/<step>.manifest.json``), their
    origin, size and digest, and what was left out. ``prompt diff``: what changed in it against the previous attempt of
    the step or a named ``RUN:ITEM:STEP``."""
    try:
        if args.prompt_verb == "diff":
            return _prompt_diff(args, project)
        _run_id, doc = _manifest(project, args.run, args.item, args.step)
    except _PromptError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    print(json.dumps(doc, ensure_ascii=False, indent=2) if args.json else prompts.explain_table(doc))
    return 0


def _prompt_diff(args, project: Path) -> int:
    run_id, target = _manifest(project, args.run, args.item, args.step, missing="PROMPT_MANIFEST_MISSING")
    if args.against:
        parts = args.against.split(":")
        if len(parts) != 3 or not all(parts):
            raise _PromptError("PROMPT_PATH_INVALID", "--against takes RUN:ITEM:STEP")
        against = (parts[0], parts[1], parts[2])
    else:
        previous = _baseline(args.step)
        if previous is None:
            raise _PromptError("PROMPT_BASELINE_MISSING", f"{args.step} is the first attempt of its step: name the prompt "
                                                          "to compare with --against RUN:ITEM:STEP")
        against = (run_id, args.item, previous)
    _base_run, base = _manifest(project, *against, missing="PROMPT_MANIFEST_MISSING")
    doc = dict(prompts.diff_manifests(base, target), run=run_id, item=args.item,
               against={"run": against[0], "item": against[1], "step": against[2]})
    print(json.dumps(doc, ensure_ascii=False, indent=2) if args.json else prompts.diff_table(doc))
    return 0


def _check_outcome(check: dict) -> str:
    """The text of one check under a ``checks.N`` interval: ``12.4 s green``, ``skipped (fail_fast)``, ``reused (12 s)``."""
    if check["skipped"]:
        return "skipped" + (f" ({check['skip_reason']})" if check.get("skip_reason") else "")
    if check["reused"]:
        return "reused" + (f" ({check['original_seconds']} s)" if check.get("original_seconds") is not None else "")
    took = f"{check['seconds']} s " if check.get("seconds") is not None else ""
    return took + ("green" if check["green"] else "red")


def _timeline(args, project: Path) -> int:
    """``timeline``: the steps of the pieces of a run as intervals with their durations, from its journal."""
    run_id = args.run or _latest(project)
    directory = engine.runs_root(project) / (run_id or "-")
    if not run_id or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id) is None or not (directory / engine.RUN_FILE).is_file():
        print(f"RUN_UNKNOWN: no conductor run {args.run or ''} in {engine.runs_root(project)}".rstrip(), file=sys.stderr)
        return 1
    rows = progress.timeline(progress.read_lines(directory), item=args.item,
                             state=engine.read_json(directory / engine.STATE_FILE) or {})
    if args.json:
        print(json.dumps(runs.display({"run": run_id, "item": args.item, "intervals": rows}), ensure_ascii=False, indent=2))
        return 0
    for row in rows:
        took = f"{row['duration_s']} s" if row["duration_s"] is not None else "-"
        print(f"{row['start']} {row['item']} {row['stage']}: {row['status']}, {took}"
              + (f" ({row['verdict']})" if row.get("verdict") else ""))
        for check in row.get("checks") or []:
            print(f"  - {check['id']} " + _check_outcome(check))
    if not rows:
        print("no steps in the journal")
    return 0


def _status_details(directory: Path, found: dict) -> dict:
    """Add read-only observability to the journal summary without rebuilding routes or options."""
    state = found["state"]
    doc = engine.read_json(directory / engine.RUN_FILE) or {}
    raises = state.get("limit_raises") or []
    limits = {}
    if doc.get("limits_run") or raises:
        limits = {"items": {}, **(doc.get("limits_run") or {}), "limit_raises": raises}
    for row in found["items"]:
        ref = row["item"]
        item_state = (state.get("items") or {}).get(ref) or {}
        folder = directory / engine.safe(ref)
        recorded = engine.read_json(folder / "routes.json") or {}
        row.update(tokens=item_state.get("tokens"), usage_incomplete=item_state.get("usage_incomplete"),
                   routes={role: runs.public_route(route) for role, route in recorded.items()
                           if isinstance(route, dict)})
        options = engine.read_json(folder / "options.json") or {}
        item_limits = (options.get("options") or {}).get("limits") or {}
        if item_limits:
            limits.setdefault("items", {})[ref] = {key: item_limits.get(key, 0)
                                                   for key in ("tokens_max", "tokens_hard_max")}
    if limits:
        limits.setdefault("limit_raises", raises)
        for change in raises:
            key = change["key"]
            if key == "tokens_hard_max":
                for ref, entry in limits.get("items", {}).items():
                    if change.get("item") in (None, ref):  # a raise names its piece; an old record holds for all
                        entry[key] = change["to"]
            elif key == "run_tokens_hard_max":
                limits[key] = {**limits.get(key, {}), "value": change["to"], "source": "invocation:--raise-limit"}
    codes = {"BUDGET_OVER", "BUDGET_UNMETERED", "STAGE_INTERRUPTED", "ROLE_ORPHAN_KILLED", "LIMIT_RAISED", "CATALOG_CHANGED"}
    beacons = {}
    for line in progress.read_lines(directory):
        if line.get("event") == "info" and line.get("reason_code") in codes:
            code = line["reason_code"]
            beacons.pop(code, None)
            beacons[code] = line
    return {"lease": runs.live_owner(directory), "limits": limits, "beacons": list(beacons.values()),
            **({"catalog_digests": doc["catalog_digests"]} if isinstance(doc.get("catalog_digests"), dict) else {})}


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
    parser = argparse.ArgumentParser(prog="swissknifeman orch conduct", description="Conduct pieces of work of a plan through "
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
    which.add_argument("--ready", action="store_true", help="the next ready pieces of the source, one by one")
    run.add_argument("--max-items", dest="max_items", type=int, default=0, metavar="N",
                     help="with --ready: at most N pieces (default: until none is ready)")
    run.add_argument("--options", type=Path, metavar="FILE", help="run-options JSON: the most specific layer")
    run.add_argument("--batch", action=argparse.BooleanOptionalAction, default=None,
                     help="the pieces of this run are one batch (default): all are taken in progress at the start and "
                          "one executor session carries them in order (`session.executor: shared`); --no-batch takes one "
                          "piece at a time, each executor step in a fresh session")
    run.add_argument("--fence", choices=("project", "plan"), default=None,
                     help="what the executor may change: the whole project (default; the plan's write set is reported "
                          "against) or only the plan's write set (`scope.fence`)")
    run.add_argument("--allow-path", dest="allow_path", action="append", default=None, metavar="DIR",
                     help="a directory outside the project the executor may also change (repeatable; `scope.extra_paths`)")
    run.add_argument("--scenario", help="the scenario of the run: wins over the scenario the plan resolves for each "
                                        "piece (overlays, `orchestration`); also for --input and --dry-run "
                                        "(default: the plan's, else default_profile)")
    run.add_argument("--frozen", action="store_true",
                     help="conduct from a snapshot of the committed orchestrator (a piece that rewrites orch itself must not "
                          "change the code that conducts it); the snapshot is removed when the run ends")
    run.add_argument("--dry-run", action="store_true", help="print what would run; claims nothing, writes nothing")
    run.add_argument("--model-catalog", dest="model_catalog", type=Path, metavar="FILE")
    run.add_argument("--adopt", action="store_true",
                     help="take over the changes in the tree as an earlier attempt of the first piece (they must lie in "
                          "its write set): the executor checks and finishes them instead of starting over")
    resume = verbs.add_parser("resume", help="continue a stopped run; closed steps are not repeated")
    resume.add_argument("--run", required=True, metavar="RUN")
    resume.add_argument("--raise-limit", action="append", default=[], metavar="KEY=N",
                        help="raise tokens_hard_max or run_tokens_hard_max (repeatable); 0 explicitly removes the limit")
    resume.add_argument("--retry", nargs="+", default=[], metavar="ITEM",
                        help="also continue these blocked pieces: their steps from the blocked executor round on are "
                             "repeated (the source must have reopened them); finished steps are kept")
    resume.add_argument("--model-catalog", dest="model_catalog", type=Path, metavar="FILE")
    resume.add_argument("--frozen", action="store_true", help="as for run: a new snapshot of the committed orchestrator")
    for sub in (run, resume):
        sub.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None,
                         help="debug mode for this run: DEBUG_MODE beacon with the observer protocol and a journal in "
                              "<run>/debug/ (default: `[orch] debug` of the project, else of the machine, else off)")
        quiet = sub.add_mutually_exclusive_group()
        quiet.add_argument("--quiet", action="store_true", help="no progress lines on stderr")
        quiet.add_argument("--json-lines", dest="json_lines", action="store_true", help="progress lines as JSON")
    settle = verbs.add_parser("settle", help="set the outcome of a piece of a run by hand (--item, --outcome), after it was "
                                             "finished or given up outside the conductor; or lift the stop of a group review "
                                             "with Blocker findings (--group, --followup-run), after its follow-up run was "
                                             "committed")
    settle.add_argument("--run", required=True, metavar="RUN")
    settle.add_argument("--item", metavar="REF", help="the piece to settle (with --outcome)")
    settle.add_argument("--outcome", choices=["done", "done_with_deviations", "blocked"])
    settle.add_argument("--group", type=int, metavar="N", help="the group (number in review-strategy.json) whose "
                                                              "GROUP_REVIEW_BLOCKER is lifted (with --followup-run)")
    settle.add_argument("--followup-run", dest="followup_run", metavar="RUN",
                        help="the finished, committed run of group-review-N.followup.json of this run")
    settle.add_argument("--reason", required=True, help="why, for the journal")
    release = verbs.add_parser("release", help="give a claimed piece of a run back to the work source, when the run stopped "
                                                "before any work began (so that a later run can claim it)")
    release.add_argument("--run", required=True, metavar="RUN")
    which = release.add_mutually_exclusive_group(required=True)
    which.add_argument("--item", action="append", metavar="REF", help="a piece to give back (repeatable)")
    which.add_argument("--all", action="store_true", help="every piece of the run that nobody worked on and that is not closed "
                                                         "(the whole batch after a stop before any work)")
    release.add_argument("--reason", default="released by hand", help="why, for the journal of the source")
    status = verbs.add_parser("status", help="state of a run from its journal (default: the latest run)")
    status.add_argument("--run", metavar="RUN")
    status.add_argument("--json", action="store_true")
    listing = verbs.add_parser("runs", help="the conductor runs of the project, newest first")
    listing.add_argument("--limit", type=int, default=None, metavar="N", help="at most N runs (default: all)")
    listing.add_argument("--json", action="store_true", help='print {"runs": [{run_id, status, reason_code, created, '
                                                              'items, resumes}]}')
    prune = verbs.add_parser("prune", help="remove the folders of runs that ended long ago (dry run unless --apply); the latest "
                                           "and a running run stay")
    prune.add_argument("--older-than", type=int, required=True, metavar="DAYS", help="runs that ended more than DAYS days ago")
    prune.add_argument("--dry-run", action="store_true", help="only list what would be removed (the default)")
    prune.add_argument("--apply", action="store_true", help="remove them")
    prune.add_argument("--json", action="store_true", help='print {"runs": [{run_id, status, age_days, paths, removed}]}')
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
    diff = prompt_verbs.add_parser("diff", help="what changed in the prompt of a step against its previous attempt or "
                                                "--against RUN:ITEM:STEP: blocks added, removed, changed (digest), tokens")
    diff.add_argument("--run", metavar="RUN")
    diff.add_argument("--item", required=True, metavar="REF")
    diff.add_argument("--step", required=True, metavar="STEP", help="such as executor.2 (compared with executor.1)")
    diff.add_argument("--against", metavar="RUN:ITEM:STEP", help="the prompt to compare with")
    diff.add_argument("--json", action="store_true")
    timeline_verb = verbs.add_parser("timeline", help="the steps of the pieces of a run as intervals with durations, "
                                                      "from its journal (default run: the latest)")
    timeline_verb.add_argument("--run", metavar="RUN")
    timeline_verb.add_argument("--item", metavar="REF", help="only the steps of this piece")
    timeline_verb.add_argument("--json", action="store_true")
    gate_list = verbs.add_parser("gates", help="provider capacity gates of this machine (exhausted account quotas); "
                                               "--clear removes them")
    gate_list.add_argument("--json", action="store_true")
    gate_list.add_argument("--clear", nargs="?", const="", default=None, metavar="PROVIDER",
                           help="remove the gate of PROVIDER, or every gate when no provider is given")
    args = parser.parse_args(argv)
    if args.verb == "run":
        if args.batch is True and not (args.items or args.ready or args.input):
            args.ready = True  # `--batch` used to select the next ready pieces
            print("note: --batch now groups the pieces of a run; selecting the next ready pieces is --ready", file=sys.stderr)
        if args.input and (args.items or args.ready or args.max_items or args.adopt):
            parser.error("--input is one piece of work: it takes no --items, --ready, --max-items or --adopt")
        if not args.input and not (args.items or args.ready):
            parser.error("one of --items or --ready is required with --plan")
        if args.commit and not args.input:
            parser.error("--commit belongs to --input: a plan source commits as its own policy says")
    if args.verb == "settle":
        if args.group is not None:
            if args.item or args.outcome or not args.followup_run:
                parser.error("--group settles a group review: it takes --followup-run, and no --item or --outcome")
        elif args.followup_run or not (args.item and args.outcome):
            parser.error("settle takes --item and --outcome, or --group and --followup-run")
    if args.verb == "runs" and args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.verb == "prune":
        if args.older_than < 1:
            parser.error("--older-than must be at least 1")
        if args.apply and args.dry_run:
            parser.error("--apply and --dry-run exclude each other")
    if args.verb == "gates":
        return _gates(args)

    context = _project(args)
    if context is None:
        return 1
    project = context.root
    if getattr(args, "frozen", False) and args.verb in ("run", "resume") and not getattr(args, "dry_run", False):
        try:
            return frozen.relaunch(list(sys.argv[1:] if argv is None else argv), project)
        except frozen.FrozenError as error:
            print(f"{error.code}: {error}", file=sys.stderr)
            return 1
    if args.verb == "runs":
        rows = runs.listing(project, args.limit)
        print(json.dumps({"runs": rows}, ensure_ascii=False, indent=2) if args.json else runs.text(rows))
        return 0
    if args.verb == "prune":
        rows = runs.prune(project, args.older_than, apply=args.apply)
        print(json.dumps({"runs": rows}, ensure_ascii=False, indent=2) if args.json else runs.prune_text(rows, args.apply))
        return 0
    if args.verb in ("answer", "questions"):
        return _questions(args, project)
    if args.verb == "prompt":
        return _prompt(args, project)
    if args.verb == "timeline":
        return _timeline(args, project)
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
        found = runs.effective_status(directory, progress.summarize(progress.read_lines(directory)))
        found["run"] = run_id
        found["state"] = engine.read_json(directory / engine.STATE_FILE) or {}
        here = (found["current"] or {}).get("item") or (found["items"][-1]["item"] if found["items"] else None)
        listed = agents.read(directory / engine.safe(here)) if here else []
        doc = engine.read_json(directory / engine.RUN_FILE) or {}
        batch = doc.get("grouped") is not False and len(doc.get("items") or []) > 1
        held = run_service.held_pieces(found["state"]) if batch and found["status"] in ("stopped", "orphaned") else []
        if args.json:
            details = _status_details(directory, found)
            if held:
                details["held"] = {"items": held, "hint": run_service.held_hint(run_id, held)}
            print(json.dumps(runs.display({key: value for key, value in found.items() if key != "state"} |
                              {"tokens": found["state"].get("tokens"), "stop": found["state"].get("stop"),
                               "last_stop": found["state"].get("last_stop"), "agents": listed, **details}),
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
        if held:
            print("  " + run_service.held_hint(run_id, held))
        tokens = found["state"].get("tokens") or {}
        print(f"  tokens: {tokens.get('input', 0)} in, {tokens.get('output', 0)} out")
        for row in listed:
            print(f"  agent {row['agent_run_id']}: {row['role']} {row['step']} {row['status']}, "
                  f"{row['tokens']['input']} in, {row['tokens']['output']} out")
        return 0

    try:
        debug = getattr(args, "debug", None)
        current = settings_mod.load(project=project, config_file=args.config,
                                    flags=None if debug is None else {"debug": debug})
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
                                 batch=args.ready, max_items=args.max_items, options_file=args.options,
                                 adopt=args.adopt, input_file=args.input, commit=args.commit, scenario=args.scenario,
                                 fence=args.fence, extra_paths=args.allow_path, grouped=args.batch)
        if args.verb == "release":
            return conductor.release(args.run, None if args.all else args.item, args.reason)
        if args.verb == "settle" and args.group is not None:
            return conductor.settle_group(args.run, args.group, args.followup_run, args.reason)
        if args.verb == "settle":
            return conductor.settle(args.run, args.item, args.outcome, args.reason)
        return conductor.resume(args.run, retry=args.retry, raise_limits=args.raise_limit)
    except engine.Stop as stop:
        print(f"{stop.code}: {stop.message}", file=sys.stderr)
        return 1
