"""Approvals of tool intents (policy §4.6, §5.12).

An approval authorizes one intent for one digest. ``approval_matches`` is the only test of "may this approval
admit the execution now"; ``consume`` is the only way to spend it. Spending is a compare-and-set on
``used_at`` (``ApprovalRepository.mark_used``), so two concurrent admissions spend an approval once.
The approval of a human is valid as long as the approver still holds the right (checked by the caller at
consumption); the approval of the system is valid only while ``auto_approval`` would still create it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, NewType
from uuid import UUID

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID
from skm.kernel.error_codes import ErrorCategory, ErrorCode
from skm.kernel.errors import Forbidden, SkmError

from .tool_intent import EffectKind, IntentState

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from skm.kernel.ids import PrincipalId, ToolIntentId

    from .permission_set import PermissionSet
    from .tool_intent import ToolIntent

__all__ = [
    "DENY_RECORD_TTL",
    "Approval",
    "ApprovalDecision",
    "ApprovalId",
    "ApprovalRequired",
    "approval_matches",
    "approve",
    "auto_approval",
    "consume",
    "denial",
    "is_system_approval",
    "system_approval_holds",
    "usable_approval",
]

ApprovalId = NewType("ApprovalId", UUID)
DENY_RECORD_TTL = timedelta(seconds=60)  # a refusal never authorizes; the row only needs a valid window


class ApprovalRequired(SkmError):
    """``APPROVAL_REQUIRED``: the intent waits for a human (policy §7, execution §3630).

    The code is of the ``waiting`` category, which the kernel keeps for outcomes; the start of an effect
    cannot return one (the result is an admission), so the refusal is raised with that exact code and no
    effect is admitted. It is a refusal of this call, not an error of the system.
    """

    category = ErrorCategory.WAITING

    def __init__(self, intent_id: ToolIntentId, state: str) -> None:
        super().__init__(
            ErrorCode.APPROVAL_REQUIRED,
            "the intent needs an approval before it can start",
            details={"intent_id": str(intent_id), "state": state},
        )


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class Approval:
    id: ApprovalId
    intent_id: ToolIntentId
    approver_id: PrincipalId
    decision: ApprovalDecision
    args_digest: str
    single_use: bool
    expires_at: datetime
    used_at: datetime | None
    reason: str
    created_at: datetime


def approve(
    intent: ToolIntent,
    *,
    approval_id: ApprovalId,
    approver_id: PrincipalId,
    now: datetime,
    ttl: timedelta,
    single_use: bool,
    reason: str,
) -> Approval:
    """The approval a human gives to the digest the intent has now."""
    if approver_id == SYSTEM_PRINCIPAL_ID:
        raise ValueError("the system approves only through auto_approval")
    return Approval(
        id=approval_id,
        intent_id=intent.id,
        approver_id=approver_id,
        decision=ApprovalDecision.APPROVE,
        args_digest=intent.args_digest,
        single_use=single_use,
        expires_at=now + ttl,
        used_at=None,
        reason=reason,
        created_at=now,
    )


def denial(
    intent: ToolIntent, *, approval_id: ApprovalId, approver_id: PrincipalId, now: datetime, reason: str
) -> Approval:
    """The durable record of a refusal; it never matches (``approval_matches`` wants ``approve``)."""
    return Approval(
        id=approval_id,
        intent_id=intent.id,
        approver_id=approver_id,
        decision=ApprovalDecision.DENY,
        args_digest=intent.args_digest,
        single_use=False,
        expires_at=now + DENY_RECORD_TTL,
        used_at=None,
        reason=reason,
        created_at=now,
    )


def _needs_human(intent: ToolIntent, perms: PermissionSet) -> bool:
    return intent.kind is EffectKind.FS_WRITE_EXTERNAL or intent.kind in perms.effects_need_approval


def auto_approval(
    intent: ToolIntent, perms: PermissionSet, now: datetime, *, approval_id: ApprovalId
) -> Approval | None:
    """The approval of the system: only for a kind that needs no human (``kind ∉ effects_need_approval``).

    Single use, valid until the intent itself expires.
    """
    if _needs_human(intent, perms) or intent.state is not IntentState.PROPOSED:
        return None
    return Approval(
        id=approval_id,
        intent_id=intent.id,
        approver_id=SYSTEM_PRINCIPAL_ID,
        decision=ApprovalDecision.APPROVE,
        args_digest=intent.args_digest,
        single_use=True,
        expires_at=intent.expires_at,
        used_at=None,
        reason="auto-approved: the kind needs no human approval",
        created_at=now,
    )


def is_system_approval(approval: Approval) -> bool:
    return approval.approver_id == SYSTEM_PRINCIPAL_ID


def system_approval_holds(approval: Approval, intent: ToolIntent, perms: PermissionSet) -> bool:
    """A system approval is still good only while the kind needs no human approval (live configuration)."""
    return is_system_approval(approval) and not _needs_human(intent, perms)


def approval_matches(approval: Approval, intent: ToolIntent, now: datetime) -> bool:
    """``approve``, for this intent and this digest, not expired, not spent (when single use)."""
    return (
        approval.decision is ApprovalDecision.APPROVE
        and approval.intent_id == intent.id
        and approval.args_digest == intent.args_digest
        and now < approval.expires_at
        and not (approval.single_use and approval.used_at is not None)
    )


def usable_approval(approvals: Sequence[Approval], intent: ToolIntent, now: datetime) -> Approval | None:
    """The newest approval that matches; the older ones stay as history."""
    matching = [item for item in approvals if approval_matches(item, intent, now)]
    return max(matching, key=lambda item: (item.created_at, str(item.id)), default=None)


def consume(approval: Approval, now: datetime) -> Approval:
    """The approval spent at ``now``; spending twice is ``APPROVAL_MISMATCH`` (``reason=already_used``)."""
    if approval.used_at is not None:
        raise Forbidden(
            ErrorCode.APPROVAL_MISMATCH,
            "the approval has been used",
            details={"reason": "already_used", "approval_id": str(approval.id)},
        )
    return replace(approval, used_at=now)
