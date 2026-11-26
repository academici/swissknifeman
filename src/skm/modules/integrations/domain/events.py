"""Domain events of the ``integrations`` module (integrations §9)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, cast, override
from uuid import UUID

from skm.kernel.events import DomainEvent
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.integrations.generated import events as generated

from .decisions import FileDecisionKind
from .projection import ProjectionId, ProjectionState

__all__ = [
    "EVENTS",
    "EVENT_TYPES",
    "DriftedProjectionFile",
    "FailedProjectionFile",
    "HookDeliveryFailed",
    "HookTestRequested",
    "ProjectionApplied",
    "ProjectionDriftDetected",
    "ProjectionRemoved",
]

EVENT_TYPES: tuple[str, ...] = (
    "urn:skm:integrations:event:projection-applied:v1",
    "urn:skm:integrations:event:projection-drift-detected:v1",
    "urn:skm:integrations:event:projection-removed:v1",
    "urn:skm:integrations:event:hook-delivery-failed:v1",
    "urn:skm:integrations:event:hook-test-requested:v1",
)


@dataclass(frozen=True, slots=True)
class FailedProjectionFile:
    relative_path: str
    error_code: str


@dataclass(frozen=True, slots=True)
class DriftedProjectionFile:
    path: str
    decision: FileDecisionKind


@dataclass(frozen=True, slots=True)
class ProjectionApplied(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:integrations:event:projection-applied:v1"
    stream_kind: ClassVar[str] = "projection"

    projection_id: ProjectionId
    workspace_id: WorkspaceId
    state: ProjectionState
    applied: int
    conflicts: tuple[str, ...]
    failed: tuple[FailedProjectionFile, ...]
    adopted: tuple[str, ...]
    removed: tuple[str, ...]

    @override
    def stream_id(self) -> UUID:
        return self.projection_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.ProjectionApplied(
            projection_id=self.projection_id,
            state=cast("Any", self.state.value),
            applied=self.applied,
            conflicts=self.conflicts,
            failed=tuple(
                generated.ProjectionAppliedFailedItem(
                    relative_path=item.relative_path,
                    error_code=item.error_code,
                )
                for item in self.failed
            ),
            adopted=self.adopted,
            removed=self.removed,
        ).to_json()


@dataclass(frozen=True, slots=True)
class ProjectionDriftDetected(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:integrations:event:projection-drift-detected:v1"
    stream_kind: ClassVar[str] = "projection"

    projection_id: ProjectionId
    workspace_id: WorkspaceId
    files: tuple[DriftedProjectionFile, ...]

    @override
    def stream_id(self) -> UUID:
        return self.projection_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.ProjectionDriftDetected(
            projection_id=self.projection_id,
            files=tuple(
                generated.ProjectionDriftDetectedFilesItem(
                    path=item.path,
                    decision=cast("Any", item.decision.value),
                )
                for item in self.files
            ),
        ).to_json()


@dataclass(frozen=True, slots=True)
class ProjectionRemoved(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:integrations:event:projection-removed:v1"
    stream_kind: ClassVar[str] = "projection"

    projection_id: ProjectionId
    workspace_id: WorkspaceId
    removed: tuple[str, ...]
    left_modified: tuple[str, ...]

    @override
    def stream_id(self) -> UUID:
        return self.projection_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.ProjectionRemoved(
            projection_id=self.projection_id,
            removed=self.removed,
            left_modified=self.left_modified,
        ).to_json()


@dataclass(frozen=True, slots=True)
class HookDeliveryFailed(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:integrations:event:hook-delivery-failed:v1"
    stream_kind: ClassVar[str] = "hook_delivery"

    delivery_id: UUID
    workspace_id: WorkspaceId | None
    subscription_id: str
    subscription_digest: str
    event_id: UUID
    failed_event_type: str
    hook_class: str
    failure_policy: str
    blocking: bool
    attempts: int
    reason: str
    status: int | None
    run_id: UUID | None = None
    task_id: UUID | None = None
    project_id: UUID | None = None

    @override
    def stream_id(self) -> UUID:
        return self.delivery_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.HookDeliveryFailed(
            delivery_id=self.delivery_id,
            subscription_id=self.subscription_id,
            subscription_digest=self.subscription_digest,
            event_id=self.event_id,
            event_type=self.failed_event_type,
            class_=cast("Any", self.hook_class),
            failure_policy=cast("Any", self.failure_policy),
            blocking=self.blocking,
            attempts=self.attempts,
            reason=self.reason,
            status=self.status,
            run_id=self.run_id,
            task_id=self.task_id,
            project_id=self.project_id,
        ).to_json()


@dataclass(frozen=True, slots=True)
class HookTestRequested(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:integrations:event:hook-test-requested:v1"
    stream_kind: ClassVar[str] = "hook_delivery"

    test_id: UUID
    workspace_id: WorkspaceId
    subscription_id: str
    requested_by: UUID
    project_id: ProjectId | None = None

    @override
    def stream_id(self) -> UUID:
        return self.test_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.HookTestRequested(
            test_id=self.test_id,
            subscription_id=self.subscription_id,
            requested_by=self.requested_by,
            project_id=self.project_id,
        ).to_json()


EVENTS: tuple[type[DomainEvent], ...] = (
    ProjectionApplied,
    ProjectionDriftDetected,
    ProjectionRemoved,
    HookDeliveryFailed,
    HookTestRequested,
)
