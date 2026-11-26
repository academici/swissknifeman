"""``access.create_principal`` (access §7.1)."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.ids import PrincipalId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access.application import events
from skm.modules.access.domain.identity import PrincipalIdentity
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.generated.commands import CreatePrincipal
from skm.modules.access.generated.results import CreatePrincipalResult
from skm.modules.access.ports import IdentityRepository, PrincipalRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: CreatePrincipal, ctx: CommandContext, uow: UnitOfWork) -> CreatePrincipalResult:
    now = ctx.clock.now()
    identities = uow.repo(IdentityRepository)
    identity: PrincipalIdentity | None = None
    principal = new_principal(
        principal_id=PrincipalId(ctx.ids.new_id()),
        kind=PrincipalKind(cmd.kind.value),
        display_name=cmd.display_name,
        created_by=ctx.actor.principal_id,
        now=now,
    )
    if cmd.identity is not None:
        if identities.find(cmd.identity.issuer, cmd.identity.subject) is not None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "this external identity is already linked to a principal",
                details={"identity": {"issuer": cmd.identity.issuer, "subject": cmd.identity.subject}},
            )
        try:
            identity = PrincipalIdentity(
                principal_id=principal.id,
                issuer=cmd.identity.issuer,
                subject=cmd.identity.subject,
                created_at=now,
            )
        except ValueError:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "invalid external identity",
                details={"field": "identity", "reason": "issuer"},
            ) from None
    uow.repo(PrincipalRepository).add(principal)
    if identity is not None:
        identities.add(identity)
    uow.record(
        events.PrincipalCreated(
            principal_id=principal.id, kind=principal.kind, display_name=principal.display_name
        )
    )
    return CreatePrincipalResult(principal_id=principal.id, row_version=principal.row_version)


SPEC = CommandSpec(
    name="access.create_principal",
    dto=CreatePrincipal,
    result=CreatePrincipalResult,
    permission="principal.manage",
    scope_of=None,
    handler=handle,
)
