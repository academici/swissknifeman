"""Domain events of the ``runtimes`` module (runtimes §9)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, override
from uuid import UUID

from skm.kernel.events import DomainEvent
from skm.kernel.ids import HostId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.runtimes.generated import events as generated

from .capability import Capability, CapabilityStatus
from .ids import RuntimeId, runtime_stream_id
from .installation import AuthState

__all__ = [
    "EVENT_TYPES",
    "CapabilityVerified",
    "HostRuntimeRecordedItem",
    "HostRuntimesRecorded",
]

EVENT_TYPES = (
    "urn:skm:runtimes:event:capability-verified:v1",
    "urn:skm:runtimes:event:host-runtimes-recorded:v1",
)


@dataclass(frozen=True, slots=True)
class HostRuntimeRecordedItem:
    runtime_id: RuntimeId
    version: str | None
    auth_state: AuthState


@dataclass(frozen=True, slots=True)
class HostRuntimesRecorded(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:runtimes:event:host-runtimes-recorded:v1"
    stream_kind: ClassVar[str] = "host"

    host_id: HostId
    runtimes: tuple[HostRuntimeRecordedItem, ...]
    removed: tuple[RuntimeId, ...]

    @override
    def stream_id(self) -> UUID:
        return self.host_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return None

    @override
    def payload(self) -> JsonObject:
        return generated.HostRuntimesRecorded(
            host_id=self.host_id,
            runtimes=tuple(
                generated.HostRuntimesRecordedRuntimesItem(
                    runtime_id=item.runtime_id,
                    version=item.version,
                    auth_state=item.auth_state.value,
                )
                for item in self.runtimes
            ),
            removed=self.removed,
        ).to_json()


@dataclass(frozen=True, slots=True)
class CapabilityVerified(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:runtimes:event:capability-verified:v1"
    stream_kind: ClassVar[str] = "runtime"

    runtime_id: RuntimeId
    runtime_version: str | None
    capability: Capability
    status: CapabilityStatus

    @override
    def stream_id(self) -> UUID:
        return runtime_stream_id(self.runtime_id)

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return None

    @override
    def payload(self) -> JsonObject:
        return generated.CapabilityVerified(
            runtime_id=self.runtime_id,
            runtime_version=self.runtime_version,
            capability=generated.Capability(self.capability.value),
            status=self.status.value,
        ).to_json()
