"""Shared pack-guard policy core for Codex and Cursor."""
from __future__ import annotations

import re

from .lifecycle_policy_core import PolicyRule, verdict

_RULE_PREFIX = "managed-target:"


def managed_target_rules(managed_targets):
    """Build declarative rules for managed pack targets."""
    rules = []
    for target in sorted(set(str(item) for item in managed_targets if isinstance(item, str) and item)):
        rules.append(PolicyRule(
            id=_RULE_PREFIX + target,
            pattern=re.escape(target),
            reason="touches a managed pack target",
            tier="high",
        ))
    return tuple(rules)


def matched_target(match_id: str):
    """Extract managed target path from a matched rule id."""
    if not isinstance(match_id, str) or not match_id.startswith(_RULE_PREFIX):
        return None
    return match_id[len(_RULE_PREFIX):]


def pack_guard_verdict(serialized_input: str, *, mode: str, managed_targets):
    """Evaluate serialized tool input against managed target rules."""
    return verdict(serialized_input, rules=managed_target_rules(managed_targets), mode=mode)
