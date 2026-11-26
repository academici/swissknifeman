"""``policy.approve_intent`` (policy §7, §4.6): a human approves exactly the digest they saw.

The bus lets every principal through (``SELF_PERMISSION``); the handler decides: the actor must be a human
(``reason=human_gate``) and hold ``intent.approve`` on the scope of the intent. The approval is for the
digest of the intent now, never wider than the configured lifetime (``policy.approval.ttl_seconds``) and
single use when the configuration says so. Approving executes nothing and extends no ceiling.
"""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed
from skm.kernel.ids import ToolIntentId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.versions import ExpectedVersion, check_expected
from skm.modules.policy.application.commands import (
    SELF_PERMISSION,
    approval_single_use,
    require,
    require_active_scope,
    require_human,
    setting,
)
from skm.modules.policy.domain.approval import ApprovalId, approve
from skm.modules.policy.domain.events import IntentApproved
from skm.modules.policy.domain.tool_intent import IntentState, transition_intent
from skm.modules.policy.generated.commands import ApproveIntent
from skm.modules.policy.generated.results import ApproveIntentResult
from skm.modules.policy.ports import ApprovalRepository, ToolIntentRepository

__all__ = ["SPEC", "handle"]

_DEFAULT_TTL = 86400
_PERMISSION = "intent.approve"


def handle(cmd: ApproveIntent, ctx: CommandContext, uow: UnitOfWork) -> ApproveIntentResult:
    require_human(ctx.actor)
    intents = uow.repo(ToolIntentRepository)
    intent = intents.get_for_update(ToolIntentId(cmd.intent_id))
    require(uow, ctx.clock, ctx.actor, _PERMISSION, intent.scope_id)
    require_active_scope(uow, intent.scope_id)
    check_expected(intent.row_version, ExpectedVersion(cmd.expected_row_version))
    approved = transition_intent(intent, IntentState.APPROVED)  # INVALID_TRANSITION unless proposed
    now = ctx.clock.now()
    if now >= intent.expires_at:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "the proposal has expired",
            details={
                "kind": "tool_intent",
                "from": intent.state.value,
                "to": "approved",
                "reason": "expired",
            },
        )
    if cmd.args_digest != intent.args_digest:
        raise Forbidden(
            ErrorCode.APPROVAL_MISMATCH,
            "the intent is not the one that was reviewed",
            details={"reason": "digest_changed", "intent_id": str(intent.id)},
        )
    configured = int(cast("int", setting(ctx.config, "policy.approval.ttl_seconds", _DEFAULT_TTL)))
    seconds = configured if cmd.ttl_seconds is None else min(cmd.ttl_seconds, configured)
    single_use = approval_single_use(ctx.config) or cmd.single_use is True
    approval = approve(
        intent,
        approval_id=ApprovalId(ctx.ids.new_id()),
        approver_id=ctx.actor.principal_id,
        now=now,
        ttl=timedelta(seconds=seconds),
        single_use=single_use,
        reason=cmd.reason or "",
    )
    uow.repo(ApprovalRepository).add(approval)
    intents.save(approved, expected_version=intent.row_version)
    uow.record(
        IntentApproved(
            intent_id=approved.id,
            workspace_id=approved.workspace_id,
            approval_id=approval.id,
            approver_id=approval.approver_id,
            auto=False,
            expires_at=approval.expires_at,
        )
    )
    return ApproveIntentResult(intent_id=approved.id, state=approved.state.value, approval_id=approval.id)


SPEC = CommandSpec(
    name="policy.approve_intent",
    dto=ApproveIntent,
    result=ApproveIntentResult,
    permission=SELF_PERMISSION,
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
