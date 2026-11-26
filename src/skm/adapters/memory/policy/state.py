"""Tables of ``skm_policy`` in the memory backend state (policy §11).

The tables live in ``MemoryBackendState.modules["policy"]``; a unit of work works on a deep copy, so a
rollback drops them. The rows are the immutable domain values themselves.
"""

from dataclasses import dataclass, field
from typing import Final

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.ids import ToolIntentId
from skm.modules.policy.domain.approval import Approval, ApprovalId
from skm.modules.policy.domain.tool_intent import ToolDecisionRecord, ToolIntent

__all__ = ["STATE_KEY", "MemoryPolicyState", "policy_state"]

STATE_KEY: Final = "policy"


@dataclass
class MemoryPolicyState:
    intents: dict[ToolIntentId, ToolIntent] = field(default_factory=dict[ToolIntentId, ToolIntent])
    approvals: dict[ApprovalId, Approval] = field(default_factory=dict[ApprovalId, Approval])
    audit: list[ToolDecisionRecord] = field(default_factory=list[ToolDecisionRecord])


def policy_state(state: MemoryBackendState) -> MemoryPolicyState:
    found = state.modules.get(STATE_KEY)
    if found is None:
        found = MemoryPolicyState()
        state.modules[STATE_KEY] = found
    if not isinstance(found, MemoryPolicyState):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "policy memory state is malformed", details={"module": STATE_KEY}
        )
    return found
