"""Test harness declarations cannot accidentally provide a fake successful application."""

from typing import cast

import pytest

from fakes.demo_module import GetEcho, GetEchoResult
from support.app import MemoryTestApp, TestApp, TestHost, memory_app, pg_app
from support.backend import MemoryTestBackend, TestBackend


@pytest.mark.parametrize("declaration", [TestApp, TestHost, TestBackend])
def test_declarations_cannot_be_instantiated(declaration: type) -> None:
    with pytest.raises(TypeError, match="Protocols cannot be instantiated"):
        declaration()


def test_memory_app_executes_a_query_through_its_bus() -> None:
    app = cast(MemoryTestApp, memory_app())
    assert app.ask(GetEcho(workspace_id=app.harness.seed.workspace_id)) == GetEchoResult(texts=())


def test_pg_app_rejects_an_object_that_is_not_a_backend() -> None:
    with pytest.raises(TypeError, match="PostgreSQL TestBackend"):
        pg_app(object())  # type: ignore[arg-type]


def test_pg_app_rejects_the_memory_backend() -> None:
    with pytest.raises(TypeError, match="PostgreSQL TestBackend"):
        pg_app(MemoryTestBackend())
