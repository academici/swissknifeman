"""Exchange a single-use pairing proof for one credential in the bus transaction."""

from typing import cast
from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.ids import HostId, PrincipalId, ScopeId, WorkerId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access import public as access
from skm.modules.workspace.application.commands.register_worker import register
from skm.modules.workspace.application.guards import require_active_workspace
from skm.modules.workspace.domain import host as host_rules
from skm.modules.workspace.domain.worker import WorkerState
from skm.modules.workspace.generated.commands import ExchangePairingToken, RegisterWorker
from skm.modules.workspace.generated.results import ExchangePairingTokenResult
from skm.modules.workspace.ports import HostRepository, WorkerRepository


def _replace_worker(
    pairing: access.PairingToken, issuer: Actor, ctx: CommandContext, uow: UnitOfWork
) -> tuple[access.PairingResult, str]:
    now = ctx.clock.now()
    old = access.prepare_worker_replacement(uow, pairing, issuer, now)
    worker = uow.repo(WorkerRepository).get(WorkerId(cast("UUID", old.worker_id)))
    if (
        worker.state is WorkerState.RETIRED
        or worker.workspace_id != pairing.workspace_id
        or worker.principal_id != old.principal_id
    ):
        raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "worker registration is unavailable")
    host_rules.require_active(uow.repo(HostRepository).get(HostId(worker.host_id)))
    token, secret = access.issue_bound_worker_token(
        uow,
        principal_id=worker.principal_id,
        issuer=issuer,
        worker_id=worker.id,
        workspace_scope_id=ScopeId(worker.workspace_id),
        host_scope_id=ScopeId(worker.host_id),
        token_name=f"worker-{worker.id}",
        pepper=ctx.gateways.get(access.TokenPepperSource).pepper(),
        entropy=ctx.entropy.bytes,
        now=now,
        settings=ctx.config.section(access.AccessSettings),
    )
    return access.PairingResult(worker.principal_id, token.id, worker.id), secret


def _issue(
    pairing: access.PairingToken, issuer: Actor, ctx: CommandContext, uow: UnitOfWork
) -> tuple[access.PairingResult, str]:
    require_active_workspace(uow, pairing.workspace_id)
    if "replaces" in pairing.binding:
        return _replace_worker(pairing, issuer, ctx, uow)
    if "worker" in pairing.binding:
        command = RegisterWorker.from_json(cast("JsonObject", pairing.binding["worker"]))
        if command.workspace_id != pairing.workspace_id:
            raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "pairing workspace does not match")
        worker, token_id = register(command, ctx, uow, issuer)
        return access.PairingResult(
            PrincipalId(worker.principal_id), token_id, worker.worker_id
        ), worker.token_secret
    return access.issue_paired_personal_token(
        uow,
        pairing,
        issuer,
        now=ctx.clock.now(),
        token_id=access.TokenId(ctx.ids.new_id()),
        pepper=ctx.gateways.get(access.TokenPepperSource).pepper(),
        entropy=ctx.entropy.bytes,
        settings=ctx.config.section(access.AccessSettings),
    )


def handle(cmd: ExchangePairingToken, ctx: CommandContext, uow: UnitOfWork) -> ExchangePairingTokenResult:
    pairing, issuer = access.lock_pairing_token(
        uow,
        cmd.pairing_id,
        cmd.pairing_secret,
        workspace_id=WorkspaceId(cmd.workspace_id),
        now=ctx.clock.now(),
        pepper=ctx.gateways.get(access.TokenPepperSource).pepper(),
    )
    secret = None
    result = pairing.result
    if result is None and issuer is not None:
        result, secret = _issue(pairing, issuer, ctx, uow)
        access.consume_pairing_token(uow, pairing, result, ctx.clock.now())
    if result is None:
        raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "pairing exchange has no outcome")
    return ExchangePairingTokenResult(
        pairing_id=pairing.id,
        worker_id=result.worker_id,
        principal_id=result.principal_id,
        token_id=result.token_id,
        status="exchanged",
        token_secret=secret,
    )


SPEC = CommandSpec(
    name="workspace.exchange_pairing_token",
    dto=ExchangePairingToken,
    result=ExchangePairingTokenResult,
    permission="system.internal",
    scope_of=lambda cmd: ScopeRef(ScopeKind.WORKSPACE, ScopeId(cmd.workspace_id)),
    internal=True,
    handler=handle,
)
