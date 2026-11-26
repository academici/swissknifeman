"""The host doctor's unit-of-work guard against a real PostgreSQL transaction.

``_TrackedUow``/``_OpenUnits`` of the production composition decide whether ``DoctorCheckCollector.collect``
may run a registered check. The unit tests stub the driver; these open real pooled transactions on a scratch
database of ``SKM_TEST_DATABASE_URL`` (loopback and ``*_test`` only), dropped afterwards.
"""

import os
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from skm.adapters.postgres.connection import PgSettings
from skm.adapters.postgres.extensions.pack_config_source import PackConnectionSlot
from skm.adapters.postgres.pool import PoolHandle, create_pool
from skm.bootstrap.composition import _TrackedUowFactory
from skm.bootstrap.doctor import DoctorCheckCollector, DoctorCheckRegistry, DoctorCheckSpec
from skm.kernel.errors import SkmError
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.platform.logging.redaction import Redactor
from support.pg import UnsafeDatabaseError, check_admin_dsn

NOW = datetime(2026, 1, 1, tzinfo=UTC)
META = RequestMeta(request_id="req_doctor_guard", surface=Surface.CLI, idempotency_key=None, received_at=NOW)


class _Conn(psycopg.Connection[Any]):
    """Repository port of the probe: the unit of work's own connection."""


class _Clock:
    def now(self) -> datetime:
        return NOW


class _NoEvents:
    """Event writer of a probe that buffers no events: the commit under test is the driver's own."""

    def write(self, *_args: object, **_kwargs: object) -> None:
        return None


@pytest.fixture
def scratch(pg_dsn: str) -> Iterator[str]:
    check_admin_dsn(pg_dsn)  # the proven guard of tests/support/pg.py: no connection before it passes
    name = f"skm_t_docguard_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield make_conninfo(pg_dsn, dbname=name)
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def _pool(dsn: str, *, size: int = 2) -> PoolHandle:
    return create_pool(
        PgSettings(dsn=dsn, application_name="skm-test", pool_max_size=size, pool_timeout_seconds=1.0)
    )


class _World:
    def __init__(self, dsn: str) -> None:
        self.pool = _pool(dsn)
        self.tracker = PackConnectionSlot()
        self.calls: list[str] = []
        spec = DoctorCheckSpec("probe", self._check)
        self.collector = DoctorCheckCollector(DoctorCheckRegistry([spec]), in_unit_of_work=self.tracker.holds)
        self.factory = _TrackedUowFactory(
            self.pool,
            {_Conn: lambda conn: conn},
            cast("Any", _NoEvents()),
            cast("Any", _Clock()),
            tracker=self.tracker,
        )

    def _check(self, _context: object) -> list[Any]:
        self.calls.append("ran")
        return []

    def collect(self) -> None:
        self.collector.collect(redactor=Redactor())

    def refused(self) -> None:
        before = len(self.calls)
        with pytest.raises(RuntimeError, match="outside every unit of work"):
            self.collect()
        assert len(self.calls) == before  # the host callback never started

    def allowed(self) -> None:
        before = len(self.calls)
        self.collect()
        assert len(self.calls) == before + 1


@pytest.fixture
def world(scratch: str) -> Iterator[_World]:
    built = _World(scratch)
    try:
        yield built
    finally:
        built.pool.close()


@pytest.mark.pg
def test_callbacks_are_refused_inside_a_real_transaction_and_run_after_it(world: _World) -> None:
    world.allowed()
    with world.factory(META) as uow:
        conn = uow.repo(_Conn)
        assert conn.execute("SELECT txid_current()").fetchone() is not None  # a real open transaction
        assert conn.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
        world.refused()
        with world.factory(
            META, readonly=True
        ):  # a nested unit of work keeps the guard until the outer one ends
            world.refused()
        world.refused()
    assert not world.tracker.holds()
    world.allowed()


@pytest.mark.pg
def test_guard_is_released_after_a_clean_exit_without_commit_and_after_an_exception(world: _World) -> None:
    # neither path calls commit(): both end in a rollback (a real commit is the next test)
    with world.factory(META) as uow:
        uow.repo(_Conn).execute("SELECT 1")
        world.refused()
    world.allowed()
    with pytest.raises(ZeroDivisionError), world.factory(META) as uow:  # noqa: PT012
        uow.repo(_Conn).execute("SELECT 1")
        raise ZeroDivisionError
    assert not world.tracker.holds()
    world.allowed()


@pytest.mark.pg
def test_guard_is_released_after_a_real_commit(world: _World, scratch: str) -> None:
    with world.factory(META) as uow:
        uow.repo(_Conn).execute("CREATE TABLE public.committed_probe (id int)")
        uow.repo(_Conn).execute("INSERT INTO public.committed_probe VALUES (1)")
        world.refused()
        uow.commit()  # the driver's COMMIT; the event writer is a no-op stub
        world.refused()  # the unit of work is still open until __exit__
    assert not world.tracker.holds()
    world.allowed()
    with psycopg.connect(scratch, autocommit=True) as other:  # another session sees the committed row
        assert other.execute("SELECT id FROM public.committed_probe").fetchall() == [(1,)]
    with world.factory(META) as uow:
        uow.repo(_Conn).execute("CREATE TABLE public.rolled_back_probe (id int)")
    with psycopg.connect(scratch, autocommit=True) as other:
        assert other.execute("SELECT to_regclass('public.rolled_back_probe')").fetchone() == (None,)


@pytest.mark.pg
def test_a_failed_enter_does_not_hold_the_guard(world: _World, scratch: str) -> None:
    closed = _pool(scratch)
    closed.close()
    broken = _TrackedUowFactory(closed, {}, cast("Any", None), cast("Any", None), tracker=world.tracker)
    with pytest.raises(Exception):  # noqa: B017, PT011 - any driver/pool refusal; the type is the pool's concern
        broken(META).__enter__()
    assert not world.tracker.holds()
    world.allowed()
    # exhausted pool: the second enter times out (pool_timeout) while the first stays open
    single = _pool(scratch, size=1)
    try:
        tracker = PackConnectionSlot()
        factory = _TrackedUowFactory(single, {}, cast("Any", None), cast("Any", None), tracker=tracker)
        with factory(META):
            errors: list[BaseException] = []
            held: list[bool] = []

            def other() -> None:
                try:
                    with factory(META):
                        pass
                except SkmError as exc:
                    errors.append(exc)
                held.append(tracker.holds())

            thread = threading.Thread(target=other)
            thread.start()
            thread.join()
            assert len(errors) == 1
            assert held == [False]  # the timed-out enter never counted in its thread
            assert tracker.holds()  # and did not disturb the thread that holds the open unit
        assert not tracker.holds()
    finally:
        single.close()


class _Proof:
    """What the killed-session scenario really observed, asserted before its outcome is trusted."""

    def __init__(self) -> None:
        self.entered = False
        self.refused = False
        self.terminated: object = None
        self.exit_error: BaseException | None = None

    def assert_complete(self) -> None:
        assert self.entered, "the unit of work was never entered"
        assert self.refused, "the guard did not refuse inside the transaction"
        assert self.terminated is True, f"pg_terminate_backend returned {self.terminated!r}"


def _kill_inside(world: _World, factory: Any, admin: psycopg.Connection[Any]) -> _Proof:
    proof = _Proof()
    try:
        with factory(META) as uow:
            conn = uow.repo(_Conn)
            pid = conn.info.backend_pid
            conn.execute("SELECT 1")
            proof.entered = True
            world.refused()
            proof.refused = True
            row = admin.execute("SELECT pg_terminate_backend(%s)", (pid,)).fetchone()
            proof.terminated = row[0] if row else None
    except (psycopg.Error, SkmError) as exc:  # only the rollback of the killed session may raise on exit
        proof.exit_error = exc
    return proof


@pytest.mark.pg
def test_a_failed_exit_still_releases_the_guard(world: _World, scratch: str) -> None:
    with psycopg.connect(scratch, autocommit=True) as admin:
        proof = _kill_inside(world, world.factory, admin)
        proof.assert_complete()
        assert not world.tracker.holds(), f"guard stuck after exit (exit raised: {proof.exit_error!r})"
    world.allowed()


@pytest.mark.pg
def test_the_killed_session_proof_fails_when_the_unit_of_work_is_never_entered(
    world: _World, scratch: str
) -> None:
    closed = _pool(scratch)
    closed.close()
    broken = _TrackedUowFactory(
        closed,
        {_Conn: lambda conn: conn},
        cast("Any", _NoEvents()),
        cast("Any", _Clock()),
        tracker=world.tracker,
    )
    with psycopg.connect(scratch, autocommit=True) as admin:
        proof = _kill_inside(
            world, broken, admin
        )  # the pre-entry failure is swallowed by the narrow catch...
        assert proof.exit_error is not None
        with pytest.raises(AssertionError, match="never entered"):  # ...but the proof refuses to pass
            proof.assert_complete()


@pytest.mark.pg
def test_the_guard_is_per_thread_while_a_real_transaction_is_open(world: _World) -> None:
    seen: list[bool] = []
    callbacks: list[int] = []

    def other_thread() -> None:
        seen.append(world.tracker.holds())
        before = len(world.calls)
        world.collect()  # another thread's open unit of work does not block this host thread
        callbacks.append(len(world.calls) - before)
        with world.factory(META) as uow:  # and its own unit of work blocks it until closed
            uow.repo(_Conn).execute("SELECT 1")
            seen.append(world.tracker.holds())
            with pytest.raises(RuntimeError, match="outside every unit of work"):
                world.collect()
        seen.append(world.tracker.holds())

    with world.factory(META) as uow:
        uow.repo(_Conn).execute("SELECT 1")
        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join()
        world.refused()  # still held in this thread
    assert seen == [False, True, False]
    assert callbacks == [1]
    world.allowed()


@pytest.mark.parametrize(
    "dsn",
    [
        "host=localhost hostaddr=203.0.113.9 dbname=x_test",
        "hostaddr=203.0.113.9 dbname=x_test",
        "host=127.0.0.1,db.example.com dbname=x_test",
        "host=db.example.com dbname=x_test",
        "service=remote dbname=x_test",
        "dbname=prod",
    ],
)
def test_the_admin_dsn_guard_refuses_redirecting_or_non_test_dsns(dsn: str) -> None:
    with pytest.raises(UnsafeDatabaseError):
        check_admin_dsn(dsn)  # parsing only: nothing connects


@pytest.mark.parametrize("variable", ["PGHOST", "PGHOSTADDR", "PGSERVICE"])
def test_the_admin_dsn_guard_sees_environment_redirection(
    variable: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(variable, "203.0.113.9" if variable != "PGSERVICE" else "remote")
    with pytest.raises(UnsafeDatabaseError):
        check_admin_dsn("dbname=x_test")
