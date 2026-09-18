"""Shared git-guardrails policy core for Codex and Cursor."""
from __future__ import annotations

from .lifecycle_policy_core import PolicyRule, verdict

RULES = (
    PolicyRule(
        id="git-push",
        pattern=r"git push",
        reason="matches dangerous git push pattern",
        tier="high",
    ),
    PolicyRule(
        id="git-reset-hard",
        pattern=r"git reset --hard",
        reason="matches dangerous git reset --hard pattern",
        tier="critical",
    ),
    PolicyRule(
        id="git-clean-fd",
        pattern=r"git clean -fd",
        reason="matches dangerous git clean -fd pattern",
        tier="critical",
    ),
    PolicyRule(
        id="git-clean-f",
        pattern=r"git clean -f",
        reason="matches dangerous git clean -f pattern",
        tier="critical",
    ),
    PolicyRule(
        id="git-branch-delete",
        pattern=r"git branch -D",
        reason="matches dangerous git branch deletion pattern",
        tier="high",
    ),
    PolicyRule(
        id="git-checkout-dot",
        pattern=r"git checkout \.",
        reason="matches dangerous checkout dot pattern",
        tier="high",
    ),
    PolicyRule(
        id="git-restore-dot",
        pattern=r"git restore \.",
        reason="matches dangerous restore dot pattern",
        tier="high",
    ),
    PolicyRule(
        id="push-force",
        pattern=r"push --force",
        reason="matches dangerous force push pattern",
        tier="critical",
    ),
    PolicyRule(
        id="push-force-with-lease",
        pattern=r"push --force-with-lease",
        reason="matches dangerous force-with-lease pattern",
        tier="critical",
    ),
    PolicyRule(
        id="reset-hard",
        pattern=r"reset --hard",
        reason="matches dangerous reset --hard pattern",
        tier="critical",
    ),
    PolicyRule(
        id="rebase-onto",
        pattern=r"rebase --onto",
        reason="matches dangerous rebase --onto pattern",
        tier="critical",
    ),
)


def git_guardrails_verdict(command: str, *, mode: str):
    """Evaluate git command against the declared off/warn/strict ladder."""
    return verdict(command, rules=RULES, mode=mode)
