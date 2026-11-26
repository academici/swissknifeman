"""Integration tests for ``integrations.host`` plan/apply/adopt/drift/remove and ``LocalCheckoutFs``."""

from __future__ import annotations

import base64
import json
import os
import threading
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from io import StringIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from fakes.clock import FrozenClock
from skm.adapters.checkout_fs.local import LocalCheckoutFs
from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext, HostServices
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.bootstrap.projection_wiring import bind_cli_projections
from skm.entrypoints.cli.host import host_context_factory
from skm.entrypoints.cli.main import Backend, main
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed, SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import FileVersionId, HostId, PrincipalId, ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta
from skm.kernel.ports_uow import Surface as PortSurface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.integrations.domain.decisions import FileDecisionKind
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.managed_block import render_block
from skm.modules.integrations.domain.merged_json import OwnedKeyPath, dumps_merged_json_bytes
from skm.modules.integrations.domain.observed import extract_managed_digest
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.projection import ProjectionState
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetCapabilities, TargetId
from skm.modules.integrations.generated.queries import GetAppliedState
from skm.modules.integrations.generated.views import AppliedStateView
from skm.modules.integrations.host.adopt_file import adopt_file
from skm.modules.integrations.host.apply_projection import apply_projection
from skm.modules.integrations.host.detect_drift import detect_drift
from skm.modules.integrations.host.observe import write_binding_journal
from skm.modules.integrations.host.plan_projection import plan_projection
from skm.modules.integrations.host.registry import HOST_OPERATIONS
from skm.modules.integrations.host.remove_projection import remove_projection
from skm.modules.integrations.ports import CheckoutFs, IntegrationTarget, IntegrationTargetRegistry
from skm.modules.workspace import public as ws_pub
from skm.modules.workspace.generated.commands import HostArch, HostOs, RegisterHostDefsHostPlatform
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.logging.logger import get_logger
from support.git_repo import GitRepoFixture, init_git_repo
from support.pg import TestDatabase, clean_test_database, pg_session, test_database
from support.seed import SEED

__all__ = ["clean_test_database", "pg_session", "test_database"]

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
OWNER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d9"))


def make_desired(
    target: TargetId, surface: Surface, relative_path: str, boundary: ManagedBoundary, managed_bytes: bytes
) -> DesiredFile:
    digest, ok = extract_managed_digest(managed_bytes, boundary)
    assert ok
    assert digest is not None
    return DesiredFile(
        target=target,
        surface=surface,
        relative_path=relative_path,
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=digest,
        source_refs=(),
        renderer=f"{target.value}.{surface.value}@1",
    )


class _StubTarget:
    def __init__(self, target_id: TargetId, files: Sequence[DesiredFile] = ()) -> None:
        self.target_id = target_id
        self.renderer_version = f"{target_id.value}@1"
        self.files: tuple[DesiredFile, ...] = tuple(files)

    def capabilities(self) -> TargetCapabilities:
        return TargetCapabilities(
            target=self.target_id,
            surfaces=dict.fromkeys(Surface, SurfaceSupport.NATIVE),
            hook_surfaces={},
            tested_client_version="1.0.0",
            verified_at=date(2026, 11, 1),
        )

    def render(self, inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
        _ = inputs
        return self.files

    def normalize_hook_payload(self, event_name: str, payload: Mapping[str, Any]) -> Any:
        raise NotImplementedError

    def render_hook_decision(self, event: Any, decision: Any) -> Any:
        raise NotImplementedError

    def client_layers(self, fs: Any, home: Any) -> tuple[Any, ...]:
        return ()

    def instruction_paths(self) -> tuple[str, ...]:
        return ()

    def summarize_session(self, payload: Mapping[str, Any], fs: Any) -> None:
        return None


class _StubRegistry:
    def __init__(self, targets: Mapping[TargetId, _StubTarget]) -> None:
        self._targets = dict(targets)

    def get(self, target: TargetId) -> IntegrationTarget:
        if target not in self._targets:
            raise NotFound(ErrorCode.NOT_FOUND, f"unknown target {target}")
        return self._targets[target]

    def all(self) -> tuple[IntegrationTarget, ...]:
        return tuple(self._targets.values())


@dataclass
class HostEnv:
    app: App
    client: SkmClient
    ctx: HostContext
    fs: LocalCheckoutFs
    checkout_dir: Path
    state_dir: Path
    ws_id: WorkspaceId
    project_id: ProjectId
    binding_id: ws_pub.CheckoutBindingId
    targets: dict[TargetId, _StubTarget]

    def ask_applied(self, target: str = "claude_code") -> AppliedStateView:
        res = self.client.ask(
            GetAppliedState(
                project_id=self.project_id,
                checkout_binding_id=self.binding_id,
                target=cast("Any", target),
            )
        )
        assert isinstance(res, AppliedStateView)
        return res


def _default_claude_files(tag: str = "v1") -> tuple[DesiredFile, ...]:
    t = TargetId.CLAUDE_CODE
    blk_bnd = ManagedBoundary(Ownership.MANAGED_BLOCK, block_ids=("skm.core",))
    blk_bytes = render_block("skm.core", f"Core rule {tag}\n")
    json_bnd = ManagedBoundary(
        Ownership.MERGED_JSON, owned_keys=(OwnedKeyPath(("permissions", "allow"), "replace"),)
    )
    json_bytes = dumps_merged_json_bytes({"permissions": {"allow": [f"Read({tag})"]}})
    toml_bnd = ManagedBoundary(Ownership.MERGED_TOML, owned_keys=(OwnedKeyPath(("skm",), "replace"),))
    toml_bytes = f'[skm]\nprofile = "{tag}"\n'.encode()
    file_bnd = ManagedBoundary(Ownership.MANAGED_FILE)
    return (
        make_desired(t, Surface.INSTRUCTIONS, "CLAUDE.md", blk_bnd, blk_bytes),
        make_desired(t, Surface.INSTRUCTIONS, ".claude/rules/skm-core.md", file_bnd, f"# {tag}\n".encode()),
        make_desired(t, Surface.PERMISSIONS, ".claude/settings.json", json_bnd, json_bytes),
        make_desired(t, Surface.MCP, ".codex/config.toml", toml_bnd, toml_bytes),
        make_desired(t, Surface.HOOKS, ".claude/hooks/pre.sh", file_bnd, b"#!/bin/sh\necho ok\n"),
    )


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def env(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[HostEnv]:
    backend = str(request.param)
    dsn: str | None = None
    if backend == "postgres":
        pg_db: TestDatabase = request.getfixturevalue("clean_test_database")
        dsn = pg_db.dsn

    clock = FrozenClock(NOW)
    bs_env = {"SKM_DATABASE_URL": dsn or "postgresql://127.0.0.1:5432/mem"}
    bs = replace(
        load_bootstrap(None, bs_env, tmp_path / "boot"),
        instance_id=SEED.instance_id,
        database_pool_min_size=0,
        database_pool_max_size=2,
    )
    ov = CompositionOverrides(
        authorizer=RbacAuthorizer(clock), scopes=StoredScopeChain(), clock=clock, instance_id=SEED.instance_id
    )
    inv: JsonObject = {}
    app = build_app(
        bs,
        surface=PortSurface.CLI,
        environ={"SKM_DATABASE_URL": dsn} if dsn else {},
        invocation=inv,
        backend="postgres" if backend == "postgres" else None,
        overrides=ov,
    )
    try:
        with app.uow_factory(RequestMeta("req_" + "1" * 26, PortSurface.CLI, None, NOW)) as uow:
            if backend == "memory":
                uow.repo(ScopeRegistry).create(
                    SEED.instance_id, ScopeKind.INSTANCE, parent=None, workspace_id=None
                )
            uow.repo(PrincipalRepository).add(
                new_principal(
                    principal_id=OWNER_ID,
                    kind=PrincipalKind.HUMAN,
                    display_name="owner",
                    created_by=None,
                    now=NOW,
                )
            )
            uow.repo(MembershipRepository).upsert(
                Membership(SEED.instance_id, OWNER_ID, Role.OWNER, None, NOW)
            )
            uow.commit()

        client = app.client(actor=Actor(OWNER_ID, PrincipalKind.HUMAN, "owner"), surface=PortSurface.CLI)

        def run_cmd(cmd: object) -> Any:
            return client.dispatch(cmd, idempotency_key=client.new_idempotency_key())

        ws_id = WorkspaceId(run_cmd(ws_pub.CreateWorkspace(slug="ws", title="WS")).workspace_id)
        proj_id = ProjectId(
            run_cmd(ws_pub.CreateProject(workspace_id=ws_id, slug="skm", title="SKM")).project_id
        )
        plat = RegisterHostDefsHostPlatform(os=HostOs.LINUX, arch=HostArch.X86_64)
        host_id = HostId(run_cmd(ws_pub.RegisterHost(name="dev", platform=plat)).host_id)
        repo_cmd = ws_pub.RegisterRepository(ws_id, "repo", "https://github.com/org/skm.git", None)
        repo_id = run_cmd(repo_cmd).repository_id
        run_cmd(ws_pub.AttachRepository(project_id=proj_id, repository_id=repo_id, mount_name="main"))

        checkout_dir = tmp_path / "checkout"
        (checkout_dir / ".git").mkdir(parents=True)
        bind_cmd = ws_pub.BindCheckout(
            repo_id,
            host_id,
            str(checkout_dir),
            str(checkout_dir),
            ("github.com/org/skm",),
            "a" * 40,
            False,
            NOW,
        )
        binding_id = ws_pub.CheckoutBindingId(run_cmd(bind_cmd).binding_id)

        state_dir = tmp_path / "state"
        fs = LocalCheckoutFs(checkout_dir, state_dir=state_dir, lock_timeout_seconds=0.1)
        targets = {
            TargetId.CLAUDE_CODE: _StubTarget(TargetId.CLAUDE_CODE, _default_claude_files("v1")),
            TargetId.CODEX: _StubTarget(TargetId.CODEX, ()),
        }
        services = HostServices(
            host_id=host_id,
            surface=PortSurface.CLI,
            gateways=GatewayTable(
                {CheckoutFs: fs, IntegrationTargetRegistry: _StubRegistry(targets)}, "host_gateway"
            ),
            host_config=dict,
            operations={spec.name: spec for spec in HOST_OPERATIONS},
        )
        ctx = services.context(client=client, cancel=CancelSource().token, log=get_logger("test.host"))
        yield HostEnv(app, client, ctx, fs, checkout_dir, state_dir, ws_id, proj_id, binding_id, targets)
    finally:
        app.close()


def test_clean_plan_apply_idempotent_update_and_foreign_preservation(env: HostEnv) -> None:
    plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,))
    assert len(plans) == 1
    assert {d.kind for d in plans[0].decisions} == {FileDecisionKind.CREATE}
    assert not (env.checkout_dir / "CLAUDE.md").exists()

    outcomes = apply_projection(env.ctx, plans)
    assert outcomes[0].state is ProjectionState.IN_SYNC
    assert len(outcomes[0].written) == 5
    assert os.access(env.checkout_dir / ".claude/hooks/pre.sh", os.X_OK)

    noop_plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,))
    assert {d.kind for d in noop_plans[0].decisions} == {FileDecisionKind.NOOP}
    noop_out = apply_projection(env.ctx, noop_plans)
    assert (noop_out[0].written, noop_out[0].state) == ((), ProjectionState.IN_SYNC)

    # User edits outside managed spans; renderer advances to v2 -> UPDATE preserves user bytes & pre-image
    claude_md = env.checkout_dir / "CLAUDE.md"
    claude_md.write_bytes(b"# Team Header\n\n" + claude_md.read_bytes() + b"\nFooter prose\n")
    (env.checkout_dir / ".claude/settings.json").write_bytes(
        dumps_merged_json_bytes({"permissions": {"allow": ["Read(v1)"]}, "userKey": 42})
    )
    toml_p = env.checkout_dir / ".codex/config.toml"
    toml_p.write_text('[user_section]\nkeep = true\n\n[skm]\nprofile = "v1"\n', encoding="utf-8")

    env.targets[TargetId.CLAUDE_CODE].files = _default_claude_files("v2")
    upd_plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,))
    upd_out = apply_projection(env.ctx, upd_plans)
    assert upd_out[0].state is ProjectionState.IN_SYNC
    updated_md = claude_md.read_text(encoding="utf-8")
    assert "# Team Header\n" in updated_md
    assert "Core rule v2" in updated_md
    assert "Footer prose\n" in updated_md
    assert '"userKey": 42' in (env.checkout_dir / ".claude/settings.json").read_text(encoding="utf-8")
    updated_toml = toml_p.read_text(encoding="utf-8")
    assert "[user_section]\nkeep = true" in updated_toml
    assert 'profile = "v2"' in updated_toml

    applied = env.ask_applied()
    by_path = {f.relative_path: f for f in applied.files}
    assert by_path["CLAUDE.md"].pre_image_file_version_id is None


def test_conflict_write_new_and_force_conflicts_pre_image(env: HostEnv) -> None:
    apply_projection(
        env.ctx, plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,))
    )
    rule_file = env.checkout_dir / ".claude/rules/skm-core.md"
    rule_file.write_text("# User edited owned rule\n", encoding="utf-8")
    env.targets[TargetId.CLAUDE_CODE].files = _default_claude_files("v2")

    c_plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,))
    by_path = {d.relative_path: d.kind for d in c_plans[0].decisions}
    assert by_path[".claude/rules/skm-core.md"] is FileDecisionKind.CONFLICT_WRITE_NEW

    c_out = apply_projection(env.ctx, c_plans)
    assert (c_out[0].state, c_out[0].conflicts) == (ProjectionState.DRIFTED, (".claude/rules/skm-core.md",))
    assert rule_file.read_text(encoding="utf-8") == "# User edited owned rule\n"
    assert (env.checkout_dir / ".claude/rules/skm-core.md.skm-new").read_text(encoding="utf-8") == "# v2\n"

    f_plans = plan_projection(
        env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,), force_conflicts=True
    )
    f_out = apply_projection(env.ctx, f_plans)
    assert f_out[0].state is ProjectionState.IN_SYNC
    assert rule_file.read_text(encoding="utf-8") == "# v2\n"
    applied = env.ask_applied()
    rec = next(f for f in applied.files if f.relative_path == ".claude/rules/skm-core.md")
    assert rec.pre_image_file_version_id is not None
    with env.client.open_file_version_content(FileVersionId(rec.pre_image_file_version_id)) as dl:
        assert dl.read() == b"# User edited owned rule\n"


@dataclass(frozen=True)
class ProjectionCli:
    repo: GitRepoFixture
    backend: Backend

    def run(self, *argv: str) -> tuple[int, dict[str, Any]]:
        stdout, stderr = StringIO(), StringIO()
        code = main(
            [*argv, "--json"],
            backend=lambda _options, _env: self.backend,
            environ={},
            stdout=stdout,
            stderr=stderr,
        )
        assert stdout.getvalue(), stderr.getvalue()
        return code, json.loads(stdout.getvalue())


@pytest.fixture
def projection_cli(env: HostEnv) -> ProjectionCli:
    repo = init_git_repo(env.checkout_dir)
    env.state_dir.mkdir()
    assert isinstance(env.ctx.gateways, GatewayTable)
    host = HostServices(env.ctx.host_id, PortSurface.CLI, env.ctx.gateways, dict, {})
    bound = bind_cli_projections(host, env.state_dir, env.client)
    assert bound is not None
    backend = Backend(
        env.client,
        host_factory=host_context_factory(bound, env.client),
        state_dir=env.state_dir,
        instance_id=env.app.instance_id,
    )
    return ProjectionCli(repo, backend)


def test_project_activate_projects_and_saves_context(env: HostEnv, projection_cli: ProjectionCli) -> None:
    code, result = projection_cli.run("project", "activate", "ws/skm")
    assert code == 0, result
    checkout = result["result"]["checkouts"][0]
    assert checkout["project_id"] == str(env.project_id)
    assert checkout["exclude_updated"]
    assert checkout["outcomes"][0]["state"] == "in_sync"
    assert (env.checkout_dir / "CLAUDE.md").read_bytes()
    assert b"/.skm\n" in (env.checkout_dir / ".git/info/exclude").read_bytes()
    saved = json.loads((env.state_dir / "cli-context.json").read_text())
    assert (saved["workspace_id"], saved["workspace_slug"]) == (str(env.ws_id), "ws")
    assert (saved["project_id"], saved["project_slug"]) == (str(env.project_id), "skm")

    code, result = projection_cli.run("workspace", "sync-projections")
    assert code == 0, result
    assert not result["result"]["checkouts"][0]["exclude_updated"]


def test_workspace_sync_ignores_only_the_exact_conflict_sidecar(
    env: HostEnv, projection_cli: ProjectionCli
) -> None:
    argv = ("workspace", "sync-projections", str(env.ws_id))
    code, result = projection_cli.run(*argv)
    assert code == 0, result
    original = env.checkout_dir / ".claude/rules/skm-core.md"
    original.write_bytes(b"local edit\n")
    env.targets[TargetId.CLAUDE_CODE].files = _default_claude_files("v2")
    code, result = projection_cli.run(*argv)
    assert code == 6
    assert result["result"]["checkouts"][0]["outcomes"][0]["conflicts"] == [".claude/rules/skm-core.md"]
    sidecar = ".claude/rules/skm-core.md.skm-new"
    assert (env.checkout_dir / sidecar).read_bytes() == b"# v2\n"
    assert original.read_bytes() == b"local edit\n"
    runner = projection_cli.repo.runner
    assert runner.run(env.checkout_dir, ("check-ignore", "--", sidecar), check=False).exit_code == 0
    assert runner.run(env.checkout_dir, ("check-ignore", "--", "other.skm-new"), check=False).exit_code == 1
    assert not (env.state_dir / "cli-context.json").exists()


def test_workspace_sync_uses_project_settings_and_skips_unbound_checkouts(
    env: HostEnv, projection_cli: ProjectionCli
) -> None:
    def dispatch(command: object) -> Any:
        return env.client.dispatch(command, idempotency_key=env.client.new_idempotency_key())

    unbound = dispatch(ws_pub.CreateProject(workspace_id=env.ws_id, slug="unbound", title="Unbound"))
    repo = dispatch(ws_pub.RegisterRepository(env.ws_id, "unbound", "https://github.com/org/other.git", None))
    dispatch(
        ws_pub.AttachRepository(
            project_id=unbound.project_id, repository_id=repo.repository_id, mount_name="main"
        )
    )
    code, result = projection_cli.run(
        "config", "set", "integrations.targets", '["codex"]', "--scope", f"project:{env.project_id}", "--yes"
    )
    assert code == 0, result
    code, result = projection_cli.run("workspace", "sync-projections", str(env.ws_id))
    assert code == 0, result
    checkouts = result["result"]["checkouts"]
    assert [row["project_id"] for row in checkouts] == [str(env.project_id)]
    assert [item["target"] for item in checkouts[0]["outcomes"]] == ["codex"]
    assert not (env.checkout_dir / "CLAUDE.md").exists()

    code, result = projection_cli.run("project", "activate", str(unbound.project_id))
    assert code == 6
    assert result["error"]["code"] == "CHECKOUT_UNBOUND"


def test_activate_reports_tracked_files_and_explicit_untrack_recovers(
    env: HostEnv, projection_cli: ProjectionCli
) -> None:
    service_file = ".skm/project.json"
    projection_cli.repo.commit_file(service_file, "checkout data\n")
    project = str(env.project_id)
    code, result = projection_cli.run("project", "activate", project)
    assert code == 6
    assert result["error"]["code"] == "TRACKED_SERVICE_FILE"
    assert result["error"]["details"]["paths"] == [service_file]
    assert result["error"]["details"]["project_id"] == project
    assert result["error"]["details"]["mount"] == "main"
    assert not (env.state_dir / "cli-context.json").exists()
    assert not (env.checkout_dir / "CLAUDE.md").exists()

    code, result = projection_cli.run("integrations", "untrack-service-files", "--project", project)
    assert code == 0, result
    assert result["result"]["untracked"] == [service_file]
    assert (env.checkout_dir / service_file).read_bytes() == b"checkout data\n"
    assert projection_cli.repo.runner.run(env.checkout_dir, ("ls-files",)).stdout == ""
    code, result = projection_cli.run("project", "activate", project)
    assert code == 0, result


def test_adopt_drift_and_remove_restore_pre_image(env: HostEnv) -> None:
    claude_md = env.checkout_dir / "CLAUDE.md"
    claude_md.write_bytes(b"# Existing Unmanaged Guide\n")
    rule_path = env.checkout_dir / ".claude/rules/skm-core.md"
    rule_path.parent.mkdir(parents=True, exist_ok=True)
    rule_path.write_bytes(b"# Existing Unmanaged Rule\n")

    plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,))
    by_path = {d.relative_path: d.kind for d in plans[0].decisions}
    assert by_path["CLAUDE.md"] is FileDecisionKind.UPDATE
    assert by_path[".claude/rules/skm-core.md"] is FileDecisionKind.ADOPT_REQUIRED

    adopted = adopt_file(
        env.ctx,
        project_id=env.project_id,
        target=TargetId.CLAUDE_CODE,
        relative_path=".claude/rules/skm-core.md",
        reason="adopt existing team rule",
    )
    assert adopted["pre_image_file_version_id"]

    with pytest.raises(PreconditionFailed) as exc_info:
        adopt_file(
            env.ctx,
            project_id=env.project_id,
            target=TargetId.CLAUDE_CODE,
            relative_path=".claude/rules/skm-core.md",
            reason="duplicate adopt",
        )
    assert exc_info.value.code is ErrorCode.INVALID_TRANSITION

    out = apply_projection(
        env.ctx, plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,))
    )
    assert out[0].state is ProjectionState.IN_SYNC
    assert "Existing Unmanaged Guide" in claude_md.read_text(encoding="utf-8")
    assert rule_path.read_bytes() == b"# v1\n"

    clean_drift = detect_drift(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,))
    assert (clean_drift[0]["drifted"], clean_drift[0]["state"]) == (0, "in_sync")

    hook_path = env.checkout_dir / ".claude/hooks/pre.sh"
    hook_path.write_text("#!/bin/sh\necho tuned\n", encoding="utf-8")
    drifted = detect_drift(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,))
    assert (drifted[0]["drifted"], drifted[0]["state"]) == (1, "drifted")

    rem = remove_projection(
        env.ctx, project_id=env.project_id, target=TargetId.CLAUDE_CODE, restore_pre_image=True
    )
    assert (rem.state, rem.left_modified) == (ProjectionState.REMOVED, (".claude/hooks/pre.sh",))
    assert hook_path.read_text(encoding="utf-8") == "#!/bin/sh\necho tuned\n"
    assert claude_md.read_bytes() == b"# Existing Unmanaged Guide\n"
    assert rule_path.read_bytes() == b"# Existing Unmanaged Rule\n"

    post_rem_drift = detect_drift(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,))
    assert (post_rem_drift[0]["recorded"], post_rem_drift[0]["state"]) == (False, "removed")


def test_multi_target_shared_skills_and_collision_refusal(env: HostEnv) -> None:
    skill_bnd = ManagedBoundary(Ownership.MANAGED_FILE)
    skill_bytes = b"---\nname: review\n---\nReview code.\n"
    skill_path = ".agents/skills/review/SKILL.md"
    env.targets[TargetId.CLAUDE_CODE].files = (
        make_desired(TargetId.CLAUDE_CODE, Surface.SKILLS, skill_path, skill_bnd, skill_bytes),
    )
    env.targets[TargetId.CODEX].files = (
        make_desired(TargetId.CODEX, Surface.SKILLS, skill_path, skill_bnd, skill_bytes),
    )
    plans = plan_projection(
        env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE, TargetId.CODEX)
    )
    outcomes = apply_projection(env.ctx, plans)
    assert [o.state for o in outcomes] == [ProjectionState.IN_SYNC, ProjectionState.IN_SYNC]
    assert (env.checkout_dir / skill_path).read_bytes() == skill_bytes

    remove_projection(env.ctx, project_id=env.project_id, target=TargetId.CLAUDE_CODE)
    assert (env.checkout_dir / skill_path).read_bytes() == skill_bytes

    env.targets[TargetId.CLAUDE_CODE].files = (
        make_desired(TargetId.CLAUDE_CODE, Surface.INSTRUCTIONS, "AGENTS.md", skill_bnd, b"claude\n"),
    )
    env.targets[TargetId.CODEX].files = (
        make_desired(TargetId.CODEX, Surface.INSTRUCTIONS, "AGENTS.md", skill_bnd, b"codex\n"),
    )
    with pytest.raises(SkmError) as exc_info:
        plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE, TargetId.CODEX))
    assert exc_info.value.code is ErrorCode.INTEGRATION_PATH_COLLISION


def test_unsafe_targets_lock_contention_version_and_cas_conflicts(env: HostEnv, tmp_path: Path) -> None:
    secret = tmp_path / "outside_secret.txt"
    secret.write_text("do-not-touch\n", encoding="utf-8")
    (env.checkout_dir / "CLAUDE.md").symlink_to(secret)
    (env.checkout_dir / "symdir").symlink_to(tmp_path)
    (env.checkout_dir / "adir").mkdir()

    bnd = ManagedBoundary(Ownership.MANAGED_FILE)
    env.targets[TargetId.CLAUDE_CODE].files = (
        make_desired(TargetId.CLAUDE_CODE, Surface.INSTRUCTIONS, "CLAUDE.md", bnd, b"x\n"),
        make_desired(TargetId.CLAUDE_CODE, Surface.INSTRUCTIONS, "symdir/f.md", bnd, b"x\n"),
        make_desired(TargetId.CLAUDE_CODE, Surface.INSTRUCTIONS, "adir", bnd, b"x\n"),
    )
    plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,))
    assert {d.kind for d in plans[0].decisions} == {FileDecisionKind.UNSAFE_TARGET}
    out = apply_projection(env.ctx, plans)
    assert out[0].state is ProjectionState.FAILED
    assert {code for _, code in out[0].failed} == {ErrorCode.INTEGRATION_UNSAFE_TARGET.value}
    assert secret.read_text(encoding="utf-8") == "do-not-touch\n"

    with pytest.raises(SkmError) as git_exc:
        env.fs.write_atomic(".git/config", b"bad", expected_whole_digest=None)
    assert git_exc.value.code is ErrorCode.INTEGRATION_UNSAFE_TARGET

    (env.checkout_dir / "CLAUDE.md").unlink()
    env.targets[TargetId.CLAUDE_CODE].files = (
        make_desired(TargetId.CLAUDE_CODE, Surface.INSTRUCTIONS, "CLAUDE.md", bnd, b"clean\n"),
    )
    clean_plan = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE,))
    locked, release = threading.Event(), threading.Event()

    def _hold() -> None:
        with env.fs.hold_binding_lock(str(env.binding_id)):
            locked.set()
            release.wait(timeout=5.0)

    holder = threading.Thread(target=_hold, daemon=True)
    holder.start()
    assert locked.wait(timeout=2.0)
    try:
        with pytest.raises(Conflict) as lock_exc:
            apply_projection(env.ctx, clean_plan)
        assert lock_exc.value.code is ErrorCode.PROJECTION_CONFLICT
    finally:
        release.set()
        holder.join(timeout=2.0)

    # CAS mismatch between plan and apply -> FAILED; stale row_version -> VERSION_CONFLICT
    (env.checkout_dir / "CLAUDE.md").write_text("concurrent-edit\n", encoding="utf-8")
    cas_out = apply_projection(env.ctx, clean_plan)
    assert cas_out[0].state is ProjectionState.FAILED
    assert cas_out[0].failed == (("CLAUDE.md", ErrorCode.PROJECTION_CONFLICT.value),)
    with pytest.raises(Conflict) as ver_exc:
        apply_projection(env.ctx, clean_plan)
    assert ver_exc.value.code is ErrorCode.VERSION_CONFLICT


def _journal_entry(rel: str, dec: str, new_b: bytes, before: bytes | None = None) -> dict[str, Any]:
    return {
        "relative_path": rel,
        "write_path": rel,
        "decision": dec,
        "surface": "instructions",
        "boundary": {"ownership": "managed_file"},
        "before_whole_digest": None if before is None else sha256_tagged(before),
        "after_whole_digest": sha256_tagged(new_b),
        "after_managed_digest": sha256_tagged(new_b),
        "new_bytes_base64": base64.b64encode(new_b).decode("ascii"),
    }


def test_crash_journal_reconciliation_apply_and_remove(env: HostEnv, tmp_path: Path) -> None:
    bnd = ManagedBoundary(Ownership.MANAGED_FILE)
    f1_bytes, f2_bytes, f3_bytes = b"one\n", b"two-new\n", b"three\n"
    (env.checkout_dir / "f1.md").write_bytes(f1_bytes)
    (env.checkout_dir / "f2.md").write_bytes(b"user-concurrent-C\n")
    outside = tmp_path / "sym_target.txt"
    outside.write_text("safe", encoding="utf-8")
    (env.checkout_dir / "f3.md").symlink_to(outside)

    write_binding_journal(
        env.fs,
        env.binding_id,
        "crash_apply",
        {
            "kind": "apply",
            "stage": "mutating",
            "host_id": str(env.ctx.host_id),
            "project_id": str(env.project_id),
            "checkout_binding_id": str(env.binding_id),
            "target": "claude_code",
            "plan_digest": sha256_tagged(b"p"),
            "desired_digest": sha256_tagged(b"d"),
            "inputs_digest": sha256_tagged(b"i"),
            "renderer_version": "claude_code@1",
            "base_row_version": None,
            "idempotency_key": env.client.new_idempotency_key(),
            "entries": [
                _journal_entry("f1.md", "create", f1_bytes),
                _journal_entry("f2.md", "update", f2_bytes, before=b"two-old\n"),
                _journal_entry("f3.md", "create", f3_bytes),
            ],
        },
    )
    env.targets[TargetId.CODEX].files = (
        make_desired(TargetId.CODEX, Surface.INSTRUCTIONS, "AGENTS.md", bnd, b"codex\n"),
    )
    apply_projection(env.ctx, plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CODEX,)))

    assert (env.fs.list_journals(str(env.binding_id)), (env.checkout_dir / "f2.md").read_bytes()) == (
        (),
        b"user-concurrent-C\n",
    )
    assert (env.checkout_dir / "f2.md.skm-new").read_bytes() == f2_bytes
    applied = env.ask_applied()
    assert applied.projection is not None
    assert (applied.projection.state, [f.relative_path for f in applied.files]) == ("failed", ["f1.md"])

    cut_bytes = b"# User Prose Only\n"
    (env.checkout_dir / "f1.md").write_bytes(cut_bytes)
    write_binding_journal(
        env.fs,
        env.binding_id,
        "crash_remove",
        {
            "kind": "remove",
            "stage": "mutating",
            "project_id": str(env.project_id),
            "projection_id": str(applied.projection.projection_id),
            "checkout_binding_id": str(env.binding_id),
            "target": "claude_code",
            "base_row_version": applied.projection.row_version,
            "idempotency_key": env.client.new_idempotency_key(),
            "entries": [
                {
                    "relative_path": "f1.md",
                    "boundary": {"ownership": "managed_file"},
                    "before_whole_digest": sha256_tagged(f1_bytes),
                    "after_whole_digest": sha256_tagged(cut_bytes),
                    "new_bytes_base64": base64.b64encode(cut_bytes).decode("ascii"),
                }
            ],
        },
    )
    apply_projection(env.ctx, plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CODEX,)))
    after_rem = env.ask_applied()
    assert after_rem.projection is not None
    assert after_rem.projection.state == "removed"
