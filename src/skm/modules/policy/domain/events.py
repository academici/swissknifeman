"""Events of the policy module (policy §9).

Every event belongs to the stream ``intent`` with ``stream_id = intent_id``; ``workspace_id`` is the workspace
of the intent (not part of the payload). Payloads carry ids, kinds and digests, never the arguments, so any
subscriber or SSE client may read them. The JSON form comes from the generated event DTOs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Literal, override
from uuid import UUID

from skm.kernel.events import DomainEvent
from skm.kernel.ids import PrincipalId, ScopeId, ToolIntentId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.policy.domain.approval import ApprovalId
from skm.modules.policy.domain.tool_intent import EffectKind, IntentOutcome, IntentState, RiskClass
from skm.modules.policy.generated import events as generated

__all__ = [
    "EVENT_TYPES",
    "IntentApproved",
    "IntentDenied",
    "IntentExecutionStarted",
    "IntentProposed",
    "IntentResolved",
]

EVENT_TYPES = (
    "urn:skm:policy:event:intent-approved:v1",
    "urn:skm:policy:event:intent-denied:v1",
    "urn:skm:policy:event:intent-execution-started:v1",
    "urn:skm:policy:event:intent-proposed:v1",
    "urn:skm:policy:event:intent-resolved:v1",
)


@dataclass(frozen=True, slots=True)
class IntentProposed(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:policy:event:intent-proposed:v1"
    stream_kind: ClassVar[str] = "intent"

    intent_id: ToolIntentId
    workspace_id: WorkspaceId
    scope_id: ScopeId
    kind: EffectKind
    risk: RiskClass
    args_digest: str
    state: IntentState
    subject_ref: str

    @override
    def stream_id(self) -> UUID:
        return self.intent_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.IntentProposed(
            intent_id=self.intent_id,
            scope_id=self.scope_id,
            kind=generated.EffectKind(self.kind.value),
            risk=generated.RiskClass(self.risk.value),
            args_digest=self.args_digest,
            state=self.state.value,
            subject_ref=self.subject_ref,
        ).to_json()


@dataclass(frozen=True, slots=True)
class IntentApproved(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:policy:event:intent-approved:v1"
    stream_kind: ClassVar[str] = "intent"

    intent_id: ToolIntentId
    workspace_id: WorkspaceId
    approval_id: ApprovalId
    approver_id: PrincipalId
    auto: bool
    expires_at: datetime

    @override
    def stream_id(self) -> UUID:
        return self.intent_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.IntentApproved(
            intent_id=self.intent_id,
            approval_id=self.approval_id,
            approver_id=self.approver_id,
            auto=self.auto,
            expires_at=self.expires_at,
        ).to_json()


@dataclass(frozen=True, slots=True)
class IntentDenied(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:policy:event:intent-denied:v1"
    stream_kind: ClassVar[str] = "intent"

    intent_id: ToolIntentId
    workspace_id: WorkspaceId
    by: PrincipalId
    reason: str

    @override
    def stream_id(self) -> UUID:
        return self.intent_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.IntentDenied(intent_id=self.intent_id, by=self.by, reason=self.reason).to_json()


@dataclass(frozen=True, slots=True)
class IntentExecutionStarted(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:policy:event:intent-execution-started:v1"
    stream_kind: ClassVar[str] = "intent"

    intent_id: ToolIntentId
    workspace_id: WorkspaceId
    approval_id: ApprovalId

    @override
    def stream_id(self) -> UUID:
        return self.intent_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.IntentExecutionStarted(
            intent_id=self.intent_id, approval_id=self.approval_id
        ).to_json()


@dataclass(frozen=True, slots=True)
class IntentResolved(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:policy:event:intent-resolved:v1"
    stream_kind: ClassVar[str] = "intent"

    intent_id: ToolIntentId
    workspace_id: WorkspaceId
    outcome: IntentOutcome | Literal["expired"]

    @override
    def stream_id(self) -> UUID:
        return self.intent_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.IntentResolved(
            intent_id=self.intent_id,
            outcome=self.outcome,
        ).to_json()
