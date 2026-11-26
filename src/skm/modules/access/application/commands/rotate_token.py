"""``access.rotate_token`` (access §7.3a, §4.5): one secret out, the old one lives out a short grace.

Not idempotent and secret-bearing: a lost response is never retried blindly. The superseded id answers
``INVALID_TRANSITION``, so one token has exactly one successor; an independent operator holding ``token.any``
recovers by rotating the active end of the ``superseded_by`` chain with ``grace_minutes=0``. Rotation keeps
kind, scope and permissions of the old token and never widens a credential.
"""

from dataclasses import replace
from datetime import timedelta

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, InternalError, NotFound, PreconditionFailed
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.application import authz, delegation, events, tokens
from skm.modules.access.domain.principal import PrincipalState
from skm.modules.access.domain.token import TokenId, TokenKind, rotate
from skm.modules.access.generated.commands import RotateToken
from skm.modules.access.generated.results import RotateTokenResult
from skm.modules.access.generated.settings import AccessSettings
from skm.modules.access.ports import PrincipalRepository, TokenPepperSource, TokenRepository, WorkerHostLookup

__all__ = ["SPEC", "handle", "require_manageable"]

SELF_PERMISSION = "token.own"


def require_manageable(uow: UnitOfWork, ctx: CommandContext, owner_id: object, token_id: object) -> None:
    """Owner check of rotate and revoke: own token, or ``token.any``; a worker only its current token."""
    actor = ctx.actor
    instance = authz.chain_of(uow, None)
    if owner_id != actor.principal_id:
        authz.require(uow, actor, "token.any", instance)
    if actor.kind is PrincipalKind.WORKER and (actor.grant is None or actor.grant.token_id != token_id):
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "a worker manages only the token it authenticates with",
            details={"reason": "not_current_token"},
        )


def handle(cmd: RotateToken, ctx: CommandContext, uow: UnitOfWork) -> RotateTokenResult:
    now = ctx.clock.now()
    actor = authz.ensure_live(uow, ctx.actor, now)
    authz.require(uow, actor, SELF_PERMISSION, authz.chain_of(uow, None))
    repo = uow.repo(TokenRepository)
    old = repo.get_for_update(TokenId(cmd.token_id))
    require_manageable(uow, ctx, old.principal_id, old.id)
    owner = uow.repo(PrincipalRepository).get(old.principal_id)
    if owner.state is not PrincipalState.ACTIVE:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "the principal is disabled",
            details={"reason": "principal_disabled"},
        )
    permissions = old.permissions
    workspace_scope = None
    if old.kind is TokenKind.PERSONAL:
        permissions = delegation.personal_rotation_permissions(uow, actor, old)
    elif old.kind is TokenKind.WORKER:
        workspace_scope = uow.repo(WorkerHostLookup).workspace_scope_id(old.principal_id)
        if workspace_scope is None:
            raise Forbidden(
                ErrorCode.FORBIDDEN,
                "worker token rotation requires a registered worker",
                details={"permission": "worker.register", "reason": "worker_registration_unavailable"},
            )
        permission = "worker.claim" if actor.kind is PrincipalKind.WORKER else "worker.register"
        authz.require(uow, actor, permission, authz.chain_of(uow, workspace_scope))
    settings = ctx.config.section(AccessSettings)
    minutes = cmd.grace_minutes if cmd.grace_minutes is not None else settings.tokens.rotation_grace_minutes
    pepper = ctx.gateways.get(TokenPepperSource).pepper()
    for _ in range(tokens.PREFIX_ATTEMPTS):
        secret, digest = tokens.fresh_secret(uow, ctx.entropy.bytes, pepper)
        superseded, successor = rotate(
            old,
            new_id=TokenId(ctx.ids.new_id()),
            new_secret_hash=digest,
            new_prefix=secret.prefix,
            now=now,
            settings=settings,
            grace=timedelta(minutes=minutes),
            created_by=actor.principal_id,
        )
        successor = replace(successor, permissions=permissions)
        repo.save(superseded)  # frees the name first; superseded_by is deferrable
        try:
            repo.add(successor)
        except Conflict as error:
            if error.code is ErrorCode.ALREADY_EXISTS and error.details.get("field") == "prefix":
                continue
            raise
        uow.record(
            events.TokenRotated(
                token_id=successor.id,
                previous_token_id=old.id,
                principal_id=old.principal_id,
                kind=old.kind,
                expires_at=successor.expires_at,
                previous_expires_at=superseded.expires_at,
                workspace_id=tokens.workspace_of_scope(
                    uow, workspace_scope if old.kind is TokenKind.WORKER else old.scope_id
                ),
            )
        )
        return RotateTokenResult(
            token_id=successor.id,
            prefix=successor.prefix,
            secret=str(secret),
            expires_at=successor.expires_at,
            previous_token_id=old.id,
            previous_expires_at=superseded.expires_at,
        )
    raise InternalError(ErrorCode.INTERNAL_ERROR, "could not store a token with an unused prefix")


def _rotation_scope(cmd: RotateToken, uow: UnitOfWork) -> ScopeRef | None:
    try:
        token = uow.repo(TokenRepository).get(TokenId(cmd.token_id))
    except NotFound:
        return None
    if token.kind is not TokenKind.WORKER:
        return None
    workspace = uow.repo(WorkerHostLookup).workspace_scope_id(token.principal_id)
    return None if workspace is None else ScopeRef(ScopeKind.WORKSPACE, workspace)


SPEC = CommandSpec(
    name="access.rotate_token",
    dto=RotateToken,
    result=RotateTokenResult,
    permission=SELF_PERMISSION,
    scope_of=None,
    scope_resolver=_rotation_scope,
    handler=handle,
    idempotency=IdempotencyMode.FORBIDDEN,
)
