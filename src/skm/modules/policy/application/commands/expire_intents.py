"""``policy.expire_intents`` (policy §7, internal): the background sweep of intents nobody decided in time.

A ``proposed`` intent past its ``expires_at`` and an ``approved`` intent whose approvals are all expired
become ``expired``; each emits ``IntentResolved{outcome: expired}``. Only the system actor calls it.
"""

from __future__ import annotations

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.policy.domain.events import IntentResolved
from skm.modules.policy.domain.tool_intent import expire
from skm.modules.policy.generated.commands import ExpireIntents
from skm.modules.policy.generated.results import ExpireIntentsResult
from skm.modules.policy.ports import ToolIntentRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: ExpireIntents, ctx: CommandContext, uow: UnitOfWork) -> ExpireIntentsResult:
    intents = uow.repo(ToolIntentRepository)
    due = intents.expired(ctx.clock.now(), limit=cmd.limit)
    for intent in due:
        expired = expire(intent)
        intents.save(expired, expected_version=intent.row_version)
        uow.record(IntentResolved(intent_id=expired.id, workspace_id=expired.workspace_id, outcome="expired"))
    return ExpireIntentsResult(expired=len(due))


SPEC = CommandSpec(
    name="policy.expire_intents",
    dto=ExpireIntents,
    result=ExpireIntentsResult,
    permission="system.internal",
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
    internal=True,
    allowed_kinds=frozenset({PrincipalKind.SERVICE}),
)
