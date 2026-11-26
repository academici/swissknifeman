"""PostgreSQL adapters of the policy repository ports (policy §3, §6, §11; DDL ``0012``).

``REPOSITORIES`` maps each port to its factory over the unit-of-work connection; it is merged with the core
table by ``bootstrap.adapters.postgres_repository_table``. The intent repository takes an optional ``clock``
(the system clock by default) for ``updated_at``.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

import psycopg

from skm.adapters.postgres.policy.approvals import PostgresApprovalRepository
from skm.adapters.postgres.policy.audit import PostgresDecisionAuditRepository
from skm.adapters.postgres.policy.intents import PostgresToolIntentRepository
from skm.modules.policy.ports import ApprovalRepository, DecisionAuditRepository, ToolIntentRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[psycopg.Connection], object]] = MappingProxyType(
    {
        ToolIntentRepository: PostgresToolIntentRepository,
        ApprovalRepository: PostgresApprovalRepository,
        DecisionAuditRepository: PostgresDecisionAuditRepository,
    }
)
