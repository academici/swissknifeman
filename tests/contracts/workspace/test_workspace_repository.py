"""WorkspaceRepository and ProjectRepository: one contract over memory and PostgreSQL (workspace §6, §11).

memory ∥ pg: round trip, slug uniqueness (instance-wide for workspaces, per workspace for projects),
``row_version`` compare-and-set, keyset pages ``(slug, id)`` filtered by state and workspace, ``count``.
PostgreSQL only: a cursor is bound to its filter, so the cursor of one workspace is refused for another; a
stored project never changes workspace, slug or creation time through ``save`` (WORKSPACE-01).
"""

from dataclasses import replace

import pytest

from contracts.workspace.harness import Side
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.modules.workspace.domain import project as project_rules
from skm.modules.workspace.domain import workspace as workspace_rules
from skm.modules.workspace.domain.project import Project, ProjectState, new_project
from skm.modules.workspace.domain.slug import Slug
from skm.modules.workspace.domain.workspace import Workspace, WorkspaceState, new_workspace
from skm.modules.workspace.ports import ProjectRepository, WorkspaceRepository
from skm.modules.workspace.public import ArchiveWorkspace


def _workspace(side: Side, slug: str) -> Workspace:
    return new_workspace(
        workspace_id=WorkspaceId(side.ids.new_id()), slug=Slug(slug), title=slug.title(), now=side.clock.now()
    )


def test_workspaces_round_trip_unique_slug_and_compare_and_set(side: Side) -> None:
    made = side.workspace("alpha")
    with side.uow(readonly=True) as uow:
        repo = uow.repo(WorkspaceRepository)
        stored = repo.get(made)
        assert (stored.slug, stored.state, stored.row_version) == (Slug("alpha"), WorkspaceState.ACTIVE, 1)
        assert repo.find_by_slug(Slug("alpha")) == stored
        assert repo.find_by_slug(Slug("nobody")) is None
        with pytest.raises(NotFound) as missing:
            repo.get(WorkspaceId(side.ids.new_id()))
    assert missing.value.details == {"kind": "workspace", "ref": missing.value.details["ref"]}
    with side.uow() as uow:
        repo = uow.repo(WorkspaceRepository)
        with pytest.raises(Conflict) as taken:
            repo.add(_workspace(side, "alpha"))
        assert (taken.value.code, taken.value.details) == (
            ErrorCode.ALREADY_EXISTS,
            {"kind": "workspace", "slug": "alpha"},
        )
        repo.save(workspace_rules.archive(stored), expected_version=1)  # the unit of work is still usable
        uow.commit()
    with side.uow() as uow:
        repo = uow.repo(WorkspaceRepository)
        archived = repo.get(made)
        assert (archived.state, archived.row_version, archived.slug) == (
            WorkspaceState.ARCHIVED,
            2,
            stored.slug,
        )
        with pytest.raises(Conflict) as stale:
            repo.save(replace(stored, title="Again", row_version=2), expected_version=1)
        assert stale.value.code is ErrorCode.VERSION_CONFLICT
        assert stale.value.details == {"kind": "workspace", "expected": 1, "actual": 2}
        with pytest.raises(NotFound):
            repo.save(_workspace(side, "ghost"), expected_version=1)


def test_workspaces_page_by_slug_then_id_and_filter_by_state(side: Side) -> None:
    slugs = ["delta", "alpha", "charlie", "bravo", "echo"]
    made = {slug: side.workspace(slug) for slug in slugs}
    side.run(ArchiveWorkspace(workspace_id=made["charlie"], expected_row_version=1, reason="done"))
    with side.uow(readonly=True) as uow:
        repo = uow.repo(WorkspaceRepository)
        seen: list[str] = []
        after: str | None = None
        while True:
            page = repo.list(state=None, after=after, limit=2)
            seen.extend(item.slug.value for item in page.items)
            if page.next is None:
                break
            after = page.next
        assert seen == sorted(slugs)
        active = repo.list(state=WorkspaceState.ACTIVE, after=None, limit=200).items
        assert [item.slug.value for item in active] == ["alpha", "bravo", "delta", "echo"]
        archived = repo.list(state=WorkspaceState.ARCHIVED, after=None, limit=200).items
        assert [item.id for item in archived] == [made["charlie"]]
        with pytest.raises(ValidationFailed) as bad:
            repo.list(state=None, after="bm90LWEtY3Vyc29y", limit=2)
    assert (bad.value.code, bad.value.details["field"]) == (ErrorCode.SCHEMA_INVALID, "after")


def _project(side: Side, workspace_id: WorkspaceId, slug: str) -> Project:
    return new_project(
        project_id=ProjectId(side.ids.new_id()),
        workspace_id=workspace_id,
        slug=Slug(slug),
        title=slug.title(),
        description="",
        now=side.clock.now(),
    )


def test_projects_round_trip_slug_unique_per_workspace_and_count(side: Side) -> None:
    ws, other = side.workspace("alpha"), side.workspace("beta")
    first = side.project(ws, "app")
    twin = side.project(other, "app")  # the same slug in another workspace is another project
    with side.uow() as uow:
        repo = uow.repo(ProjectRepository)
        stored = repo.get(first)
        assert (stored.workspace_id, stored.slug, stored.state) == (ws, Slug("app"), ProjectState.ACTIVE)
        assert repo.find_by_slug(ws, Slug("app")) == stored
        assert repo.find_by_slug(other, Slug("app")) == repo.get(twin)
        assert repo.find_by_slug(ws, Slug("nope")) is None
        with pytest.raises(Conflict) as taken:
            repo.add(_project(side, ws, "app"))
        assert taken.value.details == {"kind": "project", "slug": "app"}
        repo.save(project_rules.archive(stored), expected_version=1)
        uow.commit()
    side.project(ws, "docs")
    with side.uow(readonly=True) as uow:
        repo = uow.repo(ProjectRepository)
        assert repo.count(ws) == 2  # projects of every state
        assert repo.count(other) == 1
        assert repo.count(WorkspaceId(side.ids.new_id())) == 0
        archived = repo.get(first)
        assert (archived.state, archived.row_version, archived.workspace_id) == (ProjectState.ARCHIVED, 2, ws)
        with pytest.raises(NotFound) as missing:
            repo.get(ProjectId(side.ids.new_id()))
        assert missing.value.details["kind"] == "project"


def test_projects_list_only_their_workspace_by_slug_and_state(side: Side) -> None:
    ws, other = side.workspace("alpha"), side.workspace("beta")
    for slug in ("web", "api", "cli", "docs"):
        side.project(ws, slug)
    side.project(other, "secret")
    with side.uow() as uow:
        repo = uow.repo(ProjectRepository)
        cli = repo.find_by_slug(ws, Slug("cli"))
        assert cli is not None
        repo.save(project_rules.archive(cli), expected_version=1)
        uow.commit()
    with side.uow(readonly=True) as uow:
        repo = uow.repo(ProjectRepository)
        seen: list[str] = []
        after: str | None = None
        while True:
            page = repo.list(ws, state=None, after=after, limit=3)
            seen.extend(item.slug.value for item in page.items)
            if page.next is None:
                break
            after = page.next
        assert seen == ["api", "cli", "docs", "web"]  # nothing of the other workspace
        active = repo.list(ws, state=ProjectState.ACTIVE, after=None, limit=10).items
        assert [item.slug.value for item in active] == ["api", "docs", "web"]
        assert [item.slug.value for item in repo.list(other, state=None, after=None, limit=10).items] == [
            "secret"
        ]


@pytest.mark.pg
def test_a_project_cursor_is_bound_to_its_workspace_and_state(pg_side: Side) -> None:
    ws, other = pg_side.workspace("alpha"), pg_side.workspace("beta")
    for slug in ("a1", "a2", "a3"):
        pg_side.project(ws, slug)
    pg_side.project(other, "b1")
    with pg_side.uow(readonly=True) as uow:
        repo = uow.repo(ProjectRepository)
        first = repo.list(ws, state=None, after=None, limit=1)
        assert first.next is not None
        for replay in (
            lambda: repo.list(other, state=None, after=first.next, limit=10),
            lambda: repo.list(ws, state=ProjectState.ACTIVE, after=first.next, limit=10),
        ):
            with pytest.raises(ValidationFailed) as foreign:
                replay()
            assert foreign.value.details == {"field": "after", "reason": "query_mismatch"}
        assert [p.slug.value for p in repo.list(ws, state=None, after=first.next, limit=10).items] == [
            "a2",
            "a3",
        ]


@pytest.mark.pg
def test_save_never_moves_a_project_or_rewrites_a_workspace_slug(pg_side: Side) -> None:
    ws, other = pg_side.workspace("alpha"), pg_side.workspace("beta")
    project_id = pg_side.project(ws, "app")
    with pg_side.uow() as uow:
        projects, workspaces = uow.repo(ProjectRepository), uow.repo(WorkspaceRepository)
        stored = projects.get(project_id)
        for moved in (
            replace(stored, workspace_id=other, row_version=2),
            replace(stored, slug=Slug("renamed"), row_version=2),
            replace(stored, created_at=stored.created_at.replace(year=2020), row_version=2),
        ):
            with pytest.raises(ValueError, match="keeps its"):
                projects.save(moved, expected_version=1)
        alpha = workspaces.get(ws)
        with pytest.raises(ValueError, match="keeps its slug"):
            workspaces.save(replace(alpha, slug=Slug("gamma"), row_version=2), expected_version=1)
    rows = pg_side.sql(
        "SELECT workspace_id, slug, row_version FROM skm_workspace.projects WHERE id = %s", (project_id,)
    )
    assert rows == [(ws, "app", 1)]
