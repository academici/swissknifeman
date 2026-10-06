"""Command-line validation of exec/v1 documents."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from orch.contracts import validate
from orch.schema import SchemaProfileError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orch.py")
    verbs = parser.add_subparsers(dest="verb", required=True)
    command = verbs.add_parser("validate", help="validate an exec/v1 JSON document")
    command.add_argument("kind")
    command.add_argument("file", type=Path)
    command.add_argument("--quiet", action="store_true", help="suppress JSON output")
    args = parser.parse_args(argv)
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
