"""Translate MCP memory requests into project-bound knowledge operations."""

from typing import Any, cast

from skm.bootstrap import current_checkout_revision
from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.mcp.session import McpSession
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.workspace import public as workspace

__all__ = ["forget", "graph_neighbors", "graph_path", "lessons_list", "remember", "search"]

_manifest = next(module for module in MANIFESTS if module.id == "knowledge")
_operations = {
    cast("Any", spec).name: cast("Any", spec).dto for spec in (*_manifest.commands, *_manifest.queries)
}


def _read(session: McpSession, name: str, **fields: Any) -> Any:
    dto = _operations[f"knowledge.{name}"].from_json({"project_id": str(session.project_id), **fields})
    return session.client.ask(dto)


def _project(session: McpSession) -> workspace.ProjectView:
    return cast(
        "workspace.ProjectView", session.client.ask(workspace.GetProject(project_id=session.project_id))
    )


def _graph(session: McpSession, name: str, args: JsonObject) -> JsonObject:
    project = _project(session)
    fields = {key: value for key, value in args.items() if key != "at_revision"}
    head = current_checkout_revision(session.client, project.workspace_id, project=project)
    if head is not None:
        fields["at_revision"] = head
    return cast("JsonObject", _read(session, name, **fields, workspace_id=str(project.workspace_id)))


def graph_neighbors(session: McpSession, args: JsonObject) -> JsonObject:
    return _graph(session, "graph_neighbors", args)


def graph_path(session: McpSession, args: JsonObject) -> JsonObject:
    return _graph(session, "graph_path", args)


def _write(session: McpSession, name: str, **fields: Any) -> JsonObject:
    dto = _operations[f"knowledge.{name}"].from_json({"project_id": str(session.project_id), **fields})
    return cast(
        "JsonObject", session.client.dispatch(dto, idempotency_key=session.client.new_idempotency_key())
    )


def search(session: McpSession, args: JsonObject) -> JsonValue:
    page = _read(session, "search_memory", query=args["query"])
    return {
        "items": [
            {
                "entry_id": row["id"],
                "key": row["kind"].replace("_", "-"),
                "text": row["body"],
                "scope": "project",
                "expires_at": row["expires_at"],
            }
            for row in page["items"][: cast("int", args.get("limit", 10))]
        ]
    }


def remember(session: McpSession, args: JsonObject) -> JsonValue:
    result = _write(
        session,
        "remember",
        kind=cast("str", args["key"]).replace("-", "_"),
        body=args["text"],
        source="mcp",
        ttl_hours=args.get("ttl_hours", 48),
        expected_handoff_id=args.get("expected_handoff_id"),
    )
    return {"entry_id": result["entry_id"], "expires_at": result["expires_at"]}


def forget(session: McpSession, args: JsonObject) -> JsonValue:
    return _write(session, "forget", entry_id=args["entry_id"])


def lessons_list(session: McpSession, args: JsonObject) -> JsonValue:
    project = _project(session)
    query = cast("str", args.get("query", "")).casefold()
    limit = cast("int", args.get("limit", 10))
    items: list[JsonValue] = []
    after = None
    while True:
        page = _read(
            session,
            "list_lessons",
            workspace_id=str(project.workspace_id),
            state="curated",
            after=after,
            limit=200 if query else limit,
        )
        for row in page["items"]:
            if query in (row["trigger"] + " " + row["action"]).casefold():
                items.append(
                    {
                        "lesson_id": row["id"],
                        "title": row["trigger"],
                        "body": row["action"],
                        "confidence": row["confidence"],
                    }
                )
                if len(items) == limit:
                    return {"items": items}
        after = page["next_cursor"]
        if not after:
            return {"items": items}
