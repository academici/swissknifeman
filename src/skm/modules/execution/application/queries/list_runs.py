"""``execution.list_runs`` query handler (execution §8)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ProjectId, ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.application.queries import bad_cursor, check_limit, decode_token, encode_token
from skm.modules.execution.domain.run import RunKind, RunStatus
from skm.modules.execution.generated.queries import ListRuns
from skm.modules.execution.generated.views import RunsView
from skm.modules.execution.ports import ExecutionQueries
from skm.modules.workspace.public import workspace_of_project

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def handle(query: ListRuns, ctx: QueryContext, uow: UnitOfWork) -> RunsView:
    project_id = ProjectId(query.project_id)
    workspace_of_project(uow, project_id)
    limit = check_limit(query.limit, default=50)
    try:
        statuses = frozenset(RunStatus(s) for s in query.statuses) if query.statuses else frozenset(RunStatus)
        kinds = frozenset(RunKind(k) for k in (query.kinds if query.kinds is not None else ("plan",)))
    except ValueError:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid run filter") from None
    sig: dict[str, JsonValue] = {
        "p": str(project_id),
        "a": str(ctx.actor.principal_id),
        "s": list[JsonValue](sorted(s.value for s in statuses)),
        "k": list[JsonValue](sorted(k.value for k in kinds)),
        "pl": None if query.plan_id is None else str(query.plan_id),
    }
    raw_cursor: str | None = None
    if query.after is not None:
        tok = decode_token(query.after)
        if {k: tok.get(k) for k in sig} != sig or not isinstance(tok.get("c"), str):
            raise bad_cursor()
        raw_cursor = str(tok["c"])

    matched: list[JsonObject] = []
    cur = raw_cursor
    last_item_cursor: str | None = None
    queries = uow.repo(ExecutionQueries)
    while len(matched) < limit + 1:
        page = queries.runs_page(project_id, cur, max(limit, 50), statuses)
        page_items = cast("Sequence[JsonObject]", page.get("items", ()))
        for idx, item in enumerate(page_items):
            if item.get("kind") in {k.value for k in kinds} and (
                query.plan_id is None or item.get("plan_id") == str(query.plan_id)
            ):
                matched.append(item)
                if len(matched) == limit and (
                    idx + 1 < len(page_items) or page.get("next_after") is not None
                ):
                    last_item_cursor = (
                        f"{item.get('created_at', item.get('started_at', ''))}|{item['run_id']}"
                    )
                if len(matched) >= limit + 1:
                    break
        nxt = page.get("next_after")
        if len(matched) >= limit + 1 or nxt is None or not page_items:
            break
        cur = str(nxt)

    has_more = len(matched) > limit
    sliced = matched[:limit]
    next_after: str | None = None
    if has_more and sliced:
        last = sliced[-1]
        c_val = last_item_cursor or f"{last.get('created_at', last.get('started_at', ''))}|{last['run_id']}"
        next_after = encode_token({**sig, "c": c_val})
    clean_items = [{k: v for k, v in it.items() if not k.startswith("_")} for it in sliced]
    return RunsView.from_json({"items": clean_items, "next_after": next_after})


SPEC = QuerySpec(
    name="execution.list_runs",
    dto=ListRuns,
    result=RunsView,
    permission="run.read",
    scope_of=lambda q: ScopeRef(ScopeKind.PROJECT, ScopeId(q.project_id)),
    handler=handle,
)
