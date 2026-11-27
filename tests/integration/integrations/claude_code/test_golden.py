"""Golden native-tree byte-for-byte comparison tests for ``ClaudeCodeTarget`` (P10.02)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from skm.adapters.integrations.claude_code.target import ClaudeCodeTarget
from skm.adapters.integrations.registry import TARGETS
from skm.kernel.ids import ProjectId
from skm.modules.integrations.domain.desired import HostSubscriptionEvent, ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookClass, HookEventKind, HookSurfaceId
from skm.modules.integrations.domain.hook_rules import HookMode
from skm.modules.integrations.domain.managed_block import render_block, replace_blocks
from skm.modules.integrations.domain.merged_json import merge_owned_json, parse_json_document
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.host.plan_projection import assemble_desired

REPO_ROOT = Path(__file__).resolve().parents[4]
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "integrations" / "claude_code"
EXAMPLES_DIR = REPO_ROOT / "tests/fixtures/corpus/examples" / "integrations" / "claude_code"
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
        target=TargetId.CLAUDE_CODE,
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
                    "SKILL.md": (GOLDEN_DIR / ".claude/skills/skm-planning/SKILL.md").read_text("utf-8"),
                    "references/plan-schema.md": (
                        GOLDEN_DIR / ".claude/skills/skm-planning/references/plan-schema.md"
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
                    "SKILL.md": (GOLDEN_DIR / ".claude/skills/skm-memory/SKILL.md").read_text("utf-8"),
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
                    "SKILL.md": (GOLDEN_DIR / ".claude/skills/python-testing/SKILL.md").read_text("utf-8"),
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
            "tools": [["fs.read", "fs.edit", "fs.write", "shell.run", "web.fetch", "TodoWrite"]],
            "operations": {
                "modify_write_set": {"deny": False},
                "git_push": {"deny": False},
            },
            "effects_need_approval": ["git_push"],
        },
        profile=PermissionProfile.WORKSPACE_CONTAINED,
        hook_modes={
            HookSurfaceId.GIT_GUARDRAILS: HookMode.STRICT,
            HookSurfaceId.SAFE_DIRS: HookMode.STRICT,
            HookSurfaceId.PLAN_GUARD: HookMode.STRICT,
            HookSurfaceId.PACK_GUARD: HookMode.WARN,
            HookSurfaceId.CHANGELOG_GATE: HookMode.OFF,
            HookSurfaceId.REVIEW_GATE: HookMode.WARN,
            HookSurfaceId.COMMAND_LOG: HookMode.OFF,
            HookSurfaceId.SESSION_CONTEXT: HookMode.WARN,
            HookSurfaceId.RUN_REPORT: HookMode.OFF,
        },
        host_subscription_events=(
            HostSubscriptionEvent(
                kind=HookEventKind.PRE_SHELL,
                classes=(HookClass.ENFORCEMENT,),
            ),
        ),
        mcp_servers={
            "github": {
                "enabled": True,
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env_refs": {"GITHUB_TOKEN": "secret://env/GITHUB_TOKEN"},
            },
            "skm": {
                "enabled": True,
                "type": "stdio",
                "command": "skm",
                "args": ["mcp", "serve"],
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
        inputs_digest="sha256:" + "a" * 64,
        config_generation=1,
        diagnostics=(),
    )


def test_golden_examples_match_spec_examples() -> None:
    """Golden fixtures stay aligned with ``tests/fixtures/corpus/examples/integrations/claude_code/``."""
    assert (GOLDEN_DIR / "CLAUDE.md").read_bytes() == (EXAMPLES_DIR / "CLAUDE.md").read_bytes()
    golden_settings = (GOLDEN_DIR / ".claude/settings.json").read_bytes()
    assert golden_settings == (EXAMPLES_DIR / "settings.json").read_bytes()
    assert (GOLDEN_DIR / ".claude/settings.local.json").read_bytes() == (
        EXAMPLES_DIR / "settings.local.json"
    ).read_bytes()


def test_render_and_merge_match_golden_tree_byte_for_byte() -> None:
    """Rendering all 6 Claude Code surfaces and merging onto user files reproduces the golden tree."""
    target = TARGETS["claude_code"]
    assert isinstance(target, ClaudeCodeTarget)

    inputs = _golden_projection_inputs()
    files = target.render(inputs)
    desired = assemble_desired(
        TargetId.CLAUDE_CODE,
        inputs,
        files,
        renderer_version=target.renderer_version,
        capabilities=target.capabilities(),
    )

    by_path = {f.relative_path: f for f in desired.files}
    assert set(by_path) == {
        ".claude/agents/skm-reviewer.md",
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".claude/skills/python-testing/SKILL.md",
        ".claude/skills/skm-memory/SKILL.md",
        ".claude/skills/skm-planning/SKILL.md",
        ".claude/skills/skm-planning/references/plan-schema.md",
        ".mcp.json",
        "CLAUDE.md",
    }
    assert not any(p.endswith("skill.toml") for p in by_path)

    pre_existing_claude_md = (
        b"# Demo service\n\n"
        b"Notes written by people stay here: skm never changes text outside its own blocks.\n\n"
        + render_block("instructions.core", "Old core")
        + render_block("instructions.project", "Old project")
        + b"\n## Local tips\n\n- `make dev` starts the stack on port 8080.\n"
    )
    claude_df = by_path["CLAUDE.md"]
    merged_claude = replace_blocks(
        pre_existing_claude_md, claude_df.managed_bytes, claude_df.boundary.block_ids
    )
    assert merged_claude == (GOLDEN_DIR / "CLAUDE.md").read_bytes()

    pre_existing_settings = (
        json.dumps(
            {
                "$schema": "https://json.schemastore.org/claude-code-settings.json",
                "includeCoAuthoredBy": False,
                "permissions": {"allow": ["Read(README.md)"]},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": "./scripts/team-audit.sh"}],
                        },
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": (
                                        "skm-hook PreToolUse --target claude_code"
                                        " --surface stale.hook --project old"
                                    ),
                                }
                            ],
                        },
                    ]
                },
            },
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )
    settings_df = by_path[".claude/settings.json"]
    merged_settings = merge_owned_json(
        pre_existing_settings,
        parse_json_document(settings_df.managed_bytes),
        settings_df.boundary.owned_keys,
    ).encode("utf-8")
    expected_settings = json.loads((GOLDEN_DIR / ".claude/settings.json").read_bytes())
    safe_dirs = next(
        group
        for group in expected_settings["hooks"]["PreToolUse"]
        if any("security.safe_dirs" in hook["command"] for hook in group["hooks"])
    )
    safe_dirs["matcher"] = "Edit|Write|MultiEdit|Bash"
    assert json.loads(merged_settings) == expected_settings

    local_df = by_path[".claude/settings.local.json"]
    merged_local = merge_owned_json(
        b"{}\n",
        parse_json_document(local_df.managed_bytes),
        local_df.boundary.owned_keys,
    ).encode("utf-8")
    assert merged_local == (GOLDEN_DIR / ".claude/settings.local.json").read_bytes()

    pre_existing_mcp = (
        json.dumps(
            {
                "mcpServers": {
                    "postgres-local": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-postgres"],
                    }
                }
            },
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )
    mcp_df = by_path[".mcp.json"]
    merged_mcp = merge_owned_json(
        pre_existing_mcp,
        parse_json_document(mcp_df.managed_bytes),
        mcp_df.boundary.owned_keys,
    ).encode("utf-8")
    expected_mcp = (
        (GOLDEN_DIR / ".mcp.json").read_bytes().replace(b"secret://env/GITHUB_TOKEN", b"${GITHUB_TOKEN}")
    )
    assert merged_mcp == expected_mcp

    for rel in (
        ".claude/skills/skm-planning/SKILL.md",
        ".claude/skills/skm-planning/references/plan-schema.md",
        ".claude/skills/skm-memory/SKILL.md",
        ".claude/skills/python-testing/SKILL.md",
        ".claude/agents/skm-reviewer.md",
    ):
        assert by_path[rel].managed_bytes == (GOLDEN_DIR / rel).read_bytes()
