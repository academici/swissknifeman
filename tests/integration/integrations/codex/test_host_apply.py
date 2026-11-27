"""End-to-end bus + host projection lifecycle tests with real ``CodexTarget`` (P10.03)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
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
from skm.modules.integrations.generated.queries import GetAppliedState
from skm.modules.integrations.generated.views import AppliedStateView
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
OWNER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d9"))

_PROJECT_TEXT = (
    "## Project rules\n\n"
    "- Python 3.12; run `uv run pytest -q` and `uv run ruff check` before every commit.\n"
    "- A change of the public HTTP API needs an ADR in `docs/adr/`."
)


@dataclass
class _LiveCodexEnv:
    app: App
    client: SkmClient
    ctx: HostContext
    checkout_dir: Path
    project_id: ProjectId
    binding_id: ws_pub.CheckoutBindingId


@pytest.fixture
def live_codex_env(tmp_path: Path) -> Iterator[_LiveCodexEnv]:
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
        with app.uow_factory(RequestMeta("req_" + "1" * 26, PortSurface.CLI, None, NOW)) as uow:
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
            log=get_logger("test.codex"),
        )
        yield _LiveCodexEnv(
            app=app,
            client=client,
            ctx=ctx,
            checkout_dir=checkout_dir,
            project_id=proj_id,
            binding_id=binding_id,
        )
    finally:
        app.close()


def test_apply_idempotency_foreign_toml_comments_and_secret_refs(live_codex_env: _LiveCodexEnv) -> None:
    """First apply preserves foreign TOML comments/tables, prose, and hooks; repeat apply is NOOP."""
    env = live_codex_env
    checkout = env.checkout_dir

    initial_agents_md = "# Human Codex Notes\n\nKeep these human instructions verbatim.\n"
    (checkout / "AGENTS.md").write_text(initial_agents_md, encoding="utf-8")

    (checkout / ".codex").mkdir(parents=True, exist_ok=True)
    initial_config_toml = (
        "# Team comment line 1\n"
        "# Team comment line 2\n"
        'model_reasoning_effort = "high"\n\n'
        "[features]\n"
        "# Keep feature flags untouched\n"
        "hooks = true\n\n"
        "[mcp_servers.docs-search]\n"
        "# Custom team MCP server\n"
        'command = "npx"\n'
        'args = ["-y", "@example/docs-mcp"]\n'
    )
    (checkout / ".codex" / "config.toml").write_text(initial_config_toml, encoding="utf-8")

    initial_hooks = {
        "description": "Hooks registered by people and by skm",
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "^Bash$",
                    "hooks": [{"type": "command", "command": "./scripts/team-audit.sh"}],
                }
            ]
        },
    }
    (checkout / ".codex" / "hooks.json").write_text(
        json.dumps(initial_hooks, indent=2) + "\n", encoding="utf-8"
    )

    unmanaged_skill = checkout / ".agents" / "skills" / "team-release-notes" / "SKILL.md"
    unmanaged_skill.parent.mkdir(parents=True, exist_ok=True)
    unmanaged_bytes = b"---\nname: team-release-notes\ndescription: Hand-crafted skill\n---\n# Keep me\n"
    unmanaged_skill.write_bytes(unmanaged_bytes)

    plans1 = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CODEX,))
    out1 = apply_projection(env.ctx, plans1)
    assert out1[0].state is ProjectionState.IN_SYNC

    agents_text = (checkout / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_text.startswith(initial_agents_md)
    assert "<!-- skm:begin id=instructions.core " in agents_text
    assert "<!-- skm:begin id=instructions.project " in agents_text

    cfg_text = (checkout / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "# Team comment line 1\n# Team comment line 2\n" in cfg_text
    assert 'model_reasoning_effort = "high"\n' in cfg_text
    assert "[features]\n# Keep feature flags untouched\nhooks = true\n" in cfg_text
    assert '[mcp_servers.docs-search]\n# Custom team MCP server\ncommand = "npx"\n' in cfg_text
    assert 'approval_policy = "never"\n' in cfg_text
    assert 'sandbox_mode = "workspace-write"\n' in cfg_text
    assert "secret://env/GITHUB_TOKEN" in cfg_text
    assert "ghp_SUPER_SECRET_MUST_NEVER_APPEAR" not in cfg_text

    written_hooks = json.loads((checkout / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    assert written_hooks["description"] == "Hooks registered by people and by skm"
    pre_hooks = written_hooks["hooks"]["PreToolUse"]
    assert pre_hooks[0]["hooks"][0]["command"] == "./scripts/team-audit.sh"
    assert any("lifecycle.git_guardrails" in h["hooks"][0]["command"] for h in pre_hooks[1:])

    assert (checkout / ".agents" / "skills" / "spec-review" / "SKILL.md").is_file()
    assert not (checkout / ".agents" / "skills" / "spec-review" / "skill.toml").exists()
    assert (checkout / ".codex" / "agents" / "skm-reviewer.toml").is_file()
    assert unmanaged_skill.read_bytes() == unmanaged_bytes

    noop_plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CODEX,))
    assert {d.kind for d in noop_plans[0].decisions} == {FileDecisionKind.NOOP}
    out2 = apply_projection(env.ctx, noop_plans)
    assert out2[0].state is ProjectionState.IN_SYNC
    assert out2[0].written == ()


def test_drift_skm_new_and_remove_pre_image_restore(live_codex_env: _LiveCodexEnv) -> None:
    """Manual edits trigger ``.skm-new`` / ``LEAVE_MODIFIED`` on update, and ``remove`` restores pre-image."""
    env = live_codex_env
    checkout = env.checkout_dir

    (checkout / ".codex").mkdir(parents=True, exist_ok=True)
    initial_config_toml = (
        '# User config before skm\nmodel_reasoning_effort = "medium"\n\n[features]\nhooks = true\n'
    )
    (checkout / ".codex" / "config.toml").write_text(initial_config_toml, encoding="utf-8")
    initial_hooks_bytes = b'{\n  "description": "User hooks"\n}\n'
    (checkout / ".codex" / "hooks.json").write_bytes(initial_hooks_bytes)

    apply_projection(env.ctx, plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CODEX,)))

    agent_path = checkout / ".codex" / "agents" / "skm-reviewer.toml"
    hand_edited_agent = agent_path.read_bytes() + b"# local tweak\n"
    agent_path.write_bytes(hand_edited_agent)

    agents_md = checkout / "AGENTS.md"
    edited_agents_md = agents_md.read_text(encoding="utf-8").replace(
        "Python 3.12;", "Python 3.12 (hand-edited);"
    )
    agents_md.write_text(edited_agents_md, encoding="utf-8")

    proj_scope = SetValueDefsScopeRef(level="project", scope_id=UUID(str(env.project_id)))
    env.client.dispatch(
        SetValue(scope=proj_scope, key="integrations.agents.pack_prefix", value="team", reason="prefix"),
        idempotency_key=env.client.new_idempotency_key(),
    )
    env.client.dispatch(
        SetValue(
            scope=proj_scope,
            key="integrations.instructions.project_text",
            value=_PROJECT_TEXT + "\n- Keep public schemas versioned.",
            reason="update project rules",
        ),
        idempotency_key=env.client.new_idempotency_key(),
    )

    drift_plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CODEX,))
    out = apply_projection(env.ctx, drift_plans)
    assert out[0].state is ProjectionState.DRIFTED
    assert (checkout / "AGENTS.md.skm-new").is_file()
    assert agents_md.read_text(encoding="utf-8") == edited_agents_md
    assert agent_path.read_bytes() == hand_edited_agent
    assert (checkout / ".codex" / "agents" / "team-reviewer.toml").is_file()

    rem = remove_projection(
        env.ctx,
        project_id=env.project_id,
        target=TargetId.CODEX,
        restore_pre_image=True,
    )
    assert rem.state is ProjectionState.REMOVED
    assert (checkout / ".codex" / "config.toml").read_text(encoding="utf-8") == initial_config_toml
    assert (checkout / ".codex" / "hooks.json").read_bytes() == initial_hooks_bytes

    applied = env.client.ask(
        GetAppliedState(
            project_id=env.project_id,
            checkout_binding_id=env.binding_id,
            target=cast("Any", "codex"),
        )
    )
    assert isinstance(applied, AppliedStateView)
    assert applied.projection is not None
    assert applied.projection.state == "removed"
