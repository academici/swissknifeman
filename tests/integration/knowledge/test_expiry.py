"""Background expiry and state-change retention exercised with a frozen clock."""

from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest

from contracts.knowledge.harness import KnowledgeSide, knowledge_side
from fakes.clock import FrozenClock
from skm.adapters.knowledge.null_retriever import NullMemoryRetriever
from skm.background.memory_expirer import MemoryExpirer
from skm.bootstrap.composition import CompositionOverrides, StoredScopeChain, build_app
from skm.bootstrap.lifecycle import add_background_services
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import RbacAuthorizer
from skm.modules.context.ports import MemoryRetriever
from skm.modules.knowledge.domain.memory_entry import MemoryEntryId, MemoryState
from skm.modules.knowledge.ports import MemoryRepository
from skm.platform.config.bootstrap import load_bootstrap
from support.pg import clean_test_database, pg_session, test_database  # noqa: F401

_SYSTEM = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")

__all__ = ["knowledge_side"]


def test_frozen_clock_expiry_and_retention(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    running = add_background_services(side.app)
    expirer = next(service for service in running.services if isinstance(service, MemoryExpirer))
    projected = {"project_id": str(side.project)}
    stored = side.remember(ttl_hours=1)
    entry_id = MemoryEntryId(UUID(stored["entry_id"]))
    expires = side.clock.now() + timedelta(hours=1)
    assert side.query("search_memory", projected)["items"]
    side.clock.set(expires)
    assert side.query("search_memory", projected)["items"] == []
    with side.uow(readonly=True) as uow:
        assert uow.repo(MemoryRepository).get(entry_id).state is MemoryState.LIVE
    assert expirer.tick().processed == 1
    with side.uow(readonly=True) as uow:
        expired = uow.repo(MemoryRepository).get(entry_id)
        assert expired.state is MemoryState.EXPIRED
        assert expired.state_changed_at == expires
        assert expired.row_version == 2
    side.clock.advance(timedelta(days=7))
    assert expirer.tick().processed == 0
    side.clock.advance(timedelta(microseconds=1))
    assert expirer.tick().processed == 1
    with side.uow(readonly=True) as uow, pytest.raises(NotFound):
        uow.repo(MemoryRepository).get(entry_id)


def test_only_system_can_sweep(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    with pytest.raises(Forbidden) as denied:
        side.action("expire_memory", {})
    assert denied.value.code is ErrorCode.FORBIDDEN
    assert side.action("expire_memory", {"batch": 1}, actor=_SYSTEM) == {"expired": 0, "purged": 0}


def test_expirer_is_absent_when_knowledge_is_disabled(tmp_path: Path) -> None:
    bootstrap = load_bootstrap(None, {"SKM_DATABASE_URL": "postgresql://127.0.0.1:5432/mem"}, tmp_path)
    clock = FrozenClock()
    app = build_app(
        bootstrap,
        surface=Surface.CLI,
        environ={},
        invocation={},
        overrides=CompositionOverrides(
            authorizer=RbacAuthorizer(clock),
            scopes=StoredScopeChain(),
            clock=clock,
            disabled_modules=frozenset({"knowledge", "learning"}),
        ),
    )
    try:
        assert all(service.name != "memory_expirer" for service in add_background_services(app).services)
        assert isinstance(app.gateways.get(MemoryRetriever), NullMemoryRetriever)
    finally:
        app.close()
