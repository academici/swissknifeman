"""Cross-workspace security and isolation tests (access §8-§14, workspace §13-§18).

Verifies that:
1. Principals (human owners and authenticated worker principals) bound to ``ws-alpha``
   cannot read or mutate projects, repositories, mounts, checkouts, hosts, or workers
   in ``ws-beta``, cannot escalate privileges, and leave ``decision='denied'`` audit rows.
2. ``local_locator`` is hidden from cross-workspace principals and from same-workspace
   ``viewer`` principals lacking ``checkout.read_locator``, and never leaks into domain events.
3. PostgreSQL composite ``(workspace_id, ...)`` foreign keys reject cross-workspace
   links across projects, repositories, remotes, and checkout bindings.
"""

from __future__ import annotations

from typing import Any, cast

import psycopg.errors
import pytest

from contracts.workspace.harness import (
    NOW,
    REMOTE,
    Side,
    clean_test_database,  # noqa: F401
    pg_session,  # noqa: F401
    pg_side,  # noqa: F401
    side,  # noqa: F401
    test_database,  # noqa: F401
)
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import ScopeId
from skm.modules.access.generated.commands import (
    PrincipalKind as CmdPrincipalKind,
)
from skm.modules.access.generated.commands import (
    Role as CmdRole,
)
from skm.modules.access.ports import TokenPepperSource
from skm.modules.access.public import (
    CreatePrincipal,
    CreateToken,
    DisablePrincipal,
    GrantMembership,
    Role,
    authenticate_token,
)
from skm.modules.workspace.domain.checkout_binding import CheckoutBindingId
from skm.modules.workspace.generated.commands import (
    ArchiveProject,
    ArchiveWorkspace,
    AttachRepository,
    BindCheckout,
    CreateProject,
    DetachRepository,
    HostArch,
    HostOs,
    RecordCheckoutVerification,
    RecordWorkerHeartbeat,
    RegisterHost,
    RegisterHostDefsHostPlatform,
    RegisterRepository,
    RegisterWorker,
    SetWorkerState,
)
from skm.modules.workspace.generated.documents import (
    HostArch as DocHostArch,
)
from skm.modules.workspace.generated.documents import (
    HostOs as DocHostOs,
)
from skm.modules.workspace.generated.documents import (
    WorkerCapabilities as WorkerCapabilitiesDoc,
)
from skm.modules.workspace.generated.documents import (
    WorkerCapabilitiesDefsHostPlatform,
)
from skm.modules.workspace.public import (
    GetHost,
    GetProject,
    GetWorkspace,
    ListProjectRepositories,
    ListProjects,
    ListRepositories,
    ListWorkers,
    ResolveCheckout,
)

_CAPABILITIES_DOC = WorkerCapabilitiesDoc(
    runtimes=("claude_code",),
    isolation_profiles=("worktree",),
    max_concurrency=1,
    labels=(),
    platform=WorkerCapabilitiesDefsHostPlatform(os=DocHostOs.LINUX, arch=DocHostArch.X86_64),
    skm_version="2.0.0",
)


def _audit_rows(s: Side) -> list[tuple[Any, str, str, str | None]]:
    """Returns committed audit records as ``(actor_id, action, decision, reason_code)``."""
    if s.memory is not None:
        return [(r.actor_id, r.action, r.decision, r.reason_code) for r in s.memory.committed.core.audit]
    rows = s.sql(
        "SELECT actor_id, action, decision, reason_code FROM skm_core.audit_records ORDER BY recorded_at, id"
    )
    return [(row[0], str(row[1]), str(row[2]), cast("str | None", row[3])) for row in rows]


def _expect_forbidden(fn: Any) -> None:
    with pytest.raises(SkmError) as exc_info:
        fn()
    assert exc_info.value.code is ErrorCode.FORBIDDEN


def test_cross_workspace_worker_and_owner_isolation(side: Side) -> None:  # noqa: F811
    """A worker or owner in ws-alpha cannot read/mutate ws-beta or escalate privileges."""
    ws_alpha = side.workspace("ws-alpha", "Workspace Alpha")
    ws_beta = side.workspace("ws-beta", "Workspace Beta")

    proj_alpha = side.project(ws_alpha, "proj-alpha", "Project Alpha")
    proj_beta = side.project(ws_beta, "proj-beta", "Project Beta")

    repo_alpha = side.repository(ws_alpha, "repo-alpha", "https://github.com/org/alpha.git")
    repo_beta = side.repository(ws_beta, "repo-beta", "https://github.com/org/beta.git")

    host_alpha = side.host("host-alpha")
    host_beta = side.host("host-beta")

    side.run(
        AttachRepository(
            project_id=proj_alpha,
            repository_id=repo_alpha,
            mount_name="main",
            role="primary",
        )
    )
    side.run(
        AttachRepository(
            project_id=proj_beta,
            repository_id=repo_beta,
            mount_name="main",
            role="primary",
        )
    )
    side.run(
        BindCheckout(
            repository_id=repo_alpha,
            host_id=host_alpha,
            local_locator="/work/alpha/main",
            observed_toplevel="/work/alpha/main",
            observed_remotes=("github.com/org/alpha",),
            observed_head="a" * 40,
            observed_dirty=False,
            observed_at=NOW,
        )
    )
    bound_alpha_other_host = side.run(
        BindCheckout(
            repository_id=repo_alpha,
            host_id=host_beta,
            local_locator="/work/alpha-on-beta/main",
            observed_toplevel="/work/alpha-on-beta/main",
            observed_remotes=("github.com/org/alpha",),
            observed_head="a" * 40,
            observed_dirty=False,
            observed_at=NOW,
        )
    )
    bound_beta = side.run(
        BindCheckout(
            repository_id=repo_beta,
            host_id=host_beta,
            local_locator="/work/beta/main",
            observed_toplevel="/work/beta/main",
            observed_remotes=("github.com/org/beta",),
            observed_head="b" * 40,
            observed_dirty=False,
            observed_at=NOW,
        )
    )

    alice = side.person("alice", {ScopeId(ws_alpha): Role.OWNER})
    bob = side.person("bob", {ScopeId(ws_beta): Role.OWNER})
    _, worker_beta = side.worker(ws_beta, host_beta, "worker-beta")

    reg_alpha = side.run(
        RegisterWorker(
            workspace_id=ws_alpha,
            host_id=host_alpha,
            display_name="worker-alpha",
            capabilities=_CAPABILITIES_DOC,
        ),
        actor=alice,
    )
    pepper = side.bus._gateways.get(TokenPepperSource)
    with side.uow() as uow:
        worker_alpha_actor = authenticate_token(
            uow,
            reg_alpha.token_secret,
            pepper=pepper.pepper(),
            now=side.clock.now(),
        )
        uow.commit()
    assert worker_alpha_actor.kind is PrincipalKind.WORKER
    assert worker_alpha_actor.principal_id == reg_alpha.principal_id

    for caller in (worker_alpha_actor, alice):
        _expect_forbidden(lambda c=caller: side.ask(GetWorkspace(workspace_id=ws_beta), actor=c))
        _expect_forbidden(lambda c=caller: side.ask(GetProject(project_id=proj_beta), actor=c))
        _expect_forbidden(lambda c=caller: side.ask(ListProjects(workspace_id=ws_beta), actor=c))
        _expect_forbidden(lambda c=caller: side.ask(ListRepositories(workspace_id=ws_beta), actor=c))
        _expect_forbidden(lambda c=caller: side.ask(ListProjectRepositories(project_id=proj_beta), actor=c))
        _expect_forbidden(
            lambda c=caller: side.ask(
                ResolveCheckout(project_id=proj_beta, host_id=host_beta, mount_name="main"),
                actor=c,
            )
        )
        _expect_forbidden(lambda c=caller: side.ask(ListWorkers(workspace_id=ws_beta), actor=c))

    _expect_forbidden(lambda: side.ask(GetHost(host_id=host_beta), actor=worker_alpha_actor))

    cross_mutations: tuple[object, ...] = (
        CreateProject(workspace_id=ws_beta, slug="injected", title="Injected"),
        ArchiveProject(project_id=proj_beta, expected_row_version=1, reason="hijack"),
        RegisterRepository(
            workspace_id=ws_beta,
            title="rogue",
            remote_url="https://github.com/org/rogue.git",
            external_id=None,
        ),
        AttachRepository(
            project_id=proj_beta,
            repository_id=repo_beta,
            mount_name="rogue",
            role="secondary",
        ),
        DetachRepository(project_id=proj_beta, mount_name="main"),
        BindCheckout(
            repository_id=repo_beta,
            host_id=host_beta,
            local_locator="/work/hijack",
            observed_toplevel="/work/hijack",
            observed_remotes=("github.com/org/beta",),
            observed_head="c" * 40,
            observed_dirty=False,
            observed_at=NOW,
        ),
        RecordCheckoutVerification(
            binding_id=bound_beta.binding_id,
            expected_row_version=1,
            observed_exists=False,
            observed_toplevel=None,
            observed_remotes=(),
            observed_head=None,
            observed_dirty=None,
            observed_at=NOW,
        ),
        ArchiveWorkspace(workspace_id=ws_beta, expected_row_version=1, reason="sabotage"),
        RecordWorkerHeartbeat(worker_id=worker_beta.id, capabilities=None),
        SetWorkerState(worker_id=worker_beta.id, state="retired", expected_row_version=1),
    )
    for cmd in cross_mutations:
        _expect_forbidden(lambda dto=cmd: side.run(dto, actor=worker_alpha_actor))
        _expect_forbidden(lambda dto=cmd: side.run(dto, actor=alice))

    escalation_cmds: tuple[object, ...] = (
        GrantMembership(
            scope_id=ScopeId(ws_alpha),
            principal_id=worker_alpha_actor.principal_id,
            role=CmdRole.OWNER,
        ),
        CreatePrincipal(kind=CmdPrincipalKind.HUMAN, display_name="escalated-admin"),
        DisablePrincipal(
            principal_id=bob.principal_id,
            expected_row_version=1,
            reason="hostile takeover",
        ),
        CreateToken(
            name="stolen-owner-token",
            principal_id=alice.principal_id,
            scope_id=ScopeId(ws_alpha),
        ),
        RegisterHost(
            name="rogue-host",
            platform=RegisterHostDefsHostPlatform(os=HostOs.LINUX, arch=HostArch.X86_64),
        ),
        SetWorkerState(
            worker_id=reg_alpha.worker_id,
            state="draining",
            expected_row_version=1,
        ),
        RecordCheckoutVerification(
            binding_id=bound_alpha_other_host.binding_id,
            expected_row_version=1,
            observed_exists=True,
            observed_toplevel="/work/alpha-on-beta/main",
            observed_remotes=("github.com/org/alpha",),
            observed_head="a" * 40,
            observed_dirty=False,
            observed_at=NOW,
        ),
    )
    for cmd in escalation_cmds:
        _expect_forbidden(lambda dto=cmd: side.run(dto, actor=worker_alpha_actor))

    beta_proj = side.ask(GetProject(project_id=proj_beta), actor=bob)
    assert beta_proj.title == "Project Beta"
    assert beta_proj.row_version == 1
    beta_resolved = side.ask(
        ResolveCheckout(project_id=proj_beta, host_id=host_beta, mount_name="main"),
        actor=bob,
    )
    assert beta_resolved.local_locator == "/work/beta/main"

    audits = _audit_rows(side)
    worker_denied = [
        (action, reason)
        for actor_id, action, decision, reason in audits
        if actor_id == worker_alpha_actor.principal_id and decision == "denied"
    ]
    alice_denied = [
        (action, reason)
        for actor_id, action, decision, reason in audits
        if actor_id == alice.principal_id and decision == "denied"
    ]
    assert len(worker_denied) >= len(cross_mutations) + len(escalation_cmds)
    assert len(alice_denied) >= len(cross_mutations)
    assert all(isinstance(reason, str) and bool(reason) for _, reason in worker_denied)
    assert all(isinstance(reason, str) and bool(reason) for _, reason in alice_denied)
    worker_denied_actions = {action for action, _ in worker_denied}
    assert "access.grant_membership" in worker_denied_actions
    assert "workspace.create_project" in worker_denied_actions
    assert "workspace.record_checkout_verification" in worker_denied_actions


def test_cross_workspace_locator_secrecy(side: Side) -> None:  # noqa: F811
    """local_locator requires checkout.read_locator and never leaks across workspaces or into events."""
    ws_alpha = side.workspace("ws-alpha", "Workspace Alpha")
    ws_beta = side.workspace("ws-beta", "Workspace Beta")
    proj_alpha = side.project(ws_alpha, "proj-alpha", "Project Alpha")
    repo_alpha = side.repository(ws_alpha, "repo-alpha", REMOTE)
    host_alpha = side.host("host-alpha")

    side.run(
        AttachRepository(
            project_id=proj_alpha,
            repository_id=repo_alpha,
            mount_name="main",
            role="primary",
        )
    )
    secret_locator = "/var/private/alpha/checkout-main"
    side.run(
        BindCheckout(
            repository_id=repo_alpha,
            host_id=host_alpha,
            local_locator=secret_locator,
            observed_toplevel=secret_locator,
            observed_remotes=("github.com/acme/app",),
            observed_head="a" * 40,
            observed_dirty=False,
            observed_at=NOW,
        )
    )

    viewer_alpha = side.person("viewer-alpha", {ScopeId(ws_alpha): Role.VIEWER})
    member_alpha = side.person("member-alpha", {ScopeId(ws_alpha): Role.MEMBER})
    owner_beta = side.person("owner-beta", {ScopeId(ws_beta): Role.OWNER})

    viewer_mounts = side.ask(
        ListProjectRepositories(project_id=proj_alpha, host_id=host_alpha),
        actor=viewer_alpha,
    )
    assert len(viewer_mounts.items) == 1
    assert viewer_mounts.items[0].binding is not None
    assert viewer_mounts.items[0].binding.state == "active"
    assert viewer_mounts.items[0].binding.local_locator is None

    _expect_forbidden(
        lambda: side.ask(
            ResolveCheckout(project_id=proj_alpha, host_id=host_alpha, mount_name="main"),
            actor=viewer_alpha,
        )
    )
    _expect_forbidden(
        lambda: side.ask(
            ListProjectRepositories(project_id=proj_alpha, host_id=host_alpha),
            actor=owner_beta,
        )
    )
    _expect_forbidden(
        lambda: side.ask(
            ResolveCheckout(project_id=proj_alpha, host_id=host_alpha, mount_name="main"),
            actor=owner_beta,
        )
    )

    member_resolved = side.ask(
        ResolveCheckout(project_id=proj_alpha, host_id=host_alpha, mount_name="main"),
        actor=member_alpha,
    )
    assert member_resolved.local_locator == secret_locator

    for _etype, payload in side.events():
        assert "local_locator" not in payload
        assert secret_locator not in str(payload)


@pytest.mark.pg
def test_cross_workspace_composite_fk_isolation(pg_side: Side) -> None:  # noqa: F811
    """PostgreSQL composite (workspace_id, ...) foreign keys block cross-workspace links."""
    ws_alpha = pg_side.workspace("ws-alpha", "Workspace Alpha")
    ws_beta = pg_side.workspace("ws-beta", "Workspace Beta")
    proj_alpha = pg_side.project(ws_alpha, "proj-alpha", "Project Alpha")
    repo_alpha = pg_side.repository(ws_alpha, "repo-alpha", "https://github.com/org/alpha.git")
    repo_beta = pg_side.repository(ws_beta, "repo-beta", "https://github.com/org/beta.git")
    host_alpha = pg_side.host("host-alpha")

    with pytest.raises(SkmError) as exc_info:
        pg_side.run(
            AttachRepository(
                project_id=proj_alpha,
                repository_id=repo_beta,
                mount_name="cross",
                role="secondary",
            )
        )
    assert exc_info.value.code is ErrorCode.CHECKOUT_MISMATCH

    pg_side.run(
        AttachRepository(
            project_id=proj_alpha,
            repository_id=repo_alpha,
            mount_name="main",
            role="primary",
        )
    )

    assert pg_side.pg is not None
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        pg_side.sql(
            "INSERT INTO skm_workspace.project_repositories "
            "(workspace_id, project_id, repository_id, mount_name, role, attached_at) "
            "VALUES (%s, %s, %s, 'bad-repo', 'secondary', %s)",
            (ws_alpha, proj_alpha, repo_beta, NOW),
        )

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        pg_side.sql(
            "INSERT INTO skm_workspace.checkout_bindings "
            "(id, workspace_id, host_id, repository_id, local_locator, state, observed_remotes, "
            "observed_head, last_verified_at, row_version, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, '/work/x', 'active', %s, NULL, %s, 1, %s, %s)",
            (
                CheckoutBindingId(pg_side.ids.new_id()),
                ws_alpha,
                host_alpha,
                repo_beta,
                [],
                NOW,
                NOW,
                NOW,
            ),
        )
