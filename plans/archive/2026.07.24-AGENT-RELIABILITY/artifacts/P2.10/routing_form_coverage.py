#!/usr/bin/env python3
"""P2.10 — §3 Routing form coverage probe (stdlib-only, plans/2026.07.24-AGENT-RELIABILITY).

D78 measured (`findings/14` M4/M4.1) that `task.task_contract.build()` reads exactly one
§3 Routing column header and lets an unmapped provider model name reach `_rank()`'s raw
`order.index(...)`; on 11 of the 14 root `plans/` this produced either a fabricated empty
`required` route or an unhandled `ValueError`. This probe reproduces the same walk over
the same corpus AFTER the P2.10 repair and prints one outcome per plan — a third party
re-runs the exact command in Validation and sees the same line, never a narrated summary.

For each `plans/<ID>/plan.md` (root corpus: direct children of `--plans-root` plus its
`archive/` subdirectory, exactly `findings/14` M4.1's own enumeration) the probe:

  1. Picks the FIRST item declared in the FIRST `phases/*.md` file (lexical filename
     order) — a real, already-authored item, never a synthetic one, so whatever surfaces
     is the compiler's actual behavior on that plan's own §3 form and item fields.
  2. Calls `task_contract.build()` (never a second parser of item fields or §3 — Code
     Guidance, anti-duplicate-SSOT).
  3. On success, captures a live `actual_route` EQUAL to the resolved `required` route
     (the self-conformance pattern P2.6/P2.7 already use: `capture_actual(...,
     source="self-attested", model="probe")`) and runs `evaluate()` — the printed outcome
     is the predicate codes themselves, not a guess about them.

Three outcome shapes, one line per plan, alphabetically by plan id:

  * `ok pre_mutation=<code> pre_final=<code>`     — build() and evaluate() both returned.
  * `typed:<field>: <message>`                     — `TaskContractBuildError` (a NAMED,
    typed refusal — the compiler's own anti-padding/anti-crash contract).
  * `EXC:<ExceptionClassName>: <message>`           — anything else. This is exactly what
    Deliverables forbids: exit code is 1 if even one plan produces this shape.

No filesystem write, no network, no clock/random read (the routes it captures compare
required against itself, not a real session's clock-stamped evidence).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[4] / "packages" / "task" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task import plan_lint, route_evidence, task_contract  # noqa: E402


def _root_plan_dirs(plans_root: Path) -> list:
    """`findings/14` M4.1's own enumeration: direct children of `plans_root` plus its
    `archive/` subdirectory — never a recursive glob (an archived plan nested deeper than
    one level, if any ever appears, is out of this probe's declared corpus)."""
    dirs = [p.parent for p in sorted(plans_root.glob("*/plan.md"))]
    dirs += [p.parent for p in sorted((plans_root / "archive").glob("*/plan.md"))]
    return dirs


def _first_item_id(plan_dir: Path):
    """First item declared in the first `phases/*.md` file, lexical filename order, or
    `None` if the plan carries no phase file / no item block at all (an informational
    outcome, distinct from a build/evaluate failure)."""
    phase_paths = sorted((plan_dir / "phases").glob("*.md"))
    for phase_path in phase_paths:
        diag = plan_lint.Diagnostics()
        phase = plan_lint.parse_phase_md(phase_path, phase_path.stem, diag)
        if phase and phase.get("items"):
            return next(iter(phase["items"]))
    return None


def _probe_one(plan_dir: Path, item_id: str) -> str:
    try:
        contract = task_contract.build(plan_dir, item_id)
    except task_contract.TaskContractBuildError as error:
        return f"typed:{error.field}: {error}"
    except Exception as error:  # a plan may only fail typed or succeed — never a traceback
        return f"EXC:{type(error).__name__}: {error}"

    try:
        required = contract["route"]["required"]
        actual = route_evidence.capture_actual(
            required["model_class"], required["effort"],
            source="self-attested", ts="1970-01-01T00:00:00Z", model="probe")
        contract["route"] = route_evidence.build_task_contract_route(
            required, actual, contract["route"]["capabilities"])
        contract["version"]["content_hash"] = task_contract.content_hash(contract)
        result = task_contract.evaluate(contract)
    except Exception as error:  # pragma: no cover - defense in depth, same discipline above
        return f"EXC:{type(error).__name__}: {error}"

    return f"ok pre_mutation={result['pre_mutation']} pre_final={result['pre_final']}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe §3 Routing form coverage of task_contract.build()/evaluate() "
                    "over every root plans/<ID> (P2.10, D78).")
    parser.add_argument("--plans-root", required=True, help="repo-relative plans/ directory")
    args = parser.parse_args(argv)

    plans_root = Path(args.plans_root)
    saw_exc = False
    for plan_dir in _root_plan_dirs(plans_root):
        plan_id = plan_dir.name
        item_id = _first_item_id(plan_dir)
        if item_id is None:
            print(f"{plan_id}: typed:item: no phase file carries an item block")
            continue
        outcome = _probe_one(plan_dir, item_id)
        print(f"{plan_id} ({item_id}): {outcome}")
        if outcome.startswith("EXC:"):
            saw_exc = True

    return 1 if saw_exc else 0


if __name__ == "__main__":
    sys.exit(main())
