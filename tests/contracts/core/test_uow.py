"""Unit-of-work contract on both backends (kernel-platform §2.11, adapters §1.3/§2.2, testing §4).

Every test runs on memory and on PostgreSQL through the ``backend`` fixture; the PostgreSQL units of work
really COMMIT into the session database, which is cleaned before each test. Persisted state is read from
outside the unit of work (``table_counts``/``envelopes``), so "not visible" means no other session sees it.
Matrix: identity of stored rows, commit/rollback/no-op, failed commit, lifecycle errors, readonly and the
repository cache. Backend-specific mechanics stay in ``test_memory_uow.py`` and ``integration/postgres``.
"""

import textwrap
from collections.abc import Callable, Mapping
from uuid import UUID

import pytest

from fakes.demo_module import Echoed, Noted
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound
from skm.kernel.ids import EventId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from support.backend import MEMORY_CORE_TABLES, TestBackend

NOTE_STREAM = UUID("01900000-0000-7000-8000-0000000000c2")


def counts(backend: TestBackend) -> Mapping[str, int]:
    return dict(backend.table_counts("skm_core"))


def project_id(backend: TestBackend) -> ScopeId:
    return ScopeId(backend.ids.new_id())


def create_project(backend: TestBackend, uow: UnitOfWork, scope_id: ScopeId) -> None:
    workspace = backend.seed.workspace_id
    uow.repo(ScopeRegistry).create(
        scope_id, ScopeKind.PROJECT, parent=ScopeId(workspace), workspace_id=workspace
    )


def echoed(backend: TestBackend, text: str = "hello") -> Echoed:
    return Echoed(workspace_id=backend.seed.workspace_id, text=text)


SEEDED = dict.fromkeys(MEMORY_CORE_TABLES, 0) | {"scopes": 3}


# ------------------------------------------------------------------------------------- the fixture itself


def test_both_backends_start_from_the_same_seed(backend: TestBackend) -> None:
    assert counts(backend) == SEEDED
    with backend.uow(readonly=True) as uow:
        registry = uow.repo(ScopeRegistry)
        assert registry.instance().id == backend.seed.instance_id
        workspace = registry.get(ScopeId(backend.seed.workspace_id))
        assert (workspace.kind, workspace.parent_id, workspace.workspace_id) == (
            ScopeKind.WORKSPACE,
            backend.seed.instance_id,
            backend.seed.workspace_id,
        )


@pytest.mark.parametrize("round_", [1, 2])
def test_committed_rows_of_one_test_never_reach_the_next(backend: TestBackend, round_: int) -> None:
    """Both rounds start from the seed although each commits; whichever runs second proves the cleanup."""
    assert counts(backend) == SEEDED
    with backend.uow() as uow:
        create_project(backend, uow, project_id(backend))
        uow.record(echoed(backend, f"round {round_}"))
        uow.commit()
    assert counts(backend)["scopes"] == 4
    assert [e.payload["text"] for e in backend.envelopes()] == [f"round {round_}"]


def test_seed_workspace_exists_before_the_unit_of_work_opens(backend: TestBackend) -> None:
    workspace = WorkspaceId(backend.ids.new_id())
    with backend.uow(seed_workspace=workspace) as uow:
        record = uow.repo(ScopeRegistry).get(ScopeId(workspace))
        assert (record.kind, record.parent_id, record.workspace_id) == (
            ScopeKind.WORKSPACE,
            backend.seed.instance_id,
            workspace,
        )
    with backend.uow(seed_workspace=workspace):  # a second request is a no-op, not a duplicate
        pass
    assert counts(backend)["scopes"] == 4


# ------------------------------------------------------------------------------------- identity


def test_a_committed_row_reads_back_with_the_same_identity(backend: TestBackend) -> None:
    scope_id = project_id(backend)
    with backend.uow() as uow:
        create_project(backend, uow, scope_id)
        uow.commit()
    with backend.uow(readonly=True) as uow:
        record = uow.repo(ScopeRegistry).get(scope_id)
    assert (record.id, record.kind, record.parent_id, record.workspace_id) == (
        scope_id,
        ScopeKind.PROJECT,
        ScopeId(backend.seed.workspace_id),
        backend.seed.workspace_id,
    )
    assert record.created_at.tzinfo is not None


def test_a_duplicate_id_is_already_exists_and_keeps_the_stored_row(backend: TestBackend) -> None:
    scope_id = project_id(backend)
    with backend.uow() as uow:
        create_project(backend, uow, scope_id)
        uow.commit()
    with backend.uow() as uow, pytest.raises(Conflict) as err:
        uow.repo(ScopeRegistry).create(
            scope_id, ScopeKind.HOST, parent=backend.seed.instance_id, workspace_id=None
        )
    assert err.value.code is ErrorCode.ALREADY_EXISTS
    with backend.uow(readonly=True) as uow:
        assert uow.repo(ScopeRegistry).get(scope_id).kind is ScopeKind.PROJECT


def test_a_second_instance_is_already_exists(backend: TestBackend) -> None:
    with backend.uow() as uow, pytest.raises(Conflict) as err:
        uow.repo(ScopeRegistry).create(
            project_id(backend), ScopeKind.INSTANCE, parent=None, workspace_id=None
        )
    assert err.value.code is ErrorCode.ALREADY_EXISTS
    assert counts(backend) == SEEDED


def test_an_unknown_id_is_not_found(backend: TestBackend) -> None:
    with backend.uow(readonly=True) as uow, pytest.raises(NotFound):
        uow.repo(ScopeRegistry).get(project_id(backend))


# ------------------------------------------------------------------------------- commit, rollback, no-op


def test_writes_are_invisible_until_commit_and_then_visible_together(backend: TestBackend) -> None:
    with backend.uow() as uow:
        create_project(backend, uow, project_id(backend))
        uow.record(echoed(backend))
        assert counts(backend) == SEEDED  # another session sees nothing yet
        uow.commit()
        after = counts(backend)
    assert after == SEEDED | {
        "scopes": 4,
        "domain_events": 1,
        "outbox": 2,  # demo.on_echoed and exactly one sse row
        "event_streams": 1,
        "workspace_event_counters": 1,
    }


def test_leaving_without_commit_keeps_nothing_and_consumes_no_number(backend: TestBackend) -> None:
    with backend.uow() as uow:
        create_project(backend, uow, project_id(backend))
        uow.record(echoed(backend, "dropped"))
    assert counts(backend) == SEEDED
    with backend.uow() as uow:
        uow.record(echoed(backend, "kept"))
        uow.commit()
    (event,) = backend.envelopes()
    assert (event.payload["text"], event.workspace_seq, event.stream_seq) == ("kept", 1, 1)


def test_an_exception_in_the_body_rolls_back_and_propagates(backend: TestBackend) -> None:
    def body() -> None:
        with backend.uow() as uow:
            create_project(backend, uow, project_id(backend))
            uow.record(echoed(backend))
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        body()
    assert counts(backend) == SEEDED


def test_an_explicit_rollback_drops_the_buffers_and_the_writes(backend: TestBackend) -> None:
    with backend.uow() as uow:
        create_project(backend, uow, project_id(backend))
        uow.record(echoed(backend))
        uow.rollback()
        uow.rollback()  # idempotent
        with pytest.raises(RuntimeError):
            uow.commit()
    assert counts(backend) == SEEDED


def test_a_commit_without_writes_changes_nothing(backend: TestBackend) -> None:
    with backend.uow() as uow:
        uow.repo(ScopeRegistry).instance()
        uow.commit()
    assert counts(backend) == SEEDED


def test_a_failed_commit_stores_no_state_event_or_outbox_row(backend: TestBackend) -> None:
    def body() -> None:
        with backend.uow() as uow:
            create_project(backend, uow, project_id(backend))
            uow.record(echoed(backend, "lost"))
            uow.outbox.enqueue(EventId(backend.ids.new_id()), "hook:one")  # no such event: commit fails
            uow.commit()

    with pytest.raises(InternalError):
        body()
    assert counts(backend) == SEEDED
    with backend.uow() as uow:  # the failed attempt left no gap in the numbers
        uow.record(echoed(backend, "next"))
        uow.commit()
    (event,) = backend.envelopes()
    assert (event.payload["text"], event.workspace_seq) == ("next", 1)


# ------------------------------------------------------------------------------------- lifecycle


def test_a_second_commit_is_a_runtime_error_and_keeps_the_first(backend: TestBackend) -> None:
    with backend.uow() as uow:
        uow.record(echoed(backend))
        uow.commit()
        with pytest.raises(RuntimeError):
            uow.commit()
        with pytest.raises(RuntimeError):
            uow.record(echoed(backend, "late"))
    assert [e.payload["text"] for e in backend.envelopes()] == ["hello"]


def test_a_unit_of_work_cannot_be_entered_twice(backend: TestBackend) -> None:
    uow = backend.uow_factory(backend.meta())
    with uow:
        pass
    with pytest.raises(RuntimeError), uow:
        pass


def test_repositories_are_cached_per_unit_of_work_and_unknown_ports_fail(backend: TestBackend) -> None:
    class UnknownPort:
        pass

    with backend.uow() as uow:
        first = uow.repo(ScopeRegistry)
        assert uow.repo(ScopeRegistry) is first
        with pytest.raises(InternalError) as err:
            uow.repo(UnknownPort)
    assert err.value.code is ErrorCode.INTERNAL_ERROR
    with backend.uow() as uow:
        assert uow.repo(ScopeRegistry) is not first  # bound to that unit of work only


# ------------------------------------------------------------------------------------- readonly


def test_a_readonly_unit_of_work_refuses_events_and_outbox_rows(backend: TestBackend) -> None:
    with backend.uow(readonly=True) as uow:
        assert uow.readonly
        with pytest.raises(RuntimeError):
            uow.record(echoed(backend))
        with pytest.raises(RuntimeError):
            uow.outbox.enqueue(EventId(backend.ids.new_id()), "hook:one")
        uow.commit()  # nothing buffered: a readonly commit is a no-op
    assert counts(backend) == SEEDED


def test_a_readonly_unit_of_work_refuses_a_repository_write(backend: TestBackend) -> None:
    """Memory refuses in the adapter (RuntimeError), PostgreSQL in the server (25006 -> InternalError)."""
    with backend.uow(readonly=True) as uow, pytest.raises((RuntimeError, InternalError)):
        create_project(backend, uow, project_id(backend))
    assert counts(backend) == SEEDED


def test_a_readonly_unit_of_work_reads_committed_rows(backend: TestBackend) -> None:
    with backend.uow() as uow:
        uow.record(Noted(stream=NOTE_STREAM, text="instance"))
        uow.commit()
    with backend.uow(readonly=True) as uow:
        assert uow.repo(ScopeRegistry).instance().id == backend.seed.instance_id
    assert [e.workspace_id for e in backend.envelopes()] == [None]


# ------------------------------------------------------------------------------------- the pg gate


type Runner = Callable[..., pytest.RunResult]

GATE_PROBE = textwrap.dedent(
    """
    from support.backend import backend, pg_backend  # noqa: F401
    from support.pg import clean_test_database, pg_session, test_database  # noqa: F401


    def test_probe(backend):
        assert backend.kind in {"memory", "postgres"}
    """
)


def test_the_postgres_parameter_is_skipped_without_a_dsn(runner: Runner) -> None:
    result = runner(GATE_PROBE)
    result.assert_outcomes(passed=1, skipped=1)


def test_the_postgres_parameter_fails_under_skm_require_pg(runner: Runner) -> None:
    result = runner(GATE_PROBE, controls={"SKM_REQUIRE_PG": "1", "SKM_DATABASE_URL": "postgresql:///skm_dev"})
    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["*SKM_REQUIRE_PG=1 but SKM_TEST_DATABASE_URL is not set*"])


def test_the_postgres_parameter_is_selected_by_the_pg_marker(runner: Runner) -> None:
    result = runner(GATE_PROBE, args=("-m", "not pg"))
    result.assert_outcomes(passed=1, deselected=1)
