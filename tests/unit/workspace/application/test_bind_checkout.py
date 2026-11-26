"""``bind_checkout``, ``record_checkout_verification`` and the reads of a binding (workspace §5.3, §7, §8)."""

import json
from datetime import timedelta

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.access.domain.roles import Role
from skm.modules.workspace.public import (
    ArchiveWorkspace,
    AttachRepository,
    BindCheckout,
    ListProjectRepositories,
    RecordCheckoutVerification,
    ResolveCheckout,
)

REMOTE = "https://github.com/acme/app.git"
NORMALIZED = "github.com/acme/app"
LOCATOR = "/home/dev/app"
HEAD = "a" * 40


class Setup:
    """A workspace with a project, a mounted repository (one remote) and a host."""

    def __init__(self, world) -> None:
        self.world = world
        self.ws = world.workspace()
        self.project = world.project(self.ws)
        self.repository = world.repository(self.ws)
        self.host = world.host()
        world.run(AttachRepository(project_id=self.project, repository_id=self.repository))

    def bind(self, actor="owner", **fields):
        values = {
            "repository_id": self.repository,
            "host_id": self.host,
            "local_locator": LOCATOR,
            "observed_toplevel": LOCATOR,
            "observed_remotes": (NORMALIZED,),
            "observed_head": HEAD,
            "observed_dirty": False,
            "observed_at": self.world.clock.now(),
            **fields,
        }
        return self.world.run(BindCheckout(**values), actor)

    def verify(self, binding_id, version, actor="owner", **fields):
        values = {
            "binding_id": binding_id,
            "expected_row_version": version,
            "observed_exists": True,
            "observed_toplevel": LOCATOR,
            "observed_remotes": (NORMALIZED,),
            "observed_head": HEAD,
            "observed_dirty": False,
            "observed_at": self.world.clock.now(),
            **fields,
        }
        return self.world.run(RecordCheckoutVerification(**values), actor)


@pytest.fixture
def setup(world) -> Setup:
    return Setup(world)


def test_bind_creates_an_active_binding_and_the_event_without_the_locator(world, setup) -> None:
    result = setup.bind()
    assert (result.state, result.reason, result.row_version) == ("active", "ok", 1)
    binding = world.tables().bindings[result.binding_id]
    assert (binding.local_locator, binding.observed_head, binding.workspace_id) == (LOCATOR, HEAD, setup.ws)
    [event] = world.events("checkout-bound")
    assert event.payload == {
        "binding_id": str(result.binding_id),
        "host_id": str(setup.host),
        "repository_id": str(setup.repository),
        "state": "active",
    }
    assert LOCATOR not in json.dumps([e.payload for e in world.backend.committed.core.events])


def test_the_trailing_separator_of_the_locator_is_normalized(world, setup) -> None:
    result = setup.bind(local_locator="/home/dev/app/", observed_toplevel="/home/dev/app")
    assert world.tables().bindings[result.binding_id].local_locator == LOCATOR


def test_bind_rejects_observed_remotes_that_are_not_the_repositorys(world, setup) -> None:
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        setup.bind(observed_remotes=("github.com/evil/app",))
    assert caught.value.code is ErrorCode.CHECKOUT_MISMATCH
    assert caught.value.details["reason"] == "remotes"
    with pytest.raises(SkmError) as caught:  # no remote observed at all is no match either
        setup.bind(observed_remotes=())
    assert caught.value.code is ErrorCode.CHECKOUT_MISMATCH
    assert world.snapshot() == before


def test_a_local_repository_accepts_any_observation(world, setup) -> None:
    local = world.repository(setup.ws, title="local", remote=None)
    result = world.run(
        BindCheckout(
            repository_id=local,
            host_id=setup.host,
            local_locator="/srv/local",
            observed_toplevel="/srv/local",
            observed_remotes=(),
            observed_head=None,
            observed_dirty=None,
            observed_at=world.clock.now(),
        )
    )
    assert result.state == "active"


def test_a_second_bind_of_the_same_checkout_is_a_verification_and_another_path_conflicts(
    world, setup
) -> None:
    first = setup.bind()
    world.clock.advance(timedelta(minutes=5))
    again = setup.bind(observed_head="b" * 40)
    assert (again.binding_id, again.row_version) == (first.binding_id, 2)
    assert world.tables().bindings[first.binding_id].observed_head == "b" * 40
    assert len(world.events("checkout-bound")) == 1
    assert len(world.events("checkout-binding-verified")) == 1
    with pytest.raises(SkmError) as caught:
        setup.bind(local_locator="/elsewhere/app", observed_toplevel="/elsewhere/app")
    assert caught.value.code is ErrorCode.ALREADY_EXISTS
    assert caught.value.details["binding_id"] == str(first.binding_id)


def test_a_host_that_is_unknown_or_a_relative_locator_is_refused(world, setup) -> None:
    with pytest.raises(SkmError) as caught:
        setup.bind(host_id=world.ids.new_id())
    assert caught.value.code is ErrorCode.NOT_FOUND
    with pytest.raises(SkmError) as caught:
        setup.bind(local_locator="app")
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_bind_is_decided_on_the_workspace_of_the_repository(world, setup) -> None:
    viewer = world.person("viewer", {setup.ws: Role.VIEWER})
    member = world.person("member", {setup.ws: Role.MEMBER})
    other = world.person("other", {world.workspace("other"): Role.OWNER})
    for refused in (viewer, other):
        with pytest.raises(SkmError) as caught:
            setup.bind(refused)
        assert caught.value.code is ErrorCode.FORBIDDEN
    assert setup.bind(member).state == "active"
    assert [a for a in world.audits() if a.decision == "denied"]  # the denial of the handler is audited


def test_bind_is_refused_in_an_archived_workspace_but_a_verification_is_recorded(world, setup) -> None:
    bound = setup.bind()
    world.run(ArchiveWorkspace(workspace_id=setup.ws, expected_row_version=1, reason="closed"))
    with pytest.raises(SkmError) as caught:
        setup.bind(local_locator="/other", observed_toplevel="/other")
    assert caught.value.code is ErrorCode.PROJECT_ARCHIVED
    moved = setup.verify(bound.binding_id, bound.row_version, observed_toplevel="/moved/app")
    assert moved.state == "mismatched"  # recording what a host saw is not a new admission


def test_verification_follows_the_rules_of_the_domain(world, setup) -> None:
    bound = setup.bind()
    gone = setup.verify(
        bound.binding_id, 1, observed_exists=False, observed_toplevel=None, observed_remotes=()
    )
    assert (gone.state, gone.reason, gone.row_version) == ("missing", "missing", 2)
    moved = setup.verify(bound.binding_id, 2, observed_toplevel="/moved/app")
    assert (moved.state, moved.reason) == ("mismatched", "moved")
    foreign = setup.verify(bound.binding_id, 3, observed_remotes=("github.com/evil/app",))
    assert (foreign.state, foreign.reason) == ("mismatched", "remotes")
    back = setup.verify(bound.binding_id, 4)
    assert (back.state, back.reason, back.row_version) == ("active", "ok", 5)
    assert world.tables().bindings[bound.binding_id].local_locator == LOCATOR  # the locator never moves
    states = [e.payload["state"] for e in world.events("checkout-binding-verified")]
    assert states == ["missing", "mismatched", "mismatched", "active"]


def test_verification_needs_the_current_row_version(world, setup) -> None:
    bound = setup.bind()
    setup.verify(bound.binding_id, 1)
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        setup.verify(bound.binding_id, 1)
    assert caught.value.code is ErrorCode.VERSION_CONFLICT
    assert world.snapshot() == before


def test_a_removed_binding_cannot_be_verified(world, setup) -> None:
    from dataclasses import replace

    from skm.modules.workspace.domain.checkout_binding import BindingState

    bound = setup.bind()
    tables = world.tables()
    tables.bindings[bound.binding_id] = replace(tables.bindings[bound.binding_id], state=BindingState.REMOVED)
    with pytest.raises(SkmError) as caught:
        setup.verify(bound.binding_id, 1)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION


def test_the_locator_is_seen_only_with_checkout_read_locator(world, setup) -> None:
    bound = setup.bind()
    member = world.person("member", {setup.ws: Role.MEMBER})
    viewer = world.person("viewer", {setup.ws: Role.VIEWER})
    query = ListProjectRepositories(project_id=setup.project, host_id=setup.host)
    [seen] = world.ask(query, member).items
    assert (seen.binding.binding_id, seen.binding.local_locator, seen.binding.row_version) == (
        bound.binding_id,
        LOCATOR,
        1,
    )
    [hidden] = world.ask(query, viewer).items
    assert hidden.binding.local_locator is None
    assert LOCATOR not in json.dumps(hidden.to_json())
    [unbound] = world.ask(ListProjectRepositories(project_id=setup.project), member).items
    assert unbound.binding is None  # no host named: no binding listed
    with pytest.raises(SkmError) as caught:  # resolve_checkout names the locator, so it needs the right
        world.ask(ResolveCheckout(project_id=setup.project, mount_name="main", host_id=setup.host), viewer)
    assert caught.value.code is ErrorCode.FORBIDDEN


def test_resolve_checkout_and_its_errors(world, setup) -> None:
    def ask(mount: str = "main"):
        return world.ask(ResolveCheckout(project_id=setup.project, mount_name=mount, host_id=setup.host))

    with pytest.raises(SkmError) as caught:
        ask("nope")
    assert (caught.value.code, caught.value.details["kind"]) == (ErrorCode.NOT_FOUND, "mount")
    with pytest.raises(SkmError) as caught:
        ask()
    assert caught.value.code is ErrorCode.CHECKOUT_UNBOUND
    bound = setup.bind()
    location = ask()
    assert (location.binding_id, location.local_locator, location.state, location.is_stale) == (
        bound.binding_id,
        LOCATOR,
        "active",
        False,
    )
    world.clock.advance(timedelta(days=31))  # workspace.checkout.stale_after_days = 30
    assert ask().is_stale is True
    setup.verify(bound.binding_id, 1, observed_toplevel="/moved/app")
    with pytest.raises(SkmError) as caught:
        ask()
    assert (caught.value.code, caught.value.details["state"]) == (ErrorCode.CHECKOUT_MISMATCH, "mismatched")


def test_bind_is_idempotent_by_key(world, setup) -> None:
    values = {
        "repository_id": setup.repository,
        "host_id": setup.host,
        "local_locator": LOCATOR,
        "observed_toplevel": LOCATOR,
        "observed_remotes": (NORMALIZED,),
        "observed_head": HEAD,
        "observed_dirty": False,
        "observed_at": world.clock.now(),
    }
    first = world.run(BindCheckout(**values), key="k")
    assert world.run(BindCheckout(**values), key="k") == first
    assert len(world.events("checkout-bound")) == 1
