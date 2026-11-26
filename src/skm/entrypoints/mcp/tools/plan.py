"""Project-bound planning reads and draft authoring through the session client."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Protocol, cast
from uuid import UUID

from skm.entrypoints.mcp.session import McpSession
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.planning import public as planning

__all__ = [
    "draft_abandon",
    "draft_open",
    "draft_rebase",
    "draft_save",
    "entities",
    "entity",
    "get_entity",
    "list_plans",
    "publication_preview",
    "publish",
    "read_text",
    "revision_id",
    "show",
]


class _Record(Protocol):
    def to_json(self) -> JsonObject: ...


def _plan(session: McpSession, ref: str) -> planning.PlanRefView:
    try:
        view = cast(
            "planning.PlanRefView", session.client.ask(planning.ResolvePlanRef(session.project_id, ref))
        )
    except ValidationFailed as error:
        if session.is_assignment and error.code is ErrorCode.AMBIGUOUS_REFERENCE:
            raise _plan_not_found(ref) from None
        raise
    if session.is_assignment and not _can_read(session.refresh().permissions_by_scope, view.plan_id):
        raise _plan_not_found(ref)
    return view


def _plan_not_found(ref: str) -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, "plan not found in this project", details={"ref": ref})


def _can_read(permissions: Mapping[str, tuple[str, ...]], plan_id: UUID) -> bool:
    return "plan.read" in permissions.get(str(plan_id), ())


def revision_id(session: McpSession, plan_id: UUID, number: int | None) -> UUID:
    if number is None:
        plan = cast("planning.PlanView", session.client.ask(planning.GetPlan(plan_id)))
        if plan.current_revision_id is not None:
            return plan.current_revision_id
    else:
        page = cast(
            "planning.RevisionsView", session.client.ask(planning.ListRevisions(plan_id, number + 1, 1))
        )
        if page.items and page.items[0].revision_no == number:
            return page.items[0].revision_id
    raise NotFound(ErrorCode.NOT_FOUND, "plan revision not found")


def list_plans(session: McpSession, args: JsonObject) -> JsonValue:
    query = planning.ListPlans.from_json({"limit": 20, **args, "project_id": str(session.project_id)})
    permissions = session.refresh().permissions_by_scope if session.is_assignment else None
    fields = ("plan_id", "alias", "title", "current_revision_no", "open_drafts", "updated_at")
    while True:
        page = cast("planning.PlansView", session.client.ask(query))
        items: list[JsonValue] = []
        for item in page.items:
            if permissions is None or _can_read(permissions, item.plan_id):
                doc = item.to_json()
                items.append({key: doc[key] for key in fields})
        if permissions is None:
            return {"items": items, "next": page.next_cursor}
        if items or page.next_cursor is None:
            # An assignment has one ancestor plan. Its project page cursor may
            # contain the identity of a sibling plan outside the token's scope.
            return {"items": items, "next": None}
        query = planning.ListPlans.from_json({**query.to_json(), "after": page.next_cursor})


def show(session: McpSession, args: JsonObject) -> JsonValue:
    plan = _plan(session, str(args["plan"]))
    revision_uuid = revision_id(session, plan.plan_id, cast("int | None", args.get("revision")))
    include_tree = cast("bool", args.get("include_tree", True))
    revision = cast(
        "planning.RevisionView",
        session.client.ask(
            planning.GetRevision(
                plan.plan_id, revision_id=revision_uuid, include_document=True, include_tree=include_tree
            )
        ),
    )
    document = cast("JsonObject", revision.to_json()["document"])
    result: JsonObject = {
        "plan_id": str(plan.plan_id),
        "alias": plan.alias,
        "title": plan.title,
        "revision_no": revision.revision_no,
        "goal": document["goal"],
        "requirements_count": len(cast("list[JsonValue]", document.get("requirements", []))),
        "checks_count": len(cast("list[JsonValue]", document.get("checks", []))),
    }
    if include_tree:
        phases = cast("list[JsonObject]", (revision.tree or {})["phases"])
        result["phases"] = [
            {
                "key": phase["key"],
                "title": phase["title"],
                "items": [
                    {
                        "key": item["key"],
                        "title": item["title"],
                        "units": [unit["key"] for unit in cast("list[JsonObject]", item["units"])],
                    }
                    for item in cast("list[JsonObject]", phase["items"])
                ],
            }
            for phase in phases
        ]
    return result


def _payload(session: McpSession, args: JsonObject) -> JsonObject:
    plan_id = _plan(session, str(args["plan"])).plan_id
    return {"plan_id": str(plan_id), **{key: value for key, value in args.items() if key != "plan"}}


def _source_payload(session: McpSession, args: JsonObject) -> JsonObject:
    payload = _payload(session, args)
    number = cast("int | None", payload.pop("revision", None))
    if "draft_id" not in payload and "revision_id" not in payload:
        payload["revision_id"] = str(revision_id(session, UUID(str(payload["plan_id"])), number))
    return payload


def get_entity(session: McpSession, query: planning.GetEntity) -> planning.EntityView:
    ref = query.ref.strip()
    if "/" in ref:
        # The HTTP entity route uses one path segment. Resolve compound display
        # keys against the same pinned source before requesting the full entity.
        page_query = planning.ListEntities(
            query.plan_id,
            revision_id=query.revision_id,
            draft_id=query.draft_id,
            expected_edit_version=query.expected_edit_version,
            limit=200,
        )
        while True:
            page = cast("planning.EntityPageView", session.client.ask(page_query))
            for item in page.items:
                if item.display_key == ref:
                    return cast(
                        "planning.EntityView",
                        session.client.ask(replace(query, ref=f"entity:{item.entity_id}")),
                    )
            if page.next_cursor is None:
                raise NotFound(
                    ErrorCode.NOT_FOUND, "entity not found", details={"kind": "entity", "ref": ref}
                )
            page_query = replace(page_query, after=page.next_cursor)
    return cast("planning.EntityView", session.client.ask(query))


def entity(session: McpSession, args: JsonObject) -> JsonValue:
    payload = _source_payload(session, args)
    payload["ref"] = payload.pop("entity")
    return get_entity(session, planning.GetEntity.from_json(payload)).to_json()


def entities(session: McpSession, args: JsonObject) -> JsonValue:
    query = planning.ListEntities.from_json(_source_payload(session, args))
    return cast("planning.EntityPageView", session.client.ask(query)).to_json()


def read_text(session: McpSession, args: JsonObject) -> JsonValue:
    query = planning.ReadText.from_json(_source_payload(session, args))
    return cast("planning.TextFragmentView", session.client.ask(query)).to_json()


def publication_preview(session: McpSession, args: JsonObject) -> JsonValue:
    query = planning.PreviewPublication.from_json(_payload(session, args))
    return cast("_Record", session.client.ask(query)).to_json()


def _write(
    session: McpSession,
    args: JsonObject,
    command: type[
        planning.OpenDraft
        | planning.SaveDraft
        | planning.RebaseDraft
        | planning.PublishRevision
        | planning.AbandonDraft
    ],
) -> JsonObject:
    payload = _payload(session, args)
    key = cast("str | None", payload.pop("idempotency_key", None))
    result = session.client.dispatch(
        command.from_json(payload), idempotency_key=key or session.client.new_idempotency_key()
    )
    return cast("_Record", result).to_json()


def draft_open(session: McpSession, args: JsonObject) -> JsonValue:
    return _write(session, args, planning.OpenDraft)


def draft_save(session: McpSession, args: JsonObject) -> JsonValue:
    return _write(session, args, planning.SaveDraft)


def draft_rebase(session: McpSession, args: JsonObject) -> JsonValue:
    return _write(session, args, planning.RebaseDraft)


def publish(session: McpSession, args: JsonObject) -> JsonValue:
    return _write(session, args, planning.PublishRevision)


def draft_abandon(session: McpSession, args: JsonObject) -> JsonValue:
    return _write(session, args, planning.AbandonDraft)
