"""Memory implementations of the policy ports (policy §6, §11).

The checks PostgreSQL gets from constraints are made here too: a unique id, one open intent per ``(scope,
kind, digest)`` (``proposed|approved|executing``), optimistic ``row_version`` updates that never rewrite the
identity or the arguments of an intent, a single ``used_at`` per approval. Composite FKs and triggers are
not imitated (adapters §2.2): their contract cases run on PostgreSQL only.

Pages ascend by ``(created_at, id)``; the cursor is an opaque base64 JSON array of those two texts.
"""

import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import cast

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.policy.state import MemoryPolicyState, policy_state
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, NotFound, ValidationFailed
from skm.kernel.ids import ScopeId, ToolIntentId, WorkspaceId
from skm.kernel.pagination import Cursor, Page, validate_cursor, validate_page_limit
from skm.modules.policy.domain.approval import Approval, ApprovalDecision, ApprovalId
from skm.modules.policy.domain.tool_intent import (
    ACTIVE_STATES,
    EffectKind,
    IntentState,
    ToolDecisionRecord,
    ToolIntent,
)

__all__ = [
    "MemoryApprovalRepository",
    "MemoryDecisionAuditRepository",
    "MemoryToolIntentRepository",
]

_KEPT = (
    "workspace_id",
    "scope_id",
    "subject_ref",
    "actor_id",
    "kind",
    "normalized_args",
    "args_digest",
    "risk",
    "reason",
    "created_at",
    "expires_at",
)


def _bad_cursor() -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid page cursor", details={"field": "after"})


def _encode(moment: datetime, intent_id: ToolIntentId) -> Cursor:
    raw = json.dumps([moment.isoformat(), str(intent_id)], separators=(",", ":")).encode("utf-8")
    return validate_cursor(base64.urlsafe_b64encode(raw).decode("ascii"))


def _decode(cursor: str) -> tuple[str, str]:
    try:
        parts = json.loads(base64.urlsafe_b64decode(validate_cursor(cursor).encode("ascii")))
        items = cast("list[object]", parts) if isinstance(parts, list) else []
        if len(items) != 2 or not all(isinstance(item, str) for item in items):
            raise ValueError("cursor shape")
        return datetime.fromisoformat(cast("str", items[0])).isoformat(), cast("str", items[1])
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        raise _bad_cursor() from None


class _Tables:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._tables: MemoryPolicyState = policy_state(state)

    def _writable(self) -> MemoryPolicyState:
        self._state.core.require_writable()
        return self._tables


class MemoryToolIntentRepository(_Tables):
    def get(self, intent_id: ToolIntentId) -> ToolIntent:
        found = self._tables.intents.get(intent_id)
        if found is None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "tool intent not found",
                details={"kind": "tool_intent", "ref": str(intent_id)},
            )
        return found

    def get_for_update(self, intent_id: ToolIntentId) -> ToolIntent:
        # a memory unit of work is isolated by its copy of the state: nothing to lock
        return self.get(intent_id)

    def _open(self, scope_id: ScopeId, kind: EffectKind, digest: str) -> ToolIntent | None:
        return next(
            (
                item
                for item in self._tables.intents.values()
                if item.scope_id == scope_id
                and item.kind == kind
                and item.args_digest == digest
                and IntentState(item.state) in ACTIVE_STATES
            ),
            None,
        )

    def add(self, intent: ToolIntent) -> None:
        tables = self._writable()
        if intent.id in tables.intents or (
            IntentState(intent.state) in ACTIVE_STATES
            and self._open(intent.scope_id, intent.kind, intent.args_digest) is not None
        ):
            raise Conflict(
                ErrorCode.ALREADY_EXISTS, "tool intent already exists", details={"kind": "tool_intent"}
            )
        tables.intents[intent.id] = intent

    def save(self, intent: ToolIntent, *, expected_version: int) -> None:
        tables = self._writable()
        current = self.get(intent.id)
        if current.row_version != expected_version:
            raise Conflict(
                ErrorCode.VERSION_CONFLICT,
                f"version conflict: expected {expected_version}, actual {current.row_version}",
                details={"kind": "tool_intent", "expected": expected_version, "actual": current.row_version},
            )
        changed = [name for name in _KEPT if getattr(current, name) != getattr(intent, name)]
        if changed:
            raise ValueError(f"a stored tool intent keeps its {', '.join(changed)}")
        tables.intents[intent.id] = intent

    def find_active(self, scope_id: ScopeId, kind: EffectKind, args_digest: str) -> ToolIntent | None:
        return self._open(scope_id, kind, args_digest)

    def list(
        self,
        *,
        workspace_id: WorkspaceId,
        scope_id: ScopeId | None,
        state: IntentState | None,
        after: str | None,
        limit: int,
    ) -> Page[ToolIntent]:
        limit = validate_page_limit(limit)
        rows = sorted(
            (
                item
                for item in self._tables.intents.values()
                if item.workspace_id == workspace_id
                and (scope_id is None or item.scope_id == scope_id)
                and (state is None or item.state == state)
            ),
            key=lambda item: (item.created_at, str(item.id)),
        )
        if after is not None:
            start = _decode(after)
            rows = [item for item in rows if (item.created_at.isoformat(), str(item.id)) > start]
        items = rows[:limit]
        following = _encode(items[-1].created_at, items[-1].id) if len(rows) > limit else None
        return Page(items=tuple(items), next=following)

    def expired(self, now: datetime, *, limit: int) -> tuple[ToolIntent, ...]:
        usable = {
            approval.intent_id
            for approval in self._tables.approvals.values()
            if approval.decision is ApprovalDecision.APPROVE and approval.expires_at > now
        }
        due = [
            item
            for item in self._tables.intents.values()
            if (item.state is IntentState.PROPOSED and item.expires_at <= now)
            or (item.state is IntentState.APPROVED and item.id not in usable)
        ]
        due.sort(key=lambda item: (item.expires_at, str(item.id)))
        return tuple(due[:limit])


class MemoryApprovalRepository(_Tables):
    def add(self, approval: Approval) -> None:
        tables = self._writable()
        if approval.id in tables.approvals:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "approval already exists", details={"kind": "approval"})
        tables.approvals[approval.id] = approval

    def for_intent(self, intent_id: ToolIntentId) -> tuple[Approval, ...]:
        return tuple(
            sorted(
                (item for item in self._tables.approvals.values() if item.intent_id == intent_id),
                key=lambda item: (item.created_at, str(item.id)),
            )
        )

    def mark_used(self, approval_id: ApprovalId, used_at: datetime) -> None:
        tables = self._writable()
        found = tables.approvals.get(approval_id)
        if found is None or found.used_at is not None or found.decision is not ApprovalDecision.APPROVE:
            raise Forbidden(
                ErrorCode.APPROVAL_MISMATCH,
                "the approval has been used",
                details={"reason": "already_used", "approval_id": str(approval_id)},
            )
        tables.approvals[approval_id] = replace(found, used_at=used_at)


class MemoryDecisionAuditRepository(_Tables):
    def add_many(self, records: Sequence[ToolDecisionRecord]) -> None:
        self._writable().audit.extend(records)

    def for_scope(
        self, scope_id: ScopeId, *, operation: str | None = None, limit: int = 200
    ) -> tuple[ToolDecisionRecord, ...]:
        rows = sorted(
            (
                item
                for item in self._tables.audit
                if item.scope_id == scope_id and (operation is None or item.operation == operation)
            ),
            key=lambda item: (item.at, str(item.id)),
        )
        return tuple(rows[:limit])
