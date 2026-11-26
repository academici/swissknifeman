"""Project-authorized receipt selection for CLI and the review gate."""

from typing import Any
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import NotFound
from skm.kernel.ids import RunId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.domain.review_request import ReviewReceipt
from skm.modules.execution.ports import ExecutionQueries, ReviewRequestRepository, RunRepository


class GetReviewReceipt(WireRecord):
    SCHEMA_URN = "urn:skm:execution:query:get-review-receipt:v1"


def selected_run(query: GetReviewReceipt, uow: UnitOfWork) -> RunId:
    if "run_id" in query:
        return RunId(UUID(query["run_id"]))
    return uow.repo(ReviewRequestRepository).select_run_id(query.to_json())


def resolve_scope(query: GetReviewReceipt, uow: UnitOfWork) -> ScopeRef | None:
    if "project_id" in query:
        return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(query["project_id"])))
    try:
        run = uow.repo(RunRepository).get(selected_run(query, uow))
        return ScopeRef(ScopeKind.PROJECT, ScopeId(run.project_id))
    except NotFound:
        return None


def handle(query: GetReviewReceipt, _ctx: Any, uow: UnitOfWork) -> ReviewReceipt:
    run_id = selected_run(query, uow)
    uow.repo(ReviewRequestRepository).for_run(run_id)
    return ReviewReceipt.from_json(uow.repo(ExecutionQueries).review_receipt(run_id))


SPEC = QuerySpec(
    name="execution.get_review_receipt",
    dto=GetReviewReceipt,
    result=ReviewReceipt,
    permission="run.read",
    scope_of=None,
    handler=handle,
    scope_resolver=resolve_scope,
)
