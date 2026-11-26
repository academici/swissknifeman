"""``execution.get_step`` query handler (execution §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import Forbidden, NotFound
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.public import effective_permissions
from skm.modules.artifacts.public import require_version_read
from skm.modules.execution.application._plain import plain
from skm.modules.execution.domain.ids import StepId
from skm.modules.execution.generated.queries import GetStep
from skm.modules.execution.generated.views import StepView
from skm.modules.execution.ports import ExecutionQueries, StageRepository, StepRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def _resolve_scope(query: GetStep, uow: UnitOfWork) -> ScopeRef | None:
    try:
        step = uow.repo(StepRepository).get(StepId(query.step_id))
        stage = uow.repo(StageRepository).get(step.stage_record_id)
    except NotFound:
        return None
    return ScopeRef(ScopeKind.RUN, ScopeId(stage.run_id))


def handle(query: GetStep, ctx: QueryContext, uow: UnitOfWork) -> StepView:
    sid = StepId(query.step_id)
    step = uow.repo(StepRepository).get(sid)
    stage = uow.repo(StageRepository).get(step.stage_record_id)
    doc = plain(uow.repo(ExecutionQueries).step_view(sid))
    vids = [v for v in (step.raw_result_file_version_id, step.transcript_file_version_id) if v is not None]
    if not vids and step.result is None:
        doc["payload_visibility"] = "unavailable"
        doc.pop("result", None)
    elif vids:
        visibility = "available"
        for vid in vids:
            try:
                require_version_read(uow, ctx.actor, ctx.clock, vid, default_scope=ctx.scope)
            except Forbidden:
                visibility = "restricted"
                break
            except NotFound:
                visibility = "unavailable"
        doc["payload_visibility"] = visibility
        if visibility != "available":
            doc.pop("result", None)
            if visibility == "restricted":
                doc["transcript_file_version_id"] = None
                doc["raw_result_file_version_id"] = None
    else:
        perms = effective_permissions(uow, ctx.actor, ScopeId(stage.run_id))
        if "file.read" in perms:
            doc["payload_visibility"] = "available"
        else:
            doc["payload_visibility"] = "restricted"
            doc.pop("result", None)
    return StepView.from_json(doc)


SPEC = QuerySpec(
    name="execution.get_step",
    dto=GetStep,
    result=StepView,
    permission="run.read",
    scope_of=None,
    handler=handle,
    scope_resolver=_resolve_scope,
)
