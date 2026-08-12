#!/usr/bin/env python3
"""Build or verify Task terminal/handoff delivery receipts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent
_MONOREPO_ROOT = _PKG_ROOT.parent.parent
sys.path.insert(0, str(_PKG_ROOT / "lib"))
if (_MONOREPO_ROOT / "core").is_dir():
    sys.path.insert(0, str(_MONOREPO_ROOT))

from task import plan_delivery  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan-dir", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--kind", choices=("terminal", "handoff"), default="terminal")
    parser.add_argument("--output")
    parser.add_argument("--verify")
    args = parser.parse_args(argv)
    if args.output and args.verify:
        parser.error("--output и --verify взаимоисключаются")
    try:
        if args.verify:
            receipt = json.loads(Path(args.verify).read_text(encoding="utf-8"))
            plan_delivery.verify_receipt(args.plan_dir, receipt)
            print("plan-delivery: receipt OK")
            return 0
        receipt = (plan_delivery.build_terminal_receipt(args.plan_dir, args.subject)
                   if args.kind == "terminal"
                   else plan_delivery.build_handoff_receipt(args.plan_dir, args.subject))
        if args.output:
            plan_delivery.write_receipt(args.output, receipt)
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, plan_delivery.DeliveryError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
