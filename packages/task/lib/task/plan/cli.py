"""``plan.py`` command line: argument parsing -> ``ops`` / ``check`` / ``views`` -> output (dossier §8).

Authoring verbs only; lifecycle verbs arrive with P2.1/P2.2. Exit codes: 0 ok, 1 refusal or check errors
(stderr ``CODE: message``), 2 usage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from task import plan_numbering

from . import check, ops, store, views
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
                                  for iid in views._phase_items(plan, pid)]} for pid in order],
            "decisions": [{"id": k, "title": d.get("title"), "status": d.get("status")} for k, d in plan.decisions.items()],
            "next": views._next_batch(plan)["exact"],  # P2.1 replaces this with lifecycle.next
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
    action = views._next_batch(store.load_plan(_plan_dir(args)))  # P2.1 replaces this with lifecycle.next
    if args.json:
        _print_json(action)
        return 0
    route = action["route"]
    print(action["exact"] + (f"  ({route['class']}/{route['effort']})" if route else ""))
    return 0


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plan.py", description="Task plan (layout v3): authoring verbs.")
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
