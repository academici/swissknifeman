"""Scoped operation commit for an orch stage-result (``commit``).

Runs ``plan.py commit … --json`` as a subprocess (the bridge never imports Task's core or orch) and prints the
fragment a coordinator puts into a stage-result: ``{"commits": [{sha, role, ref, paths_digest}]}``. Every
argument after ``<plan> <ref>`` goes to ``plan.py commit`` unchanged.

Run as ``plan.py bridge orch commit <plan> <item>[/<U#>] --role executor|reviewer|fix [plan.py commit options…]``.
A Task refusal is passed on as ``CODE: message`` on stderr with exit 1.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

TASK_ROOT = Path(__file__).resolve().parents[2]
FIELDS = ("sha", "role", "ref", "paths_digest")


def plan_py() -> str:
    """``TASK_PLAN_PY`` set by the dispatcher; the package's own launcher for direct runs."""
    return os.environ.get("TASK_PLAN_PY") or str(TASK_ROOT / "scripts" / "plan.py")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="plan.py bridge orch commit", description=__doc__.splitlines()[0],
                                epilog="Other options are passed to `plan.py commit` (--role is required).")
    p.add_argument("plan")
    p.add_argument("ref", help="<item> or <item>/<U#>")
    return p


def fragment(result: dict) -> dict:
    """Stage-result ``commits`` fragment from a ``plan.py commit --json`` result."""
    if not result.get("sha"):
        raise ValueError("no commit was created (dry run)")
    return {"commits": [{key: result[key] for key in FIELDS}]}


def main(argv: list[str] | None = None) -> int:
    args, rest = parser().parse_known_args(argv)
    done = subprocess.run([sys.executable, plan_py(), "commit", args.plan, args.ref, *rest, "--json"],
                          capture_output=True, text=True, encoding="utf-8", check=False)
    if done.returncode:
        print((done.stderr or done.stdout).strip(), file=sys.stderr)
        return 1
    try:
        out = fragment(json.loads(done.stdout))
    except (ValueError, KeyError) as error:
        print(f"COMMIT_RESULT_INVALID: plan.py commit returned no commit fragment ({error})", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
