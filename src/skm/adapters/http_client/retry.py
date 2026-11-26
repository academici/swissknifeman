"""Route-owned idempotency and bounded retries for HTTP requests."""

import random
import re
from collections.abc import Callable
from concurrent.futures import Future
from threading import Thread
from typing import cast

import httpx

from skm.application_bus.registry import IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, InternalError, SkmError, ValidationFailed, error_for
from skm.kernel.json_types import JsonObject
from skm.platform.logging.redaction import Redactor

__all__ = [
    "TRANSPORT_FAILURES",
    "idempotency_key",
    "send_before_deadline",
    "send_with_retry",
    "transport_error",
]

_KEY = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_RETRY_STATUSES = {502, 503, 504}
_NO_RETRY_CODES = {ErrorCode.VERSION_CONFLICT, ErrorCode.CLIENT_TOO_OLD}
TRANSPORT_FAILURES = (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError)


def idempotency_key(
    mode: IdempotencyMode, supplied: str | None, *, retry: bool, generate: Callable[[], str]
) -> str | None:
    if mode is IdempotencyMode.FORBIDDEN:
        if supplied is not None:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "Operation forbids an idempotency key",
                details={"reason": "not_idempotent"},
            )
        return None
    if supplied is None and (retry or mode is IdempotencyMode.REQUIRED):
        return generate()
    if supplied is not None and _KEY.fullmatch(supplied) is None:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid idempotency key")
    return supplied


def transport_error(*, retryable: bool = True) -> BackendUnavailable:
    return BackendUnavailable(
        ErrorCode.BACKEND_UNAVAILABLE,
        "HTTP backend unavailable",
        details={"reason": "http_transport"},
        retryable=retryable,
    )


def _problem(response: httpx.Response, redactor: Redactor) -> SkmError:
    if (
        response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        == "application/problem+json"
    ):
        try:
            raw: object = response.json()
            if isinstance(raw, dict):
                problem = cast("JsonObject", raw)
                code = ErrorCode(problem["code"])
                message = problem.get("detail", problem.get("message"))
                details = redactor.document(problem.get("details", {}))
                retryable = problem.get("retryable")
                return error_for(
                    code,
                    redactor.text(message) if isinstance(message, str) else "HTTP request failed",
                    details=details if isinstance(details, dict) else None,
                    retryable=(
                        False
                        if 400 <= response.status_code < 500
                        else retryable
                        if type(retryable) is bool
                        else None
                    ),
                )
        except (ValueError, TypeError, KeyError):
            pass
    elif response.status_code in _RETRY_STATUSES:
        return transport_error()
    return InternalError(
        ErrorCode.INTERNAL_ERROR, "Invalid HTTP error response", details={"status": response.status_code}
    )


def send_before_deadline(send: Callable[[], httpx.Response], remaining: float) -> httpx.Response:
    """Bound the whole JSON exchange even when a peer trickles bytes between read timeouts."""
    if remaining <= 0:
        raise transport_error(retryable=False)
    reply = Future[httpx.Response]()

    def run() -> None:
        try:
            reply.set_result(send())
        except BaseException as error:  # noqa: BLE001 -- propagate transport failure to the caller
            reply.set_exception(error)

    Thread(target=run, daemon=True, name="skm-http-request").start()
    try:
        return reply.result(timeout=remaining)
    except TimeoutError:
        raise transport_error(retryable=False) from None


def send_with_retry(
    send: Callable[[], httpx.Response],
    *,
    attempts: int,
    sleeper: Callable[[float], None],
    redactor: Redactor,
    stream: bool,
) -> httpx.Response:
    for attempt in range(attempts):
        response = None
        try:
            response = send()
            if response.is_success and stream:
                return response
            response.read()
            if response.is_success:
                return response
            error = _problem(response, redactor)
        except TRANSPORT_FAILURES:
            error = transport_error(
                retryable=response is None or response.status_code >= 500 or response.is_success
            )
        finally:
            if response is not None and (not stream or not response.is_success):
                response.close()
        status = response.status_code if response is not None else 0
        retry = (
            error.code not in _NO_RETRY_CODES
            and (status == 0 or (response is not None and response.is_success) or status >= 500)
            and (status in _RETRY_STATUSES or error.retryable)
        )
        if not retry or attempt == attempts - 1:
            raise error
        sleeper(min(8.0, 0.5 * 2 ** min(attempt, 5) * random.uniform(0.75, 1.25)))
    raise AssertionError("at least one HTTP attempt is required")
