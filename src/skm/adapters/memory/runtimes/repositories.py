"""Memory implementations of the ``runtimes`` repository ports (runtimes §6, §11)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from skm.adapters.memory.access.state import STATE_KEY as ACCESS_KEY
from skm.adapters.memory.access.state import access_state
from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.extensions.mapping import extensions_state
from skm.adapters.memory.runtimes.state import MemoryRuntimesState, StoredVerification, runtimes_state
from skm.adapters.memory.workspace.state import STATE_KEY as WORKSPACE_KEY
from skm.adapters.memory.workspace.state import workspace_state
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed, error_for
from skm.kernel.ids import HostId, ResourceVersionId, WorkerId
from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityRecord,
    VerificationContext,
    validate_verification_record,
)
from skm.modules.runtimes.domain.catalog_records import (
    CanonicalModel,
    HostModelAvailability,
    ModelGuideline,
    ProviderModelOffering,
    WorkerModelSnapshot,
)
from skm.modules.runtimes.domain.detection import VerificationRecord
from skm.modules.runtimes.domain.ids import Digest, RuntimeId
from skm.modules.runtimes.domain.installation import RuntimeInstallation
from skm.platform.system_clock import SystemClock

__all__ = [
    "MemoryCapabilityVerificationRepository",
    "MemoryHostModelAvailabilityRepository",
    "MemoryHostRuntimeRepository",
    "MemoryModelCatalogRepository",
]


def _require_reference(found: bool, constraint: str) -> None:
    if not found:
        raise error_for(
            ErrorCode.INVALID_REFERENCE, "foreign key violated", details={"constraint": constraint}
        )


def _validate_verification(record: VerificationRecord) -> None:
    validate_verification_record(record)
    if not isinstance(record.recorded_by, UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "recorded_by must be a UUID")


class _Tables:
    def __init__(self, state: MemoryBackendState, *, clock: Clock | None = None) -> None:
        self._state = state
        self._tables: MemoryRuntimesState = runtimes_state(state)
        self._clock: Clock = clock if clock is not None else SystemClock()

    def _writable(self) -> MemoryRuntimesState:
        self._state.core.require_writable()
        return self._tables

    def _now(self) -> datetime:
        now = self._clock.now()
        return now if now.tzinfo is not None else now.replace(tzinfo=UTC)


class MemoryHostRuntimeRepository(_Tables):
    """In-memory ``HostRuntimeRepository`` over ``skm_runtimes.host_runtimes``."""

    def list_for_host(self, host_id: HostId) -> tuple[RuntimeInstallation, ...]:
        found = [inst for (hid, _), inst in self._tables.host_runtimes.items() if hid == host_id]
        found.sort(key=lambda item: item.runtime_id)
        return tuple(found)

    def upsert(self, installation: RuntimeInstallation) -> None:
        tables = self._writable()
        if (
            WORKSPACE_KEY in self._state.modules
            and installation.host_id not in workspace_state(self._state).hosts
        ):
            raise error_for(
                ErrorCode.INVALID_REFERENCE,
                "foreign key violated",
                details={"constraint": "fk_host_runtimes__hosts"},
            )
        tables.host_runtimes[(installation.host_id, installation.runtime_id)] = installation

    def remove_missing(self, host_id: HostId, present: frozenset[RuntimeId]) -> None:
        tables = self._writable()
        to_remove = [key for key in tables.host_runtimes if key[0] == host_id and key[1] not in present]
        for key in to_remove:
            del tables.host_runtimes[key]


class MemoryCapabilityVerificationRepository(_Tables):
    """In-memory append-only ``CapabilityVerificationRepository``."""

    def add(self, record: VerificationRecord) -> None:
        tables = self._writable()
        _validate_verification(record)
        if (
            ACCESS_KEY in self._state.modules
            and record.recorded_by not in access_state(self._state).principals
        ):
            raise error_for(
                ErrorCode.INVALID_REFERENCE,
                "foreign key violated",
                details={"constraint": "fk_capability_verifications__principals"},
            )

        dedup_key = (
            record.runtime_id,
            record.runtime_version or "",
            record.verification_key or "",
            record.record.capability.value,
            record.record.last_verified_at,
            record.record.status.value,
        )
        for existing in tables.capability_verifications:
            existing_key = (
                existing.record.runtime_id,
                existing.record.runtime_version or "",
                existing.record.verification_key or "",
                existing.record.record.capability.value,
                existing.record.record.last_verified_at,
                existing.record.record.status.value,
            )
            if existing_key == dedup_key:
                return

        tables.capability_verifications.append(
            StoredVerification(
                id=uuid4(),
                record=record,
                recorded_at=self._now(),
            )
        )

    def latest(
        self,
        runtime_id: RuntimeId,
        runtime_version: str | None,
        verification_key: Digest | None,
        *,
        installation: VerificationContext | None = None,
    ) -> tuple[CapabilityRecord, ...]:
        matching: list[tuple[int, StoredVerification]] = []
        for index, stored in enumerate(self._tables.capability_verifications):
            rec = stored.record
            if rec.runtime_id != runtime_id:
                continue
            if runtime_version is not None and rec.runtime_version not in (runtime_version, None):
                continue
            if verification_key is not None and rec.verification_key not in (verification_key, None):
                continue
            if installation is not None and (
                rec.runtime_version != runtime_version
                or rec.verification_context is None
                or replace(rec.verification_context, launch_config_digest=installation.launch_config_digest)
                != installation
            ):
                continue
            matching.append((index, stored))

        best_by_cap: dict[Capability, tuple[tuple[bool, bool, datetime, int], CapabilityRecord]] = {}
        for index, stored in matching:
            rec = stored.record
            cap = rec.record.capability
            rank = (
                verification_key is not None and rec.verification_key == verification_key,
                runtime_version is not None and rec.runtime_version == runtime_version,
                stored.recorded_at,
                index,
            )
            normalized = CapabilityRecord(
                capability=cap,
                status=rec.record.status,
                evidence=rec.record.evidence,
                tested_runtime_version=rec.runtime_version,
                limitations=rec.record.limitations,
                last_verified_at=rec.record.last_verified_at,
                verification_context=rec.verification_context,
            )
            current = best_by_cap.get(cap)
            if current is None or rank > current[0]:
                best_by_cap[cap] = (rank, normalized)

        ordered_caps = [cap for cap in Capability if cap in best_by_cap]
        return tuple(best_by_cap[cap][1] for cap in ordered_caps)


class MemoryModelCatalogRepository(_Tables):
    """In-memory catalog with the same identity and reference rules as 0017/0018."""

    def add_model(self, model: CanonicalModel) -> None:
        self._writable().canonical_models.setdefault(model.model_id, model)

    def list_models(self) -> tuple[CanonicalModel, ...]:
        return tuple(row for _, row in sorted(self._tables.canonical_models.items()))

    def upsert_offering(self, offering: ProviderModelOffering) -> None:
        tables = self._writable()
        _require_reference(
            offering.model_id in tables.canonical_models, "fk_provider_model_offerings__canonical_models"
        )
        tables.provider_model_offerings[(offering.runtime_id, offering.model_id)] = offering

    def list_offerings(self, runtime_id: RuntimeId) -> tuple[ProviderModelOffering, ...]:
        return tuple(
            row
            for (runtime, _), row in sorted(self._tables.provider_model_offerings.items())
            if runtime == runtime_id
        )

    def add_guideline(self, guideline: ModelGuideline) -> None:
        tables = self._writable()
        offering = (guideline.runtime_id, guideline.model_id)
        _require_reference(
            offering in tables.provider_model_offerings, "fk_model_guidelines__provider_model_offerings"
        )
        _require_reference(
            guideline.resource_version_id in extensions_state(self._state).versions,
            "fk_model_guidelines__resource_versions",
        )
        tables.model_guidelines.setdefault((guideline.resource_version_id, *offering), guideline)

    def list_guidelines(self, resource_version_id: ResourceVersionId) -> tuple[ModelGuideline, ...]:
        return tuple(
            row
            for (version, _, _), row in sorted(self._tables.model_guidelines.items())
            if version == resource_version_id
        )


class MemoryHostModelAvailabilityRepository(_Tables):
    """In-memory host-scoped observations."""

    def upsert(self, observation: HostModelAvailability) -> None:
        tables = self._writable()
        offering = (observation.runtime_id, observation.model_id)
        _require_reference(
            observation.host_id in workspace_state(self._state).hosts, "fk_host_model_availability__hosts"
        )
        _require_reference(
            offering in tables.provider_model_offerings,
            "fk_host_model_availability__provider_model_offerings",
        )
        key = (observation.host_id, *offering, observation.effort)
        current = tables.host_model_availability.get(key)
        if current is None or observation.observed_at > current.observed_at:
            tables.host_model_availability[key] = observation

    def list_fresh(self, host_id: HostId, *, as_of: datetime) -> tuple[HostModelAvailability, ...]:
        return tuple(
            row
            for (host, _, _, _), row in sorted(self._tables.host_model_availability.items())
            if host == host_id and row.observed_at <= as_of < row.expires_at
        )

    def replace_worker_snapshot(self, snapshot: WorkerModelSnapshot) -> bool:
        tables = self._writable()
        _require_reference(
            snapshot.worker_id in workspace_state(self._state).workers,
            "fk_worker_model_offer_snapshots__workers",
        )
        current = tables.worker_model_offers.get(snapshot.worker_id)
        if current is not None and not snapshot.supersedes(current):
            return False
        tables.worker_model_offers[snapshot.worker_id] = snapshot
        return True

    def worker_snapshot(self, worker_id: WorkerId) -> WorkerModelSnapshot | None:
        return self._tables.worker_model_offers.get(worker_id)
