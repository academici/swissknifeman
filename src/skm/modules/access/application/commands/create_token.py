"""``access.create_token`` (access §7.3, §4.5).

Not idempotent: the secret is returned once, in this result only, and no receipt may hold it. Delegation is
bounded by the caller's live role and credential. Default permissions are frozen at the requested scope,
and each explicit scope grant is checked independently.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind, ScopeGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRef
from skm.modules.access.application import authz, delegation, tokens
from skm.modules.access.application.scopes import scope_by_id
from skm.modules.access.domain.token import ApiToken, TokenId, TokenKind, TokenSecret, token_expiry
from skm.modules.access.generated.commands import CreateToken
from skm.modules.access.generated.results import CreateTokenResult
from skm.modules.access.generated.settings import AccessSettings
from skm.modules.access.ports import PrincipalRepository, TokenPepperSource

__all__ = ["SPEC", "handle", "scope_of"]

SELF_PERMISSION = "token.own"


def scope_of(cmd: CreateToken) -> ScopeRef | None:
    """The scope of the new token, or the instance."""
    return scope_by_id(cmd.scope_id)


def handle(cmd: CreateToken, ctx: CommandContext, uow: UnitOfWork) -> CreateTokenResult:
    now = ctx.clock.now()
    actor = authz.ensure_live(uow, ctx.actor, now)
    target_id = PrincipalId(cmd.principal_id) if cmd.principal_id is not None else actor.principal_id
    scope_id = ScopeId(cmd.scope_id) if cmd.scope_id is not None else None
    chain = authz.chain_of(uow, scope_id)
    authz.require(uow, actor, SELF_PERMISSION, chain)
    if target_id != actor.principal_id:  # a token for someone else needs token.any on the instance
        authz.require(uow, actor, "token.any", authz.chain_of(uow, None))
    principal = uow.repo(PrincipalRepository).get(target_id)
    if principal.state.value != "active":
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "the principal is disabled",
            details={"reason": "principal_disabled"},
        )
    if principal.kind is PrincipalKind.WORKER:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "tokens of a worker are issued by registration and rotated only",
            details={"reason": "worker_tokens_are_rotated"},
        )
    if cmd.scope_grants is None:
        delegation.ensure_scope_within_grant(uow, actor, scope_id)
        requested = None if cmd.permissions is None else frozenset(cmd.permissions)
        permissions = delegation.grant_permissions(uow, actor, chain, requested)
        scope_grants = None
    else:
        if scope_id is not None or cmd.permissions is not None:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "scope_grants is an independent grant form")
        permissions = None
        scope_grants = delegation.validate_scope_grants(
            uow,
            actor,
            tuple(
                ScopeGrant(ScopeId(pair.scope_id), frozenset(pair.permissions)) for pair in cmd.scope_grants
            ),
        )
    settings = ctx.config.section(AccessSettings)
    expires_at = token_expiry(TokenKind.PERSONAL, cmd.expires_at, now, settings)
    pepper = ctx.gateways.get(TokenPepperSource).pepper()
    token_id = TokenId(ctx.ids.new_id())

    def build(secret: TokenSecret, digest: bytes) -> ApiToken:
        return ApiToken(
            id=token_id,
            principal_id=target_id,
            kind=TokenKind.PERSONAL,
            name=cmd.name,
            prefix=secret.prefix,
            secret_hash=digest,
            scope_id=scope_id,
            permissions=permissions,
            scope_grants=scope_grants,
            expires_at=expires_at,
            created_at=now,
            created_by=actor.principal_id,
            last_used_at=None,
            revoked_at=None,
            revoked_by=None,
            assignment_id=None,
            step_id=None,
            superseded_by=None,
        )

    token, secret = tokens.add_with_fresh_secret(uow, ctx.entropy.bytes, pepper, build)
    tokens.record_created(uow, token)
    return CreateTokenResult(
        token_id=token.id, prefix=token.prefix, secret=str(secret), expires_at=token.expires_at
    )


SPEC = CommandSpec(
    name="access.create_token",
    dto=CreateToken,
    result=CreateTokenResult,
    permission=SELF_PERMISSION,
    scope_of=scope_of,
    handler=handle,
    idempotency=IdempotencyMode.FORBIDDEN,
)
