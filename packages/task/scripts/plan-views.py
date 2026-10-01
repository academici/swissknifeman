#!/usr/bin/env python3
"""Unified launcher for deterministic executable-plan projections."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PKG_ROOT / "lib"))

from task import plan_bundle, plan_closure, plan_decisions, plan_history, plan_item_state, plan_returns, plan_status  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect or check executable plan views")
    parser.add_argument("view", choices=("bundle", "closure", "decisions", "history", "returns", "status", "state"), help="view to generate")
    parser.add_argument("--plan-dir", required=True, type=Path, help="plan directory")
    parser.add_argument("--check", action="store_true", help="just check freshness")
    parser.add_argument("--all", action="store_true", help="all item (state or bundle)")
    parser.add_argument("--item", help="one item Pn.m (state, history or bundle)")
    parser.add_argument("--stdout", action="store_true", help="print bundle instead of the entry")
    parser.add_argument("--phase", help="single phase Pn (closure)")
    parser.add_argument("--output", type=Path, help="explicitly materialize history view along this path")
    parser.add_argument("--json", action="store_true", help="print deterministic JSON (returns)")
    parser.add_argument("--fingerprint", action="store_true", help="show fingerprints (returns)")
    parser.add_argument("--gate", action="store_true", help="apply return-loop v1 (returns)")
    args = parser.parse_args(argv)
    try:
        if args.view == "bundle":
            if args.all == bool(args.item) or args.phase or args.output or (args.stdout and args.all):
                raise ValueError("bundle requires exactly one of --all / --item; --stdout only with --item")
            if args.stdout:
                if args.check:
                    raise ValueError("bundle --stdout does not accept --check")
                print(plan_bundle.render(args.plan_dir, args.item), end="")
                return 0
            outputs = (plan_bundle.build_all(args.plan_dir, check=args.check) if args.all
                       else (plan_bundle.build(args.plan_dir, args.item, check=args.check),))
        elif args.view == "closure":
            if not args.phase or args.item or args.all or args.output or args.stdout:
                raise ValueError("closure only requires --phase")
            outputs = (plan_closure.build_closure(args.plan_dir, args.phase, check=args.check),)
        elif args.view == "decisions":
            outputs = plan_decisions.build_views(args.plan_dir, check=args.check)
        elif args.view == "history":
            if not args.item or args.all or args.stdout:
                raise ValueError("history requires --item and does not accept --all")
            if args.check and not args.output:
                raise ValueError("history --check requires explicit --output")
            if args.output:
                outputs = (plan_history.materialize_history(
                    args.plan_dir, args.item, args.output, check=args.check),)
            else:
                print(plan_history.render_history(args.plan_dir, args.item), end="")
                return 0
        elif args.view == "returns":
            if args.all or args.item or args.phase or args.output or args.check or args.stdout:
                raise ValueError("returns only accepts --plan-dir, --json, --fingerprint and --gate")
            result = plan_returns.returns(args.plan_dir)
            if args.gate:
                result["gates"] = plan_returns.return_loop_gates(args.plan_dir)
            if not args.fingerprint:
                result = {key: value for key, value in result.items()
                          if key not in ("fingerprints", "history")}
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 0
        elif args.view == "status":
            outputs = (plan_status.build_status(args.plan_dir, check=args.check),)
        else:
            if args.all == bool(args.item) or args.stdout:
                raise ValueError("state requires exactly one of --all / --item")
            outputs = plan_item_state.build_states(args.plan_dir, item_id=args.item, check=args.check)
    except (plan_bundle.BundleError, plan_closure.ClosureError, plan_decisions.DecisionError, plan_history.HistoryError, plan_returns.ReturnError,
            plan_item_state.ItemStateError, plan_status.StatusError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    action = "checked" if args.check else "collected"
    print(f"views: {action} ({len(outputs)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
