"""PostgreSQL authorization, scheduler, worker contention and test cleanup measurements."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from threading import Barrier
from time import perf_counter
from uuid import UUID, uuid4

import psycopg
import pytest

from contracts.execution._worker_protocol_support import claim, make_case, worker_claim
from contracts.execution.seed_helpers import seed_task
from fixtures.execution.harness import recovery as recovery
from fixtures.execution.harness import system_dispatch
from integration.artifacts.test_upload_flow import seed_principals
from skm.bootstrap.composition import StoredScopeChain
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.errors import SkmError
from skm.kernel.ids import PrincipalId, TaskId
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.execution import public as execution
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.ids import AssignmentId
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.domain.task_graph import EdgeKind, TaskEdge
from skm.modules.execution.ports import AssignmentRepository, TaskRepository
from skm.modules.workspace.public import CreateProject, CreateWorkspace, RecordWorkerHeartbeat, get_worker
from support.pg import clean_database
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from unit.execution.application._support import set_setting

pytestmark = [pytest.mark.perf, pytest.mark.pg]


def test_authorize_100_projects(recovery, measure):
    side = recovery
    workspaces = [side.ws] + [
        side.client.dispatch(CreateWorkspace(f"perf-ws-{i}", f"Perf {i}")).workspace_id for i in range(9)
    ]
    projects = [side.proj] + [
        side.client.dispatch(CreateProject(ws, f"perf-project-{i}", f"Perf {i}")).project_id
        for ws in workspaces
        for i in range(9 if ws == side.ws else 10)
    ]
    assert len(projects) == 100
    people = [(PrincipalId(uuid4()), PrincipalKind.HUMAN, f"perf-{i}") for i in range(24)]
    seed_principals(
        side.app,
        "postgres",
        people=people,
        roles=[(ScopeId(ws), pid, Role.VIEWER) for ws in workspaces for pid, _, _ in people],
    )
    actors = [side.owner, *(Actor(*person) for person in people)]
    scopes, authorizer = StoredScopeChain(), RbacAuthorizer(side.clock)
    samples = []
    for i, project in enumerate(projects * 3):
        with side.uow(readonly=True) as uow:
            start = perf_counter()
            chain = scopes.chain(uow, ScopeRef(ScopeKind.PROJECT, project))
            answer = authorizer.authorize(uow, actors[(i + i // 100) % len(actors)], "project.read", chain)
            samples.append((perf_counter() - start) * 1000)
        assert answer.allowed
    result = measure(
        "authorize_ms", samples, projects=len(projects), workspaces=len(workspaces), humans=len(actors)
    )
    assert result["p95"] <= 10


def test_scheduler_10_runs_300_tasks(recovery, measure):
    side = recovery
    set_setting(side, "execution.parallel.max_runs_per_project", 10)
    for _ in range(10):
        run, prerequisite, _, _ = make_case(side)
        with side.uow() as uow:
            edges = []
            for i in range(1, 300):
                task_id = TaskId(side.new_id())
                seed_task(
                    side,
                    uow,
                    run.id,
                    display_key=f"P1.1/U{i + 1}",
                    position=i,
                    task_id=task_id,
                    status=TaskStatus.BLOCKED,
                    blocking_reason=blocking_reason(
                        BlockingCode.BLOCKED_BY_DEPENDENCY,
                        task_id=task_id,
                        refs={"prerequisite_task_ids": [str(prerequisite.id)]},
                        now=side.clock.now(),
                        message="Waiting for the runnable task",
                    ),
                )
                edges.append(TaskEdge(run.id, task_id, prerequisite.id, EdgeKind.BLOCKS, frozenset({"perf"})))
            uow.repo(TaskRepository).add_many((), edges)
            uow.commit()
    samples, checked, scheduled, errors = [], [], [], []
    for _ in range(10):
        start = perf_counter()
        try:
            result = system_dispatch(side, "schedule_ready_tasks")
            checked.append(result["runs_checked"])
            scheduled.append(len(result["scheduled"]))
        except SkmError as error:
            errors.append(str(error.code))
        samples.append((perf_counter() - start) * 1000)
        # A failed tick already rules out a ceiling on every tick. Keep the full elapsed sample.
        if samples[-1] > 1000 or errors:
            break
    measure(
        "scheduler_tick_ms",
        samples,
        runs=10,
        tasks_per_run=300,
        checked=checked,
        scheduled=scheduled,
        errors=errors,
    )
    assert not errors
    assert checked == [10] * len(samples)
    assert max(samples) <= 1000


def _wave(count, operation):
    gate = Barrier(count)

    def invoke(i):
        gate.wait(10)
        start = perf_counter()
        try:
            result = operation(i)
            return (perf_counter() - start) * 1000, result, None
        except SkmError as error:
            return (perf_counter() - start) * 1000, None, str(error.code)

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(invoke, range(count)))


def _capacity(side, slots):
    with side.uow(readonly=True) as uow:
        capabilities = get_worker(uow, side.worker1).capabilities
    side.worker1_client.dispatch(
        RecordWorkerHeartbeat(side.worker1, replace(capabilities, max_concurrency=slots))
    )


def test_concurrent_claim(recovery, measure):
    side = recovery
    _capacity(side, 10)
    expected = {str(make_case(side)[3].id) for _ in range(10)}
    first = _wave(10, lambda i: claim(side, key=f"perf-claim:0:{i}"))
    second = _wave(10, lambda i: claim(side, key=f"perf-claim:1:{i}"))
    actual = Counter(
        result["assignment_id"] for _, result, _ in first if result and "assignment_id" in result
    )
    empty = sum(
        bool(result and result.get("outcome") == "nothing_to_claim" and "assignment_id" not in result)
        for _, result, _ in second
    )
    first_errors = [error for _, _, error in first if error]
    second_errors = [error for _, _, error in second if error]
    stats = measure(
        "claim_ms",
        [ms for ms, _, _ in first],
        clients=10,
        issued=sum(actual.values()),
        errors=first_errors,
    )
    measure("empty_claim_ms", [ms for ms, _, _ in second], clients=10, empty=empty, errors=second_errors)
    assert not first_errors
    assert not second_errors
    assert len(expected) == 10
    assert actual == Counter(expected)
    assert empty == 10
    assert stats["p95"] <= 100


def _persisted_leases(side, claims):
    leases = []
    with side.uow(readonly=True) as uow:
        repository = uow.repo(AssignmentRepository)
        for item in claims:
            lease = repository.lease(AssignmentId(UUID(item["assignment_id"])))
            assert lease is not None
            assert lease.worker_id == side.worker1
            assert lease.fencing_token == item["fencing_token"]
            leases.append(lease)
    return leases


def test_renew_32_parallel_leases(recovery, measure):
    side = recovery
    _capacity(side, 32)
    for _ in range(32):
        make_case(side)
    claimed = [claim(side) for _ in range(32)]
    assert len({item["assignment_id"] for item in claimed}) == 32
    commands = [execution.RenewLease(claim=worker_claim(side, result)) for result in claimed]
    before = _persisted_leases(side, claimed)
    # PostgreSQL stamps claims with its own clock after acquiring ownership locks.
    side.clock.set(max(lease.last_heartbeat_at for lease in before))
    results = []
    verified = 0
    advance = timedelta(seconds=1)
    for wave in range(3):
        side.clock.advance(advance)
        renewed_wave = _wave(
            32,
            lambda i, wave=wave: side.worker1_client.dispatch(
                commands[i], idempotency_key=f"perf-renew:{wave}:{i}"
            ),
        )
        results.extend(renewed_wave)
        after = _persisted_leases(side, claimed)
        verified += sum(
            new.expires_at > old.expires_at
            and datetime.fromisoformat(result["lease_expires_at"]) == new.expires_at
            for (_, result, _), old, new in zip(renewed_wave, before, after, strict=True)
            if result and "lease_expires_at" in result
        )
        before = after
    errors = [error for _, _, error in results if error]
    renewed = sum(bool(result and result.get("lease_expires_at")) for _, result, _ in results)
    stats = measure(
        "renew_ms",
        [ms for ms, _, _ in results],
        assignments=32,
        renewed=renewed,
        persisted_extensions=verified,
        clock_step_s=advance.total_seconds(),
        errors=errors,
    )
    assert not errors
    assert renewed == verified == 96
    assert stats["p95"] <= 100


def test_clean_database_cost(clean_test_database, measure):
    db = clean_test_database
    samples = []
    with psycopg.connect(db.dsn) as conn:
        assert conn.info.server_version // 10000 == 16
    for _ in range(20):
        with psycopg.connect(db.dsn) as conn:
            conn.execute(
                """
                INSERT INTO skm_core.audit_records (id, actor_id, action, decision, request_id)
                SELECT gen_random_uuid(), %s, 'perf.cleanup', 'allowed', n::text
                FROM generate_series(1, 1000) AS n
                """,
                (uuid4(),),
            )
        start = perf_counter()
        clean_database(db.dsn, db.tables)
        samples.append((perf_counter() - start) * 1000)
        with psycopg.connect(db.dsn) as conn:
            assert conn.execute("SELECT count(*) FROM skm_core.audit_records").fetchone() == (0,)
    measure("clean_database_ms", samples, audit_rows=1000, schema_tables=len(db.tables))
