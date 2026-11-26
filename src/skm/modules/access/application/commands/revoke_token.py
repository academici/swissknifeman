"""``access.revoke_token`` (access §7.4): an own token, or any token with ``token.any``.

A worker revokes only the token it authenticates with.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access.application import authz, tokens
from skm.modules.access.application.commands.rotate_token import require_manageable
from skm.modules.access.domain.token import TokenId, revoke
from skm.modules.access.generated.commands import RevokeToken
from skm.modules.access.generated.results import RevokeTokenResult
from skm.modules.access.ports import TokenRepository

__all__ = ["SPEC", "handle"]

SELF_PERMISSION = "token.own"


def handle(cmd: RevokeToken, ctx: CommandContext, uow: UnitOfWork) -> RevokeTokenResult:
    actor, now = ctx.actor, ctx.clock.now()
    authz.require(uow, actor, SELF_PERMISSION, authz.chain_of(uow, None))
    repo = uow.repo(TokenRepository)
    token = repo.get_for_update(TokenId(cmd.token_id))
    require_manageable(uow, ctx, token.principal_id, token.id)
    revoked = revoke(token, actor.principal_id, now)
    if revoked is token:  # already revoked: the first revocation stays, nothing is written
        assert token.revoked_at is not None  # noqa: S101
        return RevokeTokenResult(token_id=token.id, revoked_at=token.revoked_at)
    repo.save(revoked)
    tokens.record_revoked(uow, revoked, actor.principal_id)
    assert revoked.revoked_at is not None  # noqa: S101
    return RevokeTokenResult(token_id=revoked.id, revoked_at=revoked.revoked_at)


SPEC = CommandSpec(
    name="access.revoke_token",
    dto=RevokeToken,
    result=RevokeTokenResult,
    permission=SELF_PERMISSION,
    scope_of=None,
    handler=handle,
)
