"""The token budgets of a run: the classes of the prompt blocks against their limits, and ``tokens_max`` of a piece.
Both are beacons: nothing is cut or stopped."""
from __future__ import annotations

from aicore.content.budget import estimate_tokens

from orch.conductor.domain.item import Item

# Budget classes of the blocks (knowledge/p9-prompt#budgets). Only the measure and a beacon: nothing is cut. The kinds the
# design does not list belong to the frame or the task material of their role (progress, candidate, review_scope, diff,
# findings, instruction), so they count as core; ``retrieval`` is what the sources answered (``research``).
BUDGET_CLASSES = {
    "core": ("role_text", "input", "verification", "result_contract", "answers", "correction", "progress", "candidate",
             "review_scope", "diff", "findings", "instruction"),
    "supporting": ("repository_rules", "skill", "skill_names", "context_map", "expected_paths", "focus", "run_rules"),
    "retrieval": ("research",),
}
BUDGET_LIMITS = {"core": "prompt_core_tokens", "supporting": "prompt_supporting_tokens",
                 "retrieval": "prompt_retrieval_tokens"}  # the ``limits`` keys of the run options


def budget_class(kind: str) -> str:
    """``core``, ``supporting`` or ``retrieval``: the budget class of a block kind (a kind nobody listed is supporting)."""
    return next((name for name, kinds in BUDGET_CLASSES.items() if kind in kinds), "supporting")


def budgets(blocks, limits: dict) -> dict:
    """``{class: {tokens, limit}}``: the estimated tokens of the blocks of each class against ``limits[class]``."""
    tokens = {name: 0 for name in BUDGET_CLASSES}
    for block in blocks:
        tokens[budget_class(block.kind)] += estimate_tokens(block.text)
    return {name: {"tokens": tokens[name], "limit": int(limits.get(name) or 0)} for name in BUDGET_CLASSES}


def over_budget(blocks, limits: dict) -> list:
    """``[(class, block, class_tokens, limit)]`` for each class above its limit (0 is no limit), with the heaviest block of
    the class, the first of equals. A report only: the blocks are not touched."""
    found = []
    for name, row in budgets(blocks, limits).items():
        if row["limit"] and row["tokens"] > row["limit"]:
            members = [block for block in blocks if budget_class(block.kind) == name]
            found.append((name, max(members, key=lambda block: estimate_tokens(block.text)), row["tokens"], row["limit"]))
    return found


def budget(self, item: Item) -> None:
    """``tokens_max`` is a beacon: past it a BUDGET_OVER line is printed once per piece, nothing is stopped."""
    limit = item.options["limits"].get("tokens_max") or 0
    tokens = item.state.get("tokens", {})
    used = int(tokens.get("input", 0)) + int(tokens.get("output", 0))  # cache reads are not spend
    if limit and used > limit and not item.state.get("budget_over"):
        item.state["budget_over"] = used
        self._save()
        self.progress.emit("info", item=item.ref, reason_code="BUDGET_OVER",
                           message=f"{item.ref} used {used} fresh tokens, past tokens_max {limit}; the run goes on")
