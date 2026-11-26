"""``api-error/v1`` responses: every failure of a request becomes this envelope with a fresh correlation id.

A :class:`~gui.errors.GuiError` keeps its code and message; anything else is ``INTERNAL`` with a generic message,
and its trace goes (redacted) to ``backend.log`` only.
"""
from __future__ import annotations

import json
import logging
import traceback
import uuid
from functools import wraps
from typing import Any, Awaitable, Callable, Optional

from aicore.util.redact import redact_text
from starlette.requests import Request
from starlette.responses import Response

from ..errors import GuiError, http_status

log = logging.getLogger("gui.backend")


def json_body(document: Any) -> bytes:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def json_response(document: Any, status: int = 200, headers: Optional[dict] = None) -> Response:
    return Response(json_body(document), status_code=status, media_type="application/json", headers=headers)


def error_response(error: GuiError, correlation_id: Optional[str] = None) -> Response:
    return json_response(error.envelope(correlation_id or uuid.uuid4().hex), http_status(error.code))


def log_internal(state, exc: BaseException, correlation_id: str) -> None:
    """The redacted trace of an unexpected failure, in ``backend.log`` (never in a response)."""
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    text = redact_text(text, secrets=state.secrets())
    path = getattr(state, "log_path", None)
    if path is None:
        log.error("INTERNAL %s\n%s", correlation_id, text)
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"INTERNAL {correlation_id}\n{text}\n")
    except OSError:
        pass


def internal(state, exc: BaseException) -> Response:
    correlation_id = uuid.uuid4().hex
    log_internal(state, exc, correlation_id)
    return error_response(GuiError("INTERNAL", "unexpected backend failure; see backend.log"), correlation_id)


def endpoint(handler: Callable[[Request], Awaitable[Response]]) -> Callable[[Request], Awaitable[Response]]:
    """Wrap a route: ``GuiError`` → its envelope, anything else → ``INTERNAL``."""

    @wraps(handler)
    async def wrapped(request: Request) -> Response:
        try:
            return await handler(request)
        except GuiError as error:
            return error_response(error)
        except Exception as exc:  # noqa: BLE001 - the envelope replaces every trace
            return internal(request.app.state.backend, exc)

    return wrapped


async def read_json(request: Request, *, allowed: Optional[set] = None) -> dict:
    """The JSON object of a request body (empty body: ``{}``); ``INPUT_INVALID`` otherwise."""
    raw = await request.body()
    if not raw.strip():
        document: Any = {}
    else:
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise GuiError("INPUT_INVALID", "the body is not valid JSON",
                           issues=[{"pointer": "", "code": "json", "message": "not valid JSON"}]) from None
    if not isinstance(document, dict):
        raise GuiError("INPUT_INVALID", "the body must be a JSON object",
                       issues=[{"pointer": "", "code": "type", "message": "expected an object"}])
    if allowed is not None:
        extra = sorted(set(document) - allowed)
        if extra:
            raise GuiError("INPUT_INVALID", "unknown fields in the body",
                           issues=[{"pointer": f"/{name}", "code": "additional", "message": "unknown field"}
                                   for name in extra])
    return document
