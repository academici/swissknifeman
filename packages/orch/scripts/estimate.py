#!/usr/bin/env python3
"""Expected time of a piece of work from the history of conductor runs; markdown on stdout.

    estimate.py [--root DIR] [--input FILE | --cmd CMD ...] [--effort E] [--no-review] [--red P] [--json]

The history is every run under DIR (default ``.swissknifeman/state/orch/conductor``): the duration of each role step
(by role and effort) and the seconds of each acceptance check (by its exact command). The estimate is

    scout + executor + max(review, checks) + P(red) * (correction + red checks) + audit

with medians of the history: ``checks`` is the sum of the measured seconds of the given commands (a command never
measured counts as unknown and is listed), ``P(red)`` the share of first check rounds that were red (or ``--red``).
The commands come from ``--cmd`` or from an execution-input (``--input``, such as ``<run>/<item>/input.json``). The
point is a number to compare with the actual run afterwards (``run-usage.py``), not a promise.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys


def history(root: Path) -> tuple:
    """``(seconds of role steps by (role, effort), seconds of checks by command, first rounds, red first rounds)``."""
    steps, checks = defaultdict(list), defaultdict(list)
    first = red = 0
    for state_file in sorted(root.glob("cnd-*/state.json")):
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for item in (state.get("items") or {}).values():
            for key, step in (item.get("steps") or {}).items():
                role = step.get("role") or "deterministic"
                effort = str(step.get("route") or "").rsplit("/", 1)[-1] if step.get("route") else "-"
                kind = key.split(".", 1)[0]
                if step.get("duration_s") is not None and role != "deterministic":
                    steps[(kind, effort)].append(float(step["duration_s"]))
                    steps[(kind, "*")].append(float(step["duration_s"]))
                if kind == "checks" and isinstance(step.get("result"), list):
                    rows = step["result"]
                    for row in rows:
                        if row.get("cmd") and row.get("seconds") is not None:
                            checks[row["cmd"]].append(float(row["seconds"]))
                    if key == "checks.1":
                        first += 1
                        red += 0 if all(row.get("green") for row in rows) else 1
    return steps, checks, first, red


def median(values: list, default: float = 0.0) -> float:
    return statistics.median(values) if values else default


def estimate(root: Path, commands: list, effort: str, review: bool, red_share) -> dict:
    steps, checks, first, red = history(root)

    def role(kind: str) -> float:
        return median(steps.get((kind, effort)) or steps.get((kind, "*")) or [])

    known = {cmd: median(checks[cmd]) for cmd in commands if cmd in checks}
    unknown = [cmd for cmd in commands if cmd not in checks]
    sum_checks = sum(known.values())
    p_red = red_share if red_share is not None else (red / first if first else 0.3)
    parts = {"scout": role("scout"), "executor": role("executor"),
             "review": role("review") if review else 0.0, "checks": sum_checks,
             "correction": role("executor") * 0.15 if p_red else 0.0}
    audit = min(parts["review"], 360.0) if review else 0.0
    total = parts["scout"] + parts["executor"] + max(parts["review"], sum_checks) \
        + p_red * (parts["correction"] + sum_checks) + audit
    return {"total_s": round(total), "parts_s": {k: round(v) for k, v in parts.items()}, "audit_s": round(audit),
            "p_red": round(p_red, 2), "checks_known_s": {k: round(v) for k, v in known.items()},
            "checks_unknown": unknown, "history": {"runs": len(list(root.glob("cnd-*"))), "first_rounds": first}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(".swissknifeman/state/orch/conductor"))
    parser.add_argument("--input", type=Path, help="an execution-input whose acceptance commands are estimated")
    parser.add_argument("--cmd", action="append", default=[], help="an acceptance command (repeatable)")
    parser.add_argument("--effort", default="*", help="the executor effort of the route (low|medium|high|xhigh)")
    parser.add_argument("--no-review", dest="review", action="store_false")
    parser.add_argument("--red", type=float, default=None, help="probability of a red first round (default: history)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    commands = list(args.cmd)
    if args.input:
        doc = json.loads(args.input.read_text(encoding="utf-8"))
        commands += [check["cmd"] for check in (doc.get("acceptance") or {}).get("checks", []) if check.get("cmd")]
    found = estimate(args.root, commands, args.effort, args.review, args.red)
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
        return 0
    minutes = lambda seconds: f"{seconds / 60:.1f} min"  # noqa: E731
    print(f"# Estimate: {minutes(found['total_s'])}\n")
    print("| Part | Expected |\n| --- | --- |")
    for name, value in found["parts_s"].items():
        print(f"| {name} | {minutes(value)} |")
    print(f"| audit after a correction | {minutes(found['audit_s'])} |")
    print(f"\nP(red first round) = {found['p_red']}; history: {found['history']['runs']} run(s)")
    for cmd in found["checks_unknown"]:
        print(f"- never measured: `{cmd[:120]}`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
