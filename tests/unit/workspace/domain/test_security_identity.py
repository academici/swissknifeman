"""Identity versus observation (workspace §4.3, WORKSPACE-01/02): names and observations are no authority."""

import ast
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed, ValidationFailed
from skm.kernel.ids import HostId, ProjectId, RepositoryId, WorkspaceId
from skm.modules.workspace.domain import mount as mounts
from skm.modules.workspace.domain import project as projects
from skm.modules.workspace.domain import workspace as workspaces
from skm.modules.workspace.domain.attach import (
    AttachInput,
    CreateRepository,
    Refuse,
    RepositoryMatchView,
    UseExistingRepository,
    decide_attach,
)
from skm.modules.workspace.domain.checkout_binding import (
    BindingState,
    CheckoutBinding,
    CheckoutBindingId,
    ObservedCheckout,
    VerifyReason,
    binding_identity,
    locator_digest,
    new_binding,
    remove,
    verify,
)
from skm.modules.workspace.domain.host import (
    HostArch,
    HostName,
    HostOs,
    HostPlatform,
    HostState,
    new_host,
    require_active,
)
from skm.modules.workspace.domain.mount import MountName, MountRole
from skm.modules.workspace.domain.remote_url import NormalizedRemote, normalize_remote, remote_endpoint
from skm.modules.workspace.domain.repository import new_repository
from skm.modules.workspace.domain.slug import Slug

T0 = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)
WS = WorkspaceId(UUID(int=1))
OTHER_WS = WorkspaceId(UUID(int=2))
PROJECT = ProjectId(UUID(int=3))
REPO_1 = RepositoryId(UUID(int=4))
REPO_2 = RepositoryId(UUID(int=5))
HOST_A = HostId(UUID(int=6))
HOST_B = HostId(UUID(int=7))
REMOTE = NormalizedRemote("github.com/a/b")
LOCATOR = "/work/repo"


def observed(
    toplevel: str | None = LOCATOR, remotes: tuple[NormalizedRemote, ...] = (REMOTE,)
) -> ObservedCheckout:
    return ObservedCheckout(
        exists=True,
        toplevel=toplevel,
        remotes=remotes,
        head="a" * 40,
        marker=None,
        observed_at=T1,
        dirty=False,
    )


def bind(binding_id: int, host: HostId, repository: RepositoryId, locator: str = LOCATOR) -> CheckoutBinding:
    return new_binding(
        binding_id=CheckoutBindingId(UUID(int=binding_id)),
        workspace_id=WS,
        host_id=host,
        repository_id=repository,
        local_locator=locator,
        observed=observed(toplevel=locator),
        repository_remotes=[REMOTE],
        now=T0,
    ).binding


def _workspace() -> workspaces.Workspace:
    return workspaces.new_workspace(workspace_id=WS, slug=Slug("team"), title="Team", now=T0)


def _project() -> projects.Project:
    return projects.new_project(
        project_id=PROJECT, workspace_id=WS, slug=Slug("skm"), title="SKM", description="", now=T0
    )


# --- WORKSPACE-01/02: names and titles never change IDs or scope ---


def test_workspace_retitle_or_reslug_keeps_id_and_parent_scope_inputs() -> None:
    original = _workspace()
    renamed = replace(original, slug=Slug("renamed"), title="Another")
    assert renamed.id == original.id == WS


def test_archiving_keeps_the_identity_and_never_reopens() -> None:
    archived = workspaces.archive(_workspace())
    assert archived.id == WS
    assert archived.state is workspaces.WorkspaceState.ARCHIVED
    assert workspaces.archive(archived) is archived
    with pytest.raises(PreconditionFailed) as err:
        workspaces.require_active(archived)
    assert err.value.code is ErrorCode.PROJECT_ARCHIVED
    assert err.value.details["kind"] == "workspace"


def test_suspended_workspace_blocks_admissions_with_the_same_code() -> None:
    suspended = replace(_workspace(), state=workspaces.WorkspaceState.SUSPENDED)
    with pytest.raises(PreconditionFailed) as err:
        workspaces.require_active(suspended)
    assert err.value.code is ErrorCode.PROJECT_ARCHIVED
    assert workspaces.archive(suspended).state is workspaces.WorkspaceState.ARCHIVED


def test_reused_slug_after_archive_is_a_new_identity() -> None:
    old = projects.archive(_project())
    new = projects.new_project(
        project_id=ProjectId(UUID(int=99)),
        workspace_id=WS,
        slug=old.slug,
        title="SKM",
        description="",
        now=T1,
    )
    assert new.slug == old.slug
    assert new.id != old.id


def test_project_archive_and_requirements() -> None:
    archived = projects.archive(_project())
    assert (archived.state, archived.row_version) == (projects.ProjectState.ARCHIVED, 2)
    assert projects.archive(archived) is archived
    with pytest.raises(PreconditionFailed) as err:
        projects.require_active(archived)
    assert err.value.code is ErrorCode.PROJECT_ARCHIVED
    projects.require_active(_project())


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_blank_or_long_titles_are_schema_errors(title: str) -> None:
    with pytest.raises(ValidationFailed) as err:
        projects.new_project(
            project_id=PROJECT, workspace_id=WS, slug=Slug("skm"), title=title, description="", now=T0
        )
    assert err.value.code is ErrorCode.SCHEMA_INVALID
    with pytest.raises(ValidationFailed):
        workspaces.new_workspace(workspace_id=WS, slug=Slug("team"), title=title, now=T0)


def test_project_description_bound() -> None:
    projects.new_project(
        project_id=PROJECT, workspace_id=WS, slug=Slug("skm"), title="t", description="d" * 4000, now=T0
    )
    with pytest.raises(ValidationFailed):
        projects.new_project(
            project_id=PROJECT, workspace_id=WS, slug=Slug("skm"), title="t", description="d" * 4001, now=T0
        )


@pytest.mark.parametrize("bad", ["", "a", "-ab", "ab-", "a--b", "AB", "a_b", "x" * 64])
def test_slug_rules(bad: str) -> None:
    with pytest.raises(ValidationFailed):
        Slug(bad)


def test_host_registration_and_retirement() -> None:
    host = new_host(
        host_id=HOST_A,
        name=HostName("build-1.local"),
        platform=HostPlatform(HostOs.LINUX, HostArch.ARM64),
        now=T0,
    )
    assert (host.state, host.last_seen_at, host.row_version) == (HostState.ACTIVE, None, 1)
    require_active(host)
    with pytest.raises(PreconditionFailed):
        require_active(replace(host, state=HostState.RETIRED))
    for bad in ("", "-x", "A", "a b", "x" * 64):
        with pytest.raises(ValidationFailed):
            HostName(bad)


# --- mounts: workspace isolation and uniqueness ---


def _mount(role: MountRole, name: str, repository: RepositoryId = REPO_1) -> mounts.ProjectRepository:
    return mounts.ProjectRepository(WS, PROJECT, repository, MountName(name), role, T0)


def _repository(workspace: WorkspaceId = WS, repository: RepositoryId = REPO_1):
    return new_repository(
        repository_id=repository,
        workspace_id=workspace,
        title="r",
        remote_url="git@github.com:a/b.git",
        external_id=None,
        now=T0,
    )


def test_attach_builds_a_mount_in_the_project_workspace() -> None:
    mount = mounts.attach(_project(), _repository(), MountName("main"), MountRole.PRIMARY, [], now=T1)
    assert (mount.workspace_id, mount.project_id, mount.repository_id, mount.attached_at) == (
        WS,
        PROJECT,
        REPO_1,
        T1,
    )


def test_attach_refuses_a_repository_of_another_workspace() -> None:
    with pytest.raises(PreconditionFailed) as err:
        mounts.attach(_project(), _repository(OTHER_WS), MountName("main"), MountRole.PRIMARY, [], now=T1)
    assert err.value.code is ErrorCode.CHECKOUT_MISMATCH
    assert err.value.details == {"reason": "other_workspace"}


def test_attach_mount_name_is_unique_in_the_project() -> None:
    existing = [_mount(MountRole.PRIMARY, "main")]
    with pytest.raises(Conflict) as err:
        mounts.attach(_project(), _repository(), MountName("main"), MountRole.DOCS, existing, now=T1)
    assert err.value.code is ErrorCode.ALREADY_EXISTS


def test_attach_allows_at_most_one_primary() -> None:
    existing = [_mount(MountRole.PRIMARY, "main")]
    with pytest.raises(PreconditionFailed) as err:
        mounts.attach(_project(), _repository(), MountName("second"), MountRole.PRIMARY, existing, now=T1)
    assert err.value.code is ErrorCode.INVALID_TRANSITION
    assert err.value.details == {"reason": "primary_exists"}
    for role in (MountRole.SECONDARY, MountRole.DOCS, MountRole.INFRA):
        assert (
            mounts.attach(_project(), _repository(), MountName("second"), role, existing, now=T1).role is role
        )


def test_mounts_of_other_projects_do_not_constrain_this_one() -> None:
    elsewhere = replace(_mount(MountRole.PRIMARY, "main"), project_id=ProjectId(UUID(int=77)))
    mount = mounts.attach(
        _project(), _repository(), MountName("main"), MountRole.PRIMARY, [elsewhere], now=T1
    )
    assert mount.project_id == PROJECT


def test_detach_returns_the_mount_or_none() -> None:
    existing = [_mount(MountRole.PRIMARY, "main"), _mount(MountRole.DOCS, "docs")]
    assert mounts.detach(existing, PROJECT, MountName("docs")) == existing[1]
    assert mounts.detach(existing, PROJECT, MountName("nope")) is None
    assert mounts.detach(existing, ProjectId(UUID(int=77)), MountName("docs")) is None


# --- binding identity versus observation ---


def test_moved_locator_is_mismatched_and_rebind_is_a_new_id() -> None:
    original = bind(10, HOST_A, REPO_1)
    moved = verify(original, observed(toplevel="/new/place"), [REMOTE], T1)
    assert (moved.binding.state, moved.reason) == (BindingState.MISMATCHED, VerifyReason.MOVED)
    assert moved.binding.local_locator == LOCATOR
    assert binding_identity(moved.binding) == binding_identity(original)  # the observation did not rebind it

    # The only way to follow the checkout: remove the old binding and create a new one with a new ID.
    assert remove(moved.binding).state is BindingState.REMOVED
    rebound = bind(11, HOST_A, REPO_1, "/new/place")
    assert rebound.id != original.id
    assert binding_identity(rebound) != binding_identity(original)
    assert rebound.local_locator == "/new/place"


def test_observed_facts_change_without_changing_identity() -> None:
    original = bind(10, HOST_A, REPO_1)
    after = verify(original, replace(observed(), head="b" * 40), [REMOTE], T1).binding
    assert after.observed_head != original.observed_head
    assert binding_identity(after) == binding_identity(original)


def test_identity_is_defined_by_ids_and_the_locator_digest_not_by_observations() -> None:
    names = {f.name for f in fields(binding_identity(bind(10, HOST_A, REPO_1)))}
    assert names == {"binding_id", "host_id", "repository_id", "locator_digest"}


def test_binding_identity_hides_the_raw_locator() -> None:
    identity = binding_identity(bind(10, HOST_A, REPO_1))
    assert LOCATOR not in str(identity.to_json())
    assert identity.locator_digest == locator_digest(LOCATOR) == locator_digest(LOCATOR + "/")
    assert locator_digest("/work/other") != identity.locator_digest


def test_verify_never_rebinds_to_another_repository_or_host() -> None:
    original = bind(10, HOST_A, REPO_1)
    after = verify(original, observed(toplevel="/other", remotes=()), [REMOTE], T1).binding
    assert (after.host_id, after.repository_id, after.workspace_id) == (HOST_A, REPO_1, WS)


# --- ench6: one logical repository, two binding paths, no merging by title or URL ---


def test_one_repository_can_have_two_bindings_with_distinct_identities() -> None:
    on_a = bind(10, HOST_A, REPO_1, "/work/a/repo")
    on_b = bind(11, HOST_B, REPO_1, "/srv/b/repo")
    assert on_a.repository_id == on_b.repository_id == REPO_1
    assert binding_identity(on_a) != binding_identity(on_b)
    assert on_a.id != on_b.id


def _view(repository: RepositoryId, title: str) -> RepositoryMatchView:
    return RepositoryMatchView(repository, title, (REMOTE,), ())


def _attach(
    *known: RepositoryMatchView, assume_yes: bool = False, project: ProjectId | None = None
) -> AttachInput:
    return AttachInput(
        instance_id=UUID(int=500),
        workspace_id=WS,
        requested_project_id=project,
        observed=observed(),
        known_repositories=known,
        marker_target=None,
        assume_yes=assume_yes,
    )


def test_same_title_and_url_do_not_merge_repository_ids() -> None:
    decision = decide_attach(
        _attach(_view(REPO_1, "same title"), _view(REPO_2, "same title"), assume_yes=True)
    )
    assert isinstance(decision, Refuse)
    assert decision.code == ErrorCode.AMBIGUOUS_REFERENCE.value


def test_a_repository_is_joined_only_by_an_explicit_attach() -> None:
    needs_confirmation = decide_attach(_attach(_view(REPO_1, "r")))
    assert needs_confirmation == UseExistingRepository(REPO_1, None, needs_confirmation=True)
    explicit = decide_attach(_attach(_view(REPO_1, "r"), project=PROJECT))
    assert explicit == UseExistingRepository(REPO_1, PROJECT, needs_confirmation=False)


def test_a_new_repository_is_not_created_without_an_explicit_project() -> None:
    assert isinstance(decide_attach(_attach()), Refuse)
    assert decide_attach(_attach(project=PROJECT)) == CreateRepository(REMOTE)


def test_display_remote_and_marker_do_not_carry_approval_identity() -> None:
    # Two repositories can display the same remote text; their IDs, not the text, are what approvals bind to.
    first = _repository(repository=REPO_1)
    second = _repository(repository=REPO_2)
    assert first.canonical_remote == second.canonical_remote
    assert first.id != second.id


# --- ssh ports: one match key, two effect endpoints ---


def test_ssh_ports_share_the_match_key_but_an_approval_endpoint_differs() -> None:
    a = "ssh://git@code.example:2222/team/repo.git"
    b = "ssh://git@code.example:2200/team/repo.git"
    assert normalize_remote(a) == normalize_remote(b)
    endpoint_a, endpoint_b = remote_endpoint(a), remote_endpoint(b)
    assert endpoint_a is not None
    assert endpoint_b is not None
    assert endpoint_a != endpoint_b
    assert endpoint_a.to_json() != endpoint_b.to_json()
    assert (endpoint_a.hostname, endpoint_a.repository_path) == (
        endpoint_b.hostname,
        endpoint_b.repository_path,
    )


# --- purity: the domain never looks for a cwd, a file or a process ---

_FORBIDDEN_MODULES = {
    "os",
    "pathlib",
    "subprocess",
    "shutil",
    "socket",
    "tempfile",
    "glob",
    "io",
    "sys",
    "platform",
}
_FORBIDDEN_CALLS = {"open", "getcwd", "cwd", "environ", "getenv", "now", "utcnow", "today"}


def _domain_files() -> list[Path]:
    import skm.modules.workspace.domain as package

    root = Path(package.__file__).resolve().parent
    return sorted(root.glob("*.py"))


def _violations(source: str) -> set[str]:
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            found.add(
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else ""
            )
    return found & (_FORBIDDEN_MODULES | _FORBIDDEN_CALLS)


@pytest.mark.parametrize("path", _domain_files(), ids=lambda p: p.name)
def test_domain_module_is_free_of_io_and_ambient_state(path: Path) -> None:
    assert not _violations(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "source",
    [
        "import os\n",
        "from pathlib import Path\n",
        "import subprocess\n",
        "x = open('f')\n",
        "from pathlib import Path\nroot = Path.cwd()\n",
        "import datetime\nt = datetime.datetime.now()\n",
    ],
)
def test_the_purity_scan_catches_io_and_ambient_state(source: str) -> None:
    assert _violations(source)
