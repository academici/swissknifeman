"""``plan.py`` command line: argument parsing -> ``ops`` / ``check`` / ``views`` -> output (dossier §8).

Authoring and lifecycle verbs (the context pack of ``start`` arrives with P2.2). Exit codes: 0 ok, 1 refusal
or check errors (stderr ``CODE: message``), 2 usage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from task import plan_numbering

from . import check, lifecycle, ops, store, views
from .model import EFFORT_ORDER, PHASE_ID, PlanError


class UsageError(Exception):
    """Bad command-line input that argparse cannot catch itself (exit 2)."""


def _actor(text: str) -> dict:
    parts = text.split("/")
    if len(parts) not in (2, 3) or not all(parts):
        raise argparse.ArgumentTypeError("expected PROVIDER/MODEL[/EFFORT]")
    actor = {"provider": parts[0], "model": parts[1]}
    if len(parts) == 3:
        if parts[2] not in EFFORT_ORDER:
            raise argparse.ArgumentTypeError(f"effort must be one of {', '.join(EFFORT_ORDER)}")
        actor["effort"] = parts[2]
    return actor


def _check_result(text: str) -> tuple[str, int]:
    match = re.fullmatch(r"(V[0-9]+)=(-?[0-9]+)", text)
    if match is None:
        raise argparse.ArgumentTypeError("expected V<n>=<exit code>, for example V1=0")
    return match[1], int(match[2])


def _session(value: str | None) -> str | None:
    """``--session`` value; ``auto`` asks ``task.session_context`` and falls back to nothing."""
    if value != "auto":
        return value
    try:
        from task import session_context
        return session_context.resolve().session_id
    except (ValueError, ImportError, OSError):
        return None


def _json_value(inline: str | None, file: Path | None, *, required: bool = True):
    """Value of ``--json`` (inline text or ``@file``) or ``--file``; ``None`` when absent and optional."""
    if inline is None and file is None:
        if required:
            raise UsageError("one of --json or --file is required")
        return None
    try:
        if file is not None:
            text = Path(file).read_text(encoding="utf-8")
        elif inline.startswith("@"):
            text = Path(inline[1:]).read_text(encoding="utf-8")
        else:
            text = inline
        return json.loads(text)
    except OSError as exc:
        raise UsageError(f"cannot read JSON input: {exc}") from exc
    except ValueError as exc:
        raise UsageError(f"invalid JSON: {exc}") from exc


def _plan_dir(args) -> Path:
    return store.resolve_plan_dir(args.plan, args.plans_root)


def _print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- handlers

def cmd_new(args) -> int:
    plans_root = args.plans_root or plan_numbering.find_plans_root()
    if args.message_file is not None:
        try:
            message = args.message_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"cannot read --message-file: {exc}") from exc
    else:
        message = args.message
    plan = ops.new_plan(
        args.codename, args.title, plans_root=plans_root, repository=args.repository or Path(plans_root).resolve().parent.name,
        owner=args.owner, authoring=args.actor, message=message, date=args.date, plan_id=args.plan_id,
        short_id=args.short_id)
    print(f"created {plan.plan['id']} ({plan.plan['short_id']}) at {plan.root}")
    return 0


def cmd_show(args) -> int:
    plan = store.load_plan(_plan_dir(args))
    if args.ref is None:
        order = [p for p in plan.plan.get("phases", []) if p in plan.phases]
        summary = {
            "id": plan.plan.get("id"), "short_id": plan.plan.get("short_id"), "title": plan.plan.get("title"),
            "status": plan.plan.get("status"),
            "phases": [{"id": pid, "title": plan.phases[pid].get("title"), "design": plan.phases[pid].get("design"),
                        "closed": plan.phases[pid].get("closed"),
                        "items": [{"id": iid, "title": plan.items[iid].get("title"), "status": plan.items[iid].get("status")}
                                  for iid in lifecycle.phase_items(plan, pid)]} for pid in order],
            "decisions": [{"id": k, "title": d.get("title"), "status": d.get("status")} for k, d in plan.decisions.items()],
            "next": lifecycle.next(plan).exact,
        }
        if args.json:
            _print_json(summary)
            return 0
        print(f"{summary['short_id']} {summary['id']} — {summary['title']} [{summary['status']}]")
        for phase in summary["phases"]:
            done = sum(1 for i in phase["items"] if i["status"] in ("done", "done_with_deviations", "skipped"))
            print(f"  {phase['id']} {phase['title']} ({phase['design']}, {done}/{len(phase['items'])})")
            for item in phase["items"]:
                print(f"    {item['id']} {views._item_label(item['status'])}  {item['title']}")
        print("  decisions: " + (", ".join(f"{d['id']} {d['status']}" for d in summary["decisions"]) or "none"))
        print(f"  next: {summary['next']}")
        return 0
    if args.ref in ("plan", "brief"):
        kind, doc = args.ref, getattr(plan, args.ref)
    else:
        kind, _key, doc = ops.resolve_target(plan, args.ref)
    print(store.canonical_dump(doc, kind), end="")
    return 0


def cmd_set(args) -> int:
    patch = _json_value(args.json, args.file)
    target = _plan_dir(args)
    if args.ref == "plan":
        ops.set_plan(target, patch)
    elif args.ref == "brief":
        ops.set_brief(target, patch)
    else:
        ops.patch(target, args.ref, patch)
    print(f"updated {args.ref}")
    return 0


def cmd_push(args) -> int:
    ops.push(_plan_dir(args), args.ref, args.field, _json_value(args.json, args.file))
    print(f"pushed to {args.ref}.{args.field}")
    return 0


def cmd_add_phase(args) -> int:
    print(ops.add_phase(_plan_dir(args), args.title, phase_id=args.id, data=_json_value(args.json, args.file, required=False)))
    return 0


def cmd_add_item(args) -> int:
    if not PHASE_ID.fullmatch(args.phase):
        raise UsageError(f"invalid phase id {args.phase!r}")
    print(ops.add_item(_plan_dir(args), args.phase, args.title, batch=args.batch,
                       data=_json_value(args.json, args.file, required=False)))
    return 0


def cmd_add_decision(args) -> int:
    print(ops.add_decision(_plan_dir(args), args.title, actor=args.actor,
                           data=_json_value(args.json, args.file, required=False)))
    return 0


def cmd_batches(args) -> int:
    ops.set_batches(_plan_dir(args), args.phase, _json_value(args.json, args.file))
    print(f"updated batches of {args.phase}")
    return 0


def cmd_check(args) -> int:
    issues = check.check(store.load_plan(_plan_dir(args)))
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    if args.json:
        _print_json({"ok": not errors, "errors": len(errors), "warnings": len(warnings), "issues": [i._asdict() for i in issues]})
        return 1 if errors else 0
    for issue in errors:
        print(f"{issue.code}: {issue.where}: {issue.message}", file=sys.stderr)
    for issue in warnings:
        print(f"warning {issue.code}: {issue.where}: {issue.message}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def cmd_render(args) -> int:
    plan = store.load_plan(_plan_dir(args))
    changed = views.render_all(plan, check=args.check)
    if args.check:
        for name in changed:
            print(f"STALE_VIEW: {name}", file=sys.stderr)
        return 1 if changed else 0
    print("rendered: " + (", ".join(changed) if changed else "nothing changed"))
    return 0


def cmd_next(args) -> int:
    action = lifecycle.next(store.load_plan(_plan_dir(args)))
    if args.json:
        _print_json(action.as_dict())
        return 0
    route = action.route
    print(action.exact + (f"  ({route['class']}/{route['effort']})" if route else ""))
    return 0


def cmd_start(args) -> int:
    actor = dict(args.actor)
    session = _session(args.session)
    if session:
        actor["session"] = session
    plan_dir = _plan_dir(args)
    result = lifecycle.start(plan_dir, args.items, actor, grants=args.grant)
    if args.json:
        _print_json({"items": list(result.items), "phase": result.phase, "batch": result.batch, "route": result.route,
                     "resumed": list(result.resumed), "packs": [str(path) for path in result.packs]})
    else:
        print(result.text(plan_dir.name))
    return 0


def cmd_finish(args) -> int:
    result = lifecycle.finish(
        _plan_dir(args), args.item, args.status, notes=args.notes or "", checks=dict(args.check),
        deviations=args.deviation, pending=args.pending, escalation=args.escalation, commits=args.commit,
        decision=args.decision, actor=args.actor)
    if args.json:
        _print_json({"item": result.item, "status": result.status, "phase_closed": result.phase_closed,
                     "plan_done": result.plan_done, "next": result.next.as_dict()})
    else:
        print(result.text())
    return 0


def cmd_log(args) -> int:
    lifecycle.log(_plan_dir(args), args.target, args.type, args.summary, impact=args.impact, next=args.next,
                  refs=args.ref, actor=args.actor)
    print(f"logged {args.type} for {args.target}")
    return 0


def cmd_decide(args) -> int:
    doc = lifecycle.decide(_plan_dir(args), args.decision, args.accept, args.rationale, by=args.by, actor=args.actor)
    print(f"{args.decision} accepted: {doc['decision']}")
    return 0


def cmd_supersede(args) -> int:
    lifecycle.supersede(_plan_dir(args), args.old, args.new, actor=args.actor)
    print(f"{args.new} supersedes {args.old}")
    return 0


def cmd_grant(args) -> int:
    action = lifecycle.grant(_plan_dir(args), args.gate, args.note, actor=args.actor)
    print(f"gate {args.gate} granted\nnext: {action.exact}")
    return 0


def cmd_design_done(args) -> int:
    if not PHASE_ID.fullmatch(args.phase):
        raise UsageError(f"invalid phase id {args.phase!r}")
    lifecycle.design_done(_plan_dir(args), args.phase, actor=args.actor)
    print(f"{args.phase} detailed")
    return 0


def cmd_reopen(args) -> int:
    lifecycle.reopen(_plan_dir(args), args.item, args.reason, actor=args.actor)
    print(f"{args.item} reopened")
    return 0


def cmd_archive(args) -> int:
    print(f"archived to {lifecycle.archive(_plan_dir(args), force=args.force, reason=args.reason, actor=args.actor)}")
    return 0


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plan.py", description="Task plan (layout v3): authoring and lifecycle verbs.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--plans-root", type=Path, default=None, help="plans/ directory (default: nearest up from cwd)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="VERB")

    def verb(name, handler, help_text, plan=True):
        p = sub.add_parser(name, parents=[common], help=help_text, description=help_text)
        p.set_defaults(handler=handler)
        if plan:
            p.add_argument("plan", help="plan id, PLAN<N> or path")
        return p

    def value_args(p, required):
        group = p.add_mutually_exclusive_group(required=required)
        group.add_argument("--json", help="JSON text, or @file")
        group.add_argument("--file", type=Path, help="file holding the JSON")

    p = verb("new", cmd_new, "create a plan", plan=False)
    p.add_argument("--codename", help="CODE-NAME [A-Z][A-Z0-9-]*")
    p.add_argument("--title", required=True)
    p.add_argument("--repository")
    p.add_argument("--owner", default="repository owner")
    p.add_argument("--actor", required=True, type=_actor, help="PROVIDER/MODEL[/EFFORT]")
    message = p.add_mutually_exclusive_group()
    message.add_argument("--message", help="first owner message, verbatim")
    message.add_argument("--message-file", type=Path)
    p.add_argument("--plan-id", help="adopt an existing identity (migration)")
    p.add_argument("--short-id", help="adopt an existing PLAN<N> (migration)")
    p.add_argument("--date", help="YYYY.MM.DD (default today)")

    p = verb("show", cmd_show, "overview of a plan, or one document as canonical JSON")
    p.add_argument("ref", nargs="?", help="plan, brief, Pn, Pn.m, D#, Pn.m/U#")
    p.add_argument("--json", action="store_true", help="machine-readable overview")

    p = verb("set", cmd_set, "merge-patch plan, brief, a phase, item, decision or unit")
    p.add_argument("ref", help="plan | brief | Pn | Pn.m | D# | Pn.m/U#")
    value_args(p, True)

    p = verb("push", cmd_push, "append a value to an array field (dotted paths allowed)")
    p.add_argument("ref")
    p.add_argument("field")
    value_args(p, True)

    p = verb("add-phase", cmd_add_phase, "add a skeleton phase")
    p.add_argument("--title", required=True)
    p.add_argument("--id", help="explicit phase id (migration)")
    value_args(p, False)

    p = verb("add-item", cmd_add_item, "add a skeleton item to a phase")
    p.add_argument("phase")
    p.add_argument("--title", required=True)
    p.add_argument("--batch", help="join (or create) this batch; default a solo batch")
    value_args(p, False)

    p = verb("add-decision", cmd_add_decision, "add a decision or open question")
    p.add_argument("--title", required=True)
    p.add_argument("--actor", type=_actor, help="PROVIDER/MODEL[/EFFORT] (default: plan authoring)")
    value_args(p, False)

    p = verb("batches", cmd_batches, "replace the batches of a phase")
    p.add_argument("phase")
    value_args(p, True)

    p = verb("check", cmd_check, "check a plan; exit 1 on errors")
    p.add_argument("--json", action="store_true")

    p = verb("render", cmd_render, "regenerate the Markdown views")
    p.add_argument("--check", action="store_true", help="report stale views, write nothing")

    p = verb("next", cmd_next, "semantic next step")
    p.add_argument("--json", action="store_true")

    def actor_arg(p, required=False, text="PROVIDER/MODEL[/EFFORT] (default: the item executor, else plan authoring)"):
        p.add_argument("--actor", type=_actor, required=required, help=text)

    p = verb("start", cmd_start, "start (or resume) items of one detailed phase")
    p.add_argument("items", nargs="+", metavar="item")
    actor_arg(p, required=True, text="PROVIDER/MODEL[/EFFORT] running the items")
    p.add_argument("--session", help="provider session id, or auto")
    p.add_argument("--grant", action="append", default=[], metavar="GATE", help="record an owner gate grant now")
    p.add_argument("--json", action="store_true")

    p = verb("finish", cmd_finish, "record the outcome of an item; closes the phase and the plan when complete")
    p.add_argument("item")
    p.add_argument("--status", required=True, choices=lifecycle.FINISH_STATUSES)
    p.add_argument("--notes")
    p.add_argument("--check", action="append", default=[], type=_check_result, metavar="V1=0",
                   help="acceptance check outcome (repeatable)")
    p.add_argument("--deviation", action="append", default=[], metavar="TEXT")
    p.add_argument("--pending", action="append", default=[], metavar="TEXT")
    p.add_argument("--escalation", help="what the owner must decide or provide (blocked)")
    p.add_argument("--commit", action="append", default=[], metavar="SHA")
    p.add_argument("--decision", metavar="D#", help="accepted decision that skips the item (skipped)")
    actor_arg(p)
    p.add_argument("--json", action="store_true")

    p = verb("log", cmd_log, "record friction for an item or phase")
    p.add_argument("target", help="Pn.m or Pn")
    p.add_argument("--type", required=True, choices=lifecycle.FRICTION_TYPES)
    p.add_argument("--summary", required=True)
    p.add_argument("--impact")
    p.add_argument("--next")
    p.add_argument("--ref", action="append", default=[], metavar="REF")
    actor_arg(p)

    p = verb("decide", cmd_decide, "accept an open decision")
    p.add_argument("decision", metavar="D#")
    p.add_argument("--accept", required=True, help="option id or decision text")
    p.add_argument("--rationale", required=True)
    p.add_argument("--by", choices=("owner", "agent"), default="agent")
    actor_arg(p)

    p = verb("supersede", cmd_supersede, "mark an accepted decision as replacing another")
    p.add_argument("old", metavar="OLD_D#")
    p.add_argument("new", metavar="NEW_D#")
    actor_arg(p)

    p = verb("grant", cmd_grant, "record an owner gate grant (note quotes the owner's message)")
    p.add_argument("gate")
    p.add_argument("--note", required=True)
    actor_arg(p)

    p = verb("design-done", cmd_design_done, "mark a phase detailed after check")
    p.add_argument("phase")
    actor_arg(p)

    p = verb("reopen", cmd_reopen, "reopen a finished item (owner amendment)")
    p.add_argument("item")
    p.add_argument("--reason", required=True)
    actor_arg(p)

    p = verb("archive", cmd_archive, "move a done plan to plans/archive/")
    p.add_argument("--force", action="store_true", help="archive a plan that is not done (needs --reason)")
    p.add_argument("--reason")
    actor_arg(p)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse: 0 for --help, 2 for usage
        return int(exc.code or 0)
    if args.command == "new" and not (args.codename or args.plan_id):
        print("plan.py new: error: --codename or --plan-id is required", file=sys.stderr)
        return 2
    try:
        return args.handler(args)
    except UsageError as exc:
        print(f"plan.py {args.command}: error: {exc}", file=sys.stderr)
        return 2
    except PlanError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
