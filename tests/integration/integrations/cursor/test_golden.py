"""Golden native-tree byte-for-byte comparison and MDC conformance tests for ``CursorTarget`` (P10.04.a)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from skm.adapters.integrations._render import markdown_rules
from skm.adapters.integrations.codex.target import CodexTarget
from skm.adapters.integrations.cursor.rules import render_mdc_rule, validate_mdc_rule
from skm.adapters.integrations.cursor.target import CursorTarget
from skm.adapters.integrations.registry import TARGETS
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ProjectId
from skm.modules.integrations.domain.desired import ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookSurfaceId
from skm.modules.integrations.domain.hook_rules import HookMode
from skm.modules.integrations.domain.merged_json import merge_owned_json, parse_json_document
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.host.plan_projection import assemble_desired

REPO_ROOT = Path(__file__).resolve().parents[4]
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "integrations" / "cursor"
CODEX_GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "integrations" / "codex"
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
        target=TargetId.CURSOR,
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
        inputs_digest="sha256:" + "c" * 64,
        config_generation=1,
        diagnostics=(),
    )


def test_render_and_merge_match_golden_tree_byte_for_byte() -> None:
    """Rendering all 6 Cursor surfaces and merging onto user files reproduces the golden tree."""
    target = TARGETS["cursor"]
    assert isinstance(target, CursorTarget)

    inputs = _golden_projection_inputs()
    files = target.render(inputs)
    desired = assemble_desired(
        TargetId.CURSOR,
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
        ".cursor/agents/skm-reviewer.md",
        ".cursor/cli.json",
        ".cursor/hooks.json",
        ".cursor/mcp.json",
        ".cursor/permissions.json",
        ".cursor/rules/skm-instructions.mdc",
    }
    assert not any(p.startswith(".cursor/skills/") for p in by_path)
    assert not any(p.endswith("skill.toml") for p in by_path)

    for rel in (
        ".agents/skills/skm-planning/SKILL.md",
        ".agents/skills/skm-planning/references/plan-schema.md",
        ".agents/skills/skm-memory/SKILL.md",
        ".agents/skills/python-testing/SKILL.md",
        ".cursor/agents/skm-reviewer.md",
        ".cursor/permissions.json",
        ".cursor/rules/skm-instructions.mdc",
    ):
        assert by_path[rel].managed_bytes == (GOLDEN_DIR / rel).read_bytes()

    pre_existing_cli = json.dumps(
        {
            "editor": {"vimMode": True},
            "permissions": {"allow": ["Read(old)"], "deny": []},
        },
        indent=2,
    ).encode("utf-8")
    cli_df = by_path[".cursor/cli.json"]
    merged_cli = merge_owned_json(
        pre_existing_cli,
        parse_json_document(cli_df.managed_bytes),
        cli_df.boundary.owned_keys,
    ).encode("utf-8")
    assert merged_cli == (GOLDEN_DIR / ".cursor/cli.json").read_bytes()
    parsed_cli = parse_json_document(merged_cli)
    assert "approvalMode" not in parsed_cli
    assert "sandbox" not in parsed_cli

    pre_existing_hooks = json.dumps(
        {
            "version": 1,
            "hooks": {
                "beforeShellExecution": [
                    {"command": "./scripts/local-audit.sh", "matcher": r"\bgit\b"},
                    {
                        "command": (
                            "skm-hook beforeShellExecution --target cursor --surface stale.hook --project old"
                        ),
                        "matcher": r"\bgit\b",
                    },
                ]
            },
        },
        indent=2,
    ).encode("utf-8")
    hooks_df = by_path[".cursor/hooks.json"]
    merged_hooks = merge_owned_json(
        pre_existing_hooks,
        parse_json_document(hooks_df.managed_bytes),
        hooks_df.boundary.owned_keys,
    ).encode("utf-8")
    assert merged_hooks == (GOLDEN_DIR / ".cursor/hooks.json").read_bytes()

    pre_existing_mcp = json.dumps(
        {
            "mcpServers": {
                "docs-search": {"command": "npx", "args": ["-y", "@example/docs-mcp"]},
                "skm": {"command": "stale-skm", "args": ["old"]},
            }
        },
        indent=2,
    ).encode("utf-8")
    mcp_df = by_path[".cursor/mcp.json"]
    merged_mcp = merge_owned_json(
        pre_existing_mcp,
        parse_json_document(mcp_df.managed_bytes),
        mcp_df.boundary.owned_keys,
    ).encode("utf-8")
    assert merged_mcp == (GOLDEN_DIR / ".cursor/mcp.json").read_bytes()


def test_canonical_skills_match_codex_bytes_and_digests() -> None:
    """Cursor and Codex produce identical ``.agents/skills/`` boundaries, bytes, and digests."""
    cursor_inputs = _golden_projection_inputs()
    codex_inputs = replace(cursor_inputs, target=TargetId.CODEX)

    cursor_skills = {
        f.relative_path: f
        for f in CursorTarget().render(cursor_inputs)
        if f.relative_path.startswith(".agents/")
    }
    codex_skills = {
        f.relative_path: f
        for f in CodexTarget().render(codex_inputs)
        if f.relative_path.startswith(".agents/")
    }

    assert set(cursor_skills) == set(codex_skills)
    for rel, cur_df in cursor_skills.items():
        cdx_df = codex_skills[rel]
        assert cur_df.boundary == cdx_df.boundary
        assert cur_df.managed_bytes == cdx_df.managed_bytes
        assert cur_df.managed_digest == cdx_df.managed_digest
        assert cur_df.managed_bytes == (CODEX_GOLDEN_DIR / rel).read_bytes()


def test_mdc_frontmatter_conformance_and_validation() -> None:
    """``.mdc`` frontmatter validates ``description``, ``globs``, and ``alwaysApply: true``."""
    mdc_bytes = (GOLDEN_DIR / ".cursor/rules/skm-instructions.mdc").read_bytes()
    meta = validate_mdc_rule(mdc_bytes, require_always_apply=True)
    assert meta == {
        "description": "Repository instructions and guidelines",
        "alwaysApply": True,
    }

    scoped_rule = render_mdc_rule(
        "python-style",
        description="Scoped Python rule",
        body="Use type annotations.",
        always_apply=False,
        globs=["src/**/*.py", "tests/**/*.py"],
    )
    parsed_meta, parsed_body = markdown_rules.parse_frontmatter(scoped_rule.managed_bytes.decode("utf-8"))
    assert parsed_meta == {
        "description": "Scoped Python rule",
        "globs": ["src/**/*.py", "tests/**/*.py"],
        "alwaysApply": False,
    }
    assert parsed_body.strip() == "Use type annotations."

    with pytest.raises(ValidationFailed) as exc_always:
        validate_mdc_rule(scoped_rule.managed_bytes, require_always_apply=True)
    assert exc_always.value.code is ErrorCode.INTEGRATION_BOUNDARY_INVALID

    with pytest.raises(ValidationFailed) as exc_unknown:
        validate_mdc_rule('---\ndescription: "x"\nunknownKey: 1\n---\nbody\n')
    assert exc_unknown.value.code is ErrorCode.INTEGRATION_BOUNDARY_INVALID

    with pytest.raises(ValidationFailed) as exc_slug:
        render_mdc_rule("../escape", description="bad", body="x")
    assert exc_slug.value.code is ErrorCode.INTEGRATION_UNSAFE_TARGET
