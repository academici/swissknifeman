"""``planning.list_plans`` (planning §8): keyset-paginated list of plans in a project."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.pagination import CURSOR_MAX_LENGTH, Cursor
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import require_project
from skm.modules.planning.generated.queries import ListPlans
from skm.modules.planning.generated.views import PlanSummaryView, PlansView
from skm.modules.planning.ports import PlanningQueries, PlanRepository
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]

_MAX_LIMIT = 200


def scope_of(query: ListPlans) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(query.project_id))


def _bad_cursor() -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID, "cursor is not valid for this query", details={"field": "after"}
    )


def _encode_all_cursor(
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    principal_id: PrincipalId,
    state: str,
    purpose: str,
    updated_at: str,
    plan_id: str,
) -> str:
    payload = json.dumps(
        {
            "w": str(workspace_id),
            "p": str(project_id),
            "a": str(principal_id),
            "s": state,
            "u": purpose,
            "k": [updated_at, plan_id],
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_all_cursor(
    after: str | None,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    principal_id: PrincipalId,
    state: str,
    purpose: str,
) -> tuple[datetime, UUID] | None:
    if after is None:
        return None
    if not 1 <= len(after) <= CURSOR_MAX_LENGTH or not after.isascii():
        raise _bad_cursor()
    try:
        raw = base64.urlsafe_b64decode(after + "=" * (-len(after) % 4))
        doc: object = json.loads(raw.decode("utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("not dict")
        body = cast("dict[str, object]", doc)
        if (
            body.get("w") != str(workspace_id)
            or body.get("p") != str(project_id)
            or body.get("a") != str(principal_id)
            or body.get("s") != state
            or body.get("u") != purpose
        ):
            raise ValueError("filter mismatch")
        keys_obj = body.get("k")
        if not isinstance(keys_obj, list):
            raise ValueError("key shape")
        keys = cast("list[object]", keys_obj)
        if len(keys) != 2:
            raise ValueError("key shape")
        ts_str, id_str = keys[0], keys[1]
        if not isinstance(ts_str, str) or not isinstance(id_str, str):
            raise ValueError("key types")
        moment = datetime.fromisoformat(ts_str)
        if moment.utcoffset() is None:
            raise ValueError("naive")
        return moment, UUID(id_str)
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError):
        raise _bad_cursor() from None


def handle(query: ListPlans, ctx: QueryContext, uow: UnitOfWork) -> PlansView:
    project_id = require_project(uow, query.project_id)
    workspace_id = workspace.workspace_of_project(uow, project_id)
    if isinstance(query.limit, bool) or not 1 <= query.limit <= _MAX_LIMIT:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"limit must be between 1 and {_MAX_LIMIT}",
            details={"field": "limit"},
        )
    if query.state not in ("active", "archived", "all"):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "invalid plan list state", details={"field": "state"}
        )
    if query.purpose not in ("standard", "review_requests", "all"):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "invalid plan list purpose", details={"field": "purpose"}
        )

    queries = uow.repo(PlanningQueries)
    if query.purpose == "standard":
        cursor = None if query.after is None else Cursor(query.after)
        page = queries.list_plans(project_id, state=query.state, cursor=cursor, limit=query.limit)
        return PlansView(
            items=tuple(PlanSummaryView.from_json(item) for item in page.items),
            next_cursor=None if page.next is None else str(page.next),
        )

    bound = _decode_all_cursor(
        query.after, workspace_id, project_id, ctx.actor.principal_id, query.state, query.purpose
    )
    candidates: list[PlanSummaryView] = []

    if query.purpose == "all":
        std_cursor: Cursor | None = None
        while len(candidates) < query.limit + 1:
            std_page = queries.list_plans(project_id, state=query.state, cursor=std_cursor, limit=_MAX_LIMIT)
            for item in std_page.items:
                view = PlanSummaryView.from_json(item)
                if bound is None or (view.updated_at, view.plan_id) < bound:
                    candidates.append(view)
                    if len(candidates) >= query.limit + 1:
                        break
            if std_page.next is None:
                break
            std_cursor = std_page.next

    rr_plan = uow.repo(PlanRepository).find_review_requests_plan(project_id)
    if rr_plan is not None and (query.state == "all" or rr_plan.lifecycle.value == query.state):
        rr_view = PlanSummaryView.from_json(queries.plan_summary(rr_plan.id))
        if bound is None or (rr_view.updated_at, rr_view.plan_id) < bound:
            candidates.append(rr_view)

    candidates.sort(key=lambda c: (c.updated_at, c.plan_id), reverse=True)
    sliced = candidates[: query.limit + 1]
    items = tuple(sliced[: query.limit])
    next_cursor = (
        None
        if len(sliced) <= query.limit
        else _encode_all_cursor(
            workspace_id,
            project_id,
            ctx.actor.principal_id,
            query.state,
            query.purpose,
            items[-1].updated_at.isoformat().replace("+00:00", "Z"),
            str(items[-1].plan_id),
        )
    )
    return PlansView(items=items, next_cursor=next_cursor)


SPEC = QuerySpec(
    name="planning.list_plans",
    dto=ListPlans,
    result=PlansView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
