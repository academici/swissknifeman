"""The facts of the risk score of a piece (``risk.score`` weighs them): what changed, outside the write set, red first
checks, deviations and the executor's own advice to review."""
from __future__ import annotations

from orch.conductor import scope as scopes
from orch.conductor.domain.item import Item



def first_checks(steps: dict) -> list:
    """The rows of the first check round that ran (an auto-fix round can come before ``checks.1``)."""
    rounds = sorted(int(key.split(".", 1)[1]) for key in steps if key.startswith("checks.") and key[7:].isdigit())
    return (steps.get(f"checks.{rounds[0]}") or {}).get("result") or [] if rounds else []


def recommended(steps: dict) -> bool:
    """Any executor round advised a review: a later round that omits the optional field does not take it back."""
    return any(bool(((step.get("result") or {}).get("report") or {}).get("review_recommendation", {}).get("recommended"))
               for key, step in steps.items() if key.startswith("executor.") and isinstance(step.get("result"), dict))


def risk_facts(self, item: Item, report: dict) -> dict:
    changed = self._changed(item)
    steps = item.state.get("steps", {})
    return {"changed": changed, "outside": self._outside(item), "diff_lines": scopes.diff_lines(self.project, changed),
            "red_first": any(not row.get("green") and not row.get("skipped") for row in self._first_checks(steps)),
            "deviation": bool(item.state.get("autofixed")) or any(
                issue.get("kind") == "deviation" for issue in report.get("open_issues", [])),
            "recommended": self._recommended(steps)
            or bool((report.get("review_recommendation") or {}).get("recommended"))}
