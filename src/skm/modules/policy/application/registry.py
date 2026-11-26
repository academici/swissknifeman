"""Bus operations of the policy module (policy §7, §8)."""

from skm.modules.policy.application.commands import (
    approve_intent,
    deny_intent,
    expire_intents,
    propose_intent,
    record_intent_outcome,
    record_tool_decisions,
    start_intent_execution,
)
from skm.modules.policy.application.queries import (
    check_tool_call,
    effective_permissions,
    explain_permissions,
    get_intent,
    list_intents,
    list_profiles,
)

__all__ = ["COMMANDS", "QUERIES"]

COMMANDS = (
    propose_intent.SPEC,
    approve_intent.SPEC,
    deny_intent.SPEC,
    start_intent_execution.SPEC,
    record_intent_outcome.SPEC,
    record_tool_decisions.SPEC,
    expire_intents.SPEC,
)
QUERIES = (
    effective_permissions.SPEC,
    check_tool_call.SPEC,
    explain_permissions.SPEC,
    list_profiles.SPEC,
    list_intents.SPEC,
    get_intent.SPEC,
)
