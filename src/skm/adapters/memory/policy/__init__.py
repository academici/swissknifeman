"""Memory adapters of the policy repository ports (policy §3, §6, §11).

``REPOSITORIES`` maps each port to its factory over the backend state; ``bootstrap.adapters`` merges it with
the core table.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.policy.repositories import (
    MemoryApprovalRepository,
    MemoryDecisionAuditRepository,
    MemoryToolIntentRepository,
)
from skm.modules.policy.ports import ApprovalRepository, DecisionAuditRepository, ToolIntentRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[MemoryBackendState], object]] = MappingProxyType(
    {
        ToolIntentRepository: MemoryToolIntentRepository,
        ApprovalRepository: MemoryApprovalRepository,
        DecisionAuditRepository: MemoryDecisionAuditRepository,
    }
)
