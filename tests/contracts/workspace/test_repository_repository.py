"""RepositoryRepository and MountRepository: one contract over memory and PostgreSQL (workspace §6, §11).

memory ∥ pg: repositories round trip and compare-and-set; ``(workspace, canonical_remote)`` unique; remotes
keep the order the domain gave them, one remote belongs to one repository of a workspace (another workspace
may hold the same remote); ``match_remotes`` finds every candidate of the workspace with its mounted projects
(two candidates are the ambiguity ``match_checkout`` refuses); ``list`` pages ``(created_at, id)`` with
``id_prefix``.
Mounts: unique name, one primary per project, ``remove``, ``projects_of``; attaching a repository of another
workspace is refused before any write. PostgreSQL only: a repository never moves to another workspace.
"""

from dataclasses import replace

import pytest

from contracts.workspace.harness import REMOTE, Side
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import RepositoryId, WorkspaceId
from skm.modules.workspace.domain.mount import MountName, MountRole
from skm.modules.workspace.domain.mount import ProjectRepository as ProjectMount
from skm.modules.workspace.domain.remote_url import NormalizedRemote, RepositoryProvider
from skm.modules.workspace.domain.repository import RepositoryRemote, new_repository
from skm.modules.workspace.ports import MountRepository, RepositoryRepository
from skm.modules.workspace.public import (
    AddRepositoryRemote,
    AttachRepository,
    DetachRepository,
    MatchCheckout,
)

APP = NormalizedRemote("github.com/acme/app")


def test_repositories_round_trip_canonical_remote_unique_per_workspace(side: Side) -> None:
    ws, other = side.workspace("alpha"), side.workspace("beta")
    repo_id = side.repository(ws)
    local = side.repository(ws, title="scratch", remote=None)
    elsewhere = side.repository(other)  # the same remote in another workspace is another repository
    with side.uow() as uow:
        repos = uow.repo(RepositoryRepository)
        stored = repos.get(repo_id)
        assert (stored.workspace_id, stored.canonical_remote, stored.provider) == (
            ws,
            APP,
            RepositoryProvider.GITHUB,
        )
        assert repos.get(local).canonical_remote is None
        assert repos.get(local).provider is RepositoryProvider.NONE
        assert repos.get(elsewhere).workspace_id == other
        clash = new_repository(
            repository_id=RepositoryId(side.ids.new_id()),
            workspace_id=ws,
            title="twin",
            remote_url=REMOTE,
            external_id=None,
            now=side.clock.now(),
        )
        with pytest.raises(Conflict) as taken:
            repos.add(clash)
        assert taken.value.details == {"kind": "repository", "repository_id": str(clash.id)}
        repos.save(replace(stored, title="App", external_id="R_1", row_version=2), expected_version=1)
        uow.commit()
    with side.uow() as uow:
        repos = uow.repo(RepositoryRepository)
        saved = repos.get(repo_id)
        assert (saved.title, saved.external_id, saved.row_version) == ("App", "R_1", 2)
        with pytest.raises(Conflict) as stale:
            repos.save(replace(stored, title="Old", row_version=2), expected_version=1)
        assert stale.value.details == {"kind": "repository", "expected": 1, "actual": 2}
        with pytest.raises(NotFound) as missing:
            repos.get(RepositoryId(side.ids.new_id()))
        assert missing.value.details["kind"] == "repository"
        with pytest.raises(NotFound):
            repos.remotes(RepositoryId(side.ids.new_id()))


def test_remotes_keep_their_order_and_one_primary_through_the_handlers(side: Side) -> None:
    ws = side.workspace("alpha")
    repo_id = side.repository(ws)
    side.run(
        AddRepositoryRemote(repository_id=repo_id, url="git@gitlab.com:acme/app.git", make_primary=False)
    )
    side.run(
        AddRepositoryRemote(
            repository_id=repo_id, url="https://user@code.example/acme/app", make_primary=True
        )
    )
    side.run(
        AddRepositoryRemote(repository_id=repo_id, url="https://github.com/acme/app", make_primary=False)
    )  # no-op
    with side.uow(readonly=True) as uow:
        repos = uow.repo(RepositoryRepository)
        remotes = repos.remotes(repo_id)
        stored = repos.get(repo_id)
    assert [(r.normalized.value, r.display_url, r.is_primary) for r in remotes] == [
        ("github.com/acme/app", REMOTE, False),
        ("gitlab.com/acme/app", "gitlab.com:acme/app.git", False),
        ("code.example/acme/app", "https://code.example/acme/app", True),
    ]
    assert stored.canonical_remote == NormalizedRemote("code.example/acme/app")
    assert stored.provider is RepositoryProvider.OTHER
    assert all(r.repository_id == repo_id for r in remotes)


def test_replace_remotes_refuses_a_remote_of_another_repository_and_bad_sets(side: Side) -> None:
    ws, other = side.workspace("alpha"), side.workspace("beta")
    first = side.repository(ws)
    second = side.repository(ws, title="other", remote="https://github.com/acme/other")
    foreign = side.repository(other, title="other", remote="https://github.com/acme/other")
    taken = RepositoryRemote(second, APP, REMOTE, is_primary=False)
    mine = RepositoryRemote(second, NormalizedRemote("github.com/acme/other"), "x", is_primary=True)
    with side.uow() as uow:
        repos = uow.repo(RepositoryRepository)
        with pytest.raises(Conflict) as caught:
            repos.replace_remotes(second, [mine, taken])
        assert caught.value.details == {"kind": "remote", "repository_id": str(first)}
        for bad in (
            [mine, mine],
            [mine, replace(taken, normalized=NormalizedRemote("a.b/c"), is_primary=True)],
        ):
            with pytest.raises(ValidationFailed) as invalid:
                repos.replace_remotes(second, bad)
            assert invalid.value.details == {"field": "remotes"}
        # the remote of a repository of the other workspace is free here: one remote per workspace
        repos.replace_remotes(
            second, [mine, RepositoryRemote(second, NormalizedRemote("a.b/c"), "a.b:c", False)]
        )
        uow.commit()
    with side.uow(readonly=True) as uow:
        repos = uow.repo(RepositoryRepository)
        assert [r.normalized.value for r in repos.remotes(second)] == ["github.com/acme/other", "a.b/c"]
        assert [r.normalized.value for r in repos.remotes(foreign)] == ["github.com/acme/other"]
        assert [r.normalized.value for r in repos.remotes(first)] == ["github.com/acme/app"]
    with side.uow() as uow:
        uow.repo(RepositoryRepository).replace_remotes(second, [])
        uow.commit()
    with side.uow(readonly=True) as uow:
        assert uow.repo(RepositoryRepository).remotes(second) == ()


def test_match_remotes_finds_every_candidate_of_the_workspace_only(side: Side) -> None:
    ws, other = side.workspace("alpha"), side.workspace("beta")
    app = side.repository(ws)
    fork = side.repository(ws, title="fork", remote="https://github.com/acme/fork")
    side.run(
        AddRepositoryRemote(
            repository_id=fork, url="git@mirror.example:acme/app-mirror.git", make_primary=False
        )
    )
    side.repository(other, title="same", remote=REMOTE)  # never a candidate of ws
    p1, p2 = side.project(ws, "one"), side.project(ws, "two")
    side.run(AttachRepository(project_id=p2, repository_id=app, mount_name="main", role="primary"))
    side.run(AttachRepository(project_id=p1, repository_id=app, mount_name="code", role="secondary"))
    mirror = NormalizedRemote("mirror.example/acme/app-mirror")
    with side.uow(readonly=True) as uow:
        repos = uow.repo(RepositoryRepository)
        single = repos.match_remotes(ws, [APP])
        both = repos.match_remotes(ws, [mirror, APP, NormalizedRemote("nowhere.example/x")])
        assert repos.match_remotes(ws, []) == ()
        assert repos.match_remotes(WorkspaceId(side.ids.new_id()), [APP]) == ()
    assert [(m.repository_id, m.title, m.matched_remotes) for m in single] == [(app, "app", (APP,))]
    assert single[0].project_ids == tuple(sorted((p1, p2), key=str))
    assert sorted(both, key=lambda m: str(m.repository_id)) == list(both)
    assert {m.repository_id: m.matched_remotes for m in both} == {app: (APP,), fork: (mirror,)}
    assert {m.repository_id: m.project_ids for m in both}[fork] == ()


def test_two_candidate_repositories_are_an_ambiguous_selector(side: Side) -> None:
    ws = side.workspace("alpha")
    host = side.host()
    app = side.repository(ws)
    fork = side.repository(ws, title="fork", remote="https://github.com/acme/fork")
    project = side.project(ws, "skm")
    query = MatchCheckout(
        workspace_id=ws,
        host_id=host,
        observed_exists=True,
        observed_toplevel="/work/app",
        observed_remotes=("github.com/acme/app", "github.com/acme/fork"),
        observed_head=None,
        observed_marker=None,
        project_id=project,
        mount_name="main",
        assume_yes=True,
    )
    decision = side.ask(query)
    assert (decision.kind, decision.refuse_code) == ("refuse", "AMBIGUOUS_REFERENCE")
    candidates = {item["repository_id"] for item in decision.refuse_details["candidates"]}
    assert candidates == {str(app), str(fork)}
    single = side.ask(replace(query, observed_remotes=("github.com/acme/fork",)))
    assert (single.kind, single.repository_id) == ("use_existing_repository", fork)


def test_repositories_list_their_workspace_by_creation_then_id_prefix(side: Side) -> None:
    ws, other = side.workspace("alpha"), side.workspace("beta")
    made: list[RepositoryId] = []
    for n in range(5):
        if n % 2 == 0:
            side.tick()  # pairs share created_at: the id breaks the tie
        made.append(side.repository(ws, title=f"r{n}", remote=f"https://github.com/acme/r{n}"))
    side.repository(other, title="hidden", remote="https://github.com/acme/hidden")
    with side.uow(readonly=True) as uow:
        repos = uow.repo(RepositoryRepository)
        seen: list[RepositoryId] = []
        after: str | None = None
        while True:
            page = repos.list(ws, id_prefix=None, after=after, limit=2)
            seen.extend(item.id for item in page.items)
            if page.next is None:
                break
            after = page.next
        expected = sorted(made, key=lambda rid: (repos.get(rid).created_at, str(rid)))
        assert seen == expected
        target = made[3]
        assert [r.id for r in repos.list(ws, id_prefix=target.hex, after=None, limit=10).items] == [target]
        shared = target.hex[:12]  # the test ids share their time prefix: every repository of ws matches
        assert [r.id for r in repos.list(ws, id_prefix=shared, after=None, limit=10).items] == expected
        assert repos.list(ws, id_prefix="f" * 12, after=None, limit=10).items == ()
        assert repos.list(other, id_prefix=target.hex, after=None, limit=10).items == ()


def test_mounts_unique_name_one_primary_remove_and_projects_of(side: Side) -> None:
    ws = side.workspace("alpha")
    app = side.repository(ws)
    docs = side.repository(ws, title="docs", remote="https://github.com/acme/docs")
    infra = side.repository(ws, title="infra", remote=None)
    project, second = side.project(ws, "skm"), side.project(ws, "two")
    side.run(AttachRepository(project_id=project, repository_id=app, mount_name="main", role="primary"))
    side.tick()
    side.run(AttachRepository(project_id=project, repository_id=docs, mount_name="docs", role="docs"))
    side.run(AttachRepository(project_id=second, repository_id=app, mount_name="main", role="primary"))

    def mount(repository: RepositoryId, name: str, role: MountRole) -> ProjectMount:
        return ProjectMount(ws, project, repository, MountName(name), role, side.clock.now())

    with side.uow() as uow:
        mounts = uow.repo(MountRepository)
        for refused in (mount(infra, "main", MountRole.INFRA), mount(infra, "infra", MountRole.PRIMARY)):
            with pytest.raises(Conflict) as caught:
                mounts.add(refused)
            assert caught.value.details["kind"] == "mount"
            assert caught.value.code is ErrorCode.ALREADY_EXISTS
        mounts.add(mount(infra, "infra", MountRole.INFRA))  # still usable after the refusals
        uow.commit()
    with side.uow() as uow:
        mounts = uow.repo(MountRepository)
        assert [(m.mount_name.value, m.role) for m in mounts.for_project(project)] == [
            ("main", MountRole.PRIMARY),
            ("docs", MountRole.DOCS),
            ("infra", MountRole.INFRA),
        ]
        assert mounts.projects_of(app) == tuple(sorted((project, second), key=str))
        assert mounts.projects_of(RepositoryId(side.ids.new_id())) == ()
        removed = mounts.remove(project, MountName("docs"))
        assert removed is not None
        assert (removed.repository_id, removed.role, removed.workspace_id) == (docs, MountRole.DOCS, ws)
        assert mounts.remove(project, MountName("docs")) is None
        uow.commit()
    assert side.run(DetachRepository(project_id=project, mount_name="docs")).removed is False
    assert side.run(DetachRepository(project_id=project, mount_name="main")).removed is True
    side.tick()
    side.run(AttachRepository(project_id=project, repository_id=app, mount_name="core", role="primary"))
    with side.uow(readonly=True) as uow:
        assert [m.mount_name.value for m in uow.repo(MountRepository).for_project(project)] == [
            "infra",
            "core",
        ]
        assert uow.repo(MountRepository).projects_of(docs) == ()


def test_a_repository_of_another_workspace_is_never_attached(side: Side) -> None:
    ws, other = side.workspace("alpha"), side.workspace("beta")
    foreign = side.repository(other)
    project = side.project(ws, "skm")
    before = len(side.events())
    with pytest.raises(PreconditionFailed) as refused:
        side.run(
            AttachRepository(project_id=project, repository_id=foreign, mount_name="main", role="primary")
        )
    assert (refused.value.code, refused.value.details["reason"]) == (
        ErrorCode.CHECKOUT_MISMATCH,
        "other_workspace",
    )
    assert len(side.events()) == before
    with side.uow(readonly=True) as uow:
        assert uow.repo(MountRepository).for_project(project) == ()
        assert uow.repo(MountRepository).projects_of(foreign) == ()


@pytest.mark.pg
def test_save_never_moves_a_repository_to_another_workspace(pg_side: Side) -> None:
    ws, other = pg_side.workspace("alpha"), pg_side.workspace("beta")
    repo_id = pg_side.repository(ws)
    with pg_side.uow() as uow:
        repos = uow.repo(RepositoryRepository)
        stored = repos.get(repo_id)
        with pytest.raises(ValueError, match="keeps its workspace_id"):
            repos.save(replace(stored, workspace_id=other, row_version=2), expected_version=1)
        with pytest.raises(ValueError, match="belong to the repository"):
            repos.replace_remotes(
                repo_id, [RepositoryRemote(RepositoryId(pg_side.ids.new_id()), APP, REMOTE, True)]
            )
    assert pg_side.sql(
        "SELECT r.workspace_id, rr.workspace_id FROM skm_workspace.repositories r "
        "JOIN skm_workspace.repository_remotes rr ON rr.repository_id = r.id WHERE r.id = %s",
        (repo_id,),
    ) == [(ws, ws)]


@pytest.mark.pg
def test_a_repository_cursor_is_bound_to_its_workspace_and_prefix(pg_side: Side) -> None:
    ws, other = pg_side.workspace("alpha"), pg_side.workspace("beta")
    for n in range(3):
        pg_side.repository(ws, title=f"r{n}", remote=f"https://github.com/acme/r{n}")
    with pg_side.uow(readonly=True) as uow:
        repos = uow.repo(RepositoryRepository)
        page = repos.list(ws, id_prefix=None, after=None, limit=1)
        for replay in (
            lambda: repos.list(other, id_prefix=None, after=page.next, limit=5),
            lambda: repos.list(ws, id_prefix="0", after=page.next, limit=5),
        ):
            with pytest.raises(ValidationFailed) as foreign:
                replay()
            assert foreign.value.details["reason"] == "query_mismatch"
