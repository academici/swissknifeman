"""WorkerRepository and ``access.WorkerHostLookup``: one contract over memory and PostgreSQL (§6, §13).

memory ∥ pg: workers round trip with their capabilities document; one worker per principal; compare-and-set
``save``; ``heartbeat`` (last writer wins, ``offline -> online``, retired refused); keyset ``(registered_at,
id)`` per workspace and state; ``online`` only for the named workspaces in ``(host_id, worker_id)`` order;
``overdue``/``mark_offline_older_than`` for the sweeper; ``WorkerHostLookup`` never returns a retired worker's
host. Facade: ``list_online_workers`` gives downstream consumers labels, isolation profiles and the full
capabilities of online workers only. PostgreSQL only: a worker never changes workspace, host or principal.
"""

from dataclasses import replace
from datetime import timedelta

import pytest

from contracts.workspace.harness import Side, make_capabilities
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed
from skm.kernel.ids import PrincipalId, ScopeId, WorkerId, WorkspaceId
from skm.modules.access.ports import WorkerHostLookup
from skm.modules.workspace import public
from skm.modules.workspace.domain.host import HostArch, HostOs, HostPlatform
from skm.modules.workspace.domain.worker import WorkerCapabilities, WorkerState
from skm.modules.workspace.ports import WorkerRepository
from skm.modules.workspace.public import ListWorkers

RICH = WorkerCapabilities(
    runtimes=("claude_code", "codex"),
    isolation_profiles=("worktree", "container", "acme.box:strict"),
    max_concurrency=8,
    labels=("gpu", "region:eu-1", "arch.x86_64"),
    platform=HostPlatform(HostOs.MACOS, HostArch.ARM64),
    skm_version="2.1.0-rc.1",
)


def test_workers_round_trip_one_per_principal_and_compare_and_set(side: Side) -> None:
    ws = side.workspace("alpha")
    host = side.host("laptop")
    _, made = side.worker(ws, host, "w1", capabilities=RICH)
    with side.uow() as uow:
        workers = uow.repo(WorkerRepository)
        stored = workers.get(made.id)
        assert stored == made
        assert stored.capabilities == RICH
        assert workers.for_principal(made.principal_id) == stored
        assert workers.for_principal(PrincipalId(side.ids.new_id())) is None
        for duplicate in (replace(made, id=WorkerId(side.ids.new_id())), made):
            with pytest.raises(Conflict) as taken:
                workers.add(duplicate)
            assert taken.value.details == {"kind": "worker"}
        drained = replace(stored, state=WorkerState.DRAINING, display_name="w1 (drain)", row_version=2)
        workers.save(drained, expected_version=1)
        uow.commit()
    with side.uow() as uow:
        workers = uow.repo(WorkerRepository)
        assert workers.get(made.id) == drained
        with pytest.raises(Conflict) as stale:
            workers.save(replace(made, row_version=2), expected_version=1)
        assert stale.value.details == {"kind": "worker", "expected": 1, "actual": 2}
        with pytest.raises(NotFound) as missing:
            workers.get(WorkerId(side.ids.new_id()))
        assert missing.value.details["kind"] == "worker"


def test_heartbeat_brings_an_offline_worker_online_and_never_a_retired_one(side: Side) -> None:
    ws = side.workspace("alpha")
    host = side.host("laptop")
    _, made = side.worker(ws, host, "w1")
    _, retired = side.worker(ws, host, "w2", state=WorkerState.RETIRED)
    side.tick(30)
    with side.uow() as uow:
        workers = uow.repo(WorkerRepository)
        beaten = workers.heartbeat(made.id, side.clock.now(), None)
        assert (beaten.state, beaten.last_heartbeat_at, beaten.row_version) == (
            WorkerState.ONLINE,
            side.clock.now(),
            2,
        )
        assert beaten.capabilities == made.capabilities
        again = workers.heartbeat(made.id, side.clock.now() + timedelta(seconds=5), RICH)
        assert (again.state, again.capabilities, again.row_version) == (WorkerState.ONLINE, RICH, 3)
        uow.commit()
    with side.uow() as uow:
        workers = uow.repo(WorkerRepository)
        assert workers.get(made.id) == again
        with pytest.raises(PreconditionFailed) as refused:
            workers.heartbeat(retired.id, side.clock.now(), None)
        assert refused.value.code is ErrorCode.INVALID_TRANSITION
    with side.uow() as uow, pytest.raises(NotFound):
        uow.repo(WorkerRepository).heartbeat(WorkerId(side.ids.new_id()), side.clock.now(), None)


def test_workers_list_by_workspace_registration_and_state(side: Side) -> None:
    ws, other = side.workspace("alpha"), side.workspace("beta")
    host = side.host("laptop")
    made = []
    for n in range(5):
        if n % 2 == 0:
            side.tick()
        made.append(
            side.worker(ws, host, f"w{n}", state=WorkerState.ONLINE if n % 2 else WorkerState.OFFLINE)[1]
        )
    side.worker(other, host, "hidden")
    expected = sorted(made, key=lambda w: (w.registered_at, str(w.id)))
    with side.uow(readonly=True) as uow:
        workers = uow.repo(WorkerRepository)
        seen = []
        after: str | None = None
        while True:
            page = workers.list(ws, state=None, after=after, limit=2)
            seen.extend(page.items)
            if page.next is None:
                break
            after = page.next
        assert seen == expected
        online = workers.list(ws, state=WorkerState.ONLINE, after=None, limit=10).items
        assert [w.id for w in online] == [w.id for w in expected if w.state is WorkerState.ONLINE]
    listed = side.ask(ListWorkers(workspace_id=ws, limit=200))
    assert [item.worker_id for item in listed.items] == [w.id for w in expected]


def test_online_workers_of_the_named_workspaces_in_host_then_worker_order(side: Side) -> None:
    ws, other, third = side.workspace("alpha"), side.workspace("beta"), side.workspace("gamma")
    hosts = sorted((side.host("h1"), side.host("h2")), key=str)
    on = [
        side.worker(ws, hosts[1], "a", state=WorkerState.ONLINE, capabilities=RICH)[1],
        side.worker(ws, hosts[0], "b", state=WorkerState.ONLINE)[1],
        side.worker(other, hosts[0], "c", state=WorkerState.ONLINE)[1],
    ]
    side.worker(ws, hosts[0], "drain", state=WorkerState.DRAINING)
    side.worker(ws, hosts[0], "off", state=WorkerState.OFFLINE)
    side.worker(third, hosts[0], "elsewhere", state=WorkerState.ONLINE)
    expected = sorted(on, key=lambda w: (str(w.host_id), str(w.id)))
    with side.uow(readonly=True) as uow:
        assert uow.repo(WorkerRepository).online([ws, other, ws]) == tuple(expected)
        assert uow.repo(WorkerRepository).online([]) == ()
        views = public.list_online_workers(uow, [ws, other])
    assert [v.worker_id for v in views] == [w.id for w in expected]
    rich = next(v for v in views if v.worker_id == on[0].id)
    assert (rich.host_id, rich.workspace_id, rich.state) == (hosts[1], ws, "online")
    assert tuple(rich.capabilities.labels) == RICH.labels
    assert tuple(rich.capabilities.isolation_profiles) == RICH.isolation_profiles
    assert tuple(rich.capabilities.runtimes) == RICH.runtimes
    assert (rich.capabilities.max_concurrency, rich.capabilities.skm_version) == (8, "2.1.0-rc.1")
    assert (rich.capabilities.platform.os.value, rich.capabilities.platform.arch.value) == ("macos", "arm64")


def test_overdue_workers_are_marked_offline_once(side: Side) -> None:
    ws = side.workspace("alpha")
    host = side.host("laptop")
    _, quiet = side.worker(ws, host, "quiet", state=WorkerState.ONLINE)
    _, draining = side.worker(ws, host, "draining", state=WorkerState.DRAINING)
    _, offline = side.worker(ws, host, "offline", state=WorkerState.OFFLINE)
    _, alive = side.worker(ws, host, "alive", state=WorkerState.OFFLINE)
    side.tick(600)
    with side.uow() as uow:
        uow.repo(WorkerRepository).heartbeat(alive.id, side.clock.now(), None)
        uow.commit()
    cutoff = side.clock.now() - timedelta(seconds=120)
    with side.uow() as uow:
        workers = uow.repo(WorkerRepository)
        assert {w.id for w in workers.overdue(cutoff)} == {quiet.id, draining.id}
        marked = workers.mark_offline_older_than(cutoff)
        assert marked == tuple(sorted((quiet.id, draining.id), key=str))
        assert workers.mark_offline_older_than(cutoff) == ()
        uow.commit()
    with side.uow(readonly=True) as uow:
        workers = uow.repo(WorkerRepository)
        assert [(workers.get(w.id).state, workers.get(w.id).row_version) for w in (quiet, draining)] == [
            (WorkerState.OFFLINE, 2),
            (WorkerState.OFFLINE, 2),
        ]
        assert workers.get(offline.id).row_version == 1
        assert workers.get(alive.id).state is WorkerState.ONLINE


def test_mark_workers_offline_records_one_state_change_each(side: Side) -> None:
    ws = side.workspace("alpha")
    host = side.host("laptop")
    _, quiet = side.worker(ws, host, "quiet", state=WorkerState.ONLINE)
    side.tick(600)
    with side.uow() as uow:
        marked = public.mark_workers_offline(uow, side.clock.now() - timedelta(seconds=120))
        uow.commit()
    assert marked == (quiet.id,)
    [(_, payload)] = side.events("worker-state-changed")
    assert (payload["worker_id"], payload["from_state"], payload["to_state"]) == (
        str(quiet.id),
        "online",
        "offline",
    )


def test_worker_scope_lookup_only_returns_non_retired_workers(side: Side) -> None:
    ws = side.workspace("alpha")
    h1, h3 = side.host("h1"), side.host("h3")
    _, first = side.worker(ws, h1, "w1", state=WorkerState.ONLINE)
    _, retired = side.worker(ws, h3, "w3", state=WorkerState.RETIRED)
    with side.uow(readonly=True) as uow:
        lookup = uow.repo(WorkerHostLookup)
        missing = PrincipalId(side.ids.new_id())
        assert lookup.host_ids(first.principal_id) == frozenset({ScopeId(h1)})
        assert lookup.host_ids(retired.principal_id) == frozenset()
        assert lookup.host_ids(missing) == frozenset()
        assert lookup.workspace_scope_id(first.principal_id) == ScopeId(ws)
        assert lookup.workspace_scope_id(retired.principal_id) is None
        assert lookup.workspace_scope_id(missing) is None
    with side.uow() as uow:
        workers = uow.repo(WorkerRepository)
        workers.save(replace(first, state=WorkerState.RETIRED, row_version=2), expected_version=1)
        uow.commit()
    with side.uow(readonly=True) as uow:
        lookup = uow.repo(WorkerHostLookup)
        assert lookup.host_ids(first.principal_id) == frozenset()
        assert lookup.workspace_scope_id(first.principal_id) is None


@pytest.mark.pg
def test_save_never_moves_a_worker(pg_side: Side) -> None:
    ws, other = pg_side.workspace("alpha"), pg_side.workspace("beta")
    host, second = pg_side.host("h1"), pg_side.host("h2")
    _, made = pg_side.worker(ws, host, "w1")
    with pg_side.uow() as uow:
        workers = uow.repo(WorkerRepository)
        for changed, field in (
            (replace(made, workspace_id=WorkspaceId(other)), "workspace_id"),
            (replace(made, host_id=second), "host_id"),
            (replace(made, principal_id=PrincipalId(pg_side.ids.new_id())), "principal_id"),
        ):
            with pytest.raises(ValueError, match=field):
                workers.save(replace(changed, row_version=2), expected_version=1)
    rows = pg_side.sql(
        "SELECT workspace_id, host_id, row_version FROM skm_workspace.workers WHERE id = %s", (made.id,)
    )
    assert rows == [(ws, host, 1)]
    assert make_capabilities() == made.capabilities
