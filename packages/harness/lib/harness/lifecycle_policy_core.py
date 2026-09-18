"""Provider-neutral regex policy core for lifecycle gates."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

POLICY_MODES = ("off", "warn", "strict")


@dataclass(frozen=True)
class PolicyRule:
    """Declarative lifecycle policy rule."""

    id: str
    pattern: str
    reason: str
    tier: str


@dataclass(frozen=True)
class PolicyMatch:
    """Matched rule metadata returned by verdict()."""

    id: str
    pattern: str
    reason: str
    tier: str


@dataclass(frozen=True)
class PolicyVerdict:
    """Pure verdict for adapters to translate into provider responses."""

    mode: str
    decision: str  # allow | warn | deny
    match: PolicyMatch | None


def normalize_mode(mode: str | None) -> str:
    """Normalize unknown/empty mode values to 'off'."""
    if not isinstance(mode, str):
        return "off"
    value = mode.strip().lower()
    return value if value in POLICY_MODES else "off"


def verdict(text: str, *, rules: Iterable[PolicyRule], mode: str) -> PolicyVerdict:
    """Evaluate declarative rules against text with off/warn/strict ladder."""
    normalized = normalize_mode(mode)
    if normalized == "off" or not isinstance(text, str):
        return PolicyVerdict(normalized, "allow", None)
    for rule in rules:
        if re.search(rule.pattern, text):
            match = PolicyMatch(rule.id, rule.pattern, rule.reason, rule.tier)
            decision = "deny" if normalized == "strict" else "warn"
            return PolicyVerdict(normalized, decision, match)
    return PolicyVerdict(normalized, "allow", None)
