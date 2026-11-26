"""End-to-end bus + host projection lifecycle and cross-target tests with ``CursorTarget`` (P10.04.a)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from contracts.extensions.harness import FakeEstimator
from fakes.clock import FrozenClock
from skm.adapters.checkout_fs.local import LocalCheckoutFs
from skm.adapters.integrations.registry import default_target_registry
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.adapters.resources.pack_reader import FilesystemPackReader
from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext, HostServices
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, PrincipalId, ProjectId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta
from skm.kernel.ports_uow import Surface as PortSurface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.ports import BuiltinPacks, PackReader
from skm.modules.integrations.domain.decisions import FileDecisionKind
from skm.modules.integrations.domain.projection import ProjectionState
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.host.apply_projection import apply_projection
from skm.modules.integrations.host.plan_projection import plan_projection
from skm.modules.integrations.host.registry import HOST_OPERATIONS
from skm.modules.integrations.host.remove_projection import remove_projection
from skm.modules.integrations.ports import CheckoutFs, IntegrationTargetRegistry
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.workspace import public as ws_pub
from skm.modules.workspace.generated.commands import HostArch, HostOs, RegisterHostDefsHostPlatform
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.logging.logger import get_logger
from support.seed import SEED

REPO_ROOT = Path(__file__).resolve().parents[4]
PACKS_ROOT = REPO_ROOT / "resources" / "packs"
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
OWNER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000da"))

_PROJECT_TEXT = (
    "## Project rules\n\n"
    "- Python 3.12; run `uv run pytest -q` and `uv run ruff check` before every commit.\n"
    "- A change of the public HTTP API needs an ADR in `docs/adr/`."
)


@dataclass
class _LiveCursorEnv:
    app: App
    client: SkmClient
    ctx: HostContext
    host_id: HostId
    fs: LocalCheckoutFs
    checkout_dir: Path
    project_id: ProjectId
    binding_id: ws_pub.CheckoutBindingId


@pytest.fixture
def live_cursor_env(tmp_path: Path) -> Iterator[_LiveCursorEnv]:
    clock = FrozenClock(NOW)
    bs_env = {"SKM_DATABASE_URL": "postgresql://127.0.0.1:5432/mem"}
    bs = replace(
        load_bootstrap(None, bs_env, tmp_path / "boot"),
        instance_id=SEED.instance_id,
        database_pool_min_size=0,
        database_pool_max_size=2,
    )
    cp_gateways = GatewayTable(
        {
            BuiltinPacks: PackagedBuiltinPacks(PACKS_ROOT),
            PackReader: FilesystemPackReader(),
            TokenEstimator: FakeEstimator(),
        },
        "control_plane_gateway",
    )
    ov = CompositionOverrides(
        authorizer=RbacAuthorizer(clock),
        scopes=StoredScopeChain(),
        clock=clock,
        instance_id=SEED.instance_id,
        gateways=cp_gateways,
    )
    app = build_app(
        bs,
        surface=PortSurface.CLI,
        environ={"GITHUB_TOKEN": "ghp_SUPER_SECRET_MUST_NEVER_APPEAR"},
        invocation={},
        backend=None,
        overrides=ov,
    )
    try:
        with app.uow_factory(RequestMeta("req_" + "2" * 26, PortSurface.CLI, None, NOW)) as uow:
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

        run_cmd(SyncBuiltinPacks())
        ws_id = WorkspaceId(run_cmd(ws_pub.CreateWorkspace(slug="ws", title="WS")).workspace_id)
        proj_id = ProjectId(
            run_cmd(ws_pub.CreateProject(workspace_id=ws_id, slug="demo", title="Demo")).project_id
        )
        plat = RegisterHostDefsHostPlatform(os=HostOs.LINUX, arch=HostArch.X86_64)
        host_id = HostId(run_cmd(ws_pub.RegisterHost(name="dev", platform=plat)).host_id)
        repo_id = run_cmd(
            ws_pub.RegisterRepository(ws_id, "demo", "https://github.com/org/demo.git", None)
        ).repository_id
        run_cmd(ws_pub.AttachRepository(project_id=proj_id, repository_id=repo_id, mount_name="main"))

        checkout_dir = tmp_path / "checkout"
        (checkout_dir / ".git").mkdir(parents=True)
        binding_id = ws_pub.CheckoutBindingId(
            run_cmd(
                ws_pub.BindCheckout(
                    repo_id,
                    host_id,
                    str(checkout_dir),
                    str(checkout_dir),
                    ("github.com/org/demo",),
                    "a" * 40,
                    False,
                    NOW,
                )
            ).binding_id
        )

        proj_scope = SetValueDefsScopeRef(level="project", scope_id=UUID(str(proj_id)))
        run_cmd(
            SetValue(
                scope=proj_scope,
                key="integrations.instructions.project_text",
                value=_PROJECT_TEXT,
                reason="seed project rules",
            )
        )
        run_cmd(
            SetValue(
                scope=proj_scope,
                key="integrations.mcp.servers",
                value={
                    "github": {
                        "enabled": True,
                        "type": "stdio",
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-github"],
                        "env_refs": {"GITHUB_TOKEN": "secret://env/GITHUB_TOKEN"},
                    }
                },
                reason="seed github mcp",
            )
        )

        state_dir = tmp_path / "state"
        fs = LocalCheckoutFs(checkout_dir, state_dir=state_dir, lock_timeout_seconds=0.1)
        services = HostServices(
            host_id=host_id,
            surface=PortSurface.CLI,
            gateways=GatewayTable(
                {CheckoutFs: fs, IntegrationTargetRegistry: default_target_registry()},
                "host_gateway",
            ),
            host_config=dict,
            operations={spec.name: spec for spec in HOST_OPERATIONS},
        )
        ctx = services.context(
            client=client,
            cancel=CancelSource().token,
            log=get_logger("test.cursor"),
        )
        yield _LiveCursorEnv(
            app=app,
            client=client,
            ctx=ctx,
            host_id=host_id,
            fs=fs,
            checkout_dir=checkout_dir,
            project_id=proj_id,
            binding_id=binding_id,
        )
    finally:
        app.close()


def test_apply_idempotency_foreign_entries_and_secret_refs(live_cursor_env: _LiveCursorEnv) -> None:
    """First apply preserves foreign CLI/MCP/hook entries before SKM entries; second apply is NOOP."""
    env = live_cursor_env
    checkout = env.checkout_dir
    (checkout / ".cursor").mkdir(parents=True, exist_ok=True)

    initial_cli = {"editor": {"vimMode": True}}
    (checkout / ".cursor/cli.json").write_text(json.dumps(initial_cli, indent=2) + "\n", encoding="utf-8")

    initial_hooks = {
        "hooks": {
            "beforeShellExecution": [
                {"command": "./scripts/team-audit.sh", "matcher": r"\bgit\b"},
            ]
        },
    }
    (checkout / ".cursor/hooks.json").write_text(json.dumps(initial_hooks, indent=2) + "\n", encoding="utf-8")

    initial_mcp = {"mcpServers": {"custom-docs": {"command": "npx", "args": ["@org/docs-mcp"]}}}
    (checkout / ".cursor/mcp.json").write_text(json.dumps(initial_mcp, indent=2) + "\n", encoding="utf-8")

    plans1 = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CURSOR,))
    outcomes = apply_projection(env.ctx, plans1)
    assert len(outcomes) == 1
    assert outcomes[0].state is ProjectionState.IN_SYNC
    assert not outcomes[0].conflicts
    assert not outcomes[0].failed
    assert not (checkout / ".cursor/skills").exists()
    assert (checkout / ".cursor/rules/skm-instructions.mdc").is_file()
    assert (checkout / ".cursor/permissions.json").is_file()

    cli_doc = json.loads((checkout / ".cursor/cli.json").read_text(encoding="utf-8"))
    assert cli_doc["editor"] == {"vimMode": True}
    assert "approvalMode" not in cli_doc
    assert "sandbox" not in cli_doc
    assert "Read(.env*)" in cli_doc["permissions"]["deny"]

    hooks_doc = json.loads((checkout / ".cursor/hooks.json").read_text(encoding="utf-8"))
    assert hooks_doc["version"] == 1
    before_shell = hooks_doc["hooks"]["beforeShellExecution"]
    assert before_shell[0] == {"command": "./scripts/team-audit.sh", "matcher": r"\bgit\b"}
    assert any(h.get("command", "").startswith("skm-hook beforeShellExecution") for h in before_shell[1:])

    mcp_raw = (checkout / ".cursor/mcp.json").read_text(encoding="utf-8")
    assert "ghp_SUPER_SECRET_MUST_NEVER_APPEAR" not in mcp_raw
    mcp_doc = json.loads(mcp_raw)
    assert mcp_doc["mcpServers"]["custom-docs"] == {"command": "npx", "args": ["@org/docs-mcp"]}
    assert mcp_doc["mcpServers"]["github"]["env"]["GITHUB_TOKEN"] == "secret://env/GITHUB_TOKEN"

    second_plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CURSOR,))
    assert len(second_plans) == 1
    assert second_plans[0].writes == ()
    assert all(d.kind is FileDecisionKind.NOOP for d in second_plans[0].decisions)

    second_apply = apply_projection(env.ctx, second_plans)
    assert second_apply[0].state is ProjectionState.IN_SYNC
    assert second_apply[0].written == ()

    rem = remove_projection(
        env.ctx, project_id=env.project_id, target=TargetId.CURSOR, restore_pre_image=True
    )
    assert rem.state is ProjectionState.REMOVED
    assert not (checkout / ".cursor/rules/skm-instructions.mdc").exists()
    assert json.loads((checkout / ".cursor/hooks.json").read_text(encoding="utf-8")) == initial_hooks


def test_cross_target_shared_skills_codex_and_cursor_coexist(live_cursor_env: _LiveCursorEnv) -> None:
    """Codex and Cursor share ``.agents/skills/`` without collision and keep shared files on single remove."""
    env = live_cursor_env
    checkout = env.checkout_dir

    plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CODEX, TargetId.CURSOR))
    assert len(plans) == 2

    outcomes = apply_projection(env.ctx, plans)
    assert [o.state for o in outcomes] == [ProjectionState.IN_SYNC, ProjectionState.IN_SYNC]

    shared_skills = list((checkout / ".agents/skills").rglob("SKILL.md"))
    assert len(shared_skills) >= 1

    rem = remove_projection(env.ctx, project_id=env.project_id, target=TargetId.CURSOR)
    assert rem.state is ProjectionState.REMOVED
    for skill_md in shared_skills:
        assert skill_md.is_file()


def test_trusted_full_access_gate_and_drift_sidecar(live_cursor_env: _LiveCursorEnv) -> None:
    """``trusted_full_access`` is refused without host allowlist; drifted managed file writes ``.skm-new``."""
    env = live_cursor_env
    proj_scope = SetValueDefsScopeRef(level="project", scope_id=UUID(str(env.project_id)))

    init_plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CURSOR,))
    apply_projection(env.ctx, init_plans)
    mdc_path = env.checkout_dir / ".cursor/rules/skm-instructions.mdc"
    mdc_path.write_text('---\ndescription: "hand edited"\nalwaysApply: true\n---\n\nEdited.\n', "utf-8")

    env.client.dispatch(
        SetValue(
            scope=proj_scope,
            key="integrations.instructions.project_text",
            value="## Updated project rules\n\n- Always run checks.",
            reason="trigger update",
        ),
        idempotency_key=env.client.new_idempotency_key(),
    )
    drift_plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CURSOR,))
    drifted = apply_projection(env.ctx, drift_plans)
    assert drifted[0].state is ProjectionState.DRIFTED
    assert ".cursor/rules/skm-instructions.mdc" in drifted[0].conflicts
    assert (env.checkout_dir / ".cursor/rules/skm-instructions.mdc.skm-new").is_file()

    inst_scope = SetValueDefsScopeRef(level="instance")
    env.client.dispatch(
        SetValue(
            scope=inst_scope,
            key="integrations.permission_profile",
            value="trusted_full_access",
            confirmed=True,
            reason="request full access",
        ),
        idempotency_key=env.client.new_idempotency_key(),
    )
    refused_plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CURSOR,))
    assert any(
        d.get("code") == ErrorCode.INTEGRATION_TRUSTED_REFUSED.value for d in refused_plans[0].diagnostics
    )

    host_scope = SetValueDefsScopeRef(level="host", scope_id=UUID(str(env.host_id)))
    env.client.dispatch(
        SetValue(
            scope=host_scope,
            key="integrations.trusted_full_access.allowed",
            value=True,
            confirmed=True,
            reason="allow trusted full access on dev host",
        ),
        idempotency_key=env.client.new_idempotency_key(),
    )
    trusted_plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CURSOR,))
    assert not any(
        d.get("code") == ErrorCode.INTEGRATION_TRUSTED_REFUSED.value for d in trusted_plans[0].diagnostics
    )
    apply_projection(env.ctx, trusted_plans)
    cli_doc = json.loads((env.checkout_dir / ".cursor/cli.json").read_text(encoding="utf-8"))
    assert "approvalMode" not in cli_doc
    assert "sandbox" not in cli_doc
    ide_doc = json.loads((env.checkout_dir / ".cursor/permissions.json").read_text(encoding="utf-8"))
    assert "autoRun" not in ide_doc
