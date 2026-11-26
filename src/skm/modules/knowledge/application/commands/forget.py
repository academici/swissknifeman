"""Forget an entry only within its authorized scope."""

from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge.application.scopes import (
    project_memory_scope,
    project_ref,
    requested_scope,
    require_instance_write,
)
from skm.modules.knowledge.domain.events import MemoryForgotten
from skm.modules.knowledge.domain.memory_entry import MemoryEntryId, forget
from skm.modules.knowledge.domain.memory_scope import MemoryScopeKind, allowed_scopes, ensure_scope_allowed
from skm.modules.knowledge.generated.commands import Forget
from skm.modules.knowledge.generated.results import ForgetResult
from skm.modules.knowledge.generated.settings import KnowledgeSettings
from skm.modules.knowledge.ports import MemoryRepository


def handle(cmd: dict[str, Any], ctx: CommandContext, uow: UnitOfWork) -> ForgetResult:
    project = None if cmd["project_id"] is None else project_memory_scope(uow, cmd["project_id"])
    repo = uow.repo(MemoryRepository)
    entry_id = cmd.get("entry_id")

    if entry_id is None:
        target = cmd["scope"]
        scope = requested_scope(target["kind"], target.get("namespace"), project)
    else:
        scope = repo.get(MemoryEntryId(UUID(entry_id))).scope
        if scope != project and (project is not None or scope.kind is MemoryScopeKind.PROJECT):
            raise NotFound(ErrorCode.NOT_FOUND, "Memory entry not found")

    if project is not None:
        settings = ctx.config.section(KnowledgeSettings).memory
        ensure_scope_allowed(scope, allowed_scopes(project, settings.namespaces))
    require_instance_write(scope, project, ctx, uow)
    repo.lock_scope(scope)
    now = ctx.clock.now()
    entry = repo.live_handoff(scope, now=now) if entry_id is None else repo.get(MemoryEntryId(UUID(entry_id)))
    if entry is None:
        return ForgetResult(forgotten=0)
    updated = forget(entry, now)
    if updated is entry:
        return ForgetResult(forgotten=0)
    repo.save(updated, expected_version=entry.row_version)
    uow.record(MemoryForgotten(scope, (entry.id,)))
    return ForgetResult(forgotten=1)


SPEC = CommandSpec(
    name="knowledge.forget",
    dto=cast("type[dict[str, Any]]", Forget),
    result=ForgetResult,
    permission="memory.write",
    scope_of=lambda cmd: project_ref(cmd["project_id"]),
    handler=handle,
    idempotency=IdempotencyMode.REQUIRED,
)
