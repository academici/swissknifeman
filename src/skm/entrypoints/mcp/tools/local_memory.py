"""Handlers for episodic memory in a trusted host-only MCP session."""

from typing import cast
from uuid import UUID

from skm.entrypoints.mcp.session import LocalMemorySession, McpSession
from skm.kernel.data_classification import HOST_PRIVATE
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.knowledge.public import MemoryKind

__all__ = ["record", "search", "summarize"]


def _binding(session: McpSession) -> LocalMemorySession:
    if session.local_memory is None:
        raise Forbidden(ErrorCode.FORBIDDEN, "Local episodic memory requires a host-only session")
    return session.local_memory


def record(session: McpSession, args: JsonObject) -> JsonValue:
    local = _binding(session)
    status = local.store.record(
        local.scope,
        local.session_id,
        MemoryKind(cast("str", args["kind"])),
        cast("str", args["text"]),
        ttl_seconds=cast("int | None", args.get("ttl_seconds")),
    )
    return {"classification": HOST_PRIVATE, "status": status}


def search(session: McpSession, args: JsonObject) -> JsonValue:
    local = _binding(session)
    episodes = local.store.search(
        local.scope,
        local.session_id,
        query=cast("str", args.get("query", "")),
        limit=cast("int", args.get("limit", 10)),
    )
    return {
        "classification": HOST_PRIVATE,
        "items": [
            {
                "id": episode.id,
                "session_id": str(episode.session_id),
                "kind": episode.kind.value,
                "text": episode.text,
                "expires_at": episode.expires_at.isoformat(),
            }
            for episode in episodes
        ],
    }


def summarize(session: McpSession, args: JsonObject) -> JsonValue:
    local = _binding(session)
    source = cast("str | None", args.get("source_session_id"))
    summary = local.store.summarize_session(
        local.scope, local.session_id, source_session_id=None if source is None else UUID(source)
    )
    return {"classification": HOST_PRIVATE, "summary": summary}
