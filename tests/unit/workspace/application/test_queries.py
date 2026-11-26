"""Workspace queries (workspace §8): visibility, selectors, paging."""

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.access.domain.roles import Role
from skm.modules.workspace.public import (
    GetProject,
    GetWorkspace,
    ListProjects,
    ListRepositories,
    ListWorkspaces,
)


def test_list_workspaces_shows_only_those_where_the_actor_may_read(world) -> None:
    mine, theirs = world.workspace("mine"), world.workspace("theirs")
    viewer = world.person("viewer", {mine: Role.VIEWER})
    assert [w.workspace_id for w in world.ask(ListWorkspaces(), viewer).items] == [mine]
    assert world.person("nobody")
    assert world.ask(ListWorkspaces(), "nobody").items == ()
    assert {w.workspace_id for w in world.ask(ListWorkspaces(), "owner").items} == {mine, theirs}


def test_list_workspaces_pages_by_slug_and_filters_by_state(world) -> None:
    for slug in ("a-ws", "b-ws", "c-ws"):
        world.workspace(slug)
    first = world.ask(ListWorkspaces(limit=2))
    assert [w.slug for w in first.items] == ["a-ws", "b-ws"]
    last = world.ask(ListWorkspaces(limit=2, after=first.next))
    assert [w.slug for w in last.items] == ["c-ws"]
    assert last.next is None
    assert world.ask(ListWorkspaces(state="archived")).items == ()
    with pytest.raises(SkmError) as caught:
        world.ask(ListWorkspaces(after="not-a-cursor"))
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_get_workspace_by_id_or_slug_with_the_project_count(world) -> None:
    ws = world.workspace("team")
    world.project(ws, "one")
    world.project(ws, "two")
    by_id = world.ask(GetWorkspace(workspace_id=ws))
    by_slug = world.ask(GetWorkspace(slug="team"))
    assert by_id == by_slug
    assert by_id.project_count == 2
    for query in (GetWorkspace(), GetWorkspace(workspace_id=ws, slug="team")):
        with pytest.raises(SkmError) as caught:
            world.ask(query)
        assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_a_slug_does_not_reveal_a_workspace_the_actor_cannot_read(world) -> None:
    ws = world.workspace("secret")
    outsider = world.person("outsider")
    with pytest.raises(SkmError) as by_slug:
        world.ask(GetWorkspace(slug="secret"), outsider)
    with pytest.raises(SkmError) as missing:
        world.ask(GetWorkspace(slug="nothing-here"), outsider)
    assert (by_slug.value.code, by_slug.value.details["kind"]) == (ErrorCode.NOT_FOUND, "workspace")
    assert by_slug.value.code is missing.value.code
    assert by_slug.value.message == missing.value.message
    with pytest.raises(SkmError) as by_id:  # an id is not guessable: the honest answer
        world.ask(GetWorkspace(workspace_id=ws), outsider)
    assert by_id.value.code is ErrorCode.FORBIDDEN


def test_get_project_by_slugs_hides_what_the_actor_cannot_read(world) -> None:
    ws = world.workspace("team")
    project = world.project(ws, "app")
    reader = world.person("reader", {ws: Role.VIEWER})
    assert world.ask(GetProject(workspace_slug="team", project_slug="app"), reader).project_id == project
    outsider = world.person("outsider")
    with pytest.raises(SkmError) as caught:
        world.ask(GetProject(workspace_slug="team", project_slug="app"), outsider)
    assert caught.value.code is ErrorCode.NOT_FOUND
    for query in (
        GetProject(),
        GetProject(workspace_slug="team"),
        GetProject(project_id=project, project_slug="app"),
    ):
        with pytest.raises(SkmError) as caught:
            world.ask(query)
        assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_list_projects_pages_and_filters_by_state(world) -> None:
    ws = world.workspace()
    for slug in ("a-pr", "b-pr", "c-pr"):
        world.project(ws, slug)
    first = world.ask(ListProjects(workspace_id=ws, limit=2))
    rest = world.ask(ListProjects(workspace_id=ws, limit=2, after=first.next))
    assert [p.slug for p in first.items + rest.items] == ["a-pr", "b-pr", "c-pr"]
    assert rest.next is None
    assert world.ask(ListProjects(workspace_id=ws, state="archived")).items == ()
    outsider = world.person("outsider")
    with pytest.raises(SkmError) as caught:
        world.ask(ListProjects(workspace_id=ws), outsider)
    assert caught.value.code is ErrorCode.FORBIDDEN


def test_list_repositories_pages_by_creation_and_filters_by_id_prefix(world) -> None:
    ws, other = world.workspace("one"), world.workspace("two")
    ids = [world.repository(ws, title=f"r{n}", remote=f"https://github.com/acme/r{n}") for n in range(3)]
    world.repository(other, title="foreign", remote=None)
    first = world.ask(ListRepositories(workspace_id=ws, limit=2))
    rest = world.ask(ListRepositories(workspace_id=ws, limit=2, after=first.next))
    assert [r.repository_id for r in first.items + rest.items] == ids
    assert rest.next is None
    assert first.items[0].canonical_remote == "github.com/acme/r0"
    found = world.ask(ListRepositories(workspace_id=ws, id_prefix=ids[1].hex))
    assert [r.repository_id for r in found.items] == [ids[1]]
    shared = world.ask(
        ListRepositories(workspace_id=ws, id_prefix=ids[1].hex[:31])
    )  # ids[1], ids[2] share it
    assert [r.repository_id for r in shared.items] == [i for i in ids if i.hex.startswith(ids[1].hex[:31])]
    assert world.ask(ListRepositories(workspace_id=ws, id_prefix="f" * 32)).items == ()
    viewer = world.person("viewer", {ws: Role.VIEWER})
    assert len(world.ask(ListRepositories(workspace_id=ws), viewer).items) == 3
    with pytest.raises(SkmError) as caught:
        world.ask(ListRepositories(workspace_id=ws), world.person("outsider"))
    assert caught.value.code is ErrorCode.FORBIDDEN
