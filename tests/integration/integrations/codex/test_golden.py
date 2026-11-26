"""Golden native-tree byte-for-byte comparison tests for ``CodexTarget`` (P10.03)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from skm.adapters.integrations.codex.target import CodexTarget
from skm.adapters.integrations.registry import TARGETS
from skm.kernel.ids import ProjectId
from skm.modules.integrations.domain.desired import ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookSurfaceId
from skm.modules.integrations.domain.hook_rules import HookMode
from skm.modules.integrations.domain.managed_block import render_block, replace_blocks
from skm.modules.integrations.domain.merged_json import merge_owned_json, parse_json_document
from skm.modules.integrations.domain.merged_toml import merge_owned_toml, parse_toml
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.host.plan_projection import assemble_desired

REPO_ROOT = Path(__file__).resolve().parents[4]
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "integrations" / "codex"
EXAMPLES_DIR = REPO_ROOT / "tests/fixtures/corpus/examples" / "integrations" / "codex"
GOLDEN_PROJECT_ID = ProjectId(UUID("01928f6e-7a3b-7c41-9d2e-5b8a1f3c4d60"))

_CORE_TEXT = (
    "## Swiss Knife Man\n\n"
    "This repository is managed with SKM. Rules for coding agents working here:\n\n"
    "- Plans, decisions and progress live in SKM (`skm plan …`, `skm run …`), "
    "not in ad-hoc files of the repository.\n"
    "- Files under `.claude/skills/` and `.claude/agents/` and every block between "
    "`skm:begin` and `skm:end` markers are\n"
    "  generated: edit the source, then run `skm integrations apply`.\n"
    "- Run the project checks before you finish a change.\n"
    "- The `skm` MCP server gives short-lived project memory (`memory_search`, `memory_remember`) "
    "and the project graph\n"
    "  (`graph_neighbors`, `graph_path`); check `freshness` and `completeness` of a graph answer "
    "before relying on it."
)

_PROJECT_TEXT = (
    "## Project rules\n\n"
    "- Python 3.12; run `uv run pytest -q` and `uv run ruff check` before every commit.\n"
    "- A change of the public HTTP API needs an ADR in `docs/adr/`."
)


def _golden_projection_inputs() -> ProjectionInputs:
    return ProjectionInputs(
        project_id=GOLDEN_PROJECT_ID,
        target=TargetId.CODEX,
        instructions_core={
            "enabled": True,
            "key": "instructions/client-core",
            "version": "2.0.0",
            "content": _CORE_TEXT,
            "sections": [],
        },
        instructions_project={
            "enabled": True,
            "content": _PROJECT_TEXT,
            "project_text": _PROJECT_TEXT,
            "sections": [],
        },
        skills=(
            {
                "key": "skm-planning",
                "version": "2.0.0",
                "digest": "sha256:" + "1" * 64,
                "manifest": {
                    "key": "skm-planning",
                    "description": "Plan structure, ready leaves, and task verification contracts in SKM.",
                },
                "bodies": {
                    "skill.toml": 'key = "skm-planning"\n',
                    "SKILL.md": (GOLDEN_DIR / ".agents/skills/skm-planning/SKILL.md").read_text("utf-8"),
                    "references/plan-schema.md": (
                        GOLDEN_DIR / ".agents/skills/skm-planning/references/plan-schema.md"
                    ).read_text("utf-8"),
                },
            },
            {
                "key": "skm-memory",
                "version": "2.0.0",
                "digest": "sha256:" + "2" * 64,
                "manifest": {
                    "key": "skm-memory",
                    "description": (
                        "Query and record short-lived project memory and graph facts via the skm MCP server."
                    ),
                },
                "bodies": {
                    "skill.toml": 'key = "skm-memory"\n',
                    "SKILL.md": (GOLDEN_DIR / ".agents/skills/skm-memory/SKILL.md").read_text("utf-8"),
                },
            },
            {
                "key": "python-testing",
                "version": "1.0.0",
                "digest": "sha256:" + "3" * 64,
                "manifest": {
                    "key": "python-testing",
                    "description": (
                        "Pytest conventions, fixtures, and deterministic assertions for Python 3.12 services."
                    ),
                },
                "bodies": {
                    "skill.toml": 'key = "python-testing"\n',
                    "SKILL.md": (GOLDEN_DIR / ".agents/skills/python-testing/SKILL.md").read_text("utf-8"),
                },
            },
        ),
        permissions={
            "digest": "sha256:" + "4" * 64,
            "fs_read": [{"allow": [{"scope": "worktree", "pattern": "**"}], "deny": []}],
            "fs_write": [
                {
                    "allow": [
                        {"scope": "worktree", "pattern": "src/**"},
                        {"scope": "worktree", "pattern": "tests/**"},
                        {"scope": "tmp", "pattern": "**"},
                    ],
                    "deny": [],
                }
            ],
            "commands": {
                "mode": "allowlist",
                "allow": [
                    {"program": "uv", "subcommands": ["run pytest", "run ruff"]},
                    {"program": "git", "subcommands": ["status", "diff"]},
                ],
                "deny_patterns": [],
                "ask_patterns": [],
                "inline_interpreters": ["python", "python3", "node"],
                "trust_inline_interpreters": False,
            },
            "network": {
                "mode": "allowlist",
                "hosts": [["docs.python.org"]],
            },
            "tools": [["fs.read", "fs.edit", "fs.write", "shell.run", "web.fetch"]],
            "operations": {
                "modify_write_set": {"deny": False},
                "git_push": {"deny": False},
            },
            "effects_need_approval": ["git_push"],
        },
        profile=PermissionProfile.WORKSPACE_CONTAINED,
        hook_modes={
            HookSurfaceId.GIT_GUARDRAILS: HookMode.STRICT,
            HookSurfaceId.SAFE_DIRS: HookMode.OFF,
            HookSurfaceId.PLAN_GUARD: HookMode.OFF,
            HookSurfaceId.PACK_GUARD: HookMode.STRICT,
            HookSurfaceId.CHANGELOG_GATE: HookMode.OFF,
            HookSurfaceId.REVIEW_GATE: HookMode.OFF,
            HookSurfaceId.COMMAND_LOG: HookMode.OFF,
            HookSurfaceId.SESSION_CONTEXT: HookMode.WARN,
            HookSurfaceId.RUN_REPORT: HookMode.OFF,
        },
        host_subscription_events=(),
        mcp_servers={
            "skm": {
                "enabled": True,
                "type": "stdio",
                "command": "skm",
                "args": ["mcp"],
            },
        },
        agents=(
            {
                "key": "reviewer",
                "name": "skm-reviewer",
                "version": "2.0.0",
                "role": "reviewer",
                "title": "Reviewer",
                "description": (
                    "Reads the sealed output of an attempt against the task contract and reports findings "
                    "with severity and location. Never fixes code itself."
                ),
                "model_class": "implementation",
                "effort": "high",
                "digest": "sha256:" + "5" * 64,
            },
        ),
        inputs_digest="sha256:" + "b" * 64,
        config_generation=1,
        diagnostics=(),
    )


def test_golden_examples_match_spec_examples() -> None:
    """Golden fixtures stay aligned byte-for-byte with the Codex contract examples."""
    assert (GOLDEN_DIR / "AGENTS.md").read_bytes() == (EXAMPLES_DIR / "AGENTS.md").read_bytes()
    assert (GOLDEN_DIR / ".codex/config.toml").read_bytes() == (EXAMPLES_DIR / "config.toml").read_bytes()
    assert (GOLDEN_DIR / ".codex/hooks.json").read_bytes() == (EXAMPLES_DIR / "hooks.json").read_bytes()


def test_render_and_merge_match_golden_tree_byte_for_byte() -> None:
    """Rendering all 6 Codex surfaces and merging onto user files reproduces the golden tree."""
    target = TARGETS["codex"]
    assert isinstance(target, CodexTarget)

    inputs = _golden_projection_inputs()
    files = target.render(inputs)
    desired = assemble_desired(
        TargetId.CODEX,
        inputs,
        files,
        renderer_version=target.renderer_version,
        capabilities=target.capabilities(),
    )

    by_path = {f.relative_path: f for f in desired.files}
    assert set(by_path) == {
        ".agents/skills/python-testing/SKILL.md",
        ".agents/skills/skm-memory/SKILL.md",
        ".agents/skills/skm-planning/SKILL.md",
        ".agents/skills/skm-planning/references/plan-schema.md",
        ".codex/agents/skm-reviewer.toml",
        ".codex/config.toml",
        ".codex/hooks.json",
        "AGENTS.md",
    }
    assert not any(p.endswith("skill.toml") for p in by_path)

    pre_existing_agents_md = (
        b"# Demo service (Codex)\n\n"
        b"Notes written by people stay here: skm never changes text outside its own blocks.\n\n"
        + render_block("instructions.core", "Old core")
        + render_block("instructions.project", "Old project")
    )
    agents_df = by_path["AGENTS.md"]
    merged_agents_md = replace_blocks(
        pre_existing_agents_md, agents_df.managed_bytes, agents_df.boundary.block_ids
    )
    assert merged_agents_md == (GOLDEN_DIR / "AGENTS.md").read_bytes()

    pre_existing_config_toml = (
        "# Project Codex configuration. Keys owned by skm (merged_toml): "
        "approval_policy, sandbox_mode, [mcp_servers.skm].\n"
        "# Everything else belongs to people and is kept byte for byte.\n"
        'approval_policy = "untrusted"\n'
        'sandbox_mode = "read-only"\n'
        'model_reasoning_effort = "medium"\n\n'
        "[features]\n"
        "hooks = true\n\n"
        "[mcp_servers.skm]\n"
        'command = "old-skm"\n'
        'args = ["old"]\n\n'
        "[mcp_servers.docs-search]\n"
        'command = "npx"\n'
        'args = ["-y", "@example/docs-mcp"]\n'
    )
    cfg_df = by_path[".codex/config.toml"]
    merged_cfg = merge_owned_toml(
        pre_existing_config_toml,
        parse_toml(cfg_df.managed_bytes.decode("utf-8")),
        cfg_df.boundary.owned_keys,
    ).encode("utf-8")
    assert merged_cfg == (GOLDEN_DIR / ".codex/config.toml").read_bytes()

    pre_existing_hooks = (
        json.dumps(
            {
                "description": "Hooks registered by people and by skm",
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "^Bash$",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": (
                                        "skm-hook PreToolUse --target codex"
                                        " --surface stale.hook --project old"
                                    ),
                                }
                            ],
                        }
                    ]
                },
            },
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )
    hooks_df = by_path[".codex/hooks.json"]
    merged_hooks = merge_owned_json(
        pre_existing_hooks,
        parse_json_document(hooks_df.managed_bytes),
        hooks_df.boundary.owned_keys,
    ).encode("utf-8")
    assert merged_hooks == (GOLDEN_DIR / ".codex/hooks.json").read_bytes()

    for rel in (
        ".agents/skills/skm-planning/SKILL.md",
        ".agents/skills/skm-planning/references/plan-schema.md",
        ".agents/skills/skm-memory/SKILL.md",
        ".agents/skills/python-testing/SKILL.md",
        ".codex/agents/skm-reviewer.toml",
    ):
        assert by_path[rel].managed_bytes == (GOLDEN_DIR / rel).read_bytes()
