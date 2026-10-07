"""Command line: validate exec/v1 documents and read the launch catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from orch import launch
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
    args = parser.parse_args(argv)
    if args.verb == "launch":
        return _launch(args)
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
