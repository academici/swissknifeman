"""Isolate MCP tests from process logging configured by other test suites."""

from dataclasses import replace

import pytest

from skm.platform.logging import setup
from skm.platform.logging.redaction import Redactor


@pytest.fixture(autouse=True)
def _capture_process_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        setup._state,
        "settings",
        replace(
            setup._state.settings,
            level="info",
            detail="normal",
            fmt="json",
            stream=None,
            redactor=Redactor(),
            host="localhost",
        ),
    )
