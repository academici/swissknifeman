"""``policy.effective_permissions`` (policy §8): the permissions a scope's steps would get, with their digest.

The composition of §5.1 on the live configuration of the scope: profile ∩ ceiling ∩ restrictions ∩ role
layer ∩ task layer. ``interactive`` composes for client hooks: the interactive profile, and the human
answers for their checkout, so the delete scope is the whole worktree.
"""

from __future__ import annotations

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.policy.application.commands import effective_for, layer_of
from skm.modules.policy.application.composition import task_authority_from
from skm.modules.policy.application.queries import authority_view, permission_set_view
from skm.modules.policy.domain.operations import INTERACTIVE_AUTHORITY_DELETE_SCOPE
from skm.modules.policy.generated.queries import EffectivePermissions
from skm.modules.policy.generated.views import EffectivePermissionsView

__all__ = ["SPEC", "handle"]


def handle(query: EffectivePermissions, ctx: QueryContext, uow: UnitOfWork) -> EffectivePermissionsView:
    del uow  # the composition reads no repository
    perms = effective_for(
        ctx.config,
        profile_id=query.profile_id,
        role_layer=layer_of(query.role_layer, "role"),
        task_layer=layer_of(query.task_layer, "task"),
        interactive=query.interactive,
    )
    authority = task_authority_from(
        ctx.config,
        write_scope=None,
        delete_scope=INTERACTIVE_AUTHORITY_DELETE_SCOPE if query.interactive else (),
    )
    return EffectivePermissionsView(
        permissions=permission_set_view(perms), authority=authority_view(authority)
    )


SPEC = QuerySpec(
    name="policy.effective_permissions",
    dto=EffectivePermissions,
    result=EffectivePermissionsView,
    permission="policy.read",
    scope_of=lambda query: ScopeRef(ScopeKind.RUN, ScopeId(query.scope_id)),
    handler=handle,
)
