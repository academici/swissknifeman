"""A failed API request logs which error it was, so a 401 and a crash are told apart."""

import json
import warnings
from collections.abc import Callable
from io import StringIO
from typing import Any

import pytest

from skm.entrypoints.api.request_context import RequestContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Unauthenticated
from skm.platform.logging import setup
from skm.platform.logging.redaction import Redactor

# Starlette 0.52 uses this alias in an import-time type annotation (AnyIO 4.15).
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore", message="The anyio.abc.BlockingPortal alias is deprecated", category=DeprecationWarning
    )
    from starlette.testclient import TestClient


@pytest.fixture
def stream(monkeypatch: pytest.MonkeyPatch) -> StringIO:
    sink = StringIO()
    monkeypatch.setattr(setup._state, "settings", setup._state.settings)
    setup.configure_logging(
        level="info", detail="normal", fmt="json", stream=sink, redactor=Redactor(), host="h"
    )
    return sink


def _failing(error: Exception) -> Callable[..., Any]:
    async def app(scope: object, receive: object, send: object) -> None:
        raise error

    return app


@pytest.mark.parametrize(
    ("error", "status", "code", "kind"),
    [
        (Unauthenticated(ErrorCode.UNAUTHENTICATED, "missing token"), 401, "UNAUTHENTICATED", "SkmError"),
        (RuntimeError("boom"), 500, None, "RuntimeError"),
    ],
)
def test_request_failure_log_names_the_error(
    stream: StringIO, error: Exception, status: int, code: str | None, kind: str
) -> None:
    client = TestClient(RequestContext(_failing(error), {}, Redactor()), base_url="http://127.0.0.1")
    assert client.get("/api/v1/me").status_code == status

    (record,) = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert record["event"] == "api.request.failed"
    assert record["error.type"] == kind
    assert record.get("code") == code
    assert record["reason_code"] == (code or "INTERNAL_ERROR")
    assert "boom" not in stream.getvalue()
