"""Command line: validate exec/v1 documents, read the launch catalog, create ad-hoc input and render prompts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from orch import adhoc, launch, render
from orch.contracts import validate
from orch.schema import SchemaProfileError


def _launch(args: argparse.Namespace) -> int:
    try:
        catalog = launch.load_catalog()
        if args.action == "list":
            rows = [{"role": role, "provider": provider, **{k: v for k, v in item.items() if k != "argv"}}
                    for role, providers in catalog["launch"].items() for provider, item in providers.items()]
            print(json.dumps(rows, ensure_ascii=False))
        elif args.action == "show":
            print(json.dumps(launch.entry(catalog, args.role, args.provider), ensure_ascii=False))
        else:
            found = launch.entry(catalog, args.role, args.provider)
            result = {"argv": launch.build_argv(catalog, args.role, args.provider, model=args.model,
                                                effort=args.effort, cwd=args.cwd),
                      "transport": found["transport"], "timeout_s": found["timeout_s"]}
            print(json.dumps(result, ensure_ascii=False))
    except launch.LaunchError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    return 0


def _input_adhoc(args: argparse.Namespace) -> int:
    route = {key: value for key, value in (("class", args.model_class), ("effort", args.effort)) if value}
    try:
        doc = adhoc.build_adhoc_input(args.goal, args.include or [], args.exclude or [], args.check or [],
                                      args.procedure or [], args.read or [], route=route, review=args.review,
                                      why=args.why, expect=args.expect)
    except adhoc.AdhocError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2 if error.code == "USAGE" else 1
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return 0


def _render_prompt(args: argparse.Namespace) -> int:
    try:
        doc = json.loads(args.input.read_text(encoding="utf-8"))
        issues = [issue for issue in validate(doc, "execution-input") if issue.level == "error"]
        if issues:
            for issue in issues:
                print(f"{issue.code}: {issue.path or '/'} {issue.message}", file=sys.stderr)
            return 1
        manifest, text = render.load_role(args.role, args.roles_dir)
        sys.stdout.write(render.render_prompt(doc, manifest, text))
    except (OSError, ValueError) as error:
        print(f"INPUT_INVALID: {error}", file=sys.stderr)
        return 1
    except render.RenderError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orch.py")
    verbs = parser.add_subparsers(dest="verb", required=True)
    command = verbs.add_parser("validate", help="validate an exec/v1 JSON document")
    command.add_argument("kind")
    command.add_argument("file", type=Path)
    command.add_argument("--quiet", action="store_true", help="suppress JSON output")
    command = verbs.add_parser("launch", help="read the launch catalog (role x provider)")
    actions = command.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="every entry without its argv")
    show = actions.add_parser("show", help="one entry as JSON")
    build = actions.add_parser("argv", help="command line of one entry; the process is not started")
    for sub in (show, build):
        sub.add_argument("role")
        sub.add_argument("provider")
    build.add_argument("--model", help="required when the entry's model_set is supported")
    build.add_argument("--effort")
    build.add_argument("--cwd", default=".")
    command = verbs.add_parser("input", help="create an execution-input without a plan")
    command = command.add_subparsers(dest="kind", required=True).add_parser(
        "adhoc", help="ad-hoc input, or a read-only review with --review BASE..HEAD")
    command.add_argument("--goal")
    command.add_argument("--why")
    command.add_argument("--include", nargs="+", action="extend")
    command.add_argument("--exclude", nargs="+", action="extend")
    command.add_argument("--check", action="append", metavar="V1=CMD", help="command check, expects exit 0")
    command.add_argument("--procedure", action="append", metavar="V2=TEXT", help="manual check, expects observed")
    command.add_argument("--expect", help="expected outcome of every --check (default: exit 0)")
    command.add_argument("--read", nargs="+", action="extend", metavar="PATH")
    command.add_argument("--class", dest="model_class", choices=("economy", "implementation", "frontier"))
    command.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max", "ultra"))
    command.add_argument("--review", metavar="BASE..HEAD")
    command = verbs.add_parser("render-prompt", help="role prompt for a Claude-only run (Markdown)")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--role", required=True)
    command.add_argument("--roles-dir", type=Path)
    args = parser.parse_args(argv)
    if args.verb == "launch":
        return _launch(args)
    if args.verb == "input":
        return _input_adhoc(args)
    if args.verb == "render-prompt":
        return _render_prompt(args)
    try:
        doc = json.loads(args.file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"INPUT_INVALID: {exc}", file=sys.stderr)
        return 1
    try:
        issues = validate(doc, args.kind)
    except SchemaProfileError as exc:
        print(f"SCHEMA_PROFILE: {exc}", file=sys.stderr)
        return 1
    for issue in issues:
        print(f"{issue.code}: {issue.message}", file=sys.stderr)
    if not args.quiet:
        result = [issue._asdict() for issue in issues]
        print(json.dumps(result if issues else {"valid": True}, ensure_ascii=False))
    return 1 if any(issue.level == "error" for issue in issues) else 0
