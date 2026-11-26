"""Plan list cursors are bound to the plan list query, as every keyset cursor of the Postgres adapters."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import psycopg
import pytest

from skm.adapters.postgres.pagination import Cursor, encode_cursor, query_digest
from skm.adapters.postgres.planning.queries import list_plans
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ProjectId
from skm.kernel.pagination import Cursor as OpaqueCursor

PROJECT = ProjectId(UUID(int=7))


class _NoConnection:
    def execute(self, *_args: object) -> None:
        raise AssertionError("a refused cursor never reaches the database")


def test_a_cursor_of_an_unnamed_filter_with_the_same_fields_is_refused() -> None:
    filters = {"project_id": str(PROJECT), "state": "active"}
    at = datetime(2026, 11, 18, tzinfo=UTC).isoformat()
    foreign = encode_cursor(Cursor((at, str(UUID(int=1))), query_digest(filters)))
    with pytest.raises(ValidationFailed) as refused:
        list_plans(
            cast("psycopg.Connection", _NoConnection()),
            PROJECT,
            state="active",
            cursor=OpaqueCursor(foreign),
            limit=10,
        )
    assert refused.value.code is ErrorCode.SCHEMA_INVALID
    assert refused.value.details["field"] == "after"
