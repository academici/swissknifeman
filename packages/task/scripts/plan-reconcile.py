#!/usr/bin/env python3
"""Converge terminal plan projections and emit the verified delivery receipt."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PACKAGE / "lib"))

from task import plan_reconcile  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", required=True, type=Path)
    parser.add_argument("--item", required=True)
    args = parser.parse_args(argv)
    try:
        value = plan_reconcile.reconcile_terminal(args.plan_dir, args.item)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
