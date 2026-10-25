"""``plan.py`` command line: argument parsing -> ``ops`` / ``check`` / ``views`` -> output (dossier §8).

Authoring, lifecycle and context-pack verbs. Exit codes: 0 ok, 1 refusal
or check errors (stderr ``CODE: message``), 2 usage.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import re
import sys

from .. import integration
from . import (bridges, budget, catalog, check, context, gitops, lifecycle, ops, parallel, query, schema, settings, snapshot,
               readiness, stats, store, units, views)
from .model import EFFORT_ORDER, PHASE_ID, PlanError


_UNIT_VERBS = ("dispatch", "return", "accept", "rework", "reject")
_READ_VERBS = ("get", "list", "events", "artifact", "links", "neighborhood", "schema", "commits", "followups", "plans")


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


def _evidence(text: str) -> tuple[str, str]:
    match = re.fullmatch(r"(V[0-9]+)=(\S+)", text)
    if match is None:
        raise argparse.ArgumentTypeError("expected V<n>=<evidence path>, for example V1=@plan/artifacts/P1.2/V1.json")
    return match[1], match[2]


def _evidence_map(pairs: list[tuple[str, str]]) -> dict[str, str]:
    seen: dict[str, str] = {}
    for check_id, path in pairs:
        if check_id in seen:
            raise UsageError(f"--evidence {check_id} is given twice")
        seen[check_id] = path
    return seen


def _repo_mapping(text: str) -> tuple[str, str]:
    name, sep, path = text.partition("=")
    if not sep or not re.fullmatch(r"[a-z0-9-]+", name) or not path:
        raise argparse.ArgumentTypeError("expected NAME=PATH, for example swissknifeman=/work/swissknifeman")
    return name, path


def _session(value: str | None) -> str | None:
    """``--session`` value; ``auto`` asks ``planner.session_context`` and falls back to nothing."""
    if value != "auto":
        return value
    try:
        from planner import session_context
        return session_context.resolve().session_id
    except (ValueError, ImportError, OSError):
        return None


def _csv(text: str) -> list[str]:
    parts = [part.strip() for part in text.split(",")]
    if not all(parts):
        raise argparse.ArgumentTypeError("expected a non-empty comma-separated list")
    return parts


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


def _expected_revision(args) -> str | None:
    value = getattr(args, "expected_revision", None)
    if value is not None and not query.REVISION.fullmatch(value):
        raise UsageError("--expected-revision must look like sha256:<64 lowercase hex digits>")
    return value


def _plan_dir(args) -> Path:
    return store.resolve_plan_dir(args.plan, args.plans_root)


def _print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- handlers

def cmd_new(args) -> int:
    plans_root = args.plans_root or store.find_plans_root()
    if args.message_file is not None:
        try:
            message = args.message_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"cannot read --message-file: {exc}") from exc
    else:
        message = args.message
    plan = ops.new_plan(
        args.codename, args.title, plans_root=plans_root, repository=args.repository or ops.default_repository(plans_root),
        owner=args.owner, authoring=args.actor, message=message, date=args.date)
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
    # Keep the legacy document-only output, including knowledge/<id>.json.
    ref = args.ref.removesuffix(".json") if args.ref.startswith("knowledge/") else args.ref
    data = query.get(plan, ref)
    store.check_doc(data, "read-get", "show result")
    if data["kind"] == "artifact":
        _print_json(data["doc"])
    else:
        print(store.canonical_dump(data["doc"], data["kind"]), end="")
    return 0


def _read_result(data, kind: str) -> int:
    store.check_doc(data, kind, f"{kind} result")
    _print_json(data)
    return 0


def cmd_get(args) -> int:
    return _read_result(query.get(store.load_plan(_plan_dir(args)), args.ref, section=args.section,
                                  fields=args.fields, repos=_repos(args)), "read-get")


def cmd_plans(args) -> int:
    return _read_result(query.plans_overview(args.plans_root or store.find_plans_root()), "read-plans")


def cmd_list(args) -> int:
    return _read_result(query.list_rows(store.load_plan(_plan_dir(args)), args.kind, status=args.status,
                                       phase=args.phase, applies_to=args.applies_to), "read-list")


def cmd_events(args) -> int:
    return _read_result(query.events(store.load_plan(_plan_dir(args)), item=args.item, types=args.type,
                                    since=args.since, limit=args.limit), "read-events")


def cmd_commits(args) -> int:
    return _read_result(gitops.list_commits(_plan_dir(args), args.ref, role=args.role), "read-commits")


def cmd_followups(args) -> int:
    return _read_result(query.followups(store.load_plan(_plan_dir(args)), open_only=args.open), "read-followups")


def cmd_artifact(args) -> int:
    return _read_result(query.artifact(store.load_plan(_plan_dir(args)), args.ref, inline=args.inline,
                                      repos=_repos(args)), "read-artifact")


def cmd_links(args) -> int:
    return _read_result(query.links(store.load_plan(_plan_dir(args)), args.ref, direction=args.direction,
                                   kinds=args.kind, depth=args.depth), "read-links")


def cmd_neighborhood(args) -> int:
    return _read_result(query.neighborhood(store.load_plan(_plan_dir(args)), args.item), "read-neighborhood")


def cmd_schema(args) -> int:
    if args.kind is None:
        return _read_result(catalog.verbs(build_parser()), "read-catalog")
    registry = schema.load_registry()
    if args.kind == "defs":
        document, _base = registry.resolve(f"{schema.SCHEMA_URN_PREFIX}defs:v1", "")
    else:
        document, _base = registry.for_kind(args.kind)
    _print_json(document)  # The registry has already checked the schema's closed profile.
    return 0


def cmd_bridge(args) -> int:
    if args.name == "list":
        if args.verb is not None or args.args:
            raise UsageError("bridge list takes no arguments")
        data = bridges.listing()
        if args.output == "json":
            _print_json(data)
        else:
            for row in data["bridges"]:
                print(" ".join((row["name"], row["partner"], row["direction"], *row["verbs"])))
        return 0
    return bridges.run(args.name, args.verb, args.args)


def cmd_set(args) -> int:
    patch = _json_value(args.json, args.file)
    expected = _expected_revision(args)
    target = _plan_dir(args)
    if args.ref == "plan":
        ops.set_plan(target, patch, expected_revision=expected)
    elif args.ref == "brief":
        ops.set_brief(target, patch, expected_revision=expected)
    else:
        ops.patch(target, args.ref, patch, expected_revision=expected)
    print(f"updated {args.ref}")
    return 0


def cmd_push(args) -> int:
    expected = _expected_revision(args)
    ops.push(_plan_dir(args), args.ref, args.field, _json_value(args.json, args.file), expected_revision=expected)
    print(f"pushed to {args.ref}.{args.field}")
    return 0


def cmd_add_phase(args) -> int:
    print(ops.add_phase(_plan_dir(args), args.title, data=_json_value(args.json, args.file, required=False)))
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


def _external_issues(plan, args) -> list:
    """External checks for check or the fresh snapshot locked by readiness record."""
    document = plan.plan if isinstance(plan.plan, dict) else {}
    if getattr(args, "no_external", False) or not integration.available() or not isinstance(document.get("id"), str):
        return []
    config = settings.for_plan(plan)
    if not config.get("checks.external"):
        return []
    from ..integration import plugins
    project = settings.project_root_of(plan.root.parent)
    plan_input = plugins.build_input(plan_id=document["id"], short_id=str(document.get("short_id") or ""),
                                     plan_dir=plan.root, plans_root=plan.root.parent, project_root=project)
    failure = "error" if config.get("checks.external_failure") == "error" else "warning"
    return [check.Issue(*finding) for finding in plugins.run_checks(plan_input, project=project, failure=failure)]


def cmd_readiness(args) -> int:
    if args.action == "status":
        result = readiness.status(store.load_plan(_plan_dir(args)), args.phase)
        if args.json:
            return _read_result(result, "read-readiness")
        for row in result["phases"]:
            print(f"{row['id']}: {row['status']}" + (f" ({', '.join(row['changed'])})" if row["changed"] else ""))
    else:
        findings = []
        for value in args.finding:
            try:
                findings.append(json.loads(value))
            except ValueError as exc:
                raise UsageError(f"--finding must be a JSON object: {exc}") from None
        readiness.record(_plan_dir(args), args.phase, verdict=args.verdict, audit=args.audit, actor=args.actor,
                         findings=findings, external=lambda p: _external_issues(p, args))
        print(f"{args.phase}: {args.verdict}")
    return 0


def cmd_check(args) -> int:
    plan = store.load_plan(_plan_dir(args))
    issues = [*check.check(plan), *_external_issues(plan, args)]
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
    if args.parallel is not None:
        ready = parallel.ready_set(store.load_plan(_plan_dir(args)), args.parallel)
        store.check_doc(ready.as_dict(), "read-ready", "next --parallel result")
        if args.json:
            _print_json(ready.as_dict())
        else:
            print(ready.render())
        return 0
    action = lifecycle.next(store.load_plan(_plan_dir(args)))
    if args.json:
        _print_json(action.as_dict())
        return 0
    route = action.route
    print(action.exact + (f"  ({route['class']}/{route['effort']})" if route else ""))
    if action.batch_line:
        print(action.batch_line)
        print(_overlays_line("planner:plan-run"))
    return 0


def _overlays_line(slot: str) -> str:
    """``overlays: …`` for the slot a command reads first, so that step 0 of ``plan-run`` cannot be skipped."""
    from ..integration import overlays
    try:
        found = overlays.resolve(slot, project=overlays.project_root())
    except (LookupError, ValueError, OSError) as exc:
        return f"overlays {slot}: unavailable ({exc}); run plan.py overlays {slot}"
    listed = found.get("overlays") or []
    return f"overlays {slot}: " + (", ".join(str(o.get("path", o)) if isinstance(o, dict) else str(o) for o in listed)
                                   if listed else "none")


def cmd_start(args) -> int:
    actor = dict(args.actor)
    session = _session(args.session)
    if session:
        actor["session"] = session
    plan_dir = _plan_dir(args)
    result = lifecycle.start(plan_dir, args.items, actor, grants=args.grant, scout=args.scout, registrar=args.registrar,
                             take_over=args.take_over, in_progress_deps=args.in_progress_deps,
                             strict_route=args.strict_route, continue_kind=args.continue_kind, receipt=args.receipt,
                             findings=tuple(k for k in (args.findings or "").split(",") if k))
    if args.json:
        _print_json({"items": list(result.items), "phase": result.phase, "batch": result.batch, "route": result.route,
                     "resumed": list(result.resumed), "packs": [str(path) for path in result.packs],
                     "scouts": list(result.scouts), "warnings": list(result.warnings)})
    else:
        print(result.text(plan_dir.name))
    return 0


def _repos(args) -> dict[str, str]:
    return dict(args.repo)


def cmd_context(args) -> int:
    plan = store.load_plan(_plan_dir(args))
    if args.budget:
        if args.stdout:
            raise UsageError("--budget reports sizes and writes no pack; drop --stdout")
        report = budget.measure(plan, args.item, repos=_repos(args))
        if args.json or args.output == "json":
            _print_json(report)
        else:
            print(budget.text(report))
    elif args.stdout:
        print(context.render(plan, args.item, repos=_repos(args)), end="")
    else:
        print(lifecycle.shown_path(context.build(plan, args.item, repos=_repos(args))))
    return 0


def cmd_config(args) -> int:
    if args.plan:
        config = settings.for_plan(store.load_plan(_plan_dir(args)))
    else:
        config = settings.for_root(args.plans_root or store.find_plans_root())
    if args.action == "explain":
        if args.json:
            _print_json(config.explain_json(args.key))
        else:
            print(config.explain_text(args.key))
        return 0
    if args.key:
        raise UsageError("config show takes no key; use config explain KEY")
    if args.json:
        _print_json({"aicore": config.aicore, "layers": list(config.layers), "values": dict(config.values)})
        return 0
    for key, value in config.values.items():
        print(f"{key} = {json.dumps(value, ensure_ascii=False)}  ({config.sources.get(key, 'defaults')})")
    if config.aicore["aicore"] == "available":
        print(f"aicore: available {config.aicore['root']}")
    else:
        print("aicore: unavailable — machine and project layers are not read")
    return 0


def cmd_overlays(args) -> int:
    from ..integration import overlays
    try:
        project = overlays.project_root(project=args.project)
    except LookupError as exc:  # PROJECT_CONTEXT_CONFLICT / PROJECT_CONTEXT_REQUIRED of aicore.state
        code, _, message = str(exc).partition(": ")
        raise PlanError(getattr(exc, "code", code), message or str(exc)) from None
    found = overlays.resolve(args.slot, project=project)
    if args.json:
        _print_json({"slot": found["slot"], "overlays": found["overlays"], "warnings": found["warnings"],
                     "aicore": found["aicore"]})
    else:
        sys.stdout.write(found["text"])
        for warning in found["warnings"]:
            if isinstance(warning, dict):
                print(f"plan.py overlays: {warning['code']}: {warning['message']}", file=sys.stderr)
    return 1 if args.strict and any(isinstance(w, dict) for w in found["warnings"]) else 0


def cmd_finish(args) -> int:
    result = lifecycle.finish(
        _plan_dir(args), args.item, args.status, notes=args.notes or "", checks=dict(args.check),
        deviations=args.deviation, pending=args.pending, escalation=args.escalation, commits=args.commit,
        decision=args.decision, actor=args.actor, executed_by=args.executed_by, attempt_id=args.attempt_id,
        evidence=_evidence_map(args.evidence), owner_session=args.owner_session, review_receipt=args.review_receipt)
    if args.json:
        _print_json({"item": result.item, "status": result.status, "phase_closed": result.phase_closed,
                     "plan_done": result.plan_done, "next": result.next.as_dict(),
                     **({"already_registered": True} if result.already_registered else {})})
    else:
        print(result.text())
    return 0


def cmd_unit(args) -> int:
    plan_dir = _plan_dir(args)
    if args.target == "next":
        _print_json(units.ready(store.load_plan(plan_dir), args.item))
        return 0
    if args.action == "context":
        print(units.brief_text(store.load_plan(plan_dir), args.item, args.target), end="")
        return 0
    if args.target == "add":
        if args.action:
            raise UsageError("unit … add takes no further verb")
        if not args.title:
            raise UsageError("add needs --title")
        unit_id = units.add_unit(plan_dir, args.item, args.title, _json_value(args.json, args.file, required=False))
        print(f"{args.item}/{unit_id} added")
        return 0
    if not re.fullmatch(r"U[0-9]+", args.target) or args.action not in _UNIT_VERBS:
        raise UsageError(f"expected: unit <plan> <item> add | <U#> {'|'.join(_UNIT_VERBS)}")
    ref = f"{args.item}/{args.target}"
    if args.action == "dispatch":
        if not args.agent:
            raise UsageError("dispatch needs --agent PROVIDER/MODEL[/EFFORT]")
        print(f"{ref} dispatched; brief: {lifecycle.shown_path(units.dispatch(plan_dir, args.item, args.target, args.agent, actor=args.actor))}")
        return 0
    if args.action in ("rework", "reject") and args.notes is None:
        raise UsageError(f"{args.action} needs --notes")
    if args.executed_by and args.action != "return":
        raise UsageError("--executed-by belongs to unit … return")
    if args.attempt_id and args.action not in ("return", "accept"):
        raise UsageError("--attempt-id belongs to unit … return|accept")
    if args.evidence and args.action != "accept":
        raise UsageError("--evidence belongs to unit … accept")
    notes = args.notes or ""
    already = False
    if args.action == "return":
        already = units.return_unit(plan_dir, args.item, args.target, notes=notes, changed=args.changed,
                                    minutes=args.minutes, actor=args.actor, executed_by=args.executed_by,
                                    attempt_id=args.attempt_id)
    elif args.action == "accept":
        already = units.accept(plan_dir, args.item, args.target, notes=notes, minutes=args.minutes, actor=args.actor,
                               attempt_id=args.attempt_id, evidence=_evidence_map(args.evidence))
    elif args.action == "rework":
        units.rework(plan_dir, args.item, args.target, notes=notes, actor=args.actor)
    else:
        units.reject(plan_dir, args.item, args.target, notes=notes, actor=args.actor)
    print(f"{ref} already registered (attempt {args.attempt_id})" if already else f"{ref} {args.action}")
    return 0


def cmd_stats(args) -> int:
    collected = stats.collect(store.load_plan(_plan_dir(args)))
    if args.json:
        _print_json(collected)
    else:
        print(stats.text(collected))
    return 0


def cmd_log(args) -> int:
    data = _json_value(args.data, None, required=False)
    if data is not None and not isinstance(data, dict):
        raise UsageError("--data must be a JSON object")
    lifecycle.log(_plan_dir(args), args.target, args.type, args.summary, impact=args.impact, next=args.next,
                  refs=args.ref, actor=args.actor, data=data)
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
    report = lifecycle.design_done(_plan_dir(args), args.phase, actor=args.actor)
    if args.json or args.output == "json":
        _print_json(report)
        return 0
    print(f"{args.phase} detailed")
    if report.get("error"):
        print(f"  report unavailable: {report['error']}")
    kb = lambda size: size // 1024
    for entry in report["items"]:
        line = f"  {entry['item']} {kb(entry['bytes'])} KB"
        if entry["over_budget"]:
            line += f" OVER budget {kb(report['budget_bytes'])} KB"
        if entry["unbound_bytes"]:
            line += f" unbound {kb(entry['unbound_bytes'])} KB"
        if entry["duplicate_bytes"]:
            line += f" duplicates {kb(entry['duplicate_bytes'])} KB"
        print(line)
    for warning in report["warnings"]:
        print(f"  warning {warning['code']} {warning['where']}")
    if report["phase_documents_unread"]:
        print("  unread phase knowledge: " + ", ".join(report["phase_documents_unread"]))
    return 0


def cmd_reopen(args) -> int:
    lifecycle.reopen(_plan_dir(args), args.item, args.reason, actor=args.actor)
    print(f"{args.item} reopened")
    return 0


def cmd_reconcile(args) -> int:
    result = lifecycle.reconcile(_plan_dir(args), actor=args.actor)
    if args.json:
        _print_json(result.as_dict())
    else:
        print(result.text())
    return 0


def cmd_archive(args) -> int:
    print(f"archived to {lifecycle.archive(_plan_dir(args), force=args.force, reason=args.reason, actor=args.actor)}")
    return 0


def cmd_export(args) -> int:
    _print_json(snapshot.export(store.load_plan(_plan_dir(args))))
    return 0


def cmd_import(args) -> int:
    plan = snapshot.import_snapshot(args.plan, _json_value(args.json, args.file), replace=args.replace)
    _print_json({"id": plan.plan["id"], "path": str(plan.root), "next": lifecycle.next(plan).as_dict()})
    return 0


def cmd_apply(args) -> int:
    ops.apply(_plan_dir(args), _json_value(args.json, args.file))
    _print_json({"updated": True})
    return 0


def cmd_link(args) -> int:
    changed = ops.link(_plan_dir(args), args.source, args.target, kind=args.kind, relation=args.relation, note=args.note)
    _print_json({"linked": True, "changed": changed, "from": args.source, "to": args.target, "kind": args.kind})
    return 0


def cmd_unlink(args) -> int:
    changed = ops.unlink(_plan_dir(args), args.source, args.target, kind=args.kind, relation=args.relation)
    _print_json({"unlinked": True, "changed": changed, "from": args.source, "to": args.target, "kind": args.kind})
    return 0


def cmd_add_artifact(args) -> int:
    changed = ops.add_artifact(_plan_dir(args), args.item, args.path, args.role, artifact_id=args.id)
    _print_json({"added": True, "changed": changed, "item": args.item, "path": args.path, "role": args.role})
    return 0


def cmd_add_document(args) -> int:
    _print_json({"id": ops.add_document(_plan_dir(args), _json_value(args.json, args.file))})
    return 0


# ---------------------------------------------------------------- parser

def cmd_commit(args) -> int:
    if args.paths_only and not args.path:
        raise PlanError("USAGE", "--paths-only needs at least one --path")
    result = gitops.commit(_plan_dir(args), args.ref, role=args.role, paths=args.path,
                           leave_outside=args.leave_outside, dry_run=args.dry_run, commit_type=args.type,
                           scope=args.scope, summary=args.summary, trailers=args.trailer, actor=args.actor,
                           paths_only=args.paths_only)
    if args.json or args.output == "json":
        _print_json(result)
    else:
        sha = result["sha"] or result.get("workspace_sha") or ("dry-run" if args.dry_run else "no-commit")
        print(f"{sha} {result['ref']} {result['role']} ({len(result['paths'])} paths)")
    workspace_commit = result.get("workspace_commit") or {}
    # JSON callers read workspace_commit from the envelope next to the source commit
    if workspace_commit.get("status") in ("failed", "locked") and not (args.json or args.output == "json"):
        print(f"workspace commit {workspace_commit['status']}: {workspace_commit.get('error', '')}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plan.py", description="Planner plan (layout v4): authoring and lifecycle verbs.")
    parser.add_argument("--output", choices=("text", "json"), default="text", help="structured success/error envelope")
    parser.add_argument("--config", type=Path, default=None, metavar="FILE",
                        help="configuration file for this run: the invocation layer of [planner] (needs aicore)")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--plans-root", type=Path, default=None,
                        help="plans/ directory (default: <project>/plans of the project launcher, else the nearest "
                             "plans/ up from cwd; in launcher mode only <project>/plans is accepted)")
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
    p.add_argument("--codename", required=True, help="CODE-NAME [A-Z][A-Z0-9-]*")
    p.add_argument("--title", required=True)
    p.add_argument("--repository")
    p.add_argument("--owner", default="repository owner")
    p.add_argument("--actor", required=True, type=_actor, help="PROVIDER/MODEL[/EFFORT]")
    message = p.add_mutually_exclusive_group()
    message.add_argument("--message", help="first owner message, verbatim")
    message.add_argument("--message-file", type=Path)
    p.add_argument("--date", help="YYYY.MM.DD (default today)")

    p = verb("config", cmd_config, "show the effective [planner] configuration or explain where a value comes from",
             plan=False)
    p.add_argument("action", nargs="?", choices=("show", "explain"), default="show")
    p.add_argument("key", nargs="?", help="with explain: one key or a table such as context")
    p.add_argument("--plan", help="plan id, PLAN<N> or path: add its plan.settings layer")
    p.add_argument("--json", action="store_true", help="machine-readable output")

    p = verb("overlays", cmd_overlays, "print the owner's overlay rules of a command slot (planner:<command>)",
             plan=False)
    p.add_argument("slot", help="planner:<command> or <command>, declared in provides.overlay_slots of unit.json")
    p.add_argument("--project", type=Path, default=None, help="project root (default: the nearest git repository)")
    p.add_argument("--json", action="store_true", help='print {"slot", "overlays", "warnings", "aicore"} instead')
    p.add_argument("--strict", action="store_true", help="exit 1 when a configured overlay file was skipped")

    p = verb("show", cmd_show, "overview of a plan, or one document as canonical JSON")
    p.add_argument("ref", nargs="?", help="plan, brief, Pn, Pn.m, D#, Pn.m/U#")
    p.add_argument("--json", action="store_true", help="machine-readable overview")

    p = verb("get", cmd_get, "read one document by reference (JSON envelope)")
    p.add_argument("ref")
    p.add_argument("--section", help="knowledge section id")
    p.add_argument("--fields", type=_csv, help="comma-separated top-level fields")
    p.add_argument("--repo", action="append", type=_repo_mapping, default=[], metavar="NAME=PATH")

    p = verb("plans", cmd_plans, "list the live plans of the project with their progress (JSON envelope)", plan=False)
    p.add_argument("--json", action="store_true", help="accepted for symmetry; output is always JSON")

    p = verb("list", cmd_list, "list document rows with filters (JSON envelope)")
    p.add_argument("kind", help="item, phase, decision, document or unit (plural names also accepted)")
    p.add_argument("--status")
    p.add_argument("--phase")
    p.add_argument("--applies-to")

    p = verb("events", cmd_events, "read journal events with filters (JSON envelope)")
    p.add_argument("--item")
    p.add_argument("--type", type=_csv, help="comma-separated event types")
    p.add_argument("--since", help="inclusive ISO timestamp with timezone")
    p.add_argument("--limit", type=int, help="latest N matching events, in journal order")

    p = verb("commits", cmd_commits, "read commits linked to a plan by Plan trailers (JSON envelope)")
    p.add_argument("ref", nargs="?", help="local Pn.m or Pn.m/U# (an item includes its units)")
    p.add_argument("--role", choices=("executor", "reviewer", "fix"))
    p.add_argument("--json", action="store_true", help="accepted for symmetry; output is always JSON")

    p = verb("followups", cmd_followups, "read the follow_up and owner_decision leftovers of closed items (JSON envelope)")
    p.add_argument("--open", action="store_true", help="only those no other item follows up (related, follows_up)")
    p.add_argument("--json", action="store_true", help="accepted for symmetry; output is always JSON")

    p = verb("artifact", cmd_artifact, "read artifact metadata and optional content (JSON envelope)")
    p.add_argument("ref")
    p.add_argument("--inline", action="store_true")
    p.add_argument("--repo", action="append", type=_repo_mapping, default=[], metavar="NAME=PATH")

    p = verb("links", cmd_links, "read typed links around a reference (JSON envelope)")
    p.add_argument("ref")
    p.add_argument("--direction", choices=("out", "in", "both"), default="both")
    p.add_argument("--kind", type=_csv, help="comma-separated edge kinds")
    p.add_argument("--depth", type=int, default=1, help="graph traversal depth (integer >= 1)")

    p = verb("neighborhood", cmd_neighborhood, "read an item's graph and applicable documents (JSON envelope)")
    p.add_argument("item")

    p = verb("schema", cmd_schema, "read a document schema or the API catalog (JSON envelope)", plan=False)
    selection = p.add_mutually_exclusive_group()
    selection.add_argument("kind", nargs="?", choices=(*schema.KINDS, "defs"), help="plan/v1 schema kind")
    selection.add_argument("--verbs", action="store_true", help="describe all verbs (default when no kind is given)")

    p = verb("bridge", cmd_bridge, "list named bridges or run a bridge verb with its own arguments", plan=False)
    p.add_argument("name", help="bridge name, or list")
    p.add_argument("verb", nargs="?", help="bridge verb from its entrypoints")
    p.add_argument("args", nargs=argparse.REMAINDER, help="arguments passed to the bridge verb unchanged")

    p = verb("set", cmd_set, "merge-patch plan, brief, a phase, item, decision or unit")
    p.add_argument("ref", help="plan | brief | Pn | Pn.m | D# | Pn.m/U#")
    value_args(p, True)
    p.add_argument("--expected-revision", metavar="REV",
                   help="refuse with PLAN_REVISION_CONFLICT unless the document still has this revision (as in get)")

    p = verb("apply", cmd_apply, "validate and apply a JSON array of {ref, patch} edits together")
    value_args(p, True)
    p = verb("export", cmd_export, "export the complete plan as a current-format JSON snapshot")
    p = verb("import", cmd_import, "import a current-format JSON snapshot into the specified directory")
    value_args(p, True)
    p.add_argument("--replace", action="store_true", help="restore an existing JSON plan")
    p = verb("add-document", cmd_add_document, "add a schema-backed knowledge document")
    value_args(p, True)

    p = verb("link", cmd_link, "add a typed link between two documents of the plan; a repeat is a no-op")
    p.add_argument("source", metavar="from", help="owning document: Pn, Pn.m, D#, Pn.m/U# or knowledge/<id>")
    p.add_argument("target", metavar="to", help="linked document in the same plan")
    p.add_argument("--kind", required=True, choices=ops.LINK_KINDS)
    p.add_argument("--relation", help="related only: informs|consumes|conflicts|follows_up|supersedes")
    p.add_argument("--note", help="related only: why linked")

    p = verb("unlink", cmd_unlink, "remove a typed link between two documents of the plan; a missing link is a no-op")
    p.add_argument("source", metavar="from")
    p.add_argument("target", metavar="to")
    p.add_argument("--kind", required=True, choices=ops.LINK_KINDS)
    p.add_argument("--relation", help="related only: the relation of the link to remove")

    p = verb("add-artifact", cmd_add_artifact, "declare an input or output artifact of an item; a repeat is a no-op")
    p.add_argument("item", metavar="item")
    p.add_argument("--path", required=True, help="repository path or @plan/ path")
    p.add_argument("--role", required=True, choices=("input", "output"))
    p.add_argument("--id", help="artifact id, addressed as artifact/<id> (an output declares it, an input cites it)")

    p = verb("push", cmd_push, "append a value to an array field (dotted paths allowed)")
    p.add_argument("ref")
    p.add_argument("field")
    value_args(p, True)
    p.add_argument("--expected-revision", metavar="REV",
                   help="refuse with PLAN_REVISION_CONFLICT unless the document still has this revision (as in get)")

    p = verb("add-phase", cmd_add_phase, "add a skeleton phase")
    p.add_argument("--title", required=True)
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
    p.add_argument("--no-external", action="store_true",
                   help="skip the plugins registered at the planner:check extension point")

    p = verb("render", cmd_render, "regenerate the Markdown views")
    p.add_argument("--check", action="store_true", help="report stale views, write nothing")

    p = verb("next", cmd_next, "semantic next step")
    p.add_argument("--json", action="store_true")
    p.add_argument("--parallel", type=int, metavar="N", help="list up to N lanes that can run side by side across the plan")

    p = verb("readiness", cmd_readiness, "record or inspect phase readiness certificates", plan=False)
    readiness_sub = p.add_subparsers(dest="action", required=True)
    for action in ("record", "status"):
        child = readiness_sub.add_parser(action, description=f"{action} phase readiness")
        child.add_argument("--plans-root", type=Path, default=argparse.SUPPRESS,
                           help="plans directory (may also precede the readiness subcommand)")
        child.add_argument("plan", help="plan id, PLAN<N> or path")
        child.add_argument("phase", nargs=None if action == "record" else "?", help="phase id Pn")
        if action == "record":
            child.add_argument("--verdict", choices=readiness.VERDICTS, required=True)
            child.add_argument("--audit", required=True, help="existing knowledge/<id> audit document")
            child.add_argument("--actor", required=True, type=_actor, help="observed PROVIDER/MODEL[/EFFORT]")
            child.add_argument("--finding", action="append", default=[], help="JSON {id,severity,blocking,ref,text}")
        else:
            child.add_argument("--json", action="store_true", help="validated machine-readable readiness status")

    def actor_arg(p, required=False, text="PROVIDER/MODEL[/EFFORT] (default: the item executor, else plan authoring)"):
        p.add_argument("--actor", type=_actor, required=required, help=text)

    p = verb("commit", cmd_commit, "create one scoped Git commit for an item or unit operation")
    p.add_argument("ref", help="local Pn.m or Pn.m/U#")
    p.add_argument("--role", required=True, choices=("executor", "reviewer", "fix"))
    p.add_argument("--type", help="Conventional Commit type (default: feat, docs or fix by role)")
    p.add_argument("--scope", help="commit scope (default: settings.commit.scope or plan codename)")
    p.add_argument("--summary", help="commit subject (default: item or unit title)")
    p.add_argument("--trailer", action="append", default=[], metavar="KEY: VALUE")
    p.add_argument("--path", action="append", default=[], metavar="PATH", help="explicit extra ownership path")
    p.add_argument("--leave-outside", action="store_true", help="leave foreign dirty paths untouched")
    p.add_argument("--paths-only", action="store_true",
                   help="commit exactly the --path files (each covered by the task_files of the item): no other task "
                        "files, no plan files, no workspace commit")
    p.add_argument("--dry-run", action="store_true", help="show selection and message without writing")
    actor_arg(p)
    p.add_argument("--json", action="store_true")

    p = verb("start", cmd_start, "start (or resume) items of one detailed phase")
    p.add_argument("items", nargs="+", metavar="item")
    actor_arg(p, required=True, text="PROVIDER/MODEL[/EFFORT] running the items")
    p.add_argument("--registrar", type=_actor, metavar="PROVIDER/MODEL[/EFFORT]",
                   help="who registers the start when it is not the executor (event registered_by)")
    p.add_argument("--session", help="provider session id, or auto")
    p.add_argument("--grant", action="append", default=[], metavar="GATE", help="record an owner gate grant now")
    p.add_argument("--scout", action=argparse.BooleanOptionalAction, default=None,
                   help="ask the provider's weak model for a context map (default: plan.settings.scout)")
    p.add_argument("--take-over", action="store_true",
                   help="take an item that another session has in progress (default: refused with ITEM_OWNED)")
    p.add_argument("--strict-route", action="store_true", help="refuse a model absent from the routing pool")
    p.add_argument("--continue", dest="continue_kind", choices=["correction"],
                   help="continue the in-progress item to correct recorded review findings; the actor is checked "
                        "against route.correction (else route); needs --receipt; it does not replace --take-over")
    p.add_argument("--receipt", metavar="PATH", help="review-receipt/v1 whose findings --continue correction answers")
    p.add_argument("--findings", metavar="KEYS", help="with --continue: comma-separated finding keys fk-… "
                                                      "(default: every confirmed or open finding of the receipt)")
    p.add_argument("--in-progress-deps", action="store_true",
                   help="a dependency that is in progress counts as met: the items of one batch started one after another "
                        "(default: only done items and the items of this call count)")
    p.add_argument("--json", action="store_true")

    p = verb("context", cmd_context, "return complete JSON context (context/<item>.json)")
    p.add_argument("item")
    p.add_argument("--stdout", action="store_true", help="print the pack instead of writing it")
    p.add_argument("--budget", action="store_true", help="report the pack size by key and source; writes nothing")
    p.add_argument("--json", action="store_true", help="with --budget: print the report as JSON")
    p.add_argument("--repo", action="append", default=[], type=_repo_mapping, metavar="NAME=PATH",
                   help="repository root of references to another repository (repeatable)")

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
    actor_arg(p, text="PROVIDER/MODEL[/EFFORT] registering the outcome (default: the item executor)")
    p.add_argument("--executed-by", type=_actor, metavar="PROVIDER/MODEL[/EFFORT]",
                   help="who executed the item; route-checked, replaces result.executor")
    p.add_argument("--attempt-id", metavar="ID", help="registration attempt; a repeat of it is a no-op")
    p.add_argument("--owner-session", metavar="SESSION",
                   help="refuse with ITEM_OWNED unless the item's executor session is SESSION (fencing)")
    p.add_argument("--review-receipt", metavar="PATH", help="review-receipt/v1 file bound to the reviewed candidate")
    p.add_argument("--evidence", action="append", default=[], type=_evidence, metavar="V1=PATH",
                   help="check-evidence file (planner field contract; see `plan.py schema check-evidence`) whose "
                        "exit is the check result (repeatable)")
    p.add_argument("--json", action="store_true")

    p = verb("unit", cmd_unit, "split an item into units and move them: add | <U#> dispatch|return|accept|rework|reject")
    p.add_argument("item")
    p.add_argument("target", metavar="add|next|U#")
    p.add_argument("action", nargs="?", metavar="context|dispatch|return|accept|rework|reject")
    p.add_argument("--title", help="add: unit title")
    value_args(p, False)
    p.add_argument("--agent", metavar="PROVIDER/MODEL[/EFFORT]", help="dispatch: the worker")
    p.add_argument("--notes")
    p.add_argument("--changed", action="append", default=[], metavar="PATH", help="return: a changed path (repeatable)")
    p.add_argument("--minutes", type=int)
    p.add_argument("--executed-by", type=_actor, metavar="PROVIDER/MODEL[/EFFORT]",
                   help="return: who did the work when not the dispatched worker; route-checked")
    p.add_argument("--attempt-id", metavar="ID", help="return|accept: registration attempt; a repeat is a no-op")
    p.add_argument("--evidence", action="append", default=[], type=_evidence, metavar="V1=PATH",
                   help="accept: check-evidence file of the unit (planner field contract; see "
                        "`plan.py schema check-evidence`; repeatable)")
    actor_arg(p)

    p = verb("stats", cmd_stats, "scout, unit and friction numbers of a plan (read-only)")
    p.add_argument("--json", action="store_true")

    p = verb("log", cmd_log, "record friction for an item or phase")
    p.add_argument("target", help="Pn.m or Pn")
    p.add_argument("--type", required=True, choices=lifecycle.FRICTION_TYPES)
    p.add_argument("--summary", required=True)
    p.add_argument("--impact")
    p.add_argument("--next")
    p.add_argument("--ref", action="append", default=[], metavar="REF")
    p.add_argument("--data", metavar="JSON", help="a JSON object (inline or @file) kept in the event's data")
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

    p = verb("design-done", cmd_design_done, "mark a phase detailed after check; prints the context report")
    p.add_argument("phase")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    actor_arg(p)

    p = verb("reopen", cmd_reopen, "reopen a finished item (owner amendment)")
    p.add_argument("item")
    p.add_argument("--reason", required=True)
    actor_arg(p)

    p = verb("reconcile", cmd_reconcile, "close phases whose items are all terminal, then the plan (integrator)")
    actor_arg(p, text="PROVIDER/MODEL[/EFFORT] (default: plan authoring)")
    p.add_argument("--json", action="store_true")

    p = verb("archive", cmd_archive, "move a done plan to plans/archive/")
    p.add_argument("--force", action="store_true", help="archive a plan that is not done (needs --reason)")
    p.add_argument("--reason")
    actor_arg(p)
    return parser


def _emit(envelope: dict) -> None:
    """Print the ``--output json`` envelope; one that leaves ``schemas/plan/v1/envelope.schema.json`` is a bug."""
    issues = schema.validate(envelope, "envelope")
    if issues:
        raise RuntimeError("ENVELOPE_INVALID: " + "; ".join(f"{i.path or '/'}: {i.message}" for i in issues[:3]))
    _print_json(envelope)


def _failure(code: str, message: str, issues=()) -> dict:
    error = {"code": code, "message": message}
    listed = [i._asdict() if hasattr(i, "_asdict") else i for i in issues if hasattr(i, "_asdict") or isinstance(i, dict)]
    return {"ok": False, "error": {**error, **({"issues": listed} if listed else {})}}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    # Know the output contract even if parsing fails (missing args, bad CSV, etc.).
    tail = argv
    output = "text"
    while tail:  # leading global options, in any order
        if tail[0] in ("--output", "--config") and len(tail) >= 2:
            output, tail = (tail[1] if tail[0] == "--output" else output), tail[2:]
        elif tail[0].startswith(("--output=", "--config=")):
            output, tail = (tail[0].split("=", 1)[1] if tail[0].startswith("--output=") else output), tail[1:]
        else:
            break
    parse_as_json = output == "json" or bool(tail and tail[0] in _READ_VERBS)
    errors = io.StringIO()
    try:
        if parse_as_json:
            with redirect_stderr(errors):
                args = parser.parse_args(argv)
        else:
            args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse: 0 for --help, 2 for usage
        if exc.code and parse_as_json:
            _emit(_failure("USAGE", errors.getvalue().strip()))
        return int(exc.code or 0)
    as_json = args.output == "json" or args.command in _READ_VERBS
    # A bridge verb owns its output and exit code; only dispatcher refusals use the envelope.
    passthrough = args.command == "bridge" and args.name != "list"
    try:
        if args.config is not None:
            integration.require("--config")
        if getattr(args, "plans_root", None) is not None:
            store.require_project_plans(args.plans_root)
        settings.set_invocation(args.config)
        if as_json and not passthrough:
            output = io.StringIO()
            with redirect_stdout(output):
                code = args.handler(args)
            raw = output.getvalue().strip()
            try:
                data = json.loads(raw)
            except ValueError:
                data = {"message": raw}
            if code == 0:
                _emit({"ok": True, "data": data})
            else:  # a verb that reports its refusal on stdout (check --json); keep its issues
                issues = data.get("issues") if isinstance(data, dict) else None
                _emit(_failure("VERB_FAILED", f"{args.command} exited {code}", issues if isinstance(issues, list) else ()))
            return code
        return args.handler(args)
    except UsageError as exc:
        if as_json:
            _emit(_failure("USAGE", str(exc)))
        else:
            print(f"plan.py {args.command}: error: {exc}", file=sys.stderr)
        return 2
    except PlanError as exc:
        if as_json:
            _emit(_failure(exc.code, exc.message, exc.issues))
        else:
            print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1
    except OSError as exc:
        if as_json:
            _emit(_failure("IO_ERROR", str(exc)))
        else:
            print(f"IO_ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
