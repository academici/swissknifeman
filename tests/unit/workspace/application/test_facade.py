"""The facade of the workspace module (workspace §13): what other modules call in their transaction."""

from datetime import timedelta
from uuid import uuid4

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind
from skm.modules.workspace import public
from skm.modules.workspace.public import (
    ArchiveWorkspace,
    AttachRepository,
    BindCheckout,
    NormalizedRemote,
    normalize_remote,
    redact_remote,
)

REMOTE = "https://github.com/acme/app.git"
NORMALIZED = "github.com/acme/app"
LOCATOR = "/home/dev/app"


def test_projects_mounts_and_repositories(world) -> None:
    ws = world.workspace()
    project, repository = world.project(ws), world.repository(ws)
    world.run(AttachRepository(project_id=project, repository_id=repository))
    with world.uow(readonly=True) as uow:
        view = public.get_project(uow, project)
        assert [(m.mount_name, m.repository_id) for m in view.mounts] == [("main", repository)]
        assert public.project_mounts(uow, project) == frozenset({"main"})
        [mount] = public.project_repositories(uow, project)
        assert (mount.mount_name, mount.binding, mount.repository.canonical_remote) == (
            "main",
            None,
            NORMALIZED,
        )
        assert public.get_repository(uow, repository).title == "app"
        assert public.primary_remote(uow, repository) == NormalizedRemote(NORMALIZED)
        assert public.workspace_of_project(uow, project) == ws
        assert public.require_active_workspace(uow, ws).project_count == 1


def test_a_repository_of_another_workspace_is_not_found(world) -> None:
    one, two = world.workspace("one"), world.workspace("two")
    repository = world.repository(one)
    local = world.repository(one, title="local", remote=None)
    with world.uow(readonly=True) as uow:
        assert public.require_repository(uow, one, repository).repository_id == repository
        with pytest.raises(SkmError) as caught:
            public.require_repository(uow, two, repository)
        assert caught.value.code is ErrorCode.NOT_FOUND
        with pytest.raises(SkmError):
            public.get_repository(uow, uuid4())  # type: ignore[arg-type]
        assert public.primary_remote(uow, local) is None


def test_scope_chain_runs_from_the_instance_to_the_scope(world) -> None:
    ws = world.workspace()
    project = world.project(ws)
    with world.uow(readonly=True) as uow:
        chain = public.scope_chain(uow, ScopeId(project))
    assert [(ref.kind, ref.id) for ref in chain] == [
        (ScopeKind.INSTANCE, world.instance),
        (ScopeKind.WORKSPACE, ws),
        (ScopeKind.PROJECT, project),
    ]
    with world.uow(readonly=True) as uow:
        with pytest.raises(SkmError) as caught:
            public.scope_chain(uow, ScopeId(uuid4()))
        assert caught.value.code is ErrorCode.NOT_FOUND


def test_get_host_binding_and_resolve_checkout(world) -> None:
    ws = world.workspace()
    project, repository, host = world.project(ws), world.repository(ws), world.host("laptop")
    world.run(AttachRepository(project_id=project, repository_id=repository))
    bound = world.run(
        BindCheckout(
            repository_id=repository,
            host_id=host,
            local_locator=LOCATOR,
            observed_toplevel=LOCATOR,
            observed_remotes=(NORMALIZED,),
            observed_head=None,
            observed_dirty=None,
            observed_at=world.clock.now(),
        )
    )
    now = world.clock.now() + timedelta(days=40)
    with world.uow(readonly=True) as uow:
        assert public.get_host(uow, host).name == "laptop"
        binding = public.get_checkout_binding(uow, bound.binding_id, now=now)
        assert (binding.state, binding.is_stale, binding.local_locator) == ("active", True, None)
        location = public.resolve_checkout(uow, project, "main", host, now=world.clock.now())
        assert (location.local_locator, location.is_stale) == (LOCATOR, False)
        with pytest.raises(SkmError) as caught:
            public.resolve_checkout(uow, project, "main", world.ids.new_id(), now=now)
        assert caught.value.code is ErrorCode.CHECKOUT_UNBOUND


def test_workers_by_id_by_principal_and_the_online_list(world) -> None:
    one, two = world.workspace("one"), world.workspace("two")
    host_a, host_b = world.host("a"), world.host("b")
    live, live_id = world.worker(one, host_b, "live", state="online")
    _, also_id = world.worker(one, host_a, "also", state="online")
    world.worker(one, host_a, "asleep", state="offline")
    world.worker(one, host_a, "retired", state="retired")
    _, elsewhere = world.worker(two, host_a, "elsewhere", state="online")
    with world.uow(readonly=True) as uow:
        assert public.get_worker(uow, live_id).display_name == "live"
        found = public.worker_for_principal(uow, live.principal_id)
        assert found is not None
        assert found.worker_id == live_id
        assert public.worker_for_principal(uow, world.actor("owner").principal_id) is None
        online = public.list_online_workers(uow, [one])
        assert [w.worker_id for w in online] == sorted(
            [live_id, also_id], key=lambda i: (str(host_b if i == live_id else host_a), str(i))
        )
        assert {w.worker_id for w in public.list_online_workers(uow, [one, two])} == {
            live_id,
            also_id,
            elsewhere,
        }
        assert public.list_online_workers(uow, []) == ()


def test_mark_workers_offline_records_a_state_change_for_each_overdue_worker(world) -> None:
    ws = world.workspace()
    host = world.host()
    _, stale = world.worker(ws, host, "stale", state="online")
    _, draining = world.worker(ws, host, "draining", state="draining")
    _, offline = world.worker(ws, host, "offline", state="offline")
    world.clock.advance(timedelta(minutes=10))
    _, fresh = world.worker(ws, host, "fresh", state="online")
    with world.uow() as uow:
        marked = public.mark_workers_offline(uow, world.clock.now() - timedelta(minutes=5))
        uow.commit()
    assert set(marked) == {stale, draining}
    states = {w.id: w.state.value for w in world.tables().workers.values()}
    assert (states[stale], states[draining], states[offline], states[fresh]) == (
        "offline",
        "offline",
        "offline",
        "online",
    )
    changes = {
        (e.payload["worker_id"], e.payload["from_state"], e.payload["to_state"])
        for e in world.events("worker-state-changed")
    }
    assert changes == {(str(stale), "online", "offline"), (str(draining), "draining", "offline")}
    with world.uow() as uow:
        assert (
            public.mark_workers_offline(uow, world.clock.now() - timedelta(minutes=5)) == ()
        )  # nothing twice


def test_the_remote_helpers_are_the_domain_rules(world) -> None:
    assert normalize_remote("git@GitHub.com:Acme/App.git") == NormalizedRemote("github.com/Acme/App")
    assert normalize_remote("/local/path") is None
    assert redact_remote("https://user:token@github.com/acme/app") == "https://github.com/acme/app"
    world.run(ArchiveWorkspace(workspace_id=world.workspace(), expected_row_version=1, reason="x"))
