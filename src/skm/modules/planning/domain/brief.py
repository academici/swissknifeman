"""Contract declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID

    from skm.kernel.ids import FileVersionId, PlanId, PrincipalId, WorkspaceId


class BriefChannel(StrEnum):
    CHAT = "chat"
    ISSUE = "issue"
    MEETING = "meeting"
    DOCUMENT = "document"
    OTHER = "other"


class BriefMessageKind(StrEnum):
    OWNER = "owner"
    RECORD = "record"


@dataclass(frozen=True, slots=True)
class BriefMessage:
    key: str
    at: datetime | date | None
    channel: BriefChannel | None
    kind: BriefMessageKind
    text: str


@dataclass(frozen=True, slots=True)
class Brief:
    messages: tuple[BriefMessage, ...]
    constraints: tuple[str, ...]
    environment: str | None
    out_of_scope: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class ResearchReference:
    reference: str
    content_digest: str


@dataclass(frozen=True, slots=True)
class DesignBrief:
    id: UUID
    workspace_id: WorkspaceId
    plan_id: PlanId
    goal: str
    context_md: str | None
    constraints: tuple[str, ...]
    rag_file_version_ids: tuple[FileVersionId, ...]
    research_references: tuple[ResearchReference, ...]
    created_by: PrincipalId
    created_at: datetime
    visa_policy: Literal["optional", "required"] = "optional"
