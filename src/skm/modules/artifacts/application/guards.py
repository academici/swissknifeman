"""Authorization of artifacts handlers on a loaded file (artifacts §4.2a, §7, §8).

A file id or a version id names no scope by itself, and the request must not name one: the by-id operations
register a server-trusted ``scope_resolver`` (``file_scope_of_file``, ``file_scope_of_version``). The bus
calls it in the operation's own unit of work, reads only the owner link of the stored file and authorises
``file.read`` (queries) or ``file.write`` (commands) on the scope it returns, so a token narrowed to that
one right passes without ``token.own``. The resolver returns a ``ScopeRef`` and nothing else; an unknown id
resolves to ``None`` and fails closed on the instance scope.

The handler never trusts the resolution: ``require_bound`` refuses a stored file whose scope is not the
one the bus authorised (``ctx.scope``), which closes a file that changed owner or appeared between the two
steps, and the handler decides the real permission again on the scope **of the stored file** (its project,
else its workspace), never on a digest, a storage key or a workspace the caller wrote in the request. The
decision is the production ``RbacAuthorizer`` decision, reason code included.

A worker never mutates a logical file (``require_not_worker``) and reads a file version only with an
active ``assignment`` grant on exactly that version (``require_version_read``): equal digests share no
grant. A worker holding an assignment token needs the grant of **that** assignment (``grant.ref`` is its
assignment id): another assignment's grant on the same version opens nothing.
"""

from uuid import UUID

from skm.application_bus.context import CommandContext, QueryContext
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound
from skm.kernel.ids import FileVersionId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRef, ScopeRegistry
from skm.modules.access.public import RbacAuthorizer
from skm.modules.artifacts.domain.access_grant import GrantReason, grant_is_active
from skm.modules.artifacts.domain.file import File, FileId
from skm.modules.artifacts.domain.file_version import FileVersion
from skm.modules.artifacts.ports import AccessGrantRepository, FileRepository, FileVersionRepository

__all__ = [
    "can_read_version",
    "file_scope",
    "file_scope_of_file",
    "file_scope_of_version",
    "holds",
    "holds_grant",
    "require",
    "require_bound",
    "require_file",
    "require_not_worker",
    "require_version_read",
]


def file_scope(file: File) -> ScopeRef:
    """The scope the stored file belongs to: its project, or its workspace for a workspace-level file."""
    if file.project_id is not None:
        return ScopeRef(ScopeKind.PROJECT, ScopeId(file.project_id))
    return ScopeRef(ScopeKind.WORKSPACE, ScopeId(file.workspace_id))


def file_scope_of_file(query: object, uow: UnitOfWork) -> ScopeRef | None:
    """Bus ``scope_resolver`` of an operation naming a file: the stored file's scope, ``None`` if unknown.

    It reads the owner link only and hands back a scope, never the file or a reason.
    """
    file_id = getattr(query, "file_id", None)
    if not isinstance(file_id, UUID):
        return None
    try:
        return file_scope(uow.repo(FileRepository).get(FileId(file_id)))
    except NotFound:
        return None


def file_scope_of_version(query: object, uow: UnitOfWork) -> ScopeRef | None:
    """Bus ``scope_resolver`` of an operation naming a file version: the scope of the version's file."""
    version_id = getattr(query, "file_version_id", None)
    if not isinstance(version_id, UUID):
        return None
    try:
        version = uow.repo(FileVersionRepository).get(FileVersionId(version_id))
        return file_scope(uow.repo(FileRepository).get(version.file_id))
    except NotFound:
        return None


def require_bound(ctx: CommandContext | QueryContext, file: File) -> None:
    """The stored file belongs to the scope the bus authorised; otherwise ``FORBIDDEN``, nothing is read.

    The bus decided on the scope it resolved before the handler loaded the file. A file whose scope is
    another one (an unknown id that appeared since, a file that changed owner) was not authorised there.
    """
    if file_scope(file) != ctx.scope:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "the file is outside the authorised scope",
            details={"reason": "scope_changed"},
        )


def _chain(uow: UnitOfWork, scope: ScopeRef) -> tuple[ScopeRecord, ...]:
    return uow.repo(ScopeRegistry).ancestors(scope.id)


def _decision(
    uow: UnitOfWork, clock: Clock, actor: Actor, permission: str, scope: ScopeRef
) -> tuple[bool, str | None]:
    verdict = RbacAuthorizer(clock).authorize(uow, actor, permission, _chain(uow, scope))
    return verdict.allowed, verdict.reason_code


def holds(uow: UnitOfWork, clock: Clock, actor: Actor, permission: str, scope: ScopeRef) -> bool:
    return _decision(uow, clock, actor, permission, scope)[0]


def require(uow: UnitOfWork, clock: Clock, actor: Actor, permission: str, scope: ScopeRef) -> None:
    """``FORBIDDEN`` unless ``actor`` holds ``permission`` on ``scope`` now."""
    allowed, reason = _decision(uow, clock, actor, permission, scope)
    if not allowed:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            f"{permission} is not granted here",
            details={"permission": permission, "scope_id": str(scope.id), "reason_code": reason or ""},
        )


def require_file(uow: UnitOfWork, ctx: CommandContext | QueryContext, permission: str, file: File) -> None:
    require(uow, ctx.clock, ctx.actor, permission, file_scope(file))


def require_not_worker(actor: Actor) -> None:
    """A worker never creates, versions, trashes or restores a logical file, even holding ``file.write``."""
    if actor.kind is PrincipalKind.WORKER:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "a worker cannot change a logical file",
            details={"reason": "worker_forbidden"},
        )


def holds_grant(uow: UnitOfWork, ctx: CommandContext | QueryContext, version: FileVersion) -> bool:
    """An active assignment grant of the actor on exactly this version, in the version's workspace.

    An assignment token is bound to one assignment: only the grant whose ``ref`` is that assignment's id
    counts, whatever other claims the principal holds on the version. Without a grant on the actor (or with a
    worker token) any active assignment grant of the principal counts. Anything else is refused.
    """
    token = ctx.actor.grant
    ref: str | None = None
    if token is not None and token.kind == "assignment":
        if token.assignment_id is None:  # the TokenGrant invariant; never trust a half-built grant
            return False
        ref = str(token.assignment_id)
    now = ctx.clock.now()
    grant = uow.repo(AccessGrantRepository).active_for(
        ctx.actor.principal_id, version.id, now, reason=GrantReason.ASSIGNMENT, ref=ref
    )
    return (
        grant is not None
        and grant.reason is GrantReason.ASSIGNMENT
        and (ref is None or grant.ref == ref)
        and grant.principal_id == ctx.actor.principal_id
        and grant.file_version_id == version.id
        and grant.workspace_id == version.workspace_id
        and grant_is_active(grant, now)
    )


def require_version_read(
    uow: UnitOfWork, ctx: CommandContext | QueryContext, file: File, version: FileVersion
) -> None:
    """``file.read`` on the file's scope; a worker also needs an active grant on this very version."""
    require_file(uow, ctx, "file.read", file)
    if ctx.actor.kind is PrincipalKind.WORKER and not holds_grant(uow, ctx, version):
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "no active access grant for this file version",
            details={"reason": "no_active_grant", "file_version_id": str(version.id)},
        )


def can_read_version(
    uow: UnitOfWork, ctx: CommandContext | QueryContext, file: File, version: FileVersion
) -> bool:
    """``require_version_read`` as a predicate (used to filter a listing)."""
    if not holds(uow, ctx.clock, ctx.actor, "file.read", file_scope(file)):
        return False
    return ctx.actor.kind is not PrincipalKind.WORKER or holds_grant(uow, ctx, version)
