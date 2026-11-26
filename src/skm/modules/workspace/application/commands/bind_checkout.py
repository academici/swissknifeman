"""``workspace.bind_checkout`` (workspace §7).

The host op sends facts it observed; the server re-checks the remotes against the repository before it trusts
the decision (``CHECKOUT_MISMATCH``, ``reason=remotes``). The DTO names a repository, which is not a scope:
the bus checks the self right and this handler decides ``checkout.bind`` on the repository's workspace.
``local_locator`` is never written to an event.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import HostId, RepositoryId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.workspace.application.events import CheckoutBindingVerified, CheckoutBound
from skm.modules.workspace.application.guards import SELF_PERMISSION, require, require_active_workspace
from skm.modules.workspace.domain import checkout_binding as binding_rules
from skm.modules.workspace.domain.checkout_binding import CheckoutBindingId, ObservedCheckout
from skm.modules.workspace.domain.host import require_active as require_active_host
from skm.modules.workspace.domain.remote_url import NormalizedRemote
from skm.modules.workspace.domain.repository import Repository
from skm.modules.workspace.generated.commands import BindCheckout
from skm.modules.workspace.generated.results import BindCheckoutResult
from skm.modules.workspace.ports import CheckoutBindingRepository, HostRepository, RepositoryRepository

__all__ = ["PERMISSION", "SPEC", "handle"]

PERMISSION = "checkout.bind"


def _authorized_repository(cmd: BindCheckout, ctx: CommandContext, uow: UnitOfWork) -> Repository:
    repository = uow.repo(RepositoryRepository).get(RepositoryId(cmd.repository_id))
    require(uow, ctx.clock, ctx.actor, PERMISSION, repository.workspace_id)
    return repository


def _replay_guard(cmd: BindCheckout, ctx: CommandContext, uow: UnitOfWork) -> None:
    _authorized_repository(cmd, ctx, uow)


def handle(cmd: BindCheckout, ctx: CommandContext, uow: UnitOfWork) -> BindCheckoutResult:
    repository = _authorized_repository(cmd, ctx, uow)
    workspace = require_active_workspace(uow, repository.workspace_id)
    host = uow.repo(HostRepository).get(HostId(cmd.host_id))
    require_active_host(host)
    locator = binding_rules.normalize_locator(cmd.local_locator)
    now = ctx.clock.now()
    observed = ObservedCheckout(
        exists=cmd.observed_toplevel is not None,
        toplevel=cmd.observed_toplevel,
        remotes=tuple(NormalizedRemote(item) for item in cmd.observed_remotes),
        head=cmd.observed_head,
        marker=None,
        observed_at=cmd.observed_at,
        dirty=cmd.observed_dirty,
    )
    remotes = tuple(item.normalized for item in uow.repo(RepositoryRepository).remotes(repository.id))
    bindings = uow.repo(CheckoutBindingRepository)
    existing = bindings.find(host.id, repository.id)
    if existing is not None:
        if existing.local_locator != locator:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "the repository is already bound on this host",
                details={"kind": "binding", "binding_id": str(existing.id)},
            )
        result = binding_rules.verify(
            existing, observed, remotes, now
        )  # the same checkout: a fresh observation
        bindings.save(result.binding, expected_version=existing.row_version)
        uow.record(
            CheckoutBindingVerified(
                result.binding.id, workspace.id, result.binding.state, result.reason.value
            )
        )
    else:
        result = binding_rules.new_binding(
            binding_id=CheckoutBindingId(ctx.ids.new_id()),
            workspace_id=workspace.id,
            host_id=host.id,
            repository_id=repository.id,
            local_locator=locator,
            observed=observed,
            repository_remotes=remotes,
            now=now,
        )
        bindings.add(result.binding)
        uow.record(
            CheckoutBound(result.binding.id, workspace.id, host.id, repository.id, result.binding.state)
        )
    return BindCheckoutResult(
        binding_id=result.binding.id,
        state=result.binding.state.value,
        reason=result.reason.value,
        row_version=result.binding.row_version,
    )


SPEC = CommandSpec(
    name="workspace.bind_checkout",
    dto=BindCheckout,
    result=BindCheckoutResult,
    permission=SELF_PERMISSION,
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
    replay_guard=_replay_guard,
)
