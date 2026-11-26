"""``access.bootstrap_local_owner`` (access §7.7, internal): the first human owner of an instance.

Called once by ``skm init`` as ``SYSTEM_ACTOR``. A second call finds the ``local/owner`` identity and creates
nothing: the plaintext secret exists only in the result of the call that created it, never again.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.ids import PrincipalId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRegistry
from skm.modules.access.application import events, tokens
from skm.modules.access.application.passwords import set_first_password
from skm.modules.access.domain.identity import LOCAL_ISSUER, LOCAL_OWNER_SUBJECT, PrincipalIdentity
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.domain.roles import ROLE_PERMISSIONS, Role
from skm.modules.access.domain.token import ApiToken, TokenId, TokenKind, TokenSecret
from skm.modules.access.generated.commands import BootstrapLocalOwner
from skm.modules.access.generated.results import BootstrapLocalOwnerResult
from skm.modules.access.ports import (
    IdentityRepository,
    MembershipRepository,
    PrincipalRepository,
    TokenPepperSource,
)

__all__ = ["SPEC", "handle"]


def handle(cmd: BootstrapLocalOwner, ctx: CommandContext, uow: UnitOfWork) -> BootstrapLocalOwnerResult:
    now = ctx.clock.now()
    identities = uow.repo(IdentityRepository)
    known = identities.find(LOCAL_ISSUER, LOCAL_OWNER_SUBJECT)
    if known is not None:
        set_first_password(uow, known.principal_id, cmd.password, ctx.entropy.bytes)
        return BootstrapLocalOwnerResult(principal_id=known.principal_id, created=False, token_secret=None)
    instance = uow.repo(ScopeRegistry).instance()
    principal = new_principal(
        principal_id=PrincipalId(ctx.ids.new_id()),
        kind=PrincipalKind.HUMAN,
        display_name=cmd.display_name,
        created_by=None,
        now=now,
    )
    uow.repo(PrincipalRepository).add(principal)
    identities.add(
        PrincipalIdentity(
            principal_id=principal.id, issuer=LOCAL_ISSUER, subject=LOCAL_OWNER_SUBJECT, created_at=now
        )
    )
    uow.repo(MembershipRepository).upsert(
        Membership(
            scope_id=instance.id, principal_id=principal.id, role=Role.OWNER, granted_by=None, granted_at=now
        )
    )
    uow.record(
        events.PrincipalCreated(
            principal_id=principal.id, kind=principal.kind, display_name=principal.display_name
        )
    )
    uow.record(
        events.MembershipGranted(
            scope_id=instance.id,
            principal_id=principal.id,
            role=Role.OWNER,
            previous_role=None,
            workspace_id=None,
        )
    )
    set_first_password(uow, principal.id, cmd.password, ctx.entropy.bytes)
    pepper = ctx.gateways.get(TokenPepperSource).pepper()
    token_id = TokenId(ctx.ids.new_id())

    def build(secret: TokenSecret, digest: bytes) -> ApiToken:
        return ApiToken(
            id=token_id,
            principal_id=principal.id,
            kind=TokenKind.PERSONAL,
            name=cmd.token_name,
            prefix=secret.prefix,
            secret_hash=digest,
            scope_id=instance.id,
            permissions=ROLE_PERMISSIONS[Role.OWNER],
            expires_at=None,
            created_at=now,
            created_by=principal.id,
            last_used_at=None,
            revoked_at=None,
            revoked_by=None,
            assignment_id=None,
            step_id=None,
            superseded_by=None,
        )

    token, secret = tokens.add_with_fresh_secret(uow, ctx.entropy.bytes, pepper, build)
    tokens.record_created(uow, token)
    return BootstrapLocalOwnerResult(principal_id=principal.id, created=True, token_secret=str(secret))


SPEC = CommandSpec(
    name="access.bootstrap_local_owner",
    dto=BootstrapLocalOwner,
    result=BootstrapLocalOwnerResult,
    permission="system.bootstrap",
    scope_of=None,
    handler=handle,
    idempotency=IdempotencyMode.FORBIDDEN,
    internal=True,
)
