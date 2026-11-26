"""Dual-backend memory scope, receipt and concurrency contracts."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import partial
from hashlib import sha256
from typing import Any
from uuid import UUID

import psycopg
import pytest

from integration.artifacts.test_upload_flow import dispatch_new
from skm.adapters.postgres.knowledge.memory import PostgresMemoryRepository
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, NotFound, PreconditionFailed, SkmError
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import Surface
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import Role
from skm.modules.context.ports import MemoryRetriever
from skm.modules.knowledge.domain.memory_entry import MemoryEntryId, MemoryState
from skm.modules.knowledge.domain.memory_scope import MemoryScope, MemoryScopeKind
from skm.modules.knowledge.ports import MemoryRepository
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.workspace.public import CreateWorkspace
from support.pg import TestDatabase, clean_test_database, pg_session, test_database  # noqa: F401
from support.seed import SEED

from .harness import KnowledgeSide, knowledge_side

__all__ = ["clean_test_database", "knowledge_side"]


def _race(run: Callable[[], Any]) -> tuple[ErrorCode | None, ...]:
    def attempt() -> ErrorCode | None:
        try:
            run()
        except SkmError as error:
            return error.code
        return None

    with ThreadPoolExecutor(max_workers=2) as threads:
        return tuple(threads.map(lambda _: attempt(), range(2)))


def test_ninth_remember_is_rejected_under_concurrent_writers(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    for _ in range(7):
        side.remember()
    side.remember(kind="active_handoff")
    side.remember(kind="health_probe")
    assert set(_race(side.remember)) == {None, ErrorCode.MEMORY_LIMIT_REACHED}
    page = side.query("list_memory", {"project_id": str(side.project), "limit": 8})
    assert len(page["items"]) == 8
    assert page["has_more"]
    tail = side.query("list_memory", {"project_id": str(side.project), "after": page["next_cursor"]})
    assert len(tail["items"]) == 2
    assert not tail["has_more"]
    assert not ({row["id"] for row in page["items"]} & {row["id"] for row in tail["items"]})
    events = _memory_events(side)
    assert len(events) == 10
    assert all("Temporary pool status" not in str(e.payload) for e in events)


def _memory_events(side: KnowledgeSide) -> tuple[Any, ...]:
    from skm.application_bus.ports import EventReader

    with side.uow(readonly=True) as uow:
        return uow.repo(EventReader).after_workspace_seq(
            side.workspace,
            0,
            types=frozenset({"urn:skm:knowledge:event:memory-remembered:v1"}),
            limit=100,
        )


def test_handoff_cas_expired_unswept_and_lost_response(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    assert set(_race(lambda: side.remember(kind="active_handoff", ttl_hours=1))) == {
        None,
        ErrorCode.VERSION_CONFLICT,
    }
    query = {"project_id": str(side.project)}
    old_id = side.query("search_memory", query)["items"][0]["id"]
    side.clock.advance(timedelta(hours=1))
    assert side.query("search_memory", query)["items"] == []
    with pytest.raises(Conflict) as failure:
        side.remember(kind="active_handoff")
    assert failure.value.code == ErrorCode.VERSION_CONFLICT

    replacement = side.remember(kind="active_handoff", expected_handoff_id=old_id)
    current_id = replacement["entry_id"]
    assert replacement["superseded_id"] == old_id
    assert set(_race(lambda: side.remember(kind="active_handoff", expected_handoff_id=current_id))) == {
        None,
        ErrorCode.VERSION_CONFLICT,
    }
    newest = side.query("search_memory", query)["items"]
    assert len(newest) == 1
    assert newest[0]["supersedes_id"] == current_id
    cmd = {
        **query,
        "kind": "active_handoff",
        "body": "Keep the current handoff",
        "ttl_hours": None,
        "source": "api",
        "expected_handoff_id": newest[0]["id"],
    }
    first = side.action("remember", cmd, key="lost-response")
    assert first == side.action("remember", cmd, key="lost-response")
    with side.uow(readonly=True) as uow:
        old = uow.repo(MemoryRepository).get(MemoryEntryId(UUID(old_id)))
        assert old.state is MemoryState.SUPERSEDED
        assert old.row_version == 2


def test_shared_recall_and_foreign_forget(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    other = side.new_project("other")
    private = side.remember(body="Private rendezvous status")["entry_id"]
    client = side.app.client(actor=side.owner, surface=Surface.TEST)

    def share_namespace(project: ScopeId) -> None:
        dispatch_new(
            client,
            SetValue(
                SetValueDefsScopeRef("project", project),
                "knowledge.memory.namespaces",
                ["squad-a"],
            ),
        )

    share_namespace(ScopeId(side.project))
    shared = side.remember(
        scope={"kind": "namespace", "namespace": "squad-a"}, body="Shared rendezvous status"
    )
    assert [
        row["id"]
        for row in side.query(
            "search_memory",
            {
                "project_id": str(side.project),
                "query": "rendezvous",
            },
        )["items"]
    ] == [private]
    assert (
        len(
            side.query(
                "search_memory",
                {
                    "project_id": str(side.project),
                    "include_shared": True,
                },
            )["items"]
        )
        == 2
    )
    assert side.query("search_memory", {"project_id": str(other), "include_shared": True})["items"] == []
    with pytest.raises(Forbidden) as denied:
        side.query(
            "search_memory",
            {
                "project_id": str(other),
                "include_shared": True,
                "scope": {"kind": "namespace", "namespace": "squad-a"},
            },
        )
    assert denied.value.code == ErrorCode.FORBIDDEN
    share_namespace(ScopeId(other))
    assert [
        row["id"]
        for row in side.query(
            "search_memory",
            {
                "project_id": str(other),
                "include_shared": True,
            },
        )["items"]
    ] == [shared["entry_id"]]
    foreign = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="foreign", title="Foreign")).workspace_id)
    isolated = side.new_project("isolated", foreign)
    share_namespace(ScopeId(isolated))
    assert side.query("search_memory", {"project_id": str(isolated), "include_shared": True})["items"] == []

    with pytest.raises(NotFound):
        side.action("forget", {"project_id": str(other), "entry_id": private})
    with pytest.raises(PreconditionFailed) as missing:
        side.remember(project_id=None)
    assert missing.value.code == ErrorCode.MEMORY_SCOPE_REQUIRED
    assert side.action("forget", {"project_id": str(side.project), "entry_id": private})["forgotten"] == 1
    assert side.action("forget", {"project_id": str(side.project), "entry_id": private})["forgotten"] == 0


def test_private_hits_are_rechecked_after_membership_revoke(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    reader = Actor(PrincipalId(UUID(int=810)), PrincipalKind.HUMAN, "reader")
    scope = ScopeId(side.project)
    now = side.clock.now()
    with side.uow() as uow:
        uow.repo(PrincipalRepository).add(
            new_principal(
                principal_id=reader.principal_id,
                kind=reader.kind,
                display_name=reader.display_name,
                created_by=side.owner.principal_id,
                now=now,
            )
        )
        uow.repo(MembershipRepository).upsert(Membership(scope, reader.principal_id, Role.VIEWER, None, now))
        uow.commit()
    side.remember()
    retriever = side.app.gateways.get(MemoryRetriever)
    recall = partial(
        retriever.search,
        workspace_id=side.workspace,
        project_id=side.project,
        query="",
        top_k=2,
        actor=reader,
    )
    with side.uow(readonly=True) as uow:
        assert recall(uow)
    with side.uow() as uow:
        uow.repo(MembershipRepository).delete(scope, reader.principal_id)
        uow.commit()
    with side.uow(readonly=True) as uow:
        assert recall(uow) == ()
    with pytest.raises(Forbidden):
        side.query("search_memory", {"project_id": str(side.project), "include_shared": True}, actor=reader)


def test_search_scores_all_candidates_before_each_scope_quota(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    scope = SetValueDefsScopeRef("project", ScopeId(side.project))
    dispatch_new(client, SetValue(scope, "knowledge.memory.namespaces", ["squad-a"]))
    dispatch_new(
        client,
        SetValue(
            SetValueDefsScopeRef("instance", SEED.instance_id), "knowledge.memory.max_live_per_scope", 30
        ),
    )
    shared_scope = {"kind": "namespace", "namespace": "squad-a"}
    private_best = side.remember(body="pool timeout")["entry_id"]
    shared_best = side.remember(scope=shared_scope, body="pool timeout")["entry_id"]
    side.clock.advance(timedelta(seconds=1))
    for _ in range(21):
        side.remember(kind="blocker", body="pool_timeout")
    for _ in range(6):
        side.remember(scope=shared_scope, kind="blocker", body="pool_timeout")

    result = side.query(
        "search_memory", {"project_id": str(side.project), "query": "pool timeout", "include_shared": True}
    )
    items = result["items"]
    assert result["truncated"]
    assert len(items) == 25
    assert items[0]["id"] == private_best
    assert all(row["scope"]["kind"] == "project" for row in items[:20])
    assert items[20]["id"] == shared_best
    assert all(row["scope"]["kind"] == "namespace" for row in items[20:])


@pytest.mark.pg
def test_postgres_scope_lock_uses_canonical_signed_key(clean_test_database: TestDatabase) -> None:
    scope = MemoryScope(MemoryScopeKind.NAMESPACE, None, "squad-a", WorkspaceId(UUID(int=810)))
    payload = b'["skm-memory-scope-v1","namespace",null,"squad-a","00000000-0000-0000-0000-00000000032a"]'
    key = int.from_bytes(sha256(payload).digest()[:8], "big", signed=True)
    probe = "SELECT pg_try_advisory_xact_lock(%s)"
    with (
        psycopg.connect(clean_test_database.dsn) as held,
        psycopg.connect(clean_test_database.dsn) as contender,
    ):
        PostgresMemoryRepository(held).lock_scope(scope)
        assert contender.execute(probe, (key,)).fetchone() == (False,)
        held.commit()
        assert contender.execute(probe, (key,)).fetchone() == (True,)
