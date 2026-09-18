"""Shared daemon-safety policy core for Codex and Cursor."""
from __future__ import annotations

from .lifecycle_policy_core import PolicyRule, verdict

RULES = (
    PolicyRule(
        id="kill-perplexity-family",
        pattern=r"pkill.*(perplexity|playwright|chromium|chrome)",
        reason="matches destructive daemon kill pattern",
        tier="critical",
    ),
    PolicyRule(
        id="killall-perplexity-family",
        pattern=r"killall.*(perplexity|playwright|chromium|chrome)",
        reason="matches destructive daemon killall pattern",
        tier="critical",
    ),
    PolicyRule(
        id="kill9-perplexity-family",
        pattern=r"kill +-9.*(perplexity|playwright|chromium)",
        reason="matches destructive daemon SIGKILL pattern",
        tier="critical",
    ),
    PolicyRule(
        id="remove-singleton-lock",
        pattern=r"rm .*Singleton",
        reason="matches singleton-lock cleanup pattern",
        tier="high",
    ),
    PolicyRule(
        id="remove-playwright-profile",
        pattern=r"rm .*\.playwright/(profile|profiles)",
        reason="matches playwright profile deletion pattern",
        tier="critical",
    ),
    PolicyRule(
        id="remove-perplexity-mcp-cache",
        pattern=r"rm .*perplexity-web-mcp",
        reason="matches perplexity-web-mcp removal pattern",
        tier="high",
    ),
    PolicyRule(
        id="remove-profile-lock",
        pattern=r"rm .*profile\.lock",
        reason="matches profile lock deletion pattern",
        tier="high",
    ),
    PolicyRule(
        id="remove-perplexity-socket",
        pattern=r"rm .*perplexity.*\.sock",
        reason="matches perplexity socket deletion pattern",
        tier="high",
    ),
)


def daemon_safety_verdict(command: str, *, mode: str):
    """Evaluate daemon-safety command against the declared off/warn/strict ladder."""
    return verdict(command, rules=RULES, mode=mode)
