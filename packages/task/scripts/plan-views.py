#!/usr/bin/env python3
"""Unified launcher for deterministic executable-plan projections."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PKG_ROOT / "lib"))

from task import plan_decisions  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Собрать или проверить виды исполняемого плана")
    parser.add_argument("view", choices=("decisions",), help="вид для генерации")
    parser.add_argument("--plan-dir", required=True, type=Path, help="каталог плана")
    parser.add_argument("--check", action="store_true", help="только проверить свежесть")
    args = parser.parse_args(argv)
    try:
        outputs = plan_decisions.build_views(args.plan_dir, check=args.check)
    except (plan_decisions.DecisionError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    action = "проверены" if args.check else "собраны"
    print(f"views: {action} ({len(outputs)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
