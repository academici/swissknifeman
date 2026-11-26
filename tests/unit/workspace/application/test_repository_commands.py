"""Repository commands (workspace §7): register, add a remote, attach to a project, detach."""

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.access.domain.roles import Role
from skm.modules.workspace.public import (
    AddRepositoryRemote,
    AttachRepository,
    DetachRepository,
    GetProject,
    RegisterRepository,
)

REMOTE = "https://github.com/acme/app.git"
NORMALIZED = "github.com/acme/app"


def register(world, ws, **fields):
    values = {"title": "app", "remote_url": REMOTE, "external_id": None, **fields}
    return world.run(RegisterRepository(workspace_id=ws, **values))


def test_register_normalizes_the_remote_and_records_the_event(world) -> None:
    ws = world.workspace()
    result = register(world, ws, remote_url="git@GitHub.com:acme/app.git")
    assert (result.canonical_remote, result.provider) == (NORMALIZED, "github")
    [event] = world.events("repository-registered")
    assert event.payload["canonical_remote"] == NORMALIZED
    assert event.payload["provider"] == "github"
    [remote] = world.tables().remotes[result.repository_id]
    assert (remote.normalized.value, remote.is_primary, remote.display_url) == (
        NORMALIZED,
        True,
        "GitHub.com:acme/app.git",  # the user info is redacted for display, the case is kept
    )


def test_a_local_repository_has_no_remote(world) -> None:
    ws = world.workspace()
    result = register(world, ws, remote_url=None)
    assert (result.canonical_remote, result.provider) == (None, "none")
    assert world.tables().remotes[result.repository_id] == ()


def test_the_same_remote_in_one_workspace_conflicts_and_names_the_holder(world) -> None:
    ws = world.workspace()
    first = register(world, ws)
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        register(world, ws, title="again", remote_url="ssh://git@github.com/acme/app")
    assert caught.value.code is ErrorCode.ALREADY_EXISTS
    assert caught.value.details["repository_id"] == str(first.repository_id)
    assert world.snapshot() == before


def test_the_same_remote_may_live_in_two_workspaces(world) -> None:
    assert (
        register(world, world.workspace("one")).repository_id
        != register(world, world.workspace("two")).repository_id
    )


def test_a_url_that_is_not_a_network_remote_is_refused(world) -> None:
    ws = world.workspace()
    with pytest.raises(SkmError) as caught:
        register(world, ws, remote_url="/srv/git/app")
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["reason"] == "not_a_network_remote"
    assert world.events("repository-registered") == []


def test_add_remote_keeps_one_primary_and_a_duplicate_is_a_no_op(world) -> None:
    ws = world.workspace()
    repository = register(world, ws).repository_id
    second = world.run(AddRepositoryRemote(repository_id=repository, url="https://gitlab.com/acme/app.git"))
    assert [(r.normalized, r.is_primary) for r in second.remotes] == [
        (NORMALIZED, True),
        ("gitlab.com/acme/app", False),
    ]
    switched = world.run(
        AddRepositoryRemote(repository_id=repository, url="https://bitbucket.org/acme/app", make_primary=True)
    )
    assert [r.is_primary for r in switched.remotes] == [False, False, True]
    assert world.tables().repositories[repository].canonical_remote.value == "bitbucket.org/acme/app"
    assert world.tables().repositories[repository].provider.value == "bitbucket"
    version = world.tables().repositories[repository].row_version
    world.run(AddRepositoryRemote(repository_id=repository, url=REMOTE))  # already a remote: nothing changes
    assert world.tables().repositories[repository].row_version == version


def test_a_remote_of_another_repository_conflicts(world) -> None:
    ws = world.workspace()
    register(world, ws)
    other = register(world, ws, title="other", remote_url="https://github.com/acme/other").repository_id
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        world.run(AddRepositoryRemote(repository_id=other, url=REMOTE))
    assert caught.value.code is ErrorCode.ALREADY_EXISTS
    assert world.snapshot() == before


def test_add_remote_is_decided_on_the_workspace_of_the_repository(world) -> None:
    one, two = world.workspace("one"), world.workspace("two")
    repository = register(world, one).repository_id
    maintainer = world.person("maintainer", {one: Role.MAINTAINER})
    viewer = world.person("viewer", {one: Role.VIEWER})
    elsewhere = world.person("elsewhere", {two: Role.OWNER})
    command = AddRepositoryRemote(repository_id=repository, url="https://gitlab.com/acme/app")
    for refused in (viewer, elsewhere):
        with pytest.raises(SkmError) as caught:
            world.run(command, refused)
        assert caught.value.code is ErrorCode.FORBIDDEN
    assert len(world.run(command, maintainer).remotes) == 2


def test_attach_mounts_the_repository_and_records_the_event(world) -> None:
    ws = world.workspace()
    project, repository = world.project(ws), register(world, ws).repository_id
    result = world.run(AttachRepository(project_id=project, repository_id=repository))
    assert (result.mount_name, result.repository_id) == ("main", repository)
    [event] = world.events("repository-attached")
    assert (event.stream_kind, event.stream_id) == ("project", project)
    assert event.payload == {
        "project_id": str(project),
        "repository_id": str(repository),
        "mount_name": "main",
        "role": "primary",
    }
    view = world.ask(GetProject(project_id=project))
    assert [(m.mount_name, m.role, m.canonical_remote) for m in view.mounts] == [
        ("main", "primary", NORMALIZED)
    ]


def test_attach_refuses_a_second_mount_name_a_second_primary_and_a_foreign_repository(world) -> None:
    one, two = world.workspace("one"), world.workspace("two")
    project, repository = world.project(one), register(world, one).repository_id
    docs = register(world, one, title="docs", remote_url=None).repository_id
    foreign = register(world, two).repository_id
    world.run(AttachRepository(project_id=project, repository_id=repository))
    before = world.snapshot()
    cases = [
        (AttachRepository(project_id=project, repository_id=docs), ErrorCode.ALREADY_EXISTS),  # name main
        (
            AttachRepository(project_id=project, repository_id=docs, mount_name="docs"),
            ErrorCode.INVALID_TRANSITION,
        ),
        (
            AttachRepository(project_id=project, repository_id=foreign, mount_name="x", role="docs"),
            ErrorCode.CHECKOUT_MISMATCH,
        ),
    ]
    for command, code in cases:
        with pytest.raises(SkmError) as caught:
            world.run(command)
        assert caught.value.code is code
    assert world.snapshot() == before
    world.run(AttachRepository(project_id=project, repository_id=docs, mount_name="docs", role="docs"))


def test_detach_removes_once_and_records_one_event(world) -> None:
    ws = world.workspace()
    project, repository = world.project(ws), register(world, ws).repository_id
    world.run(AttachRepository(project_id=project, repository_id=repository))
    first = world.run(DetachRepository(project_id=project, mount_name="main"))
    again = world.run(DetachRepository(project_id=project, mount_name="main"))
    assert (first.removed, again.removed) == (True, False)
    [event] = world.events("repository-detached")
    assert event.payload["repository_id"] == str(repository)
    assert world.tables().repositories[repository]  # the repository itself stays


def test_attach_and_detach_need_project_manage(world) -> None:
    ws = world.workspace()
    project, repository = world.project(ws), register(world, ws).repository_id
    member = world.person("member", {ws: Role.VIEWER})
    for command in (
        AttachRepository(project_id=project, repository_id=repository),
        DetachRepository(project_id=project, mount_name="main"),
    ):
        with pytest.raises(SkmError) as caught:
            world.run(command, member)
        assert caught.value.code is ErrorCode.FORBIDDEN


def test_attach_is_idempotent_by_key(world) -> None:
    ws = world.workspace()
    project, repository = world.project(ws), register(world, ws).repository_id
    command = AttachRepository(project_id=project, repository_id=repository)
    first = world.run(command, key="k")
    assert world.run(command, key="k") == first
    assert len(world.events("repository-attached")) == 1
