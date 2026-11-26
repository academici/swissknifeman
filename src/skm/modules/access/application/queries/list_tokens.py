"""``access.list_tokens`` (access §8): own tokens, or those of another principal with ``token.any``.

Summaries carry ``superseded_by`` so an operator can follow a rotation chain to its active end; they never
carry a hash or a secret.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import PrincipalId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access.application import authz
from skm.modules.access.application.views import token_summary
from skm.modules.access.domain.token import TokenKind
from skm.modules.access.generated.queries import ListTokens
from skm.modules.access.generated.views import ListTokensView
from skm.modules.access.ports import TokenRepository

__all__ = ["SPEC", "handle"]


def handle(query: ListTokens, ctx: QueryContext, uow: UnitOfWork) -> ListTokensView:
    actor, now = ctx.actor, ctx.clock.now()
    owner = actor.principal_id if query.principal_id is None else PrincipalId(query.principal_id)
    if owner != actor.principal_id:
        authz.require(uow, actor, "token.any", authz.chain_of(uow, None))
    page = uow.repo(TokenRepository).list_for(
        owner,
        include_inactive=query.include_inactive,
        after=query.after,
        limit=query.limit,
        kind=None if query.kind is None else TokenKind(query.kind.value),
    )
    return ListTokensView(items=tuple(token_summary(t, now) for t in page.items), next=page.next)


SPEC = QuerySpec(
    name="access.list_tokens",
    dto=ListTokens,
    result=ListTokensView,
    permission="token.own",
    scope_of=None,
    handler=handle,
)
