"""Workspace read isolation and archive admission through the real bus on memory and PostgreSQL (§5.4, §8).

WORKSPACE-01: the scope chain ``instance -> workspace -> project`` and the workspace of a project never
change, also across archive. WORKSPACE-03: archiving a workspace keeps its projects' stored states, mounts,
bindings, scopes and history; an *active* project of an archived workspace fails ``require_active_project``
and refuses new attach/bind; historical reads stay available; a repeated archive is a no-op without an event.
Reads are isolated by workspace: a member of one workspace neither lists nor reads the projects, repositories
or workers of another.
"""

import pytest

from contracts.workspace.harness import Side
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed
from skm.kernel.ids import HostId, RepositoryId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.public import Role
from skm.modules.workspace import public
from skm.modules.workspace.domain.checkout_binding import BindingState
from skm.modules.workspace.domain.project import ProjectState
from skm.modules.workspace.ports import CheckoutBindingRepository, MountRepository, ProjectRepository
from skm.modules.workspace.public import (
    ArchiveWorkspace,
    AttachRepository,
    BindCheckout,
    GetProject,
    ListProjectRepositories,
    ListProjects,
    ListRepositories,
    ListWorkers,
    ListWorkspaces,
)

LOCATOR = "/home/dev/app"


def _bind(side: Side, repository: RepositoryId, host: HostId) -> BindCheckout:
    return BindCheckout(
        repository_id=repository,
        host_id=host,
        local_locator=LOCATOR,
        observed_toplevel=LOCATOR,
        observed_remotes=("github.com/acme/app",),
        observed_head=None,
        observed_dirty=None,
        observed_at=side.clock.now(),
    )


def test_archiving_a_workspace_keeps_history_and_closes_new_admissions(side: Side) -> None:
    ws = side.workspace("alpha")
    host = side.host("laptop")
    app = side.repository(ws)
    docs = side.repository(ws, title="docs", remote="https://github.com/acme/docs")
    project = side.project(ws, "skm")
    side.run(AttachRepository(project_id=project, repository_id=app, mount_name="main", role="primary"))
    binding = side.run(_bind(side, app, host)).binding_id
    with side.uow(readonly=True) as uow:
        chain = [(r.kind, r.id) for r in uow.repo(ScopeRegistry).ancestors(ScopeId(project))]
    events_before = side.events()

    archived = side.run(ArchiveWorkspace(workspace_id=ws, expected_row_version=1, reason="closing"))
    assert (archived.state, archived.row_version) == ("archived", 2)
    again = side.run(ArchiveWorkspace(workspace_id=ws, expected_row_version=2, reason="again"))
    assert (again.state, again.row_version) == ("archived", 2)
    assert len(side.events("workspace-archived")) == 1
    assert side.events()[: len(events_before)] == events_before  # history is not rewritten

    with side.uow(readonly=True) as uow:
        stored = uow.repo(ProjectRepository).get(project)
        assert (stored.state, stored.workspace_id, stored.row_version) == (
            ProjectState.ACTIVE,
            ws,
            1,
        )  # no cascade
        assert [(r.kind, r.id) for r in uow.repo(ScopeRegistry).ancestors(ScopeId(project))] == chain
        assert chain[:2] == [(ScopeKind.INSTANCE, chain[0][1]), (ScopeKind.WORKSPACE, ScopeId(ws))]
        assert [m.repository_id for m in uow.repo(MountRepository).for_project(project)] == [app]
        kept = uow.repo(CheckoutBindingRepository).get(binding)
        assert (kept.state, kept.local_locator) == (BindingState.ACTIVE, LOCATOR)
        with pytest.raises(PreconditionFailed) as closed:
            public.require_active_project(uow, project)
        assert (closed.value.code, closed.value.details["kind"]) == (ErrorCode.PROJECT_ARCHIVED, "workspace")
        with pytest.raises(PreconditionFailed):
            public.require_active_workspace(uow, ws)

    for refused in (
        AttachRepository(project_id=project, repository_id=docs, mount_name="docs", role="docs"),
        _bind(side, docs, host),
    ):
        with pytest.raises(PreconditionFailed) as admission:
            side.run(refused)
        assert admission.value.code is ErrorCode.PROJECT_ARCHIVED

    view = side.ask(GetProject(project_id=project))  # historical reads stay available
    assert (view.workspace_id, view.state, [m.repository_id for m in view.mounts]) == (ws, "active", [app])
    mounts = side.ask(ListProjectRepositories(project_id=project, host_id=host))
    assert mounts.items[0].binding.binding_id == binding


def test_a_member_of_one_workspace_reads_nothing_of_another(side: Side) -> None:
    mine, theirs = side.workspace("alpha"), side.workspace("beta")
    host = side.host("laptop")
    side.project(mine, "own")
    hidden_project = side.project(theirs, "secret")
    side.repository(theirs, title="secret", remote="https://github.com/acme/secret")
    side.worker(theirs, host, "their-worker")
    side.person("ann", {ScopeId(mine): Role.MEMBER})

    listed = side.ask(ListWorkspaces(), "ann")
    assert [item.workspace_id for item in listed.items] == [mine]
    assert [item.slug for item in side.ask(ListProjects(workspace_id=mine), "ann").items] == ["own"]
    for denied in (
        ListProjects(workspace_id=theirs),
        ListRepositories(workspace_id=theirs),
        ListWorkers(workspace_id=theirs),
        GetProject(project_id=hidden_project),
        ListProjectRepositories(project_id=hidden_project),
    ):
        with pytest.raises(Forbidden) as caught:
            side.ask(denied, "ann")
        assert caught.value.code is ErrorCode.FORBIDDEN
    assert side.ask(ListRepositories(workspace_id=mine), "ann").items == ()
    assert side.ask(ListWorkers(workspace_id=mine), "ann").items == ()


def test_a_bind_with_foreign_remotes_is_refused_by_the_server(side: Side) -> None:
    ws = side.workspace("alpha")
    host = side.host("laptop")
    app = side.repository(ws)
    foreign = BindCheckout(
        repository_id=app,
        host_id=host,
        local_locator=LOCATOR,
        observed_toplevel=LOCATOR,
        observed_remotes=("github.com/evil/app",),
        observed_head=None,
        observed_dirty=None,
        observed_at=side.clock.now(),
    )
    with pytest.raises(PreconditionFailed) as refused:
        side.run(foreign)
    assert (refused.value.code, refused.value.details["reason"]) == (ErrorCode.CHECKOUT_MISMATCH, "remotes")
    with side.uow(readonly=True) as uow:
        assert uow.repo(CheckoutBindingRepository).find(host, app) is None
    assert side.events("checkout-bound") == []
