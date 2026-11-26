"""Tables of ``skm_integrations`` in the memory backend state (integrations §6, §11).

The tables live in ``MemoryBackendState.modules["integrations"]``; a unit of work operates on a deep copy so
a rollback drops uncommitted mutations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.modules.integrations.domain.observed import AppliedFileRecord
from skm.modules.integrations.domain.projection import Projection, ProjectionId

__all__ = [
    "STATE_KEY",
    "MemoryIntegrationsState",
    "StoredProjection",
    "integrations_state",
]

STATE_KEY: Final = "integrations"


@dataclass(frozen=True, slots=True)
class StoredProjection:
    projection: Projection
    created_at: datetime
    updated_at: datetime


@dataclass
class MemoryIntegrationsState:
    projections: dict[ProjectionId, StoredProjection] = field(
        default_factory=dict[ProjectionId, StoredProjection]
    )
    files: dict[ProjectionId, tuple[AppliedFileRecord, ...]] = field(
        default_factory=dict[ProjectionId, tuple[AppliedFileRecord, ...]]
    )


def integrations_state(state: MemoryBackendState) -> MemoryIntegrationsState:
    found = state.modules.get(STATE_KEY)
    if found is None:
        found = MemoryIntegrationsState()
        state.modules[STATE_KEY] = found
    if not isinstance(found, MemoryIntegrationsState):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            "integrations memory state is malformed",
            details={"module": STATE_KEY},
        )
    return found
