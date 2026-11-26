"""Hosts and their scope (workspace §7, §8, §18 K17; access §4.4 rows 6a/6b)."""

import pytest

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import ScopeId
from skm.modules.access.domain.roles import Role
from skm.modules.access.ports import WorkerHostLookup
from skm.modules.workspace.generated.commands import HostArch, HostOs
from skm.modules.workspace.public import GetHost, ListHosts, RegisterHost, RegisterHostDefsHostPlatform

PLATFORM = RegisterHostDefsHostPlatform(os=HostOs.MACOS, arch=HostArch.ARM64)


def refused(world, dto, actor, code: ErrorCode = ErrorCode.FORBIDDEN) -> SkmError:
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        world.run(dto, actor) if hasattr(dto, "platform") else world.ask(dto, actor)
    assert caught.value.code is code
    assert world.snapshot() == before
    return caught.value


def test_a_member_of_only_a_workspace_lists_every_host_through_that_workspace(world) -> None:
    ws = world.workspace()
    world.host("laptop")
    world.host("server")
    viewer = world.person("viewer", {ws: Role.VIEWER})
    page = world.ask(ListHosts(workspace_id=ws), viewer)
    assert [h.name for h in page.items] == ["laptop", "server"]
    assert page.next is None


def test_without_a_workspace_the_instance_membership_is_needed(world) -> None:
    ws = world.workspace()
    world.host("laptop")
    viewer = world.person("viewer", {ws: Role.VIEWER})
    refused(world, ListHosts(), viewer)
    assert [h.name for h in world.ask(ListHosts(), "owner").items] == ["laptop"]


def test_another_workspace_gives_no_right_through_a_workspace_id(world) -> None:
    one, two = world.workspace("one"), world.workspace("two")
    world.host()
    outsider = world.person("outsider", {two: Role.OWNER})
    refused(world, ListHosts(workspace_id=one), outsider)


def test_list_hosts_pages_and_filters_by_name_and_state(world) -> None:
    ws = world.workspace()
    for name in ("a-host", "b-host", "c-host"):
        world.host(name)
    viewer = world.person("viewer", {ws: Role.VIEWER})
    first = world.ask(ListHosts(workspace_id=ws, limit=2), viewer)
    assert [h.name for h in first.items] == ["a-host", "b-host"]
    assert first.next is not None
    last = world.ask(ListHosts(workspace_id=ws, limit=2, after=first.next), viewer)
    assert [h.name for h in last.items] == ["c-host"]
    assert last.next is None
    assert [h.name for h in world.ask(ListHosts(workspace_id=ws, name="b-host"), viewer).items] == ["b-host"]
    assert world.ask(ListHosts(workspace_id=ws, name="b-host", state="retired"), viewer).items == ()
    assert world.ask(ListHosts(workspace_id=ws, name="missing"), viewer).items == ()


def test_a_worker_reads_its_own_host_and_not_another(world) -> None:
    ws = world.workspace()
    mine, other = world.host("mine"), world.host("other")
    worker, _ = world.worker(ws, mine)
    assert world.ask(GetHost(host_id=mine), worker).name == "mine"
    assert refused(world, GetHost(host_id=other), worker).details["permission"] == "workspace.read"


def test_a_retired_worker_gives_no_host_rights(world) -> None:
    ws = world.workspace()
    host = world.host()
    worker, _ = world.worker(ws, host, state="retired")
    refused(world, GetHost(host_id=host), worker)
    with world.uow(readonly=True) as uow:
        assert uow.repo(WorkerHostLookup).host_ids(worker.principal_id) == frozenset()


def test_the_lookup_lists_the_hosts_of_live_workers_only(world) -> None:
    ws = world.workspace()
    a, b = world.host("a"), world.host("b")
    live, _ = world.worker(ws, a, "live", state="online")
    gone, _ = world.worker(ws, b, "gone", state="retired")
    with world.uow(readonly=True) as uow:
        lookup = uow.repo(WorkerHostLookup)
        assert lookup.host_ids(live.principal_id) == frozenset({ScopeId(a)})
        assert lookup.host_ids(gone.principal_id) == frozenset()
        assert lookup.host_ids(world.actor("owner").principal_id) == frozenset()


def test_a_person_with_any_workspace_membership_reads_a_host_by_id_and_by_name(world) -> None:
    ws = world.workspace()
    host = world.host("laptop")
    viewer = world.person("viewer", {ws: Role.VIEWER})
    assert world.ask(GetHost(host_id=host), viewer).name == "laptop"
    assert world.ask(GetHost(name="laptop", workspace_id=ws), viewer).host_id == host
    stranger = world.person("stranger")
    refused(world, GetHost(host_id=host), stranger)
    refused(world, GetHost(name="laptop"), viewer)  # no workspace_id: the instance membership is needed


def test_get_host_wants_exactly_one_of_id_and_name_and_reports_a_missing_name(world) -> None:
    world.host("laptop")
    for query in (GetHost(), GetHost(host_id=world.host("x"), name="x")):
        with pytest.raises(SkmError) as caught:
            world.ask(query, "owner")
        assert caught.value.code is ErrorCode.SCHEMA_INVALID
    with pytest.raises(SkmError) as caught:
        world.ask(GetHost(name="nope"), "owner")
    assert caught.value.code is ErrorCode.NOT_FOUND


def test_register_host_by_a_worker_is_forbidden_and_by_a_person_works(world) -> None:
    ws = world.workspace()
    worker, _ = world.worker(ws, world.host("seed"))
    refused(world, RegisterHost(name="new", platform=PLATFORM), worker)
    result = world.run(RegisterHost(name="new", platform=PLATFORM))
    [event] = [e for e in world.events("host-registered") if e.stream_id == result.host_id]
    assert (event.stream_kind, event.stream_id, event.workspace_id) == ("host", result.host_id, None)
    assert event.payload["platform"] == {"os": "macos", "arch": "arm64"}
    assert world.tables().hosts[result.host_id].last_seen_at is None


def test_register_host_needs_host_manage_and_a_service_may_register(world) -> None:
    ws = world.workspace()
    maintainer = world.person("maintainer", {ws: Role.MAINTAINER})
    refused(world, RegisterHost(name="new", platform=PLATFORM), maintainer)
    service = world.person("svc", {world.instance: Role.OWNER}, kind=PrincipalKind.SERVICE)
    assert world.run(RegisterHost(name="svc-host", platform=PLATFORM), service).name == "svc-host"


def test_a_host_name_is_unique_and_checked(world) -> None:
    world.host("laptop")
    assert refused(world, RegisterHost(name="laptop", platform=PLATFORM), "owner", ErrorCode.ALREADY_EXISTS)
    with pytest.raises(SkmError) as caught:
        world.run(RegisterHost(name="Bad Name", platform=PLATFORM))
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
