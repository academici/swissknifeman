"""Tables of ``skm_runtimes`` in the memory backend state (runtimes §6, §11).

The tables live in ``MemoryBackendState.modules["runtimes"]``; a unit of work works on a deep copy, so a
rollback drops uncommitted changes. ``capability_verifications`` is append-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.ids import HostId, ResourceVersionId, WorkerId
from skm.modules.runtimes.domain.catalog_records import (
    CanonicalModel,
    HostModelAvailability,
    ModelGuideline,
    ProviderModelOffering,
    WorkerModelSnapshot,
)
from skm.modules.runtimes.domain.classes import Effort
from skm.modules.runtimes.domain.detection import VerificationRecord
from skm.modules.runtimes.domain.ids import ModelId, RuntimeId
from skm.modules.runtimes.domain.installation import RuntimeInstallation

__all__ = [
    "STATE_KEY",
    "MemoryRuntimesState",
    "StoredVerification",
    "runtimes_state",
]

STATE_KEY: Final = "runtimes"


@dataclass(frozen=True, slots=True)
class StoredVerification:
    id: UUID
    record: VerificationRecord
    recorded_at: datetime


@dataclass
class MemoryRuntimesState:
    host_runtimes: dict[tuple[HostId, RuntimeId], RuntimeInstallation] = field(
        default_factory=dict[tuple[HostId, RuntimeId], RuntimeInstallation]
    )
    capability_verifications: list[StoredVerification] = field(default_factory=list[StoredVerification])
    canonical_models: dict[ModelId, CanonicalModel] = field(default_factory=dict[ModelId, CanonicalModel])
    provider_model_offerings: dict[tuple[RuntimeId, ModelId], ProviderModelOffering] = field(
        default_factory=dict[tuple[RuntimeId, ModelId], ProviderModelOffering]
    )
    model_guidelines: dict[tuple[ResourceVersionId, RuntimeId, ModelId], ModelGuideline] = field(
        default_factory=dict[tuple[ResourceVersionId, RuntimeId, ModelId], ModelGuideline]
    )
    worker_model_offers: dict[WorkerId, WorkerModelSnapshot] = field(
        default_factory=dict[WorkerId, WorkerModelSnapshot]
    )
    host_model_availability: dict[tuple[HostId, RuntimeId, ModelId, Effort], HostModelAvailability] = field(
        default_factory=dict[tuple[HostId, RuntimeId, ModelId, Effort], HostModelAvailability]
    )


def runtimes_state(state: MemoryBackendState) -> MemoryRuntimesState:
    found = state.modules.get(STATE_KEY)
    if found is None:
        found = MemoryRuntimesState()
        state.modules[STATE_KEY] = found
    if not isinstance(found, MemoryRuntimesState):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "runtimes memory state is malformed", details={"module": STATE_KEY}
        )
    return found
