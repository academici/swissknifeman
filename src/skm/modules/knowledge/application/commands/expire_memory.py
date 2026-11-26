"""Sweep expired memory and purge terminal rows past retention."""

from datetime import timedelta
from typing import Any, cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge.generated.commands import ExpireMemory
from skm.modules.knowledge.generated.results import ExpireMemoryResult
from skm.modules.knowledge.generated.settings import KnowledgeSettings
from skm.modules.knowledge.ports import MemoryRepository


def handle(cmd: dict[str, Any], ctx: CommandContext, uow: UnitOfWork) -> ExpireMemoryResult:
    now = ctx.clock.now()
    settings = ctx.config.section(KnowledgeSettings).memory
    batch = cmd.get("batch", 500)
    repo = uow.repo(MemoryRepository)
    expired = repo.expire_due(now=now, batch=batch)
    purged = repo.purge_older_than(before=now - timedelta(days=settings.retention_days), batch=batch)
    return ExpireMemoryResult(expired=expired, purged=purged)


SPEC = CommandSpec(
    name="knowledge.expire_memory",
    dto=cast("type[dict[str, Any]]", ExpireMemory),
    result=ExpireMemoryResult,
    permission="system.internal",
    scope_of=None,
    handler=handle,
    internal=True,
    allowed_kinds=frozenset({PrincipalKind.SERVICE}),
)
