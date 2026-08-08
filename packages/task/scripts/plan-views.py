#!/usr/bin/env python3
"""Unified launcher for deterministic executable-plan projections."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PKG_ROOT / "lib"))

from task import plan_bundle, plan_closure, plan_decisions, plan_history, plan_item_state, plan_status  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Собрать или проверить виды исполняемого плана")
    parser.add_argument("view", choices=("bundle", "closure", "decisions", "history", "status", "state"), help="вид для генерации")
    parser.add_argument("--plan-dir", required=True, type=Path, help="каталог плана")
    parser.add_argument("--check", action="store_true", help="только проверить свежесть")
    parser.add_argument("--all", action="store_true", help="все item (state или bundle)")
    parser.add_argument("--item", help="один item Pn.m (state, history или bundle)")
    parser.add_argument("--stdout", action="store_true", help="напечатать bundle вместо записи")
    parser.add_argument("--phase", help="одна фаза Pn (closure)")
    parser.add_argument("--output", type=Path, help="явно материализовать history view по этому пути")
    args = parser.parse_args(argv)
    try:
        if args.view == "bundle":
            if args.all == bool(args.item) or args.phase or args.output or (args.stdout and args.all):
                raise ValueError("bundle требует ровно один из --all / --item; --stdout только с --item")
            if args.stdout:
                if args.check:
                    raise ValueError("bundle --stdout не принимает --check")
                print(plan_bundle.render(args.plan_dir, args.item), end="")
                return 0
            outputs = (plan_bundle.build_all(args.plan_dir, check=args.check) if args.all
                       else (plan_bundle.build(args.plan_dir, args.item, check=args.check),))
        elif args.view == "closure":
            if not args.phase or args.item or args.all or args.output or args.stdout:
                raise ValueError("closure требует только --phase")
            outputs = (plan_closure.build_closure(args.plan_dir, args.phase, check=args.check),)
        elif args.view == "decisions":
            outputs = plan_decisions.build_views(args.plan_dir, check=args.check)
        elif args.view == "history":
            if not args.item or args.all or args.stdout:
                raise ValueError("history требует --item и не принимает --all")
            if args.check and not args.output:
                raise ValueError("history --check требует явный --output")
            if args.output:
                outputs = (plan_history.materialize_history(
                    args.plan_dir, args.item, args.output, check=args.check),)
            else:
                print(plan_history.render_history(args.plan_dir, args.item), end="")
                return 0
        elif args.view == "status":
            outputs = (plan_status.build_status(args.plan_dir, check=args.check),)
        else:
            if args.all == bool(args.item) or args.stdout:
                raise ValueError("state требует ровно один из --all / --item")
            outputs = plan_item_state.build_states(args.plan_dir, item_id=args.item, check=args.check)
    except (plan_bundle.BundleError, plan_closure.ClosureError, plan_decisions.DecisionError, plan_history.HistoryError,
            plan_item_state.ItemStateError, plan_status.StatusError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    action = "проверены" if args.check else "собраны"
    print(f"views: {action} ({len(outputs)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
