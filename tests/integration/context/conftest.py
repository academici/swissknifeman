"""Dual-backend context and execution fixtures for research boundary regressions."""

import pytest

from contracts.context.harness import ctx_side
from contracts.execution.harness import exec_side
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "ctx_side", "exec_side", "pg_session", "test_database"]


@pytest.fixture(autouse=True)
def trusted_research_sources(request):
    """Register a real instance source through the settings bus, for either backend harness."""
    from integration.context.test_research_repository import source_setting

    for name in ("ctx_side", "exec_side"):
        if name in request.fixturenames:
            source_setting(request.getfixturevalue(name))
