"""Token budgets: the known usage of a logical step, the limit in force, the admission rule of hard limits on
accounted fresh tokens and the informational budgets of prompt blocks. The accounting itself (slots, charges, the
state it changes) is ``application/budget_service.py``."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from aicore.content.budget import estimate_tokens

from orch.conductor import records
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop

HARD_LIMITS = ("tokens_hard_max", "run_tokens_hard_max")
DEFAULT_CHARGE = 50000  # limits.unmetered_charge_tokens when an item carries no options of its own
_USAGE = ("input", "cached", "output")  # the keys of one attempt; fresh spend is input + output


def _read_record(path: Path, kind: str) -> Optional[dict]:
    """The checked agent record at ``path`` (records/v1 ``kind``); ``None`` when there is none or it cannot be opened.
    Bytes that are not JSON stop with ``STATE_CORRUPT``, a record that does not match with ``RECORD_INVALID``: a
    damaged usage file is never read as zero usage."""
    try:
        return records.read(path, kind)
    except OSError:
        return None


def _add_usage(total: dict, usage: dict) -> None:
    for name in _USAGE:
        total[name] = int(total.get(name, 0)) + int(usage.get(name, 0) or 0)


def known_stage_usage(item: Item, key: str) -> dict:
    """Known fresh usage of logical step ``key`` already stored for ``item``.

    The piece's ``stage_usage`` record wins. Without it (a run saved before that record), receipts that name the
    step are summed, then the usage files of agents whose request names the step. Anything else starts at zero:
    the old shared counter was not kept across a process.
    """
    saved = (item.state.get("stage_usage") or {}).get(key) if isinstance(item.state, dict) else None
    if isinstance(saved, dict):
        return saved
    total = {"input": 0, "output": 0}
    labelled = False
    for attempts in (item.state.get("usage_by_agent") or {}).values():
        if not isinstance(attempts, dict):
            continue
        for receipt in attempts.values():
            if not isinstance(receipt, dict) or receipt.get("step") != key:
                continue
            labelled = True
            _add_usage(total, receipt)
    if labelled:
        return total
    directory = getattr(item, "directory", None)
    agents = Path(directory) / "agents" if directory else None
    if agents is not None and agents.is_dir():
        from_files = {"input": 0, "output": 0}
        found = False
        for request_path in agents.glob("*/request.json"):
            request = _read_record(request_path, "agent-request") or {}
            if request.get("step") != key:
                continue
            usage = _read_record(request_path.with_name("usage.json"), "agent-usage")
            if not usage:
                continue
            found = True
            _add_usage(from_files, usage)
        if found:
            return from_files
    return total


def effective_limit(key: str, *, limit_raises: list, limits_run: Optional[dict], item_options: Optional[dict],
                    item_ref: str) -> int:
    """An explicit raise (including zero to remove a limit), else the frozen run cap or the piece's options. A raise of
    ``tokens_hard_max`` names the piece it was made for and holds for that piece only; an older record without ``item``
    holds for every piece, as it did when it was written. ``limits_run`` is read only for ``run_tokens_hard_max``."""
    for change in reversed(limit_raises):
        if change["key"] == key and (key != "tokens_hard_max" or change.get("item") in (None, item_ref)):
            return change["to"]
    run_caps = limits_run or {}
    if key == "run_tokens_hard_max" and key in run_caps:
        return run_caps[key]["value"]
    return ((item_options or {}).get("limits") or {}).get(key, 0) or 0


def admission(*, scope: str, item_ref: str, run_id: str, item_tokens: dict, run_tokens: dict, limits: dict,
              item_limits: dict, usage_incomplete: bool, usage_unmetered: list, stage_max: int = 0,
              stage_used: int = 0, stage_key: Optional[str] = None) -> Optional[Stop]:
    """The ``Stop`` that refuses one more model call, or ``None``; the rule of ``budget_service.admit``.

    ``limits`` is the limit in force of each of :data:`HARD_LIMITS` the scope reads; ``scope`` selects ``item``, ``run`` or both
    (``all``), and ``attempt`` adds the unmetered rule and the step's fresh tokens (``stage_used``) against
    ``stage_max`` (``budgets.stage_tokens_max``, 0 does not apply). Cache reads do not count."""
    for name, key, tokens, label in (
            ("item", "tokens_hard_max", item_tokens, item_ref),
            ("run", "run_tokens_hard_max", run_tokens, f"run {run_id}")):
        if scope not in ("all", "attempt", name):
            continue
        limit = limits[key]
        used = int(tokens.get("input", 0)) + int(tokens.get("output", 0))
        if limit and used >= limit:
            return Stop("TOKEN_BUDGET", f"{label} used {used} fresh tokens >= {key} {limit}; needs_replan: split the item "
                        f"or raise the limit (conduct resume --run {run_id} --raise-limit {key}=<value>)")
    if scope in ("all", "attempt") and item_limits.get("unmetered", "stop") != "charge":
        own = bool(usage_incomplete) and any(limits[key] > 0 for key in HARD_LIMITS)
        # unknown usage of any piece of the run escapes a run-wide limit: it is kept at run scope, not only in the piece
        unknown = sorted(usage_unmetered or []) if limits["run_tokens_hard_max"] > 0 else []
        if own or unknown:
            named = ", ".join(unknown) if unknown else item_ref
            return Stop("TOKEN_BUDGET_UNMETERED", f"{named}: a model attempt reported no usage while a hard token limit is "
                        "set; resume with an --options file that sets limits.unmetered to \"charge\" (a fixed "
                        "limits.unmetered_charge_tokens per attempt without usage), or set it in [orch.conductor.limits]")
    if scope == "attempt" and stage_max and stage_used >= stage_max:
        return Stop("TOKEN_BUDGET", f"{item_ref} step {stage_key or '-'} used {stage_used} fresh tokens >= "
                    f"budgets.stage_tokens_max {stage_max} of the run policy; needs_replan: split the item or "
                    "raise stage_tokens_max in the policy")
    return None

# Budget classes of the blocks (knowledge/p9-prompt#budgets). Only the measure and a beacon: nothing is cut. ``core`` is
# the frame the conductor writes for every role (role text, contract, checks, corrections, progress); ``task`` is the
# material of the piece itself (the execution input, the candidate and its diff, the findings to judge): its size is the
# plan's and the change's, so it is measured with no limit (18-37 K of input put every role past a core limit of 12 K
# and drowned the other beacons in P7/P8, while nothing could be cut); ``retrieval`` is what the sources answered.
BUDGET_CLASSES = {
    "core": ("role_text", "verification", "result_contract", "answers", "correction", "progress", "instruction"),
    "task": ("input", "candidate", "review_scope", "diff", "findings"),
    "supporting": ("repository_rules", "skill", "skill_names", "context_map", "expected_paths", "focus", "run_rules",
                   "stub"),
    "retrieval": ("research",),
}
BUDGET_LIMITS = {"core": "prompt_core_tokens", "supporting": "prompt_supporting_tokens",
                 "retrieval": "prompt_retrieval_tokens"}  # the ``limits`` keys of the run options; ``task`` has none


def budget_class(kind: str) -> str:
    """``core``, ``task``, ``supporting`` or ``retrieval``: the budget class of a block kind (a kind nobody listed is
    supporting)."""
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
