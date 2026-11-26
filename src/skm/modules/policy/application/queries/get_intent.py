"""``policy.get_intent`` (policy §8): one intent with its normalized arguments, digest and approvals.

The DTO names an intent, not a scope: the bus checks the self right and this handler decides ``policy.read``
on the scope of the intent.
"""

from __future__ import annotations

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ToolIntentId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.policy.application.commands import SELF_PERMISSION, approval_single_use, intent_view, require
from skm.modules.policy.domain.tool_intent import IntentState
from skm.modules.policy.generated.intent_approval import IntentApprovalView
from skm.modules.policy.generated.queries import GetIntent
from skm.modules.policy.ports import ApprovalRepository, ToolIntentRepository

__all__ = ["SPEC", "handle"]


def handle(query: GetIntent, ctx: QueryContext, uow: UnitOfWork) -> IntentApprovalView:
    intent = uow.repo(ToolIntentRepository).get(ToolIntentId(query.intent_id))
    require(uow, ctx.clock, ctx.actor, "policy.read", intent.scope_id)
    view = intent_view(intent, uow.repo(ApprovalRepository).for_intent(intent.id)).to_json()
    if query.include_approval_binding:
        view["effect_id"] = str(intent.id)
        if intent.state is IntentState.PROPOSED:
            view["single_use"] = approval_single_use(ctx.config)
    return IntentApprovalView.from_json(view)


SPEC = QuerySpec(
    name="policy.get_intent",
    dto=GetIntent,
    result=IntentApprovalView,
    permission=SELF_PERMISSION,
    scope_of=None,
    handler=handle,
)
