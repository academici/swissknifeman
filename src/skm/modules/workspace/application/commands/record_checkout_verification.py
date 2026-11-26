"""``workspace.record_checkout_verification`` (workspace §7).

A recording handler: it works on a binding of a closed workspace too (it only records what a host observed).
The DTO names a binding, which is not a scope: the bus checks the self right and this handler decides
``checkout.bind`` on the binding's workspace.
"""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.versions import ExpectedVersion, check_expected
from skm.modules.workspace.application.events import CheckoutBindingVerified
from skm.modules.workspace.application.guards import SELF_PERMISSION, require
from skm.modules.workspace.domain import checkout_binding as binding_rules
from skm.modules.workspace.domain.checkout_binding import CheckoutBinding, CheckoutBindingId, ObservedCheckout
from skm.modules.workspace.domain.remote_url import NormalizedRemote
from skm.modules.workspace.generated.commands import RecordCheckoutVerification
from skm.modules.workspace.generated.results import RecordCheckoutVerificationResult
from skm.modules.workspace.ports import CheckoutBindingRepository, RepositoryRepository

__all__ = ["PERMISSION", "SPEC", "handle"]

PERMISSION = "checkout.bind"


def _authorized_binding(
    cmd: RecordCheckoutVerification, ctx: CommandContext, uow: UnitOfWork
) -> CheckoutBinding:
    binding = uow.repo(CheckoutBindingRepository).get(CheckoutBindingId(cmd.binding_id))
    require(uow, ctx.clock, ctx.actor, PERMISSION, binding.workspace_id)
    return binding


def _replay_guard(cmd: RecordCheckoutVerification, ctx: CommandContext, uow: UnitOfWork) -> None:
    _authorized_binding(cmd, ctx, uow)


def handle(
    cmd: RecordCheckoutVerification, ctx: CommandContext, uow: UnitOfWork
) -> RecordCheckoutVerificationResult:
    binding = _authorized_binding(cmd, ctx, uow)
    check_expected(binding.row_version, ExpectedVersion(cmd.expected_row_version))
    observed = ObservedCheckout(
        exists=cmd.observed_exists,
        toplevel=cmd.observed_toplevel,
        remotes=tuple(NormalizedRemote(item) for item in cmd.observed_remotes),
        head=cmd.observed_head,
        marker=None,
        observed_at=cmd.observed_at,
        dirty=cmd.observed_dirty,
    )
    remotes = tuple(item.normalized for item in uow.repo(RepositoryRepository).remotes(binding.repository_id))
    result = binding_rules.verify(binding, observed, remotes, ctx.clock.now())
    uow.repo(CheckoutBindingRepository).save(result.binding, expected_version=binding.row_version)
    uow.record(
        CheckoutBindingVerified(
            result.binding.id, binding.workspace_id, result.binding.state, result.reason.value
        )
    )
    return RecordCheckoutVerificationResult(
        binding_id=result.binding.id,
        state=result.binding.state.value,
        reason=result.reason.value,
        row_version=result.binding.row_version,
    )


SPEC = CommandSpec(
    name="workspace.record_checkout_verification",
    dto=RecordCheckoutVerification,
    result=RecordCheckoutVerificationResult,
    permission=SELF_PERMISSION,
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
    replay_guard=_replay_guard,
)
