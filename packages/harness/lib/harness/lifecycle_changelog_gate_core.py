"""Shared changelog-gate policy core for Codex and Cursor."""
from __future__ import annotations

from .lifecycle_policy_core import PolicyRule, verdict

RELEASE_TYPES = ("feat", "fix", "perf", "refactor")

RULES = tuple(
    PolicyRule(
        id=f"type-{commit_type}",
        pattern=rf"^{commit_type}(\([^)]*\))?!?:\s",
        reason="matches release-sensitive commit type",
        tier="high",
    )
    for commit_type in RELEASE_TYPES
)


def changelog_gate_verdict(commit_message: str, *, mode: str):
    """Evaluate the first commit message against release-sensitive rules."""
    return verdict(commit_message, rules=RULES, mode=mode)
