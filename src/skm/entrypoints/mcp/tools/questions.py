"""Record assignment questions and read project decision requests."""

from typing import cast

from skm.entrypoints.mcp.session import McpSession
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution import public as execution

from .notes import record_step_note

__all__ = ["ask_question", "decision_summary", "inbox_list"]


def ask_question(session: McpSession, args: JsonObject) -> JsonValue:
    options = cast("list[JsonObject]", args.get("options", []))
    return record_step_note(
        session,
        {
            "kind": "question",
            "text": args["question"],
            "options": [{"id": option["key"], "text": option["text"]} for option in options],
            "why_blocked": args["why_blocked"],
            "urgency": "blocking" if args.get("urgency") == "high" else "normal",
        },
    )


def decision_summary(item: JsonObject) -> JsonValue:
    payload = cast("JsonObject", item["payload"])
    for key in ("question", "text", "summary", "reason"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return item["kind"]


def inbox_list(session: McpSession, args: JsonObject) -> JsonValue:
    run_id = session.run_id
    scope = {"kind": "project", "id": str(session.project_id)}
    if run_id is not None:
        scope = {"kind": "run", "id": str(run_id)}
    query = execution.ListDecisionRequests.from_json(
        {
            "scope": scope,
            "limit": args.get("limit", 20),
            **({"kinds": [args["kind"]]} if "kind" in args else {}),
        }
    )
    page = cast("execution.DecisionRequestsView", session.client.ask(query))
    return {
        "items": [
            {
                "request_id": item["request_id"],
                "kind": item["kind"],
                "run_id": item.get("run_id"),
                "task_key": item.get("task_display_key"),
                "summary": decision_summary(item),
                "asked_at": item["created_at"],
            }
            for item in cast("list[JsonObject]", page.to_json()["items"])
        ],
        "next": page.next_after,
    }
