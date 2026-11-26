"""The required PostgreSQL fixture fails instead of skipping when SKM_REQUIRE_PG=1."""

from contracts.execution.harness import exec_side as exec_side
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "exec_side", "pg_session", "test_database"]
