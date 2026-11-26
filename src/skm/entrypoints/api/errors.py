"""Catalog-owned HTTP statuses and the public problem document boundary."""

from types import MappingProxyType

from starlette.requests import Request
from starlette.responses import JSONResponse

from skm.kernel.error_codes import CATALOG, ErrorCategory, ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.json_types import JsonObject
from skm.platform.logging.redaction import Redactor

__all__ = ["HTTP_STATUS", "problem_response"]

HTTP_STATUS = MappingProxyType({code: info.http_status for code, info in CATALOG.items()})


def problem_response(request: Request, error: Exception) -> JSONResponse:
    """Never serialize an unknown exception, its cause or internal error details."""
    if not isinstance(error, SkmError) or error.category is ErrorCategory.INTERNAL:
        error = error_for(ErrorCode.INTERNAL_ERROR, "Internal error")
    redactor: Redactor = getattr(request.state, "redactor", Redactor())
    document: JsonObject = {
        "type": f"urn:skm:error:{error.code}",
        "title": error.code.value.replace("_", " ").capitalize(),
        "status": HTTP_STATUS[error.code],
        "code": error.code.value,
        "category": error.category.value,
        "detail": redactor.text(error.message),
        "details": redactor.document(dict(error.details)),
        "retryable": error.retryable,
        "request_id": getattr(request.state, "request_id", ""),
        "instance": request.scope["path"],
    }
    headers: dict[str, str] = {}
    if error.category is ErrorCategory.UNAUTHENTICATED:
        headers["WWW-Authenticate"] = "Bearer"
    if error.category is ErrorCategory.BACKEND and error.retryable:
        headers["Retry-After"] = "2"
    elif error.code is ErrorCode.AUTH_RATE_LIMITED:
        retry_after = error.details.get("retry_after")
        headers["Retry-After"] = (
            str(retry_after) if isinstance(retry_after, int) and retry_after > 0 else "60"
        )
    return JSONResponse(
        document,
        status_code=HTTP_STATUS[error.code],
        headers=headers,
        media_type="application/problem+json",
    )
