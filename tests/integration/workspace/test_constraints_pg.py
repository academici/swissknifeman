"""``skm_workspace`` DDL 0007 on a live server: composite workspace FKs, unique mounts, remotes and bindings.

The database must refuse even a writer that bypasses the adapters, so the constraints are exercised with raw
SQL as the owner on the session database (``support.pg``), and through the PostgreSQL adapters, which turn the
same refusals into the errors of the memory adapter (workspace §6, §11, §15):

* a mount, remote or binding of a repository of another workspace fails the composite FK;
* a second primary mount, a taken mount name and the same repository mounted twice in one project are unique
  violations; through ``PostgresMountRepository`` they are ``ALREADY_EXISTS`` and the transaction goes on;
* one remote per workspace, one primary remote per repository, one canonical remote per workspace;
* one live binding per ``(host, repository)``; a removed one frees the pair; the locator and HEAD checks;
* one worker per principal;
* the runtime role ``skm_app`` works through the adapters and cannot switch the constraints off.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import errors as pgerr

from skm.adapters.postgres.access.repositories import PostgresPrincipalRepository
from skm.adapters.postgres.workspace.bindings import PostgresCheckoutBindingRepository
from skm.adapters.postgres.workspace.mounts import PostgresMountRepository
from skm.adapters.postgres.workspace.projects import PostgresProjectRepository
from skm.adapters.postgres.workspace.workspaces import PostgresWorkspaceRepository
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, SkmError
from skm.kernel.ids import HostId, PrincipalId, ProjectId, RepositoryId, WorkspaceId
from skm.modules.access.domain.principal import new_principal
from skm.modules.workspace.domain.checkout_binding import BindingState, CheckoutBinding, CheckoutBindingId
from skm.modules.workspace.domain.mount import MountName, MountRole
from skm.modules.workspace.domain.mount import ProjectRepository as ProjectMount
from skm.modules.workspace.domain.project import archive as archive_project
from skm.modules.workspace.domain.slug import Slug
from skm.modules.workspace.domain.workspace import new_workspace
from support.pg import TestDatabase, clean_test_database, pg_session, test_database  # noqa: F401
from support.seed import SEED

pytestmark = pytest.mark.pg

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
_CAPABILITIES = (
    '{"runtimes": [], "isolation_profiles": ["worktree"], "max_concurrency": 1, "labels": [], '
    '"platform": {"os": "linux", "arch": "x86_64"}, "skm_version": "2.0.0"}'
)


@dataclass
class Tree:
    """Two workspaces (A, B) with a project and a repository each, and one host."""

    conn: psycopg.Connection
    ws_a: UUID
    ws_b: UUID
    project_a: UUID
    project_b: UUID
    repo_a: UUID
    repo_b: UUID
    host: UUID

    def run(self, statement: LiteralString, params: tuple[Any, ...]) -> None:
        self.conn.execute(statement, params)


_SCOPE = "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) VALUES (%s, %s, %s, %s)"
_WORKSPACE = (
    "INSERT INTO skm_workspace.workspaces (id, slug, title, created_at, updated_at) "
    "VALUES (%s, %s, 'W', %s, %s)"
)
_PROJECT = (
    "INSERT INTO skm_workspace.projects (id, workspace_id, slug, title, created_at, updated_at) "
    "VALUES (%s, %s, %s, 'P', %s, %s)"
)
_REPOSITORY = (
    "INSERT INTO skm_workspace.repositories "
    "(id, workspace_id, title, canonical_remote, provider, created_at, updated_at) "
    "VALUES (%s, %s, 'R', %s, %s, %s, %s)"
)
_REMOTE = (
    "INSERT INTO skm_workspace.repository_remotes "
    "(workspace_id, repository_id, normalized_url, display_url, is_primary, added_at) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)
_MOUNT = (
    "INSERT INTO skm_workspace.project_repositories "
    "(workspace_id, project_id, repository_id, mount_name, role, attached_at) VALUES (%s, %s, %s, %s, %s, %s)"
)
_BINDING = (
    "INSERT INTO skm_workspace.checkout_bindings "
    "(id, workspace_id, host_id, repository_id, local_locator, state, observed_head, last_verified_at, "
    "created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_WORKER = (
    "INSERT INTO skm_workspace.workers "
    "(id, workspace_id, host_id, principal_id, display_name, capabilities, registered_at) "
    "VALUES (%s, %s, %s, %s, 'w', %s::jsonb, %s)"
)


@pytest.fixture
def tree(clean_test_database: TestDatabase) -> Iterator[Tree]:  # noqa: F811 - the imported fixture
    ws_a, ws_b = UUID(int=SEED.workspace_id.int), UUID(int=SEED.other_workspace_id.int)
    made = Tree(
        psycopg.connect(clean_test_database.dsn, connect_timeout=5),
        ws_a,
        ws_b,
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    try:
        with made.conn.transaction():
            for ws, slug in ((ws_a, "alpha"), (ws_b, "beta")):
                made.run(_WORKSPACE, (ws, slug, NOW, NOW))
            for project, ws in ((made.project_a, ws_a), (made.project_b, ws_b)):
                made.run(_SCOPE, (project, "project", ws, ws))
                made.run(_PROJECT, (project, ws, "app", NOW, NOW))
            for repo, ws in ((made.repo_a, ws_a), (made.repo_b, ws_b)):
                made.run(_REPOSITORY, (repo, ws, "github.com/acme/app", "github", NOW, NOW))
            made.run(_SCOPE, (made.host, "host", SEED.instance_id, None))
            made.run(
                "INSERT INTO skm_workspace.hosts (id, name, os, arch, registered_at) "
                "VALUES (%s, 'laptop', 'linux', 'x86_64', %s)",
                (made.host, NOW),
            )
        yield made
    finally:
        made.conn.close()


def _refused(
    tree: Tree, error: type[psycopg.Error], constraint: str, statement: LiteralString, params: tuple[Any, ...]
) -> None:
    with pytest.raises(error) as caught, tree.conn.transaction():
        tree.run(statement, params)
    assert caught.value.diag.constraint_name == constraint


def _mount(tree: Tree, ws: UUID, project: UUID, repo: UUID, name: str, role: MountRole) -> ProjectMount:
    return ProjectMount(WorkspaceId(ws), ProjectId(project), RepositoryId(repo), MountName(name), role, NOW)


# ---------------------------------------------------------------------------------------------------------
# composite workspace FKs


def test_a_repository_of_another_workspace_is_never_mounted(tree: Tree) -> None:
    # the mount names workspace A: B's repository is not (A, repo_b)
    _refused(
        tree,
        pgerr.ForeignKeyViolation,
        "fk_project_repositories__repositories",
        _MOUNT,
        (tree.ws_a, tree.project_a, tree.repo_b, "main", "primary", NOW),
    )
    # the mount names workspace B: A's project is not (B, project_a)
    _refused(
        tree,
        pgerr.ForeignKeyViolation,
        "fk_project_repositories__projects",
        _MOUNT,
        (tree.ws_b, tree.project_a, tree.repo_b, "main", "primary", NOW),
    )
    mounts = PostgresMountRepository(tree.conn)
    with pytest.raises(SkmError) as caught, tree.conn.transaction():
        mounts.add(_mount(tree, tree.ws_a, tree.project_a, tree.repo_b, "main", MountRole.PRIMARY))
    assert caught.value.code is ErrorCode.INVALID_REFERENCE
    assert caught.value.details["constraint"] == "fk_project_repositories__repositories"
    with tree.conn.transaction():
        mounts.add(_mount(tree, tree.ws_a, tree.project_a, tree.repo_a, "main", MountRole.PRIMARY))
    assert [m.repository_id for m in mounts.for_project(ProjectId(tree.project_a))] == [tree.repo_a]


def test_remotes_and_bindings_follow_the_workspace_of_their_repository(tree: Tree) -> None:
    _refused(
        tree,
        pgerr.ForeignKeyViolation,
        "fk_repository_remotes__repositories",
        _REMOTE,
        (tree.ws_a, tree.repo_b, "github.com/acme/app", "x", True, NOW),
    )
    _refused(
        tree,
        pgerr.ForeignKeyViolation,
        "fk_checkout_bindings__repositories",
        _BINDING,
        (uuid4(), tree.ws_a, tree.host, tree.repo_b, "/src/app", "active", None, NOW, NOW, NOW),
    )
    bindings = PostgresCheckoutBindingRepository(tree.conn)
    foreign = CheckoutBinding(
        id=CheckoutBindingId(uuid4()),
        workspace_id=WorkspaceId(tree.ws_a),
        host_id=HostId(tree.host),
        repository_id=RepositoryId(tree.repo_b),
        local_locator="/src/app",
        state=BindingState.ACTIVE,
        observed_remotes=(),
        observed_head=None,
        last_verified_at=NOW,
        row_version=1,
        created_at=NOW,
    )
    with pytest.raises(SkmError) as caught, tree.conn.transaction():
        bindings.add(foreign)
    assert (caught.value.code, caught.value.details["constraint"]) == (
        ErrorCode.INVALID_REFERENCE,
        "fk_checkout_bindings__repositories",
    )


# ---------------------------------------------------------------------------------------------------------
# mounts


def test_two_primary_mounts_a_taken_name_or_a_twice_mounted_repository_fail(tree: Tree) -> None:
    other = uuid4()
    with tree.conn.transaction():
        tree.run(_REPOSITORY, (other, tree.ws_a, None, "none", NOW, NOW))
        tree.run(_MOUNT, (tree.ws_a, tree.project_a, tree.repo_a, "main", "primary", NOW))
    _refused(
        tree,
        pgerr.UniqueViolation,
        "uq_project_repositories__one_primary",
        _MOUNT,
        (tree.ws_a, tree.project_a, other, "second", "primary", NOW),
    )
    _refused(
        tree,
        pgerr.UniqueViolation,
        "pk_project_repositories",
        _MOUNT,
        (tree.ws_a, tree.project_a, other, "main", "docs", NOW),
    )
    _refused(
        tree,
        pgerr.UniqueViolation,
        "uq_project_repositories__project_id_repository_id",
        _MOUNT,
        (tree.ws_a, tree.project_a, tree.repo_a, "again", "secondary", NOW),
    )
    _refused(
        tree,
        pgerr.CheckViolation,
        "ck_project_repositories__mount_name",
        _MOUNT,
        (tree.ws_a, tree.project_a, other, "Bad Name", "docs", NOW),
    )
    mounts = PostgresMountRepository(tree.conn)
    with tree.conn.transaction():
        for name, role in (("second", MountRole.PRIMARY), ("main", MountRole.DOCS)):
            with pytest.raises(Conflict) as caught:
                mounts.add(_mount(tree, tree.ws_a, tree.project_a, other, name, role))
            assert (caught.value.code, caught.value.details) == (
                ErrorCode.ALREADY_EXISTS,
                {"kind": "mount", "mount_name": name},
            )
        mounts.add(_mount(tree, tree.ws_a, tree.project_a, other, "docs", MountRole.DOCS))  # still usable
    assert [m.mount_name.value for m in mounts.for_project(ProjectId(tree.project_a))] == ["docs", "main"]


# ---------------------------------------------------------------------------------------------------------
# remotes, canonical remotes, bindings, workers


def test_one_remote_per_workspace_one_primary_and_one_canonical_remote(tree: Tree) -> None:
    other = uuid4()
    with tree.conn.transaction():
        tree.run(_REPOSITORY, (other, tree.ws_a, None, "none", NOW, NOW))
        tree.run(_REMOTE, (tree.ws_a, tree.repo_a, "github.com/acme/app", "a", True, NOW))
        tree.run(
            _REMOTE, (tree.ws_b, tree.repo_b, "github.com/acme/app", "a", True, NOW)
        )  # another workspace
    _refused(
        tree,
        pgerr.UniqueViolation,
        "uq_repository_remotes__workspace_id_normalized_url",
        _REMOTE,
        (tree.ws_a, other, "github.com/acme/app", "a", False, NOW),
    )
    _refused(
        tree,
        pgerr.UniqueViolation,
        "uq_repository_remotes__one_primary",
        _REMOTE,
        (tree.ws_a, tree.repo_a, "gitlab.com/acme/app", "g", True, NOW),
    )
    _refused(
        tree,
        pgerr.CheckViolation,
        "ck_repository_remotes__normalized",
        _REMOTE,
        (tree.ws_a, tree.repo_a, "no-slash", "n", False, NOW),
    )
    _refused(
        tree,
        pgerr.UniqueViolation,
        "uq_repositories__workspace_id_canonical_remote",
        _REPOSITORY,
        (uuid4(), tree.ws_a, "github.com/acme/app", "github", NOW, NOW),
    )
    _refused(
        tree,
        pgerr.CheckViolation,
        "ck_repositories__provider_none",
        _REPOSITORY,
        (uuid4(), tree.ws_a, None, "github", NOW, NOW),
    )


def test_one_live_binding_per_host_and_repository_and_the_locator_checks(tree: Tree) -> None:
    first = uuid4()
    with tree.conn.transaction():
        tree.run(
            _BINDING, (first, tree.ws_a, tree.host, tree.repo_a, "/src/app", "active", None, NOW, NOW, NOW)
        )
    _refused(
        tree,
        pgerr.UniqueViolation,
        "uq_checkout_bindings__host_id_repository_id_live",
        _BINDING,
        (uuid4(), tree.ws_a, tree.host, tree.repo_a, "/src/other", "missing", None, NOW, NOW, NOW),
    )
    for locator in ("relative/path", "/with\nnewline", ""):
        _refused(
            tree,
            pgerr.CheckViolation,
            "ck_checkout_bindings__locator",
            _BINDING,
            (uuid4(), tree.ws_b, tree.host, tree.repo_b, locator, "active", None, NOW, NOW, NOW),
        )
    _refused(
        tree,
        pgerr.CheckViolation,
        "ck_checkout_bindings__head",
        _BINDING,
        (uuid4(), tree.ws_b, tree.host, tree.repo_b, "/src/b", "active", "ABC", NOW, NOW, NOW),
    )
    with tree.conn.transaction():
        tree.run("UPDATE skm_workspace.checkout_bindings SET state = 'removed' WHERE id = %s", (first,))
        tree.run(
            _BINDING,
            (uuid4(), tree.ws_a, tree.host, tree.repo_a, "C:\\src\\app", "active", "b" * 40, NOW, NOW, NOW),
        )
    rows = tree.conn.execute(
        "SELECT state, count(*) FROM skm_workspace.checkout_bindings GROUP BY state ORDER BY state"
    ).fetchall()
    assert rows == [("active", 1), ("removed", 1)]


def test_one_worker_per_principal(tree: Tree) -> None:
    principal = new_principal(
        principal_id=PrincipalId(uuid4()),
        kind=PrincipalKind.WORKER,
        display_name="w",
        created_by=None,
        now=NOW,
    )
    with tree.conn.transaction():
        PostgresPrincipalRepository(tree.conn).add(principal)
        tree.run(_WORKER, (uuid4(), tree.ws_a, tree.host, principal.id, _CAPABILITIES, NOW))
    _refused(
        tree,
        pgerr.UniqueViolation,
        "uq_workers__principal_id",
        _WORKER,
        (uuid4(), tree.ws_b, tree.host, principal.id, _CAPABILITIES, NOW),
    )
    _refused(
        tree,
        pgerr.ForeignKeyViolation,
        "fk_workers__principals",
        _WORKER,
        (uuid4(), tree.ws_a, tree.host, uuid4(), _CAPABILITIES, NOW),
    )


# ---------------------------------------------------------------------------------------------------------
# the runtime role


def test_the_adapters_work_as_the_runtime_role_and_cannot_switch_constraints_off(tree: Tree) -> None:
    if tree.conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'skm_app'").fetchone() is None:
        pytest.skip("skm_app was not created: the test user can neither create roles nor see them")
    tree.conn.commit()
    tree.conn.execute("SET ROLE skm_app")
    with tree.conn.transaction():
        projects = PostgresProjectRepository(tree.conn)
        project = projects.get(ProjectId(tree.project_a))
        projects.save(archive_project(project), expected_version=1)
        mounts = PostgresMountRepository(tree.conn)  # takes the row locks of §11 as skm_app
        mounts.add(_mount(tree, tree.ws_a, tree.project_a, tree.repo_a, "main", MountRole.PRIMARY))
        scope = uuid4()
        tree.run(_SCOPE, (scope, "workspace", SEED.instance_id, scope))
        PostgresWorkspaceRepository(tree.conn).add(
            new_workspace(workspace_id=WorkspaceId(scope), slug=Slug("gamma"), title="Gamma", now=NOW)
        )
    with pytest.raises(SkmError) as caught, tree.conn.transaction():
        mounts.add(_mount(tree, tree.ws_a, tree.project_a, tree.repo_b, "other", MountRole.DOCS))
    assert caught.value.code is ErrorCode.INVALID_REFERENCE
    for statement in (
        "ALTER TABLE skm_workspace.project_repositories "
        "DROP CONSTRAINT fk_project_repositories__repositories",
        "ALTER TABLE skm_workspace.project_repositories DISABLE TRIGGER ALL",
        "SET session_replication_role = replica",
    ):
        with pytest.raises(pgerr.InsufficientPrivilege), tree.conn.transaction():
            tree.conn.execute(statement)
