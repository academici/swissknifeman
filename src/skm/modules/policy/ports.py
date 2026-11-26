"""Ports of the policy module (policy §6): repositories of intents, approvals and the decision audit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from skm.kernel.gateways import host_gateway
from skm.kernel.ports_uow import repository_port

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from skm.kernel.ids import ScopeId, ToolIntentId, WorkspaceId
    from skm.kernel.pagination import Page
    from skm.modules.policy.domain.approval import Approval, ApprovalId
    from skm.modules.policy.domain.operations import PathOrigin
    from skm.modules.policy.domain.tool_intent import EffectKind, IntentState, ToolDecisionRecord, ToolIntent


@repository_port
class ToolIntentRepository(Protocol):
    def get(self, intent_id: ToolIntentId) -> ToolIntent: ...
    def get_for_update(self, intent_id: ToolIntentId) -> ToolIntent:
        """The intent under a row lock until the end of the unit of work (consume, outcome, expiry)."""
        ...

    def add(self, intent: ToolIntent) -> None:
        """``ALREADY_EXISTS`` when an active intent of the same ``(scope, kind, digest)`` exists."""
        ...

    def save(self, intent: ToolIntent, *, expected_version: int) -> None:
        """Compare-and-set on ``row_version``; identity and arguments are never rewritten."""
        ...

    def find_active(self, scope_id: ScopeId, kind: EffectKind, args_digest: str) -> ToolIntent | None:
        """The intent in ``proposed|approved|executing`` of that effect, if any."""
        ...

    def list(
        self,
        *,
        workspace_id: WorkspaceId,
        scope_id: ScopeId | None,
        state: IntentState | None,
        after: str | None,
        limit: int,
    ) -> Page[ToolIntent]: ...
    def expired(self, now: datetime, *, limit: int) -> tuple[ToolIntent, ...]:
        """Open intents (``proposed``; ``approved`` without a usable approval) due at ``now``, locked and
        skipping rows other transactions hold."""
        ...


@repository_port
class ApprovalRepository(Protocol):
    def add(self, approval: Approval) -> None: ...
    def for_intent(self, intent_id: ToolIntentId) -> tuple[Approval, ...]:
        """In order of ``(created_at, id)``."""
        ...

    def mark_used(self, approval_id: ApprovalId, used_at: datetime) -> None:
        """Set ``used_at`` once (``UPDATE ... WHERE used_at IS NULL``); a spent or unknown approval is
        ``Forbidden(APPROVAL_MISMATCH)``."""
        ...


@repository_port
class DecisionAuditRepository(Protocol):
    def add_many(self, records: Sequence[ToolDecisionRecord]) -> None: ...
    def for_scope(
        self, scope_id: ScopeId, *, operation: str | None = None, limit: int = 200
    ) -> tuple[ToolDecisionRecord, ...]:
        """In order of ``(at, id)``; ``operation`` keeps the rows of one operation (the risk signal)."""
        ...


@host_gateway
class PathFacts(Protocol):
    def resolve(self, path: str, cwd: str) -> str: ...
    def origins(self, path: str) -> frozenset[PathOrigin]: ...
    def expand(self, pattern: str, cwd: str) -> tuple[str, ...] | None: ...


@host_gateway
class ExternalFileWriter(Protocol):
    def __call__(self, destination: str, data: bytes) -> None: ...
