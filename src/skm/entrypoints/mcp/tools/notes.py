"""Append a note bound to the current assignment-token step."""

from typing import cast

from skm.entrypoints.mcp.session import McpSession
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution import public as execution

__all__ = ["record_note", "record_step_note"]


def record_step_note(session: McpSession, payload: JsonObject) -> JsonObject:
    if not session.is_assignment or session.step_id is None or session.assignment_id is None:
        raise Forbidden(ErrorCode.FORBIDDEN, "A step-bound assignment token is required")
    result = cast(
        "execution.RecordStepNoteResult",
        session.client.dispatch(
            execution.RecordStepNote.from_json({**payload, "step_id": str(session.step_id)}),
            idempotency_key=session.client.new_idempotency_key(),
        ),
    )
    return {"note_id": result["note_id"]}


def record_note(session: McpSession, args: JsonObject) -> JsonValue:
    return record_step_note(session, args)
