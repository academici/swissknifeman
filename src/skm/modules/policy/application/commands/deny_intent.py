"""``policy.deny_intent`` (policy §7): a human refuses a proposed or approved intent.

The same gate as approval (a human with ``intent.approve`` on the scope of the intent), but refusing is
allowed in an archived area: closing a scope must not keep an approved effect alive. The refusal is kept as a
``deny`` approval row (who, when, why); it never authorizes anything.
"""

from __future__ import annotations

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ids import ToolIntentId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.versions import ExpectedVersion, check_expected
from skm.modules.policy.application.commands import SELF_PERMISSION, require, require_human
from skm.modules.policy.domain.approval import ApprovalId, denial
from skm.modules.policy.domain.events import IntentDenied
from skm.modules.policy.domain.tool_intent import DeniedReason, deny
from skm.modules.policy.generated.commands import DenyIntent
from skm.modules.policy.generated.results import DenyIntentResult
from skm.modules.policy.ports import ApprovalRepository, ToolIntentRepository

__all__ = ["SPEC", "handle"]

_PERMISSION = "intent.approve"


def handle(cmd: DenyIntent, ctx: CommandContext, uow: UnitOfWork) -> DenyIntentResult:
    require_human(ctx.actor)
    intents = uow.repo(ToolIntentRepository)
    intent = intents.get_for_update(ToolIntentId(cmd.intent_id))
    require(uow, ctx.clock, ctx.actor, _PERMISSION, intent.scope_id)
    check_expected(intent.row_version, ExpectedVersion(cmd.expected_row_version))
    denied = deny(intent, DeniedReason.BY_APPROVER)  # INVALID_TRANSITION unless proposed or approved
    uow.repo(ApprovalRepository).add(
        denial(
            intent,
            approval_id=ApprovalId(ctx.ids.new_id()),
            approver_id=ctx.actor.principal_id,
            now=ctx.clock.now(),
            reason=cmd.reason,
        )
    )
    intents.save(denied, expected_version=intent.row_version)
    uow.record(
        IntentDenied(
            intent_id=denied.id,
            workspace_id=denied.workspace_id,
            by=ctx.actor.principal_id,
            reason=cmd.reason,
        )
    )
    return DenyIntentResult(intent_id=denied.id, state=denied.state.value)


SPEC = CommandSpec(
    name="policy.deny_intent",
    dto=DenyIntent,
    result=DenyIntentResult,
    permission=SELF_PERMISSION,
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
