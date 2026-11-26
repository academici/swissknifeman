"""Ports of runtimes (runtimes §6): the session contract ``AgentRuntime`` and its gateways/repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from skm.kernel.gateways import host_gateway, shared_gateway
from skm.kernel.ports_uow import repository_port

from .domain.ids import is_runtime_id, require_utc
from .domain.request import ProcessOwnership

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skm.kernel.ids import HostId, ResourceVersionId, WorkerId
    from skm.modules.runtimes.domain.capability import (
        CapabilityRecord,
        RuntimeCapabilities,
        SelfLoadedSource,
        VerificationContext,
    )
    from skm.modules.runtimes.domain.catalog_records import (
        CanonicalModel,
        HostModelAvailability,
        ModelGuideline,
        ProviderModelOffering,
        WorkerModelSnapshot,
    )
    from skm.modules.runtimes.domain.classes import Effort
    from skm.modules.runtimes.domain.detection import CancellationResult, DetectProbe, VerificationRecord
    from skm.modules.runtimes.domain.error_rules import ErrorRule
    from skm.modules.runtimes.domain.ids import Digest, RuntimeId
    from skm.modules.runtimes.domain.installation import RuntimeInstallation
    from skm.modules.runtimes.domain.request import AgentRequest
    from skm.modules.runtimes.domain.result import RuntimeResult
    from skm.modules.runtimes.domain.session_events import SessionEvent


@host_gateway
class AgentRuntime(Protocol):
    """Host gateway implemented by ``adapters/runtimes/<p>/``; used only by host operations.

    Synchronous; process streams are read inside the adapter. ``start`` takes an admitted, pinned request and
    never reroutes it. ``events`` blocks and ends with exactly one terminal event (``validate_event_stream``);
    ``result`` is idempotent after it and always carries usage.
    """

    runtime_id: RuntimeId

    def capabilities(self) -> RuntimeCapabilities: ...
    def detect(self, probe: DetectProbe) -> RuntimeInstallation: ...
    def self_loaded_context(self, request: AgentRequest) -> tuple[SelfLoadedSource, ...]: ...
    def start(self, request: AgentRequest) -> SessionHandle: ...
    def events(self, handle: SessionHandle) -> Iterator[SessionEvent]: ...
    def cancel(self, handle: SessionHandle, *, grace_seconds: float) -> CancellationResult: ...
    def result(self, handle: SessionHandle) -> RuntimeResult: ...


@dataclass(frozen=True, slots=True)
class SessionHandle:
    """A started session; ``ownership`` is the actual spawned unit (None only without a child process)."""

    runtime_id: RuntimeId
    request_id: str  # = AgentRequest.request_id (StepId)
    pid: int | None
    process_start_ticks: int | None  # with pid: process identity that survives pid reuse
    started_at: datetime
    ownership: ProcessOwnership | None

    def __post_init__(self) -> None:
        if not is_runtime_id(self.runtime_id):
            raise ValueError(f"not a runtime id: {self.runtime_id!r}")
        require_utc(self.started_at, "started_at")
        if self.pid is not None and self.pid <= 0:
            raise ValueError("pid must be positive")
        if self.ownership is not None:
            if not isinstance(self.ownership, ProcessOwnership):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise TypeError("ownership must be a ProcessOwnership")
            owner = self.ownership.owner
            if owner.unit_kind != "step" or owner.unit_id != UUID(self.request_id):
                raise ValueError("a session is owned by its step: unit_kind=step, unit_id=request_id")


@host_gateway
class RuntimeRegistry(Protocol):
    """Host gateway (``HostGateways.runtime_registry``) assembled by ``bootstrap/runtimes.py``."""

    def ids(self) -> frozenset[RuntimeId]: ...
    def get(self, runtime_id: RuntimeId) -> AgentRuntime: ...  # NOT_FOUND(kind=runtime)


@host_gateway
class WorkerModelOfferPolicy(Protocol):
    """Machine-local model grants and account status used to publish a full worker snapshot."""

    def now(self) -> datetime: ...
    def account_available(self, installation: RuntimeInstallation) -> bool: ...
    def observe_installation(
        self, runtime: AgentRuntime, installation: RuntimeInstallation | None
    ) -> None: ...
    def allows_model(self, runtime_id: RuntimeId, model_id: str, effort: Effort) -> bool: ...


@shared_gateway
class CapabilityCatalog(Protocol):
    """Static capabilities of built-in adapters and allowed plugins; data only, in both gateway tables."""

    def static(self, runtime_id: RuntimeId) -> RuntimeCapabilities: ...
    def error_rules(self, runtime_id: RuntimeId) -> tuple[ErrorRule, ...]: ...
    def registered(self) -> frozenset[RuntimeId]: ...


@repository_port
class HostRuntimeRepository(Protocol):
    def list_for_host(self, host_id: HostId) -> tuple[RuntimeInstallation, ...]: ...
    def upsert(self, installation: RuntimeInstallation) -> None: ...
    def remove_missing(self, host_id: HostId, present: frozenset[RuntimeId]) -> None: ...


@repository_port
class CapabilityVerificationRepository(Protocol):
    def add(self, record: VerificationRecord) -> None: ...
    def latest(
        self,
        runtime_id: RuntimeId,
        runtime_version: str | None,
        verification_key: Digest | None,
        *,
        installation: VerificationContext | None = None,
    ) -> tuple[CapabilityRecord, ...]:
        """Optionally scope to exact installation facts while discovering a recorded launch template."""
        ...


@repository_port
class ModelCatalogRepository(Protocol):
    """Stable model identities, current offerings, and guidelines scoped to a published resource."""

    def add_model(self, model: CanonicalModel) -> None: ...
    def list_models(self) -> tuple[CanonicalModel, ...]: ...
    def upsert_offering(self, offering: ProviderModelOffering) -> None: ...
    def list_offerings(self, runtime_id: RuntimeId) -> tuple[ProviderModelOffering, ...]: ...
    def add_guideline(self, guideline: ModelGuideline) -> None: ...
    def list_guidelines(self, resource_version_id: ResourceVersionId) -> tuple[ModelGuideline, ...]: ...


@repository_port
class HostModelAvailabilityRepository(Protocol):
    def upsert(self, observation: HostModelAvailability) -> None:
        """Keep the newest observation for each host/runtime/model/effort key."""
        ...

    def list_fresh(self, host_id: HostId, *, as_of: datetime) -> tuple[HostModelAvailability, ...]:
        """Return observations whose half-open validity interval contains as_of."""
        ...

    def replace_worker_snapshot(self, snapshot: WorkerModelSnapshot) -> bool:
        """Replace the complete snapshot atomically for its validated current publisher."""
        ...

    def worker_snapshot(self, worker_id: WorkerId) -> WorkerModelSnapshot | None: ...
