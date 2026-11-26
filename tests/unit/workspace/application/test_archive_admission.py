"""Archive protocol (workspace §5.4, WORKSPACE-03): new admissions close, data and history stay.

``archive`` moves ``active -> archived`` and nothing else: no row is deleted, no stored state of a child is
rewritten, the history stays readable under the ordinary RBAC, and the admission points
(``require_active_project`` / ``require_active_workspace``) read the current states, so a project is closed
by its own archive *or* by the archive of its workspace. Cleanup and recording handlers are not admissions.
"""

from datetime import timedelta

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeRegistry
from skm.modules.access.domain.roles import Role
from skm.modules.access.ports import MembershipRepository
from skm.modules.workspace import public
from skm.modules.workspace.public import (
    AddRepositoryRemote,
    ArchiveProject,
    ArchiveWorkspace,
    AttachRepository,
    BindCheckout,
    CreateProject,
    DetachRepository,
    GetProject,
    GetWorkspace,
    ListProjectRepositories,
    ListProjects,
    ListWorkspaces,
    RecordCheckoutVerification,
    RegisterRepository,
)

REMOTE = "https://github.com/acme/app.git"
NORMALIZED = "github.com/acme/app"
LOCATOR = "/home/dev/app"


class Setup:
    """A workspace, two projects (one mounted with a bound checkout), a viewer and an outsider."""

    def __init__(self, world) -> None:
        self.world = world
        self.ws = world.workspace()
        self.project = world.project(self.ws, "one")
        self.quiet = world.project(self.ws, "two")
        self.repository = world.repository(self.ws)
        self.host = world.host()
        world.run(AttachRepository(project_id=self.project, repository_id=self.repository))
        self.binding = world.run(
            BindCheckout(
                repository_id=self.repository,
                host_id=self.host,
                local_locator=LOCATOR,
                observed_toplevel=LOCATOR,
                observed_remotes=(NORMALIZED,),
                observed_head=None,
                observed_dirty=None,
                observed_at=world.clock.now(),
            )
        )
        self.viewer = world.person("viewer", {self.ws: Role.VIEWER})
        self.outsider = world.person("outsider")

    def archive_project(self, project=None, version: int = 1, **kwargs):
        return self.world.run(
            ArchiveProject(project_id=project or self.project, expected_row_version=version, reason="done"),
            **kwargs,
        )

    def archive_workspace(self, version: int = 1, **kwargs):
        return self.world.run(
            ArchiveWorkspace(workspace_id=self.ws, expected_row_version=version, reason="closed"), **kwargs
        )

    def admitted(self, fn) -> SkmError:
        """``fn`` must be refused as a closed area; nothing may be written."""
        before = self.world.snapshot()
        with pytest.raises(SkmError) as caught:
            fn()
        assert caught.value.code is ErrorCode.PROJECT_ARCHIVED
        assert self.world.snapshot() == before
        return caught.value


@pytest.fixture
def setup(world) -> Setup:
    return Setup(world)


def test_archiving_a_project_keeps_every_row_and_records_one_event(world, setup) -> None:
    before = world.tables()
    kept = (dict(before.mounts), dict(before.bindings), dict(before.repositories))
    result = setup.archive_project()
    assert (result.state, result.row_version) == ("archived", 2)
    [event] = world.events("project-archived")
    assert event.payload == {
        "project_id": str(setup.project),
        "workspace_id": str(setup.ws),
        "reason": "done",
    }
    after = world.tables()
    assert (dict(after.mounts), dict(after.bindings), dict(after.repositories)) == kept
    assert after.projects[setup.project].title == "SKM"  # the row is kept, only the state moved
    with world.uow(readonly=True) as uow:
        assert uow.repo(ScopeRegistry).get(ScopeId(setup.project)).parent_id == setup.ws  # the scope stays
        assert uow.repo(MembershipRepository).get(ScopeId(setup.ws), setup.viewer.principal_id) is not None


def test_a_repeated_archive_is_a_no_op_without_a_second_event(world, setup) -> None:
    setup.archive_project()
    again = setup.archive_project(version=2)
    assert (again.state, again.row_version) == ("archived", 2)
    assert len(world.events("project-archived")) == 1
    with pytest.raises(SkmError) as caught:  # an old version is still a version conflict
        setup.archive_project(version=1)
    assert caught.value.code is ErrorCode.VERSION_CONFLICT
    key = world.run(ArchiveProject(project_id=setup.quiet, expected_row_version=1, reason="x"), key="k")
    assert (
        world.run(ArchiveProject(project_id=setup.quiet, expected_row_version=1, reason="x"), key="k") == key
    )
    assert len(world.events("project-archived")) == 2


def test_an_archived_project_takes_no_new_attach_and_no_facade_admission(world, setup) -> None:
    setup.archive_project()
    docs = world.repository(setup.ws, title="docs", remote=None)
    error = setup.admitted(
        lambda: world.run(
            AttachRepository(project_id=setup.project, repository_id=docs, mount_name="docs", role="docs")
        )
    )
    assert error.details["kind"] == "project"
    with world.uow(readonly=True) as uow:
        with pytest.raises(SkmError) as caught:
            public.require_active_project(uow, setup.project)
        assert (caught.value.code, caught.value.details["kind"]) == (ErrorCode.PROJECT_ARCHIVED, "project")
        public.require_active_project(uow, setup.quiet)  # the sibling project is open
    world.run(AttachRepository(project_id=setup.quiet, repository_id=docs))


def test_archiving_the_workspace_closes_its_projects_without_rewriting_them(world, setup) -> None:
    projects = dict(world.tables().projects)
    result = setup.archive_workspace()
    assert (result.state, result.row_version) == ("archived", 2)
    assert dict(world.tables().projects) == projects  # no cascade of stored states
    assert {p.state.value for p in world.tables().projects.values()} == {"active"}
    with world.uow(readonly=True) as uow:
        for project in (setup.project, setup.quiet):
            with pytest.raises(SkmError) as caught:
                public.require_active_project(uow, project)  # closed through the workspace ancestor
            assert (caught.value.code, caught.value.details["kind"]) == (
                ErrorCode.PROJECT_ARCHIVED,
                "workspace",
            )
        with pytest.raises(SkmError) as caught:
            public.require_active_workspace(uow, setup.ws)
        assert caught.value.code is ErrorCode.PROJECT_ARCHIVED
    [event] = world.events("workspace-archived")
    assert event.payload == {"workspace_id": str(setup.ws), "reason": "closed"}


def test_new_create_attach_register_and_bind_are_refused_in_an_archived_workspace(world, setup) -> None:
    setup.archive_workspace()
    docs_id = world.ids.new_id()
    bind = BindCheckout(
        repository_id=setup.repository,
        host_id=setup.host,
        local_locator="/other",
        observed_toplevel="/other",
        observed_remotes=(NORMALIZED,),
        observed_head=None,
        observed_dirty=None,
        observed_at=world.clock.now(),
    )
    for operation in (
        lambda: world.run(CreateProject(workspace_id=setup.ws, slug="late", title="Late")),
        lambda: world.run(
            RegisterRepository(workspace_id=setup.ws, title="x", remote_url=None, external_id=None)
        ),
        lambda: world.run(AttachRepository(project_id=setup.quiet, repository_id=setup.repository)),
        lambda: world.run(
            AddRepositoryRemote(repository_id=setup.repository, url="https://gitlab.com/acme/app")
        ),
        lambda: world.run(bind),
    ):
        setup.admitted(operation)
    del docs_id


def test_cleanup_and_recording_are_not_admissions(world, setup) -> None:
    setup.archive_workspace()
    moved = world.run(
        RecordCheckoutVerification(
            binding_id=setup.binding.binding_id,
            expected_row_version=1,
            observed_exists=True,
            observed_toplevel="/moved",
            observed_remotes=(NORMALIZED,),
            observed_head=None,
            observed_dirty=None,
            observed_at=world.clock.now(),
        )
    )
    assert moved.state == "mismatched"
    assert world.run(DetachRepository(project_id=setup.project, mount_name="main")).removed is True
    assert world.tables().bindings[setup.binding.binding_id].local_locator == LOCATOR  # bindings are kept


def test_history_stays_readable_under_the_ordinary_rbac(world, setup) -> None:
    setup.archive_project()
    setup.archive_workspace()
    view = world.ask(GetProject(project_id=setup.project), setup.viewer)
    assert (view.state, [m.mount_name for m in view.mounts]) == ("archived", ["main"])
    assert [
        i.mount_name for i in world.ask(ListProjectRepositories(project_id=setup.project), setup.viewer).items
    ] == ["main"]
    assert world.ask(GetWorkspace(workspace_id=setup.ws), setup.viewer).state == "archived"
    assert {p.slug for p in world.ask(ListProjects(workspace_id=setup.ws), setup.viewer).items} == {
        "one",
        "two",
    }
    archived = world.ask(ListWorkspaces(state="archived"), setup.viewer)
    assert [w.workspace_id for w in archived.items] == [setup.ws]
    for query in (GetProject(project_id=setup.project), ListProjects(workspace_id=setup.ws)):
        with pytest.raises(SkmError) as caught:
            world.ask(query, setup.outsider)  # archive grants nothing to a stranger
        assert caught.value.code is ErrorCode.FORBIDDEN


def test_archive_needs_the_manage_right_and_is_final(world, setup) -> None:
    member = world.person("member", {setup.ws: Role.MEMBER})
    for operation in (
        lambda: setup.archive_workspace(actor=member),
        lambda: setup.archive_project(actor=member),
    ):
        before = world.snapshot()
        with pytest.raises(SkmError) as caught:
            operation()
        assert caught.value.code is ErrorCode.FORBIDDEN
        assert world.snapshot() == before
    setup.archive_workspace()
    again = setup.archive_workspace(version=2)
    assert (again.state, again.row_version) == ("archived", 2)
    assert len(world.events("workspace-archived")) == 1
    world.clock.advance(timedelta(days=400))
    assert world.tables().workspaces[setup.ws].state.value == "archived"  # no restore, no expiry in v2.0
