"""``execution.list_decision_requests`` query handler (execution §8)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ProjectId, RunId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.application.queries import (
    bad_cursor,
    check_limit,
    decode_token,
    encode_token,
    parse_inbox_scope,
)
from skm.modules.execution.domain.decision_request import DecisionKind, DecisionState
from skm.modules.execution.generated.queries import ListDecisionRequests
from skm.modules.execution.generated.views import DecisionRequestsView
from skm.modules.execution.ports import ExecutionQueries, RunRepository
from skm.modules.workspace.public import workspace_of_project

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def _resolve_scope(query: ListDecisionRequests, _uow: UnitOfWork) -> ScopeRef | None:
    return parse_inbox_scope(query.scope)


def handle(query: ListDecisionRequests, ctx: QueryContext, uow: UnitOfWork) -> DecisionRequestsView:
    scope_ref = parse_inbox_scope(query.scope)
    if scope_ref.kind is ScopeKind.PROJECT:
        workspace_of_project(uow, ProjectId(UUID(str(scope_ref.id))))
    else:
        uow.repo(RunRepository).get(RunId(UUID(str(scope_ref.id))))
    limit = check_limit(query.limit, default=50)
    try:
        kinds = frozenset(DecisionKind(k) for k in query.kinds) if query.kinds else frozenset(DecisionKind)
        states = {DecisionState(s).value for s in (query.states if query.states is not None else ("open",))}
    except ValueError:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid decision filter") from None
    sig: dict[str, JsonValue] = {
        "sc": f"{scope_ref.kind.value}:{scope_ref.id}",
        "a": str(ctx.actor.principal_id),
        "k": list[JsonValue](sorted(k.value for k in kinds)),
        "st": list[JsonValue](sorted(states)),
    }
    raw_cur: str | None = None
    if query.after is not None:
        tok = decode_token(query.after)
        if {k: tok.get(k) for k in sig} != sig or not isinstance(tok.get("c"), str):
            raise bad_cursor()
        raw_cur = str(tok["c"])
    matched: list[JsonObject] = []
    cur = raw_cur
    queries = uow.repo(ExecutionQueries)
    while len(matched) < limit + 1:
        page = queries.inbox_page((scope_ref.id,), cur, max(limit, 50), kinds)
        page_items = cast("Sequence[JsonObject]", page.get("items", ()))
        for item in page_items:
            if item.get("state") in states:
                matched.append(item)
                if len(matched) >= limit + 1:
                    break
        nxt = page.get("next_after")
        if len(matched) >= limit + 1 or nxt is None or not page_items:
            break
        cur = str(nxt)
    has_more = len(matched) > limit
    sliced = matched[:limit]
    next_after = (
        None
        if not (has_more and sliced)
        else encode_token({**sig, "c": f"{sliced[-1]['created_at']}|{sliced[-1]['request_id']}"})
    )
    return DecisionRequestsView.from_json({"items": sliced, "next_after": next_after})


SPEC = QuerySpec(
    name="execution.list_decision_requests",
    dto=ListDecisionRequests,
    result=DecisionRequestsView,
    permission="inbox.read",
    scope_of=None,
    handler=handle,
    scope_resolver=_resolve_scope,
)
