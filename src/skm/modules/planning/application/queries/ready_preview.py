"""``planning.ready_preview`` (planning §5.5, §8): ready lanes, conflicts, waiting, and route groups."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import read_source
from skm.modules.planning.domain.compile_graph import compile_execution_graph
from skm.modules.planning.domain.item import route_to_doc
from skm.modules.planning.domain.ready_preview import preview_ready
from skm.modules.planning.generated.queries import ReadyPreview
from skm.modules.planning.generated.views import ReadyPreviewView

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]

_MAX_LIMIT = 64
_MAX_ASSUME_DONE = 5000
_MAX_ASSUME_GRANTED = 100


def scope_of(query: ReadyPreview) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def handle(query: ReadyPreview, _ctx: QueryContext, uow: UnitOfWork) -> ReadyPreviewView:
    source = read_source(
        uow,
        plan_id=query.plan_id,
        revision_id=query.revision_id,
        draft_id=query.draft_id,
        expected_edit_version=query.expected_edit_version,
    )
    if isinstance(query.limit, bool) or not 1 <= query.limit <= _MAX_LIMIT:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"limit must be between 1 and {_MAX_LIMIT}",
            details={"field": "limit"},
        )
    assume_done = query.assume_done or ()
    assume_granted = query.assume_granted or ()
    if len(assume_done) > _MAX_ASSUME_DONE:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"assume_done cannot exceed {_MAX_ASSUME_DONE} entries",
            details={"field": "assume_done"},
        )
    if len(assume_granted) > _MAX_ASSUME_GRANTED:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"assume_granted cannot exceed {_MAX_ASSUME_GRANTED} entries",
            details={"field": "assume_granted"},
        )

    graph = compile_execution_graph(source.spec)
    preview = preview_ready(
        graph,
        source.spec,
        assume_done=frozenset(assume_done),
        assume_granted=frozenset(assume_granted),
        limit=query.limit,
    )
    payload = {
        "limit": preview.limit,
        "assume_done": list(preview.assume_done),
        "assume_granted": list(preview.assume_granted),
        "lanes": [
            {
                "kind": lane.kind,
                "tasks": list(lane.tasks),
                "route": None if lane.route is None else route_to_doc(lane.route),
                "batch_key": lane.batch_key,
            }
            for lane in preview.lanes
        ],
        "conflicts": [
            {
                "task": c.task,
                "with_task": c.with_task,
                "reason": c.reason,
                "paths": list(c.paths),
            }
            for c in preview.conflicts
        ],
        "waiting": [{"task": w.task, "reason": w.reason, "detail": list(w.detail)} for w in preview.waiting],
        "deferred": list(preview.deferred),
        "route_groups": [
            {"route": route_to_doc(rg.route), "lanes": list(rg.lanes)} for rg in preview.route_groups
        ],
        "source": source.source_view_json(),
    }
    return ReadyPreviewView.from_json(payload)


SPEC = QuerySpec(
    name="planning.ready_preview",
    dto=ReadyPreview,
    result=ReadyPreviewView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
