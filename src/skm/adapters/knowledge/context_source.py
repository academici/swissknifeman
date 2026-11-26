"""Recheck live knowledge and access in the caller's context transaction."""

from hashlib import sha256
from typing import override

from skm.kernel.actor import Actor
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.access.public import RbacAuthorizer
from skm.modules.context.domain.contracts import MemoryHit
from skm.modules.context.ports import MemoryRetriever
from skm.modules.knowledge.generated.settings import KnowledgeSettings
from skm.modules.knowledge.public import list_lessons_for_context, search_memory_for_context
from skm.modules.workspace.public import require_active_project, workspace_of_project
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, ScopeTree

__all__ = ["KnowledgeMemoryRetriever"]


def _hit(row: JsonObject, *, lesson: bool) -> MemoryHit:
    source_ref = f"{'knowledge' if lesson else 'memory'}:{row['id']}"
    if lesson:
        conflict = "Potentially conflicting lesson\n" if row.get("atomic_group") is not None else ""
        text = f"{conflict}Trigger: {row['trigger']}\nAction: {row['action']}\nFreshness: {row['freshness']}"
    else:
        text = str(row["body"]).strip()
    return {
        "source_kind": "lesson" if lesson else "memory_entry",
        "source_ref": source_ref,
        "source_version": str(row["row_version"]),
        "content_digest": "sha256:" + sha256(text.encode()).hexdigest(),
        "text": text,
        "classification": "private",
        "scope_id": row.get("scope_id") if lesson else None,
        "scope": None if lesson else row["scope"],
        **(
            {
                "lesson_id": row["id"],
                "freshness": row["freshness"],
                "applicability": row["applicability"],
                "atomic_group": row["atomic_group"],
                "potential_conflict_ids": row["potential_conflict_ids"],
                "evidence": row["evidence"],
            }
            if lesson
            else {}
        ),
    }


class KnowledgeMemoryRetriever(MemoryRetriever):
    def __init__(self, clock: Clock, config: ConfigLoader) -> None:
        self._clock = clock
        self._config = config
        self._authorizer = RbacAuthorizer(clock)

    @override
    def search(
        self,
        uow: UnitOfWork,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        project_id: ProjectId,
        query: str,
        top_k: int,
    ) -> tuple[MemoryHit, ...]:
        """Read current knowledge as seen by the caller's context transaction."""
        if top_k < 1:
            return ()
        now = self._clock.now()
        try:
            if workspace_of_project(uow, project_id) != workspace_id:
                return ()
            require_active_project(uow, project_id)
            chain = uow.repo(ScopeRegistry).ancestors(ScopeId(project_id))
        except NotFound:
            return ()
        except PreconditionFailed as error:
            if error.code is ErrorCode.PROJECT_ARCHIVED:
                return ()
            raise
        if not chain or chain[-1].kind is not ScopeKind.PROJECT or chain[-1].workspace_id != workspace_id:
            return ()
        project_scope = ScopeRef(ScopeKind.PROJECT, ScopeId(project_id))
        settings = self._config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), project_scope).section(
            KnowledgeSettings
        )
        allowed_lessons = tuple(
            ScopeRef(scope.kind, scope.id)
            for index, scope in enumerate(chain)
            if scope.workspace_id == workspace_id
            and self._authorizer.authorize(uow, actor, "lesson.read", chain[: index + 1]).allowed
        )
        lessons = list_lessons_for_context(
            uow,
            allowed_lessons,
            now=now,
            limit=top_k,
            min_confidence=settings.lessons.inject_min_confidence,
        )
        memory = (
            search_memory_for_context(
                uow,
                project_scope.id,
                now=now,
                query=query or None,
                settings=settings.memory,
            )
            if len(lessons) < top_k and self._authorizer.authorize(uow, actor, "memory.read", chain).allowed
            else ()
        )
        return (
            *(_hit(row, lesson=True) for row in lessons),
            *(_hit(row, lesson=False) for row in memory[: top_k - len(lessons)]),
        )
