"""``workspace.match_checkout`` (workspace §5.2, §8): every branch of the decision, read-only."""

from uuid import uuid4

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.access.domain.roles import Role
from skm.modules.workspace.public import AttachRepository, MatchCheckout

REMOTE = "https://github.com/acme/app.git"
NORMALIZED = "github.com/acme/app"
OTHER = "github.com/acme/other"
TOP = "/home/dev/app"


class Setup:
    def __init__(self, world) -> None:
        self.world = world
        self.ws = world.workspace()
        self.project = world.project(self.ws, "one")
        self.second = world.project(self.ws, "two")
        self.repository = world.repository(self.ws)
        self.host = world.host()
        world.run(AttachRepository(project_id=self.project, repository_id=self.repository))

    def marker(self, **fields):
        values = {
            "schema": "urn:skm:workspace:checkout-marker:v1",
            "instance_id": str(self.world.instance),
            "workspace_id": str(self.ws),
            "project_id": str(self.project),
            "repository_id": str(self.repository),
            "mount_name": "main",
            **fields,
        }
        return values

    def match(self, actor="owner", **fields):
        values = {
            "workspace_id": self.ws,
            "host_id": self.host,
            "observed_exists": True,
            "observed_toplevel": TOP,
            "observed_remotes": (),
            "observed_head": None,
            "observed_marker": None,
            **fields,
        }
        before = self.world.snapshot()
        view = self.world.ask(MatchCheckout(**values), actor)
        assert self.world.snapshot() == before  # a query writes nothing
        return view


@pytest.fixture
def setup(world) -> Setup:
    return Setup(world)


@pytest.mark.parametrize("fields", [{"observed_exists": False}, {"observed_toplevel": None}])
def test_row_1_not_a_git_checkout_is_refused(setup, fields) -> None:
    view = setup.match(observed_remotes=(NORMALIZED,), **fields)
    assert (view.kind, view.refuse_code, view.refuse_details) == (
        "refuse",
        "CHECKOUT_MISMATCH",
        {"reason": "not_a_git_checkout"},
    )


def test_row_4_a_marker_with_an_existing_target_is_used(setup) -> None:
    view = setup.match(observed_marker=setup.marker())
    assert (view.kind, view.project_id, view.repository_id, view.mount_name, view.needs_confirmation) == (
        "use_marker",
        setup.project,
        setup.repository,
        "main",
        False,
    )
    assert view.diagnostics == ()


def test_row_4_an_explicit_project_other_than_the_markers_is_refused(setup) -> None:
    view = setup.match(observed_marker=setup.marker(), project_id=setup.second)
    assert (view.kind, view.refuse_code, view.refuse_details) == (
        "refuse",
        "CHECKOUT_MISMATCH",
        {"reason": "marker_other_project"},
    )


def test_row_3_a_marker_of_another_workspace_is_refused(setup) -> None:
    view = setup.match(observed_marker=setup.marker(workspace_id=str(uuid4())))
    assert (view.kind, view.refuse_details) == ("refuse", {"reason": "marker_other_workspace"})


def test_row_2_a_marker_of_another_instance_is_ignored_with_a_diagnostic(setup) -> None:
    view = setup.match(observed_marker=setup.marker(instance_id=str(uuid4())), observed_remotes=(NORMALIZED,))
    assert [d["code"] for d in view.diagnostics] == ["MARKER_FOREIGN_INSTANCE"]
    assert (view.kind, view.repository_id) == (
        "use_existing_repository",
        setup.repository,
    )  # went on to remotes


def test_row_4a_a_marker_whose_target_is_gone_is_stale(setup) -> None:
    view = setup.match(
        observed_marker=setup.marker(repository_id=str(uuid4())), observed_remotes=(NORMALIZED,)
    )
    assert [d["code"] for d in view.diagnostics] == ["MARKER_STALE"]
    assert view.kind == "use_existing_repository"


def test_row_4a_a_marker_naming_a_project_of_another_workspace_is_stale(world, setup) -> None:
    foreign = world.project(world.workspace("elsewhere"), "foreign")
    view = setup.match(observed_marker=setup.marker(project_id=str(foreign)), observed_remotes=(NORMALIZED,))
    assert [d["code"] for d in view.diagnostics] == ["MARKER_STALE"]


def test_row_5_remotes_matching_several_repositories_are_ambiguous(world, setup) -> None:
    world.repository(setup.ws, title="other", remote="https://github.com/acme/other")
    view = setup.match(observed_remotes=(NORMALIZED, OTHER))
    assert (view.kind, view.refuse_code) == ("refuse", "AMBIGUOUS_REFERENCE")
    assert len(view.refuse_details["candidates"]) == 2


def test_row_6_one_repository_needs_confirmation_unless_the_project_is_named(setup) -> None:
    asked = setup.match(observed_remotes=(NORMALIZED,))
    assert (asked.kind, asked.repository_id, asked.project_id, asked.needs_confirmation) == (
        "use_existing_repository",
        setup.repository,
        setup.project,  # the one project the repository is already mounted in
        True,
    )
    assert setup.match(observed_remotes=(NORMALIZED,), assume_yes=True).needs_confirmation is False
    named = setup.match(observed_remotes=(NORMALIZED,), project_id=setup.second)
    assert (named.project_id, named.needs_confirmation) == (setup.second, False)


def test_row_7_no_repository_needs_a_project_and_then_creates_one(setup) -> None:
    refused = setup.match(observed_remotes=("github.com/acme/new",))
    assert (refused.kind, refused.refuse_code, refused.refuse_details) == (
        "refuse",
        "SCHEMA_INVALID",
        {"reason": "project_required"},
    )
    created = setup.match(
        observed_remotes=("github.com/acme/new",), project_id=setup.second, mount_name="docs"
    )
    assert (created.kind, created.canonical_remote, created.project_id, created.mount_name) == (
        "create_repository",
        "github.com/acme/new",
        setup.second,
        "docs",
    )
    local = setup.match(project_id=setup.second)
    assert (local.kind, local.canonical_remote) == ("create_repository", None)


def test_match_needs_checkout_bind_and_known_references(world, setup) -> None:
    viewer = world.person("viewer", {setup.ws: Role.VIEWER})
    with pytest.raises(SkmError) as caught:
        setup.match(viewer)
    assert caught.value.code is ErrorCode.FORBIDDEN
    member = world.person("member", {setup.ws: Role.MEMBER})
    assert setup.match(member, observed_remotes=(NORMALIZED,)).kind == "use_existing_repository"
    foreign = world.project(world.workspace("elsewhere"), "foreign")
    with pytest.raises(SkmError) as caught:
        setup.match(project_id=foreign)
    assert caught.value.code is ErrorCode.NOT_FOUND
    with pytest.raises(SkmError) as caught:
        setup.match(host_id=uuid4())
    assert caught.value.code is ErrorCode.NOT_FOUND
