"""Bind ad hoc execution and standalone assembly to the MCP session project."""

from typing import cast

from skm.entrypoints.mcp.session import McpSession
from skm.kernel.json_types import JsonObject
from skm.modules.context import public as context
from skm.modules.execution import public as execution

__all__ = ["context_assemble", "run_adhoc"]


def run_adhoc(session: McpSession, args: JsonObject) -> JsonObject:
    command = execution.RunAdhoc.from_json({**args, "project_id": str(session.project_id)})
    result = cast(
        "execution.StartRunResult",
        session.client.dispatch(command, idempotency_key=session.client.new_idempotency_key()),
    )
    return result.to_json()


def context_assemble(session: McpSession, args: JsonObject) -> JsonObject:
    command = context.AssembleContext.from_json({**args, "project_id": str(session.project_id)})
    result = cast(
        "context.AssembleContextResult",
        session.client.dispatch(command, idempotency_key=session.client.new_idempotency_key()),
    )
    return result.to_json()
