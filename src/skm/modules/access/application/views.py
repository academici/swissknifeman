"""Domain values -> generated views. Hashes and secrets have no field here, so no query can return them."""

from collections.abc import Sequence
from datetime import datetime

from skm.kernel.scopes import ScopeKind
from skm.modules.access.domain.identity import PrincipalIdentity
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import Principal
from skm.modules.access.domain.token import ApiToken, token_state
from skm.modules.access.generated import views
from skm.modules.access.generated.commands import ScopeGrantSpec

__all__ = ["membership_view", "principal_summary", "principal_view", "token_summary"]


def token_summary(token: ApiToken, now: datetime) -> views.TokenSummaryView:
    return views.TokenSummaryView(
        token_id=token.id,
        kind=views.TokenKind(token.kind.value),
        name=token.name,
        prefix=token.prefix,
        scope_id=token.scope_id,
        permissions=None if token.permissions is None else tuple(sorted(token.permissions)),
        scope_grants=None
        if token.scope_grants is None
        else tuple(
            ScopeGrantSpec(scope_id=pair.scope_id, permissions=tuple(sorted(pair.permissions)))
            for pair in token.scope_grants
        ),
        state=token_state(token, now).value,
        expires_at=token.expires_at,
        last_used_at=token.last_used_at,
        created_at=token.created_at,
        superseded_by=token.superseded_by,
        assignment_id=token.assignment_id,
        step_id=token.step_id,
    )


def principal_view(principal: Principal, identities: Sequence[PrincipalIdentity]) -> views.PrincipalView:
    return views.PrincipalView(
        principal_id=principal.id,
        kind=views.PrincipalKind(principal.kind.value),
        display_name=principal.display_name,
        state=principal.state.value,
        created_at=principal.created_at,
        row_version=principal.row_version,
        identities=tuple(
            views.PrincipalViewIdentitiesItem(issuer=i.issuer, subject=i.subject) for i in identities
        ),
    )


def principal_summary(principal: Principal) -> views.PrincipalSummaryView:
    return views.PrincipalSummaryView(
        principal_id=principal.id,
        kind=views.PrincipalKind(principal.kind.value),
        display_name=principal.display_name,
        state=principal.state.value,
    )


def membership_view(membership: Membership, scope_kind: ScopeKind, display_name: str) -> views.MembershipView:
    return views.MembershipView(
        scope_id=membership.scope_id,
        scope_kind=scope_kind.value,
        principal_id=membership.principal_id,
        display_name=display_name,
        role=views.Role(membership.role.value),
        granted_at=membership.granted_at,
    )
