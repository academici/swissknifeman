"""The risk score of a piece after its executor round (P7.2): a pure function of facts the engine collects, with the
weights and path patterns of ``[orch.conductor.risk]``. A score at or above ``review.dynamic_threshold`` adds the
review to a piece whose run policy has none. No model is asked: the score is a sum of fixed weights, so the same
facts always give the same score and every feature names its evidence."""
from __future__ import annotations

from orch.conductor.scope import matches

DEFAULT_WEIGHTS = {"public_cli": 25, "schema": 25, "security": 30, "shared": 15, "diff_size": 10, "red_first": 10,
                   "deviation": 10, "outside_write_set": 15, "executor_recommended": 30}
DEFAULT_PATTERNS = {
    "public_cli": ["bin/**", "**/cli.py", "packages/*/scripts/*.py"],
    "schema": ["**/schemas/**", "**/migrations/**"],
    "security": ["**/auth/**", "**/security/**", "**/permissions*", "**/*secret*"],
    "shared": ["packages/aicore/**"],
}
DEFAULT_DIFF_LINES = 400
DEFAULT_THRESHOLD = 60
SAMPLE = 3  # paths named as the evidence of one feature


def defaults() -> dict:
    """The built-in ``[orch.conductor.risk]`` as plain data (fresh copies)."""
    return {"weights": dict(DEFAULT_WEIGHTS), "patterns": {key: list(value) for key, value in DEFAULT_PATTERNS.items()},
            "diff_lines": DEFAULT_DIFF_LINES}


def _named(paths: list) -> str:
    more = f" (+{len(paths) - SAMPLE} more)" if len(paths) > SAMPLE else ""
    return ", ".join(paths[:SAMPLE]) + more


def score(facts: dict, config: dict | None = None) -> dict:
    """``{"score": 0..100, "features": [{"name", "weight", "evidence"}]}``.

    ``facts``: ``changed`` and ``outside`` (repository paths), ``diff_lines`` (changed lines), ``red_first``,
    ``deviation`` and ``recommended`` (booleans). ``config``: ``weights``, ``patterns`` and ``diff_lines``, each key
    optional (the built-in value stands in for a missing one); a weight of 0 turns its feature off. The sum is
    capped at 100."""
    config = config or {}
    weights = {**DEFAULT_WEIGHTS, **(config.get("weights") or {})}
    patterns = {**DEFAULT_PATTERNS, **(config.get("patterns") or {})}
    limit = config.get("diff_lines", DEFAULT_DIFF_LINES)
    changed = sorted(set(facts.get("changed") or []))
    outside = sorted(set(facts.get("outside") or []))
    found = []
    for name in DEFAULT_PATTERNS:
        hits = [path for path in changed if any(matches(path, pattern) for pattern in patterns[name])]
        if hits:
            found.append((name, f"{len(hits)} changed path(s): {_named(hits)}"))
    lines = int(facts.get("diff_lines") or 0)
    if lines > limit:
        found.append(("diff_size", f"{lines} changed lines > {limit}"))
    if facts.get("red_first"):
        found.append(("red_first", "an acceptance check was red in the first round"))
    if facts.get("deviation"):
        found.append(("deviation", "the executor reported a deviation"))
    if outside:
        found.append(("outside_write_set", f"{len(outside)} path(s) outside the write set: {_named(outside)}"))
    if facts.get("recommended"):
        found.append(("executor_recommended", "the executor recommended a review"))
    features = [{"name": name, "weight": int(weights[name]), "evidence": evidence}
                for name, evidence in found if int(weights[name]) > 0]
    return {"score": min(100, sum(row["weight"] for row in features)), "features": features}
