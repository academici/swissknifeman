"""The facts of the risk score of a piece (``risk.score`` weighs them): what changed, outside the write set, red first
checks, deviations and the executor's own advice to review."""
from __future__ import annotations

from orch.conductor.domain.item import Item, done_steps


def first_checks(steps: dict) -> list:
    """The rows of the first check round that ran (an auto-fix round can come before ``checks.1``)."""
    steps = done_steps(steps)
    rounds = sorted(int(key.split(".", 1)[1]) for key in steps if key.startswith("checks.") and key[7:].isdigit())
    return (steps.get(f"checks.{rounds[0]}") or {}).get("result") or [] if rounds else []


def recommended(steps: dict) -> bool:
    """Any executor round advised a review: a later round that omits the optional field does not take it back."""
    return any(bool(((step.get("result") or {}).get("report") or {}).get("review_recommendation", {}).get("recommended"))
               for key, step in done_steps(steps).items() if key.startswith("executor.") and isinstance(step.get("result"), dict))


def risk_facts(item: Item, report: dict, *, changed: list, outside: list, diff_lines: int) -> dict:
    """The facts of ``item`` after its executor and check rounds; the caller reads the tree (``changed``, ``outside``
    and ``diff_lines`` of ``changed``)."""
    steps = item.state.get("steps", {})
    return {"changed": changed, "outside": outside, "diff_lines": diff_lines,
            "red_first": any(not row.get("green") and not row.get("skipped") for row in first_checks(steps)),
            "deviation": bool(item.state.get("autofixed")) or any(
                issue.get("kind") == "deviation" for issue in report.get("open_issues", [])),
            "recommended": recommended(steps)
            or bool((report.get("review_recommendation") or {}).get("recommended"))}
