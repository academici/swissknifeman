"""HostRepository and CheckoutBindingRepository: one contract over memory and PostgreSQL (workspace §6, §11).

memory ∥ pg: hosts round trip, unique name, ``touch`` only moves ``last_seen_at`` forward and keeps
``row_version``, keyset ``(name, id)``. Bindings: one live binding per ``(host, repository)`` (a removed one
frees the pair), compare-and-set ``save``; a verification after the checkout moved is ``mismatched`` and never
moves the locator (WORKSPACE-01: the binding identity is ``(binding, host, repository, locator)``);
``local_locator`` is never part of a committed event and is listed only for ``checkout.read_locator``.
PostgreSQL only: ``save`` refuses a value that changes the binding identity.
"""

from dataclasses import replace
from datetime import timedelta

import pytest

from contracts.workspace.harness import Side
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.ids import HostId, RepositoryId, ScopeId
from skm.modules.access.public import Role
from skm.modules.workspace.domain.checkout_binding import BindingState, CheckoutBindingId, remove
from skm.modules.workspace.domain.host import HostArch, HostName, HostOs, HostPlatform, HostState, new_host
from skm.modules.workspace.domain.remote_url import NormalizedRemote
from skm.modules.workspace.ports import CheckoutBindingRepository, HostRepository
from skm.modules.workspace.public import (
    AttachRepository,
    BindCheckout,
    ListProjectRepositories,
    RecordCheckoutVerification,
    ResolveCheckout,
)

LOCATOR = "/home/dev/src/app-checkout"
HEAD = "a" * 40


def test_hosts_round_trip_unique_name_touch_and_compare_and_set(side: Side) -> None:
    host_id = side.host("laptop")
    with side.uow() as uow:
        hosts = uow.repo(HostRepository)
        stored = hosts.get(host_id)
        assert (stored.name, stored.state, stored.last_seen_at, stored.row_version) == (
            "laptop",
            HostState.ACTIVE,
            None,
            1,
        )
        assert stored.platform == HostPlatform(HostOs.LINUX, HostArch.X86_64)
        assert hosts.find_by_name("laptop") == stored
        assert hosts.find_by_name("desktop") is None
        twin = new_host(
            host_id=HostId(side.ids.new_id()),
            name=HostName("laptop"),
            platform=HostPlatform(HostOs.MACOS, HostArch.ARM64),
            now=side.clock.now(),
        )
        with pytest.raises(Conflict) as taken:
            hosts.add(twin)
        assert taken.value.details == {"kind": "host", "name": "laptop"}
        seen = side.clock.now() + timedelta(minutes=5)
        hosts.touch(host_id, seen)
        hosts.touch(host_id, seen - timedelta(minutes=1))  # never backwards
        with pytest.raises(NotFound):
            hosts.touch(HostId(side.ids.new_id()), seen)
    with side.uow() as uow:  # the refused touch ended that unit of work: nothing was written
        hosts = uow.repo(HostRepository)
        assert hosts.get(host_id).last_seen_at is None
        hosts.touch(host_id, seen)
        hosts.touch(host_id, seen - timedelta(minutes=1))
        uow.commit()
    with side.uow() as uow:
        hosts = uow.repo(HostRepository)
        touched = hosts.get(host_id)
        assert (touched.last_seen_at, touched.row_version) == (seen, 1)
        hosts.save(replace(touched, state=HostState.RETIRED, row_version=2), expected_version=1)
        with pytest.raises(Conflict) as stale:
            hosts.save(replace(touched, row_version=2), expected_version=1)
        assert stale.value.details == {"kind": "host", "expected": 1, "actual": 2}
        uow.commit()
    with side.uow(readonly=True) as uow:
        assert uow.repo(HostRepository).get(host_id).state is HostState.RETIRED


def test_hosts_page_by_name_then_id_and_filter_by_state(side: Side) -> None:
    names = ["zeta", "alpha", "mu", "beta", "omega"]
    made = {name: side.host(name) for name in names}
    with side.uow() as uow:
        hosts = uow.repo(HostRepository)
        mu = hosts.get(made["mu"])
        hosts.save(replace(mu, state=HostState.RETIRED, row_version=2), expected_version=1)
        uow.commit()
    with side.uow(readonly=True) as uow:
        hosts = uow.repo(HostRepository)
        seen: list[str] = []
        after: str | None = None
        while True:
            page = hosts.list(state=None, after=after, limit=2)
            seen.extend(item.name for item in page.items)
            if page.next is None:
                break
            after = page.next
        assert seen == sorted(names)
        assert [h.name for h in hosts.list(state=HostState.RETIRED, after=None, limit=10).items] == ["mu"]
        with pytest.raises(ValidationFailed):
            hosts.list(state=None, after="Zm9v", limit=2)


def _bind(side: Side, repository: RepositoryId, host: HostId, locator: str = LOCATOR) -> CheckoutBindingId:
    result = side.run(
        BindCheckout(
            repository_id=repository,
            host_id=host,
            local_locator=locator,
            observed_toplevel=locator,
            observed_remotes=("github.com/acme/app",),
            observed_head=HEAD,
            observed_dirty=False,
            observed_at=side.clock.now(),
        )
    )
    assert result.state == "active"
    return CheckoutBindingId(result.binding_id)


def test_one_live_binding_per_host_and_repository_and_a_removed_one_frees_it(side: Side) -> None:
    ws = side.workspace("alpha")
    host, other_host = side.host("laptop"), side.host("desktop")
    app = side.repository(ws)
    first = _bind(side, app, host)
    _bind(side, app, other_host, "/srv/app")  # another host may bind the same repository
    with pytest.raises(Conflict) as again:
        side.run(
            BindCheckout(
                repository_id=app,
                host_id=host,
                local_locator="/elsewhere/app",
                observed_toplevel="/elsewhere/app",
                observed_remotes=("github.com/acme/app",),
                observed_head=None,
                observed_dirty=None,
                observed_at=side.clock.now(),
            )
        )
    assert again.value.details["binding_id"] == str(first)
    with side.uow() as uow:
        bindings = uow.repo(CheckoutBindingRepository)
        live = bindings.find(host, app)
        assert live is not None
        assert (live.id, live.local_locator, live.state, live.observed_head) == (
            first,
            LOCATOR,
            BindingState.ACTIVE,
            HEAD,
        )
        assert live.observed_remotes == (NormalizedRemote("github.com/acme/app"),)
        assert bindings.get(first) == live
        duplicate = replace(live, id=CheckoutBindingId(side.ids.new_id()))
        with pytest.raises(Conflict) as taken:
            bindings.add(duplicate)
        assert taken.value.details == {"kind": "binding", "binding_id": str(first)}
        removed = remove(live)
        bindings.save(removed, expected_version=live.row_version)
        assert bindings.find(host, app) is None
        bindings.add(replace(duplicate, local_locator="/elsewhere/app"))  # the pair is free again
        with pytest.raises(NotFound) as missing:
            bindings.get(CheckoutBindingId(side.ids.new_id()))
        assert missing.value.details["kind"] == "binding"
        uow.commit()
    with side.uow(readonly=True) as uow:
        bindings = uow.repo(CheckoutBindingRepository)
        assert bindings.get(first).state is BindingState.REMOVED
        assert bindings.get(first).local_locator == LOCATOR
        found = bindings.find(host, app)
        assert found is not None
        assert (found.id, found.local_locator) == (duplicate.id, "/elsewhere/app")


def test_verification_never_moves_the_locator_and_bumps_the_row_version(side: Side) -> None:
    ws = side.workspace("alpha")
    host = side.host("laptop")
    app = side.repository(ws)
    binding_id = _bind(side, app, host)
    side.tick(60)
    moved = side.run(
        RecordCheckoutVerification(
            binding_id=binding_id,
            expected_row_version=1,
            observed_exists=True,
            observed_toplevel="/somewhere/else",
            observed_remotes=("github.com/acme/app",),
            observed_head="b" * 40,
            observed_dirty=True,
            observed_at=side.clock.now(),
        )
    )
    assert (moved.state, moved.reason, moved.row_version) == ("mismatched", "moved", 2)
    side.tick(60)
    back = side.run(
        RecordCheckoutVerification(
            binding_id=binding_id,
            expected_row_version=2,
            observed_exists=True,
            observed_toplevel=LOCATOR,
            observed_remotes=("github.com/acme/app",),
            observed_head="c" * 40,
            observed_dirty=False,
            observed_at=side.clock.now(),
        )
    )
    assert (back.state, back.reason, back.row_version) == ("active", "ok", 3)
    with pytest.raises(Conflict) as stale:
        side.run(
            RecordCheckoutVerification(
                binding_id=binding_id,
                expected_row_version=2,
                observed_exists=False,
                observed_toplevel=None,
                observed_remotes=(),
                observed_head=None,
                observed_dirty=None,
                observed_at=side.clock.now(),
            )
        )
    assert stale.value.code is ErrorCode.VERSION_CONFLICT
    with side.uow(readonly=True) as uow:
        stored = uow.repo(CheckoutBindingRepository).get(binding_id)
    assert (stored.local_locator, stored.host_id, stored.repository_id, stored.workspace_id) == (
        LOCATOR,
        host,
        app,
        ws,
    )
    assert (stored.state, stored.observed_head, stored.row_version) == (BindingState.ACTIVE, "c" * 40, 3)
    assert stored.last_verified_at == side.clock.now()


def test_the_locator_is_never_in_an_event_and_listed_only_with_read_locator(side: Side) -> None:
    ws = side.workspace("alpha")
    host = side.host("laptop")
    app = side.repository(ws)
    project = side.project(ws, "skm")
    side.run(AttachRepository(project_id=project, repository_id=app, mount_name="main", role="primary"))
    binding_id = _bind(side, app, host)
    location = side.ask(ResolveCheckout(project_id=project, mount_name="main", host_id=host))
    assert (location.binding_id, location.local_locator, location.state) == (binding_id, LOCATOR, "active")
    side.run(
        RecordCheckoutVerification(
            binding_id=binding_id,
            expected_row_version=1,
            observed_exists=True,
            observed_toplevel="/moved/app",
            observed_remotes=(),
            observed_head=None,
            observed_dirty=None,
            observed_at=side.clock.now(),
        )
    )
    events = side.events()
    assert len(side.events("checkout-bound")) == len(side.events("checkout-binding-verified")) == 1
    assert all(LOCATOR not in repr(payload) and "/moved/app" not in repr(payload) for _, payload in events)
    side.person("viewer", {ScopeId(ws): Role.VIEWER})
    hidden = side.ask(ListProjectRepositories(project_id=project, host_id=host), "viewer")
    shown = side.ask(ListProjectRepositories(project_id=project, host_id=host))
    assert hidden.items[0].binding.binding_id == binding_id
    assert hidden.items[0].binding.local_locator is None
    assert shown.items[0].binding.local_locator == LOCATOR  # the owner holds it through the instance


@pytest.mark.pg
def test_save_refuses_a_change_of_the_binding_identity(pg_side: Side) -> None:
    ws, other = pg_side.workspace("alpha"), pg_side.workspace("beta")
    host, other_host = pg_side.host("laptop"), pg_side.host("desktop")
    app = pg_side.repository(ws)
    foreign = pg_side.repository(other)
    binding_id = _bind(pg_side, app, host)
    with pg_side.uow() as uow:
        bindings = uow.repo(CheckoutBindingRepository)
        stored = bindings.get(binding_id)
        for changed, field in (
            (replace(stored, local_locator="/moved/app"), "local_locator"),
            (replace(stored, host_id=other_host), "host_id"),
            (replace(stored, repository_id=foreign, workspace_id=other), "workspace_id"),
        ):
            with pytest.raises(ValueError, match=field):
                bindings.save(replace(changed, row_version=2), expected_version=1)
    assert pg_side.sql(
        "SELECT local_locator, host_id, repository_id, row_version "
        "FROM skm_workspace.checkout_bindings WHERE id = %s",
        (binding_id,),
    ) == [(LOCATOR, host, app, 1)]
