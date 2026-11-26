"""``policy.list_intents`` (policy §8): intents of a workspace by ``(created_at, id)``, by scope and state."""

from __future__ import annotations

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.pagination import DEFAULT_PAGE_LIMIT
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.policy.domain.tool_intent import IntentState
from skm.modules.policy.generated.queries import ListIntents
from skm.modules.policy.generated.views import EffectKind, IntentSummaryView, IntentsView, RiskClass
from skm.modules.policy.ports import ToolIntentRepository

__all__ = ["SPEC", "handle"]


def handle(query: ListIntents, ctx: QueryContext, uow: UnitOfWork) -> IntentsView:
    del ctx
    page = uow.repo(ToolIntentRepository).list(
        workspace_id=WorkspaceId(query.workspace_id),
        scope_id=None if query.scope_id is None else ScopeId(query.scope_id),
        state=None if query.state is None else IntentState(query.state),
        after=query.after,
        limit=DEFAULT_PAGE_LIMIT if query.limit is None else query.limit,
    )
    return IntentsView(
        items=tuple(
            IntentSummaryView(
                intent_id=item.id,
                kind=EffectKind(item.kind.value),
                risk=RiskClass(item.risk.value),
                state=item.state.value,
                subject_ref=item.subject_ref,
                created_at=item.created_at,
                expires_at=item.expires_at,
            )
            for item in page.items
        ),
        next_cursor=page.next,
    )


SPEC = QuerySpec(
    name="policy.list_intents",
    dto=ListIntents,
    result=IntentsView,
    permission="policy.read",
    scope_of=lambda query: ScopeRef(ScopeKind.WORKSPACE, ScopeId(query.workspace_id)),
    handler=handle,
)
