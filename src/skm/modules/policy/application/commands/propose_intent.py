"""``policy.propose_intent`` (policy §7) and the facade ``propose_intent``.

One intent per ``(scope, kind, digest)`` while it is open: a repeated proposal returns the open one. The
effective permissions decide at once: a kind outside the ceiling or arguments nobody may approve make a
``denied`` intent; a kind that needs no human approval is approved by the system in the same transaction.
Approving and executing are other commands; nothing here performs the effect.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import PrincipalId, ScopeId, ToolIntentId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.policy.application.commands import (
    chain_of,
    effective_for,
    layer_of,
    require_active_scope,
    require_operator,
    risk_of,
    setting,
    workspace_of,
)
from skm.modules.policy.domain.approval import ApprovalId, auto_approval
from skm.modules.policy.domain.events import IntentApproved, IntentDenied, IntentProposed
from skm.modules.policy.domain.permission_set import PermissionSet
from skm.modules.policy.domain.tool_intent import (
    EffectKind,
    EnforcementMode,
    IntentState,
    ToolIntent,
    propose,
    transition_intent,
)
from skm.modules.policy.generated.commands import ProposeIntent
from skm.modules.policy.generated.results import ProposeIntentResult
from skm.modules.policy.ports import ApprovalRepository, ToolIntentRepository

__all__ = ["SPEC", "handle", "propose_in"]

_DEFAULT_PROPOSAL_TTL = 259200


def propose_in(
    uow: UnitOfWork,
    ctx: CommandContext,
    *,
    scope_id: ScopeId,
    subject_ref: str,
    kind: EffectKind,
    args: Mapping[str, object],
    reason: str,
    perms: PermissionSet,
) -> ToolIntent:
    """The intent for the proposal in the caller's unit of work (the facade and the command share it)."""
    require_active_scope(uow, scope_id)
    workspace_id = workspace_of(chain_of(uow, scope_id))
    now = ctx.clock.now()
    ttl = timedelta(
        seconds=int(
            cast("int", setting(ctx.config, "policy.intents.proposal_ttl_seconds", _DEFAULT_PROPOSAL_TTL))
        )
    )
    candidate = propose(
        kind,
        args,
        perms,
        now,
        ttl,
        intent_id=ToolIntentId(ctx.ids.new_id()),
        workspace_id=workspace_id,
        scope_id=scope_id,
        subject_ref=subject_ref,
        actor_id=ctx.actor.principal_id,
        risk=risk_of(ctx.config, kind),
        reason=reason,
        mode=(
            EnforcementMode.AGENT_UNATTENDED
            if ctx.actor.kind is PrincipalKind.WORKER
            else EnforcementMode.INTERACTIVE
        ),
    )
    intents = uow.repo(ToolIntentRepository)
    if candidate.state is IntentState.PROPOSED:
        open_intent = intents.find_active(scope_id, candidate.kind, candidate.args_digest)
        if open_intent is not None:
            return open_intent
    try:
        intents.add(candidate)
    except Conflict as error:
        if error.code is not ErrorCode.ALREADY_EXISTS or candidate.state is not IntentState.PROPOSED:
            raise
        raced = intents.find_active(scope_id, candidate.kind, candidate.args_digest)
        if raced is None:
            raise
        return raced
    uow.record(
        IntentProposed(
            intent_id=candidate.id,
            workspace_id=candidate.workspace_id,
            scope_id=candidate.scope_id,
            kind=candidate.kind,
            risk=candidate.risk,
            args_digest=candidate.args_digest,
            state=candidate.state,
            subject_ref=candidate.subject_ref,
        )
    )
    if candidate.state is IntentState.DENIED:
        uow.record(
            IntentDenied(
                intent_id=candidate.id,
                workspace_id=candidate.workspace_id,
                by=SYSTEM_PRINCIPAL_ID,
                reason=cast("str", candidate.denied_reason),
            )
        )
        return candidate
    approval = auto_approval(candidate, perms, now, approval_id=ApprovalId(ctx.ids.new_id()))
    if approval is None:
        return candidate
    uow.repo(ApprovalRepository).add(approval)
    approved = transition_intent(candidate, IntentState.APPROVED)
    intents.save(approved, expected_version=candidate.row_version)
    uow.record(
        IntentApproved(
            intent_id=approved.id,
            workspace_id=approved.workspace_id,
            approval_id=approval.id,
            approver_id=PrincipalId(approval.approver_id),
            auto=True,
            expires_at=approval.expires_at,
        )
    )
    return approved


def handle(cmd: ProposeIntent, ctx: CommandContext, uow: UnitOfWork) -> ProposeIntentResult:
    scope_id = ScopeId(cmd.scope_id)
    require_operator(uow, ctx, scope_id)
    perms = effective_for(
        ctx.config,
        profile_id=cmd.profile_id,
        role_layer=layer_of(cmd.role_layer, "role"),
        task_layer=layer_of(cmd.task_layer, "task"),
    )
    intent = propose_in(
        uow,
        ctx,
        scope_id=scope_id,
        subject_ref=cmd.subject_ref,
        kind=EffectKind(cmd.kind.value),
        args=cmd.args,
        reason=cmd.reason,
        perms=perms,
    )
    return ProposeIntentResult(
        intent_id=intent.id,
        state=intent.state.value,
        args_digest=intent.args_digest,
        needs_approval=intent.state is IntentState.PROPOSED,
    )


SPEC = CommandSpec(
    name="policy.propose_intent",
    dto=ProposeIntent,
    result=ProposeIntentResult,
    permission="policy.read",
    scope_of=lambda cmd: ScopeRef(ScopeKind.RUN, ScopeId(cmd.scope_id)),
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
