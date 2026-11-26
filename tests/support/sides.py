"""The memory/PostgreSQL ``side`` and ``pg_side`` fixture bodies shared by contract harnesses.

A harness keeps its own ``memory_side``/``postgres_side`` builders and declares the fixtures as::

    @pytest.fixture(params=BACKEND_PARAMS)
    def side(request):
        yield from iter_side(request, memory_side, postgres_side)
"""

from collections.abc import Callable, Iterator
from typing import Final, Protocol

import pytest

from support.pg import TestDatabase

__all__ = ["BACKEND_PARAMS", "iter_pg_side", "iter_side"]

BACKEND_PARAMS: Final = ("memory", pytest.param("postgres", marks=pytest.mark.pg))


class _Closable(Protocol):
    def close(self) -> None: ...


def iter_side[S: _Closable](
    request: pytest.FixtureRequest, memory: Callable[[], S], postgres: Callable[[TestDatabase], S]
) -> Iterator[S]:
    """Build the side of ``request.param`` and close it after the test."""
    made = memory() if request.param == "memory" else postgres(request.getfixturevalue("clean_test_database"))
    try:
        yield made
    finally:
        made.close()


def iter_pg_side[S: _Closable](database: TestDatabase, postgres: Callable[[TestDatabase], S]) -> Iterator[S]:
    """Build a PostgreSQL-only side on ``database`` and close it after the test."""
    made = postgres(database)
    try:
        yield made
    finally:
        made.close()
