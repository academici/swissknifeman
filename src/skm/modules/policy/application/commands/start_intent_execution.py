"""``policy.start_intent_execution`` (policy §7) and the facade ``require_approved``: the one admission.

Everything is decided from the facts of this transaction, under the row lock of the intent:

1. the scope is open (no archived project or workspace on the chain) and the intent is ``approved``;
2. the caller presents the digest of the intent, and an approval exists that matches it (digest, expiry,
   not spent);
3. the *current* configuration still permits the kind (``external_effects``): a revoked kind is refused at
   once, whatever was approved before;
4. the approver is still who approved: a stored, active human who holds ``intent.approve`` on the scope now
   (``approval_authority_revoked`` otherwise), or, for the approval of the system, the condition that made
   it still holds;
5. the approval is spent (compare-and-set on ``used_at``) and the intent becomes ``executing``.

The caller performs the external IO only after this call returns, and outside the transaction. Two
concurrent starts serialize on the row lock; the second sees ``executing`` and is refused.
"""

from __future__ import annotations

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden
from skm.kernel.ids import ToolIntentId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.policy.application.commands import (
    SELF_PERMISSION,
    approver_still_authorized,
    effective_for,
    require_active_scope,
    require_operator,
)
from skm.modules.policy.domain.approval import (
    Approval,
    ApprovalRequired,
    consume,
    is_system_approval,
    system_approval_holds,
    usable_approval,
)
from skm.modules.policy.domain.events import IntentExecutionStarted
from skm.modules.policy.domain.tool_intent import EffectKind, IntentState, ToolIntent, transition_intent
from skm.modules.policy.generated.commands import StartIntentExecution
from skm.modules.policy.generated.results import StartIntentExecutionResult
from skm.modules.policy.ports import ApprovalRepository, ToolIntentRepository

__all__ = ["SPEC", "handle", "start_in"]


def _mismatch(intent: ToolIntent, reason: str) -> Forbidden:
    return Forbidden(
        ErrorCode.APPROVAL_MISMATCH,
        "no approval admits this execution",
        details={"reason": reason, "intent_id": str(intent.id)},
    )


def _require_approved_state(intent: ToolIntent) -> None:
    state = IntentState(intent.state)
    if state is IntentState.APPROVED:
        return
    if state is IntentState.PROPOSED:
        raise ApprovalRequired(intent.id, state.value)
    if state is IntentState.DENIED:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "the intent was denied",
            details={"reason": intent.denied_reason or "denied", "intent_id": str(intent.id)},
        )
    raise _mismatch(intent, "expired" if state is IntentState.EXPIRED else "already_started")


def start_in(
    uow: UnitOfWork, ctx: CommandContext, *, intent_id: ToolIntentId, args_digest: str
) -> tuple[ToolIntent, Approval]:
    """Admit the execution in the caller's unit of work; the returned intent is ``executing``."""
    intents = uow.repo(ToolIntentRepository)
    intent = intents.get_for_update(intent_id)
    if intent.kind is EffectKind.FS_WRITE_EXTERNAL and ctx.actor.kind is PrincipalKind.WORKER:
        raise Forbidden(ErrorCode.FORBIDDEN, "unattended workers cannot execute external file writes")
    require_active_scope(uow, intent.scope_id)
    _require_approved_state(intent)
    approvals = uow.repo(ApprovalRepository)
    history = approvals.for_intent(intent.id)
    if not history:
        raise ApprovalRequired(intent.id, intent.state.value)
    if args_digest != intent.args_digest:
        raise _mismatch(intent, "digest_changed")
    now = ctx.clock.now()
    approval = usable_approval(history, intent, now)
    if approval is None:
        raise _mismatch(intent, "no_valid_approval")
    perms = effective_for(ctx.config, profile_id=None, role_layer=None, task_layer=None)
    if intent.kind not in perms.external_effects:  # revocation acts at once, whatever was approved
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "the effect kind is no longer permitted",
            details={"reason": "revoked", "intent_id": str(intent.id), "kind": intent.kind.value},
        )
    if is_system_approval(approval):
        if not system_approval_holds(approval, intent, perms):
            raise _mismatch(intent, "auto_approval_not_current")
    elif not approver_still_authorized(uow, ctx.clock, approval.approver_id, intent.scope_id):
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "the approver no longer holds the right to approve",
            details={"reason": "approval_authority_revoked", "intent_id": str(intent.id)},
        )
    approvals.mark_used(approval.id, now)  # compare-and-set: spent once, whatever else races
    executing = transition_intent(intent, IntentState.EXECUTING)
    intents.save(executing, expected_version=intent.row_version)
    uow.record(
        IntentExecutionStarted(
            intent_id=executing.id, workspace_id=executing.workspace_id, approval_id=approval.id
        )
    )
    return executing, consume(approval, now)


def handle(cmd: StartIntentExecution, ctx: CommandContext, uow: UnitOfWork) -> StartIntentExecutionResult:
    intent_id = ToolIntentId(cmd.intent_id)
    require_operator(uow, ctx, uow.repo(ToolIntentRepository).get(intent_id).scope_id)
    executing, approval = start_in(uow, ctx, intent_id=intent_id, args_digest=cmd.args_digest)
    return StartIntentExecutionResult(
        intent_id=executing.id, state=executing.state.value, approval_id=approval.id
    )


SPEC = CommandSpec(
    name="policy.start_intent_execution",
    dto=StartIntentExecution,
    result=StartIntentExecutionResult,
    permission=SELF_PERMISSION,
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
