"""Zero-shadowing preserves user instructions and canonical shared skill bytes."""

import json
from dataclasses import replace

import pytest

from integration.integrations.claude_code.test_host_apply import _LiveClaudeEnv
from integration.integrations.claude_code.test_host_apply import live_claude_env as live_claude_env
from skm.adapters.integrations.claude_code.mcp import render_mcp
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.managed_block import render_block
from skm.modules.integrations.domain.ownership import Ownership
from skm.modules.integrations.domain.projection import ProjectionState
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.host.apply_projection import apply_projection
from skm.modules.integrations.host.plan_projection import plan_projection
from skm.modules.integrations.host.remove_projection import remove_projection
from unit.adapters.integrations.test_skill_invocation_rendering import _inputs


def test_zero_shadowing_apply_and_remove(live_claude_env: _LiveClaudeEnv) -> None:
    env = live_claude_env
    claude = env.checkout_dir / "CLAUDE.md"
    agents = env.checkout_dir / "AGENTS.md"
    claude_user = b"# Claude local\n"
    agents_user = b"# Shared local\n\n<!-- skm:local:start -->\nKeep this.\n<!-- skm:local:end -->\n"
    claude.write_bytes(claude_user)
    agents.write_bytes(agents_user)
    targets = (TargetId.CLAUDE_CODE, TargetId.CODEX, TargetId.CURSOR, TargetId.GEMINI_CLI, TargetId.GROK)
    plans = plan_projection(env.ctx, project_id=env.project_id, targets=targets, preset="dart-project")
    assert all(
        write.boundary.ownership is Ownership.MANAGED_BLOCK
        for plan in plans
        for write in plan.writes
        if write.relative_path in {"CLAUDE.md", "AGENTS.md"}
    )
    outcomes = apply_projection(env.ctx, plans)
    assert all(item.state is ProjectionState.IN_SYNC for item in outcomes), outcomes
    assert claude.read_bytes().startswith(claude_user)
    managed = claude.read_text().splitlines()[1:]
    assert len(managed) == 3
    assert managed[1] == "@AGENTS.md"
    assert agents.read_bytes().startswith(agents_user)
    assert agents.read_text().count("/grill-me") == 1
    assert len(agents.read_text().splitlines()) < 40
    shared = env.checkout_dir / ".agents/skills/to-spec/SKILL.md"
    native = env.checkout_dir / ".claude/skills/to-spec/SKILL.md"
    assert shared.read_bytes() == native.read_bytes()
    assert b"disable-model-invocation: true" in shared.read_bytes()
    assert not shared.is_symlink()
    assert not native.is_symlink()
    assert not (env.checkout_dir / "GEMINI.md").exists()
    for target in targets:
        assert (
            remove_projection(env.ctx, project_id=env.project_id, target=target).state
            is ProjectionState.REMOVED
        )
    assert claude.read_bytes() == claude_user
    assert agents.read_bytes() == agents_user
    assert not shared.exists()


@pytest.mark.parametrize(
    "ref", ["secret://env:FOO", "secret://env/foo", "secret://file/~/token", "secret://keyring/service/token"]
)
def test_claude_rejects_unsupported_or_invalid_secret_refs(ref: str) -> None:
    with pytest.raises(ValidationFailed):
        render_mcp(
            replace(
                _inputs(TargetId.CLAUDE_CODE),
                mcp_servers={"docs": {"command": "docs", "env_refs": {"TOKEN": ref}}},
            )
        )


def test_claude_uses_native_env_reference() -> None:
    inputs = replace(
        _inputs(TargetId.CLAUDE_CODE),
        mcp_servers={"docs": {"command": "docs", "env_refs": {"TOKEN": "secret://env/FOO"}}},
    )
    projected = render_mcp(inputs)
    assert projected is not None
    assert json.loads(projected.managed_bytes)["mcpServers"]["docs"]["env"] == {"TOKEN": "${FOO}"}


def test_presets_replace_preexisting_managed_claude_blocks(live_claude_env: _LiveClaudeEnv) -> None:
    env = live_claude_env
    default_plans = plan_projection(env.ctx, project_id=env.project_id)
    assert apply_projection(env.ctx, default_plans)[0].state is ProjectionState.IN_SYNC
    claude = env.checkout_dir / "CLAUDE.md"
    claude.write_bytes(b"# Personal instructions\n" + claude.read_bytes() + b"\nLocal tail.\n")
    preset_plans = plan_projection(env.ctx, project_id=env.project_id, preset="php-project")
    assert apply_projection(env.ctx, preset_plans)[0].state is ProjectionState.IN_SYNC
    assert claude.read_bytes() == (
        b"# Personal instructions\n\nLocal tail.\n" + render_block("instructions.project", "@AGENTS.md")
    )
