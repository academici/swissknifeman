"""Read the immutable, bounded correction handoff (execution §§5.9, 8)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import NotFound
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.domain.fix_brief import fix_brief_to_json
from skm.modules.execution.domain.ids import FixBriefId
from skm.modules.execution.ports import AttemptRepository, ReviewRepository

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "FixBriefView", "GetFixBrief", "handle"]


@dataclass(frozen=True, slots=True)
class GetFixBrief:
    """Bus wrapper for the generated JSON-mode query contract."""

    fix_brief_id: UUID
    SCHEMA_URN: ClassVar[str] = "urn:skm:execution:query:get-fix-brief:v1"

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Self:
        return cls(UUID(str(data["fix_brief_id"])))

    def to_json(self) -> JsonObject:
        return {"fix_brief_id": str(self.fix_brief_id)}


@dataclass(frozen=True, slots=True)
class FixBriefView:
    document: JsonObject
    full_report_file_version_id: UUID
    SCHEMA_URN: ClassVar[str] = "urn:skm:execution:view:get-fix-brief:v1"

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Self:
        return cls(deepcopy(data["document"]), UUID(str(data["full_report_file_version_id"])))

    def to_json(self) -> JsonObject:
        return {
            "document": deepcopy(self.document),
            "full_report_file_version_id": str(self.full_report_file_version_id),
        }


def _resolve_scope(query: GetFixBrief, uow: UnitOfWork) -> ScopeRef | None:
    try:
        brief = uow.repo(ReviewRepository).get_fix_brief(FixBriefId(query.fix_brief_id))
        attempt = uow.repo(AttemptRepository).get(brief.attempt_id)
    except NotFound:
        return None
    return ScopeRef(ScopeKind.RUN, ScopeId(attempt.run_id))


def handle(query: GetFixBrief, _ctx: QueryContext, uow: UnitOfWork) -> FixBriefView:
    brief = uow.repo(ReviewRepository).get_fix_brief(FixBriefId(query.fix_brief_id))
    return FixBriefView(fix_brief_to_json(brief), brief.full_report_file_version_id)


SPEC = QuerySpec(
    name="execution.get_fix_brief",
    dto=GetFixBrief,
    result=FixBriefView,
    permission="run.read",
    scope_of=None,
    handler=handle,
    scope_resolver=_resolve_scope,
)
