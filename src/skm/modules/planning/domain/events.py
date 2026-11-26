"""Domain events of the planning module (planning §9).

Every event lives in the stream ``plan`` / ``plan_id``; a payload carries digests and ids, never the
specification document. ``workspace_id`` scopes the event and is part of the payload only for ``PlanCreated``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Literal, override

from skm.kernel.events import DomainEvent
from skm.modules.planning.generated import events as generated

if TYPE_CHECKING:
    from uuid import UUID

    from skm.kernel.ids import PlanId, ProjectId, RevisionId, WorkspaceId
    from skm.kernel.json_types import JsonObject
    from skm.modules.planning.domain.draft import DraftId
    from skm.modules.planning.domain.plan import PlanPurpose
    from skm.modules.planning.domain.revision import RevisionOrigin

__all__ = [
    "EVENT_TYPES",
    "DraftAbandoned",
    "DraftOpened",
    "DraftRebased",
    "DraftSaved",
    "PlanArchived",
    "PlanCreated",
    "PlanRevisionPublished",
    "PlanRevisionRestored",
]

EVENT_TYPES = (
    "urn:skm:planning:event:draft-abandoned:v1",
    "urn:skm:planning:event:draft-opened:v1",
    "urn:skm:planning:event:draft-rebased:v1",
    "urn:skm:planning:event:draft-saved:v1",
    "urn:skm:planning:event:plan-archived:v1",
    "urn:skm:planning:event:plan-created:v1",
    "urn:skm:planning:event:plan-revision-published:v1",
    "urn:skm:planning:event:plan-revision-restored:v1",
)

_PREFIX = "urn:skm:planning:event:"


def _urn(name: str) -> str:
    return f"{_PREFIX}{name}:v1"


@dataclass(frozen=True, slots=True)
class PlanCreated(DomainEvent):
    event_type: ClassVar[str] = _urn("plan-created")
    stream_kind: ClassVar[str] = "plan"

    plan_id: PlanId
    workspace_id: WorkspaceId
    project_id: ProjectId
    alias: str
    title: str
    purpose: PlanPurpose

    @override
    def stream_id(self) -> UUID:
        return self.plan_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.PlanCreated(
            plan_id=self.plan_id,
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            alias=self.alias,
            title=self.title,
            purpose=self.purpose.value,
        ).to_json()


@dataclass(frozen=True, slots=True)
class DraftOpened(DomainEvent):
    event_type: ClassVar[str] = _urn("draft-opened")
    stream_kind: ClassVar[str] = "plan"

    plan_id: PlanId
    workspace_id: WorkspaceId
    draft_id: DraftId
    base_revision_id: RevisionId | None
    source: Literal["current", "empty", "template", "import"]
    edit_version: int

    @override
    def stream_id(self) -> UUID:
        return self.plan_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.DraftOpened(
            plan_id=self.plan_id,
            draft_id=self.draft_id,
            base_revision_id=self.base_revision_id,
            source=self.source,
            edit_version=self.edit_version,
        ).to_json()


@dataclass(frozen=True, slots=True)
class DraftSaved(DomainEvent):
    event_type: ClassVar[str] = _urn("draft-saved")
    stream_kind: ClassVar[str] = "plan"

    plan_id: PlanId
    workspace_id: WorkspaceId
    draft_id: DraftId
    edit_version: int
    document_digest: str
    error_count: int
    warning_count: int
    info_count: int

    @override
    def stream_id(self) -> UUID:
        return self.plan_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.DraftSaved(
            plan_id=self.plan_id,
            draft_id=self.draft_id,
            edit_version=self.edit_version,
            document_digest=self.document_digest,
            counts=generated.DraftSavedCounts(
                error=self.error_count, warning=self.warning_count, info=self.info_count
            ),
        ).to_json()


@dataclass(frozen=True, slots=True)
class DraftRebased(DomainEvent):
    event_type: ClassVar[str] = _urn("draft-rebased")
    stream_kind: ClassVar[str] = "plan"

    plan_id: PlanId
    workspace_id: WorkspaceId
    draft_id: DraftId
    edit_version: int
    previous_base_revision_id: RevisionId | None
    base_revision_id: RevisionId | None
    taken_from_current: int
    kept_from_draft: int
    resolved: int

    @override
    def stream_id(self) -> UUID:
        return self.plan_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.DraftRebased(
            plan_id=self.plan_id,
            draft_id=self.draft_id,
            edit_version=self.edit_version,
            previous_base_revision_id=self.previous_base_revision_id,
            base_revision_id=self.base_revision_id,
            taken_from_current=self.taken_from_current,
            kept_from_draft=self.kept_from_draft,
            resolved=self.resolved,
        ).to_json()


@dataclass(frozen=True, slots=True)
class DraftAbandoned(DomainEvent):
    event_type: ClassVar[str] = _urn("draft-abandoned")
    stream_kind: ClassVar[str] = "plan"

    plan_id: PlanId
    workspace_id: WorkspaceId
    draft_id: DraftId
    edit_version: int
    reason: Literal["user", "plan_archived"]

    @override
    def stream_id(self) -> UUID:
        return self.plan_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.DraftAbandoned(
            plan_id=self.plan_id,
            draft_id=self.draft_id,
            edit_version=self.edit_version,
            reason=self.reason,
        ).to_json()


@dataclass(frozen=True, slots=True)
class PlanRevisionPublished(DomainEvent):
    event_type: ClassVar[str] = _urn("plan-revision-published")
    stream_kind: ClassVar[str] = "plan"

    plan_id: PlanId
    workspace_id: WorkspaceId
    revision_id: RevisionId
    revision_no: int
    parent_revision_id: RevisionId | None
    content_digest: str
    title: str
    origin: RevisionOrigin
    draft_id: DraftId | None

    @override
    def stream_id(self) -> UUID:
        return self.plan_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.PlanRevisionPublished(
            plan_id=self.plan_id,
            revision_id=self.revision_id,
            revision_no=self.revision_no,
            parent_revision_id=self.parent_revision_id,
            content_digest=self.content_digest,
            title=self.title,
            origin=self.origin.value,
            draft_id=self.draft_id,
        ).to_json()


@dataclass(frozen=True, slots=True)
class PlanRevisionRestored(DomainEvent):
    event_type: ClassVar[str] = _urn("plan-revision-restored")
    stream_kind: ClassVar[str] = "plan"

    plan_id: PlanId
    workspace_id: WorkspaceId
    revision_id: RevisionId
    revision_no: int
    restored_from_revision_id: RevisionId
    restored_from_revision_no: int
    content_digest: str

    @override
    def stream_id(self) -> UUID:
        return self.plan_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.PlanRevisionRestored(
            plan_id=self.plan_id,
            revision_id=self.revision_id,
            revision_no=self.revision_no,
            restored_from_revision_id=self.restored_from_revision_id,
            restored_from_revision_no=self.restored_from_revision_no,
            content_digest=self.content_digest,
        ).to_json()


@dataclass(frozen=True, slots=True)
class PlanArchived(DomainEvent):
    event_type: ClassVar[str] = _urn("plan-archived")
    stream_kind: ClassVar[str] = "plan"

    plan_id: PlanId
    workspace_id: WorkspaceId
    project_id: ProjectId
    alias: str
    abandoned_draft_ids: tuple[DraftId, ...]

    @override
    def stream_id(self) -> UUID:
        return self.plan_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.PlanArchived(
            plan_id=self.plan_id,
            project_id=self.project_id,
            alias=self.alias,
            abandoned_draft_ids=self.abandoned_draft_ids,
        ).to_json()
