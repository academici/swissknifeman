"""Fixtures of the core contract suites: ``backend`` runs each test on memory and PostgreSQL (testing §4)."""

from support.backend import backend, pg_backend  # noqa: F401 - fixtures by name
from support.pg import clean_test_database, pg_session, test_database  # noqa: F401 - fixtures by name
