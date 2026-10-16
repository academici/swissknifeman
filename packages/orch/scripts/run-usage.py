#!/usr/bin/env python3
"""Time and tokens per role and stage of conductor runs, from their ``progress.jsonl``; markdown on stdout.

    run-usage.py [--root DIR] [RUN ...]     DIR defaults to .swissknifeman/state/orch/conductor
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def rows(progress: Path) -> list:
    out = []
    for line in progress.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("event") == "stage.end" and event.get("stage"):
            tokens = event.get("tokens") or {}
            out.append({"item": event.get("item", "-"), "stage": event["stage"], "role": event.get("role", "-"),
                        "route": event.get("route", ""), "s": float(event.get("duration_s") or 0),
                        "in": int(tokens.get("input", 0)), "cached": int(tokens.get("cached", 0)),
                        "out": int(tokens.get("output", 0)), "verdict": event.get("verdict", "")})
    return out


def fmt(seconds: float) -> str:
    return f"{seconds / 60:.1f} мин" if seconds >= 60 else f"{seconds:.0f} с"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".swissknifeman/state/orch/conductor")
    parser.add_argument("runs", nargs="*")
    args = parser.parse_args(argv)
    root = Path(args.root)
    runs = args.runs or sorted(path.name for path in root.iterdir() if (path / "progress.jsonl").is_file())
    for run in runs:
        found = rows(root / run / "progress.jsonl")
        if not found:
            continue
        print(f"### {run}\n")
        print("| Пункт | Шаг | Роль / маршрут | Время | Токены in (свежие) | cache_read | out | Итог |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- |")
        totals = defaultdict(lambda: [0.0, 0, 0, 0])
        for row in found:
            print(f"| {row['item']} | {row['stage']} | {row['role']} {row['route']} | {fmt(row['s'])} | {row['in']:,} | "
                  f"{row['cached']:,} | {row['out']:,} | {row['verdict'][:40]} |")
            total = totals[row["role"]]
            total[0] += row["s"]
            total[1] += row["in"]
            total[2] += row["cached"]
            total[3] += row["out"]
        print("\n| Роль | Время | in | cache_read | out |\n| --- | --- | --- | --- | --- |")
        for role, (seconds, tin, cached, tout) in sorted(totals.items(), key=lambda pair: -pair[1][0]):
            print(f"| {role} | {fmt(seconds)} | {tin:,} | {cached:,} | {tout:,} |")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
