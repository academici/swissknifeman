#!/usr/bin/env python3
"""CLI for downstream-gate v1."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "lib"))

from task.plan_downstream import DownstreamError, dumps, evaluate, record  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Drive away Validation consumers of the producer point")
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--item", required=True, help="item-producer Pn.m")
    parser.add_argument("--producer-commit", default="HEAD")
    parser.add_argument("--record", action="store_true", help="write item-scoped findings")
    parser.add_argument("--json", action="store_true", help="print machine result")
    args = parser.parse_args(argv)
    try:
        result = evaluate(args.plan_dir, args.item, producer_commit=args.producer_commit)
        if args.record:
            result["records"] = [str(path) for path in record(args.plan_dir, result)]
    except (DownstreamError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(dumps(result), end="")
    else:
        print(f"{result['outcome'].upper()}: {args.item}; consumers={len(result['consumers'])}")
    return 1 if result["blocks"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
