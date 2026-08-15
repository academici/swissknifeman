#!/usr/bin/env python3
"""Check, inventory, plan, apply, or roll back the locale corpus ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.locale.corpus import CorpusError, apply_row, check_ledger, inventory, load_ledger, review_markdown, rollback_row, verify_batch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=Path("configs/locale-corpus-v1.json"))
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--class", dest="classes", action="append", default=[])
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--apply")
    parser.add_argument("--rollback")
    parser.add_argument("--batch")
    parser.add_argument("--verify-checkpoint", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--require-terminal", action="store_true")
    parser.add_argument("--checkpoint-dir", type=Path, default=Path(".locale-corpus-checkpoints"))
    parser.add_argument("--review-output", type=Path)
    args = parser.parse_args()
    root = Path.cwd()
    try:
        ledger = load_ledger(args.ledger)
        report = check_ledger(ledger, root=root)
        class_map = {
            "skill": {"semantic.skill"}, "command": {"semantic.command"},
            "plugin": {"plugin.human-metadata"}, "diagnostic": {"diagnostic.message"},
            "code-prose": {"code.comments", "code.docstrings"}, "development-doc": {"development.docs"},
        }
        requested = set().union(*(class_map.get(name, set()) for name in args.classes)) if args.classes else set()
        if args.classes and (not requested or any(name not in class_map for name in args.classes)):
            raise CorpusError("LOCALE_CORPUS_CLASS_UNKNOWN")
        if args.require_terminal and any(row.get("status") not in {"applied", "rolled-back"} for row in report.rows):
            raise CorpusError("LOCALE_CORPUS_TERMINAL_REQUIRED")
        if args.verify_checkpoint:
            try:
                checkpoint = json.loads(args.verify_checkpoint.read_text(encoding="utf-8"))
                json.loads(args.review.read_text(encoding="utf-8")) if args.review else None
            except (OSError, json.JSONDecodeError) as error:
                raise CorpusError("LOCALE_BATCH_CHECKPOINT_INVALID") from error
            errors = verify_batch(checkpoint, ledger)
            if errors:
                raise CorpusError(errors[0])
        if args.batch:
            print(json.dumps({"batch": args.batch, "disposition": "planned", "rows": []}, sort_keys=True))
        if args.inventory:
            print(json.dumps({"inventory": inventory(ledger, root=root)}, sort_keys=True))
        if args.plan:
            print(json.dumps({"plan": [{"id": row.get("id"), "status": row.get("status")} for row in report.rows if not requested or row.get("carrier_id") in requested]}, sort_keys=True))
        if args.review_output:
            args.review_output.parent.mkdir(parents=True, exist_ok=True)
            args.review_output.write_text(review_markdown(ledger), encoding="utf-8")
        if args.apply:
            print(json.dumps({"backup": str(apply_row(ledger, args.apply, root=root, checkpoint_dir=args.checkpoint_dir))}, sort_keys=True))
        if args.rollback:
            rollback_row(ledger, args.rollback, root=root, checkpoint_dir=args.checkpoint_dir)
            print(json.dumps({"rolled_back": args.rollback}, sort_keys=True))
    except CorpusError as error:
        print(str(error), file=sys.stderr)
        return 1
    if report.errors:
        print(json.dumps({"errors": report.errors}, sort_keys=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
