"""Memory repositories of the workspace module: the rules PostgreSQL enforces by constraint (§6, §11)."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import RepositoryId, WorkerId
from skm.modules.workspace.domain.mount import MountName, MountRole
from skm.modules.workspace.domain.mount import ProjectRepository as ProjectMount
from skm.modules.workspace.domain.remote_url import NormalizedRemote
from skm.modules.workspace.domain.repository import RepositoryRemote
from skm.modules.workspace.domain.worker import WorkerState
from skm.modules.workspace.ports import (
    HostRepository,
    MountRepository,
    RepositoryRepository,
    WorkerRepository,
    WorkspaceRepository,
)

REMOTE = "https://github.com/acme/app.git"


def test_a_cursor_that_is_not_ours_is_a_validation_error(world) -> None:
    with world.uow(readonly=True) as uow:
        for repo in (uow.repo(WorkspaceRepository), uow.repo(HostRepository)):
            with pytest.raises(SkmError) as caught:
                repo.list(state=None, after="Zm9v", limit=10)  # valid base64, wrong shape
            assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_a_page_limit_out_of_bounds_is_refused(world) -> None:
    with world.uow(readonly=True) as uow, pytest.raises(ValueError, match="page limit"):
        uow.repo(WorkspaceRepository).list(state=None, after=None, limit=0)


def test_a_rolled_back_unit_of_work_leaves_no_row(world) -> None:
    ws = world.workspace()
    repository = world.repository(ws)
    before = world.snapshot()
    with world.uow() as uow:
        uow.repo(RepositoryRepository).replace_remotes(repository, [])
        uow.rollback()
    assert world.snapshot() == before


def test_replace_remotes_refuses_a_remote_of_another_repository_and_two_primaries(world) -> None:
    ws = world.workspace()
    first = world.repository(ws)
    second = world.repository(ws, title="other", remote="https://github.com/acme/other")
    taken = RepositoryRemote(second, NormalizedRemote("github.com/acme/app"), REMOTE, is_primary=True)
    with world.uow() as uow:
        with pytest.raises(SkmError) as caught:
            uow.repo(RepositoryRepository).replace_remotes(second, [taken])
        assert caught.value.code is ErrorCode.ALREADY_EXISTS
        assert caught.value.details["repository_id"] == str(first)
        one = RepositoryRemote(second, NormalizedRemote("github.com/acme/x"), "x", is_primary=True)
        two = RepositoryRemote(second, NormalizedRemote("github.com/acme/y"), "y", is_primary=True)
        with pytest.raises(SkmError) as caught:
            uow.repo(RepositoryRepository).replace_remotes(second, [one, two])
        assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_match_remotes_lists_only_the_workspace_and_the_matched_remotes(world) -> None:
    one, two = world.workspace("one"), world.workspace("two")
    repository = world.repository(one)
    world.repository(two)
    with world.uow(readonly=True) as uow:
        found = uow.repo(RepositoryRepository).match_remotes(
            one, [NormalizedRemote("github.com/acme/app"), NormalizedRemote("github.com/acme/none")]
        )
        assert [(m.repository_id, m.matched_remotes) for m in found] == [
            (repository, (NormalizedRemote("github.com/acme/app"),))
        ]
        assert uow.repo(RepositoryRepository).match_remotes(one, []) == ()


def test_a_mount_name_and_the_primary_role_are_unique_in_a_project(world) -> None:
    ws = world.workspace()
    project, a, b = world.project(ws), world.repository(ws), world.repository(ws, title="b", remote=None)
    now = world.clock.now()

    def mount(repository: RepositoryId, name: str, role: MountRole) -> ProjectMount:
        return ProjectMount(ws, project, repository, MountName(name), role, now)

    with world.uow() as uow:
        mounts = uow.repo(MountRepository)
        mounts.add(mount(a, "main", MountRole.PRIMARY))
        for clash in (mount(b, "main", MountRole.DOCS), mount(b, "other", MountRole.PRIMARY)):
            with pytest.raises(SkmError) as caught:
                mounts.add(clash)
            assert caught.value.code is ErrorCode.ALREADY_EXISTS
        mounts.add(mount(b, "docs", MountRole.DOCS))
        assert mounts.projects_of(a) == (project,)
        assert [m.mount_name.value for m in mounts.for_project(project)] == [
            "docs",
            "main",
        ]  # same attach time: by name
        assert mounts.remove(project, MountName("nope")) is None


def test_a_worker_row_is_unique_per_principal_and_versions_are_checked(world) -> None:
    ws = world.workspace()
    host = world.host()
    actor, worker_id = world.worker(ws, host)
    with world.uow() as uow:
        workers = uow.repo(WorkerRepository)
        row = workers.get(worker_id)
        with pytest.raises(SkmError) as caught:
            workers.add(replace(row, id=WorkerId(uuid4())))  # the same principal again
        assert caught.value.code is ErrorCode.ALREADY_EXISTS
        with pytest.raises(SkmError) as caught:
            workers.save(row, expected_version=9)
        assert caught.value.code is ErrorCode.VERSION_CONFLICT
        assert workers.for_principal(actor.principal_id) == row


def test_the_sweeper_marks_only_live_overdue_workers(world) -> None:
    ws = world.workspace()
    host = world.host()
    _, online = world.worker(ws, host, "a", state="online")
    _, retired = world.worker(ws, host, "b", state="retired")
    cutoff = world.clock.now() + timedelta(seconds=1)
    with world.uow() as uow:
        workers = uow.repo(WorkerRepository)
        assert [w.id for w in workers.overdue(cutoff)] == [online]
        assert workers.mark_offline_older_than(cutoff) == (online,)
        assert workers.get(online).state is WorkerState.OFFLINE
        assert workers.get(retired).state is WorkerState.RETIRED
        assert workers.mark_offline_older_than(cutoff) == ()
