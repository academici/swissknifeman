"""``access.whoami`` (access §8): who the credential in hand is and what it may do, read live."""

from skm.application_bus.context import QueryContext
from skm.application_bus.ports import EventReader
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRegistry
from skm.modules.access.application import authz
from skm.modules.access.application.views import membership_view, principal_view, token_summary
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.token import TokenId
from skm.modules.access.generated.queries import WhoAmI
from skm.modules.access.generated.views import MembershipView, WhoAmIView
from skm.modules.access.ports import (
    IdentityRepository,
    MembershipRepository,
    PrincipalRepository,
    TokenRepository,
)

__all__ = ["SPEC", "all_memberships", "handle"]

OPTIONAL_MODULES = ("knowledge", "learning", "exports")  # `modules.<id>.enabled` of the platform section
_PAGE = 200


def all_memberships(uow: UnitOfWork, principal_id: PrincipalId) -> list[Membership]:
    repo = uow.repo(MembershipRepository)
    found: list[Membership] = []
    after: str | None = None
    while True:
        page = repo.list(scope_id=None, principal_id=principal_id, after=after, limit=_PAGE)
        found.extend(page.items)
        if page.next is None:
            return found
        after = page.next


def handle(query: WhoAmI, ctx: QueryContext, uow: UnitOfWork) -> WhoAmIView:
    now = ctx.clock.now()
    actor = authz.ensure_live(uow, ctx.actor, now)
    principal = uow.repo(PrincipalRepository).get(actor.principal_id)
    scopes = uow.repo(ScopeRegistry)
    held = all_memberships(uow, principal.id)
    grants = None if actor.grant is None else actor.grant.scope_grants
    if grants is not None:
        roots = {pair.scope_id for pair in grants}
        held = [
            membership
            for membership in held
            if any(record.id in roots for record in scopes.ancestors(membership.scope_id))
        ]
    views: list[MembershipView] = [
        membership_view(m, scopes.get(m.scope_id).kind, principal.display_name) for m in held
    ]
    chain = authz.chain_of(uow, None if query.scope_id is None else ScopeId(query.scope_id))
    by_scope = {
        str(m.scope_id): tuple(sorted(authz.effective(uow, actor, authz.chain_of(uow, m.scope_id))))
        for m in held
    }
    workspace_id = authz.workspace_id_of(chain)
    permissions = authz.effective(uow, actor, chain)
    token = (
        None
        if actor.grant is None
        else token_summary(uow.repo(TokenRepository).get(TokenId(actor.grant.token_id)), now)
    )
    if token is not None and token.scope_id is not None:
        token_chain = authz.chain_of(uow, ScopeId(token.scope_id))
        for idx, scope in enumerate(token_chain[1:], start=1):
            by_scope[str(scope.id)] = tuple(sorted(authz.effective(uow, actor, token_chain[: idx + 1])))
    for pair in grants or ():
        by_scope[str(pair.scope_id)] = tuple(
            sorted(authz.effective(uow, actor, authz.chain_of(uow, pair.scope_id)))
        )
    return WhoAmIView(
        principal=principal_view(principal, uow.repo(IdentityRepository).for_principal(principal.id)),
        token=token,
        memberships=tuple(views),
        effective_permissions=tuple(sorted(permissions)),
        modules={name: bool(ctx.config.get(f"modules.{name}.enabled")) for name in OPTIONAL_MODULES},
        permissions_by_scope=by_scope,
        events_cursor=None
        if workspace_id is None or "workspace.read" not in permissions
        else uow.repo(EventReader).head_workspace_seq(workspace_id),
    )


SPEC = QuerySpec(
    name="access.whoami",
    dto=WhoAmI,
    result=WhoAmIView,
    permission=None,
    scope_of=None,
    handler=handle,
)
