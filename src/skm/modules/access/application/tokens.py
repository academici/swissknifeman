"""Shared token mechanics of the handlers and the facade (access §5, §7.3, §7.3a, §13).

Secrets are minted here and handed back to the caller exactly once; nothing in this module stores, logs or
puts a plaintext secret into an event. Only the peppered hash reaches ``TokenRepository``.
"""

from collections.abc import Callable, Mapping
from functools import cache
from typing import Final, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRegistry
from skm.modules.access.application import events
from skm.modules.access.domain.token import (
    ApiToken,
    TokenId,
    TokenSecret,
    generate_secret,
    hash_secret,
)
from skm.modules.access.generated.settings import AccessSettings
from skm.modules.access.ports import TokenRepository
from skm.platform.schema.registry import SchemaRegistry

__all__ = [
    "PREFIX_ATTEMPTS",
    "add_with_fresh_secret",
    "default_settings",
    "fresh_secret",
    "record_created",
    "record_revoked",
    "workspace_of_scope",
]

PREFIX_ATTEMPTS: Final = 3


@cache
def default_settings() -> AccessSettings:
    """The ``access`` section at its schema defaults, for facade callers that carry no effective config."""
    document = SchemaRegistry.load_default().get(AccessSettings.SCHEMA_URN)
    sections = cast(
        "Mapping[str, Mapping[str, Mapping[str, Mapping[str, JsonValue]]]]", document["properties"]
    )
    values = {
        f"access.{section}.{name}": leaf["default"]
        for section, node in sections.items()
        for name, leaf in node["properties"].items()
    }
    return AccessSettings.from_settings(values)


def workspace_of_scope(uow: UnitOfWork, scope_id: ScopeId | None) -> WorkspaceId | None:
    """Workspace a token or membership scope belongs to; ``None`` for the instance, hosts and no scope."""
    if scope_id is None:
        return None
    return uow.repo(ScopeRegistry).get(scope_id).workspace_id


def fresh_secret(
    uow: UnitOfWork, entropy: Callable[[int], bytes], pepper: bytes
) -> tuple[TokenSecret, bytes]:
    """A secret whose prefix is unused, with its hash; ``PREFIX_ATTEMPTS`` draws, then ``INTERNAL_ERROR``."""
    tokens = uow.repo(TokenRepository)
    for _ in range(PREFIX_ATTEMPTS):
        secret = generate_secret(entropy)
        if tokens.find_by_prefix(secret.prefix) is None:
            return secret, hash_secret(secret, pepper)
    raise InternalError(ErrorCode.INTERNAL_ERROR, "could not draw an unused token prefix")


def _prefix_collision(error: Conflict) -> bool:
    return error.code is ErrorCode.ALREADY_EXISTS and error.details.get("field") == "prefix"


def add_with_fresh_secret(
    uow: UnitOfWork,
    entropy: Callable[[int], bytes],
    pepper: bytes,
    build: Callable[[TokenSecret, bytes], ApiToken],
) -> tuple[ApiToken, TokenSecret]:
    """Draw a secret, build the token from it and add it; a prefix collision draws again (up to 3 times)."""
    tokens = uow.repo(TokenRepository)
    for _ in range(PREFIX_ATTEMPTS):
        secret, digest = fresh_secret(uow, entropy, pepper)
        token = build(secret, digest)
        try:
            tokens.add(token)
        except Conflict as error:
            if not _prefix_collision(error):
                raise
            continue
        return token, secret
    raise InternalError(ErrorCode.INTERNAL_ERROR, "could not store a token with an unused prefix")


def record_created(uow: UnitOfWork, token: ApiToken) -> None:
    """``TokenCreated`` without secret or hash."""
    uow.record(
        events.TokenCreated(
            token_id=token.id,
            principal_id=token.principal_id,
            kind=token.kind,
            name=token.name,
            prefix=token.prefix,
            scope_id=token.scope_id,
            expires_at=token.expires_at,
            workspace_id=workspace_of_scope(uow, token.scope_id),
        )
    )


def record_revoked(uow: UnitOfWork, token: ApiToken, by: PrincipalId) -> None:
    uow.record(
        events.TokenRevoked(
            token_id=token.id,
            principal_id=token.principal_id,
            revoked_by=by,
            workspace_id=workspace_of_scope(uow, token.scope_id),
        )
    )


def new_token_id(value: UUID) -> TokenId:
    return TokenId(value)
