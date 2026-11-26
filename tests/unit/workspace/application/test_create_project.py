"""``workspace.create_project``: the golden slice (workspace §7) through the real bus and memory backend."""

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.domain.roles import Role
from skm.modules.workspace.public import ArchiveWorkspace, CreateProject, GetProject, ListProjectRepositories


def test_creates_the_project_scope_and_the_event(world) -> None:
    ws = world.workspace("personal")
    result = world.run(CreateProject(workspace_id=ws, slug="skm", title="SKM", description="d"))
    assert (result.slug, result.row_version, result.workspace_id) == ("skm", 1, ws)
    with world.uow(readonly=True) as uow:
        scope = uow.repo(ScopeRegistry).get(ScopeId(result.project_id))
    assert (scope.kind, scope.parent_id, scope.workspace_id) == (ScopeKind.PROJECT, ws, ws)
    [event] = world.events("project-created")
    assert (event.stream_kind, event.stream_id, event.workspace_id) == ("project", result.project_id, ws)
    assert event.payload == {
        "project_id": str(result.project_id),
        "workspace_id": str(ws),
        "slug": "skm",
        "title": "SKM",
    }


def test_a_project_without_a_checkout_is_readable(world) -> None:
    ws = world.workspace()
    project = world.project(ws)
    view = world.ask(GetProject(project_id=project))
    assert (view.slug, view.state, view.mounts, view.row_version) == ("skm", "active", (), 1)
    assert world.ask(ListProjectRepositories(project_id=project)).items == ()
    by_slug = world.ask(GetProject(workspace_slug="personal", project_slug="skm"))
    assert by_slug.project_id == project


def test_a_duplicate_slug_conflicts_and_writes_nothing(world) -> None:
    ws = world.workspace()
    world.project(ws)
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        world.run(CreateProject(workspace_id=ws, slug="skm", title="Other"))
    assert caught.value.code is ErrorCode.ALREADY_EXISTS
    assert world.snapshot() == before


def test_the_same_slug_may_live_in_two_workspaces(world) -> None:
    first = world.project(world.workspace("one"))
    second = world.project(world.workspace("two"))
    assert first != second


def test_an_archived_workspace_takes_no_new_project(world) -> None:
    ws = world.workspace()
    world.run(ArchiveWorkspace(workspace_id=ws, expected_row_version=1, reason="closed"))
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        world.run(CreateProject(workspace_id=ws, slug="skm", title="SKM"))
    assert caught.value.code is ErrorCode.PROJECT_ARCHIVED
    assert caught.value.details["kind"] == "workspace"
    assert world.snapshot() == before


def test_the_same_idempotency_key_returns_the_same_result_once(world) -> None:
    ws = world.workspace()
    command = CreateProject(workspace_id=ws, slug="skm", title="SKM")
    first = world.run(command, key="k1")
    assert world.run(command, key="k1") == first
    assert len(world.events("project-created")) == 1


@pytest.mark.parametrize(("role", "allowed"), [(Role.MAINTAINER, True), (Role.VIEWER, False), (None, False)])
def test_only_a_role_with_project_create_may_create(world, role: Role | None, allowed: bool) -> None:
    ws = world.workspace()
    actor = world.person("p", {} if role is None else {ws: role})
    if allowed:
        world.run(CreateProject(workspace_id=ws, slug="skm", title="SKM"), actor)
        return
    with pytest.raises(SkmError) as caught:
        world.run(CreateProject(workspace_id=ws, slug="skm", title="SKM"), actor)
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert world.events("project-created") == []
