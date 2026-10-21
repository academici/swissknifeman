"""Token accounting, informational budgets and hard admission limits on accounted fresh tokens."""
from __future__ import annotations

from aicore.content.budget import estimate_tokens

from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop

HARD_LIMITS = ("tokens_hard_max", "run_tokens_hard_max")


def effective_limit(self, item: Item, key: str) -> int:
    """An explicit raise (including zero to remove a limit), else the frozen run cap or the piece's options. A raise of
    ``tokens_hard_max`` names the piece it was made for and holds for that piece only; an older record without ``item``
    holds for every piece, as it did when it was written."""
    for change in reversed(self.state.get("limit_raises", [])):
        if change["key"] == key and (key != "tokens_hard_max" or change.get("item") in (None, item.ref)):
            return change["to"]
    if key == "run_tokens_hard_max" and key in self.run_doc.get("limits_run", {}):
        return self.run_doc["limits_run"][key]["value"]
    return ((item.options or {}).get("limits") or {}).get(key, 0) or 0


def admit(self, item: Item, scope: str = "all") -> None:
    """Stop admission once accounted fresh usage reaches a hard limit; cache reads and missing usage do not count.

    ``scope`` selects ``item``, ``run`` or both (``all``). A single model call can cross the boundary: this check never
    interrupts one, and does not guess at unmetered usage.
    """
    for name, key, state, label in (
            ("item", "tokens_hard_max", item.state, item.ref),
            ("run", "run_tokens_hard_max", self.state, f"run {self.run_id}")):
        if scope not in ("all", name):
            continue
        limit = effective_limit(self, item, key)
        tokens = state.get("tokens", {})
        used = int(tokens.get("input", 0)) + int(tokens.get("output", 0))
        if limit and used >= limit:
            raise Stop("TOKEN_BUDGET", f"{label} used {used} fresh tokens >= {key} {limit}; needs_replan: split the item "
                       f"or raise the limit (conduct resume --run {self.run_id} --raise-limit {key}=<value>)")

# Budget classes of the blocks (knowledge/p9-prompt#budgets). Only the measure and a beacon: nothing is cut. The kinds the
# design does not list belong to the frame or the task material of their role (progress, candidate, review_scope, diff,
# findings, instruction), so they count as core; ``retrieval`` is what the sources answered (``research``).
BUDGET_CLASSES = {
    "core": ("role_text", "input", "verification", "result_contract", "answers", "correction", "progress", "candidate",
             "review_scope", "diff", "findings", "instruction"),
    "supporting": ("repository_rules", "skill", "skill_names", "context_map", "expected_paths", "focus", "run_rules",
                   "stub"),
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


def unmetered(self, item: Item) -> None:
    """Remember an unmetered model attempt and announce it once, even when that attempt stops the run."""
    with self.store.mutating():  # a role thread gets here while the main loop saves the state (I2)
        first = not item.state.get("usage_incomplete")
        if first:
            item.state["usage_incomplete"] = True
            self._save()
    if first:  # announced after the lock
        self.progress.emit("info", item=item.ref, reason_code="BUDGET_UNMETERED",
                           message=f"{item.ref}: a model attempt reported no usage; token limits cannot see it")


def budget(self, item: Item) -> None:
    """``tokens_max`` is a beacon: past it a BUDGET_OVER line is printed once per piece, nothing is stopped."""
    limit = item.options["limits"].get("tokens_max") or 0
    tokens = item.state.get("tokens", {})
    used = int(tokens.get("input", 0)) + int(tokens.get("output", 0))  # cache reads are not spend
    with self.store.mutating():
        first = bool(limit and used > limit and not item.state.get("budget_over"))
        if first:
            item.state["budget_over"] = used
            self._save()
    if first:
        self.progress.emit("info", item=item.ref, reason_code="BUDGET_OVER",
                           message=f"{item.ref} used {used} fresh tokens, past tokens_max {limit}; the run goes on")
