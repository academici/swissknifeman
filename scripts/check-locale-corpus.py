#!/usr/bin/env python3
"""Check, inventory, plan, apply, or roll back the locale corpus ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.locale.corpus import CorpusError, apply_row, check_ledger, inventory, load_ledger, review_markdown, rollback_row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=Path("configs/locale-corpus-v1.json"))
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--apply")
    parser.add_argument("--rollback")
    parser.add_argument("--batch")
    parser.add_argument("--checkpoint-dir", type=Path, default=Path(".locale-corpus-checkpoints"))
    parser.add_argument("--review-output", type=Path)
    args = parser.parse_args()
    root = Path.cwd()
    try:
        ledger = load_ledger(args.ledger)
        report = check_ledger(ledger, root=root)
        if args.batch:
            print(json.dumps({"batch": args.batch, "disposition": "planned", "rows": []}, sort_keys=True))
        if args.inventory:
            print(json.dumps({"inventory": inventory(ledger, root=root)}, sort_keys=True))
        if args.plan:
            print(json.dumps({"plan": [{"id": row.get("id"), "status": row.get("status")} for row in report.rows]}, sort_keys=True))
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
