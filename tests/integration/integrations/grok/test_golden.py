"""Golden tree comparison, capabilities, and idempotency tests for ``GrokTarget`` (P10.04.b)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from skm.adapters.checkout_fs.local import LocalCheckoutFs
from skm.adapters.integrations.codex.target import CodexTarget
from skm.adapters.integrations.cursor.target import CursorTarget
from skm.adapters.integrations.grok.rules import render_markdown_rule
from skm.adapters.integrations.grok.target import GrokTarget
from skm.adapters.integrations.registry import TARGETS
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ProjectId
from skm.modules.integrations.domain.decisions import FileDecisionKind, decide_file
from skm.modules.integrations.domain.desired import ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookSurfaceId
from skm.modules.integrations.domain.hook_rules import HookMode
from skm.modules.integrations.domain.merged_toml import merge_owned_toml, parse_toml
from skm.modules.integrations.domain.observed import AppliedFileRecord
from skm.modules.integrations.domain.ownership import sha256_tagged
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.integrations.domain.projection import ProjectionId, build_planned_write
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.host.observe import observe_path
from skm.modules.integrations.host.plan_projection import assemble_desired

REPO_ROOT = Path(__file__).resolve().parents[4]
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "integrations" / "grok"
CODEX_GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "integrations" / "codex"
GOLDEN_PROJECT_ID = ProjectId(UUID("01928f6e-7a3b-7c41-9d2e-5b8a1f3c4d60"))
TEST_PROJECTION_ID = ProjectionId(UUID("01928f6e-7a3b-7c41-9d2e-5b8a1f3c4d99"))

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
        target=TargetId.GROK,
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
        inputs_digest="sha256:" + "d" * 64,
        config_generation=1,
        diagnostics=(),
    )


def test_render_and_merge_match_golden_tree_and_report_unsupported_agents() -> None:
    """Rendering Grok surfaces matches golden tree byte-for-byte and emits zero agent files."""
    target = TARGETS["grok"]
    assert isinstance(target, GrokTarget)

    inputs = _golden_projection_inputs()
    files = target.render(inputs)
    desired = assemble_desired(
        TargetId.GROK,
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
        ".grok/config.toml",
        ".grok/hooks/skm.json",
        ".grok/rules/skm-instructions.md",
    }
    assert not any(f.surface is Surface.AGENTS for f in desired.files)
    assert not any(p.startswith(".grok/agents/") or p.startswith(".agents/agents/") for p in by_path)
    assert not any(p.endswith("skill.toml") for p in by_path)

    cap_diags = [d for d in desired.diagnostics if d.get("code") == "CAPABILITY_UNAVAILABLE"]
    assert len(cap_diags) == 1
    assert cap_diags[0]["severity"] == "info"
    assert cap_diags[0]["surface"] == "agents"

    for rel in (
        ".agents/skills/skm-planning/SKILL.md",
        ".agents/skills/skm-planning/references/plan-schema.md",
        ".agents/skills/skm-memory/SKILL.md",
        ".agents/skills/python-testing/SKILL.md",
        ".grok/hooks/skm.json",
        ".grok/rules/skm-instructions.md",
    ):
        assert by_path[rel].managed_bytes == (GOLDEN_DIR / rel).read_bytes()

    pre_existing_config_toml = (
        "# Project Grok configuration. Tables owned by skm (merged_toml): [permission], [mcp_servers.skm].\n"
        "# Everything else belongs to people and is kept byte for byte.\n"
        "[permission]\n"
        'deny = ["Read(.env*)"]\n\n'
        "[mcp]\n"
        "max_output_bytes = 65536\n\n"
        "[mcp_servers.skm]\n"
        'command = "old-skm"\n'
        'args = ["old"]\n\n'
        "[mcp_servers.docs-search]\n"
        'command = "npx"\n'
        'args = ["-y", "@example/docs-mcp"]\n'
    )
    cfg_df = by_path[".grok/config.toml"]
    merged_cfg = merge_owned_toml(
        pre_existing_config_toml,
        parse_toml(cfg_df.managed_bytes.decode("utf-8")),
        cfg_df.boundary.owned_keys,
    ).encode("utf-8")
    assert merged_cfg == (GOLDEN_DIR / ".grok/config.toml").read_bytes()


def test_canonical_skills_match_codex_and_cursor_bytes_and_digests() -> None:
    """Grok, Codex, and Cursor produce identical ``.agents/skills/`` boundaries, bytes, and digests."""
    grok_inputs = _golden_projection_inputs()
    codex_inputs = replace(grok_inputs, target=TargetId.CODEX)
    cursor_inputs = replace(grok_inputs, target=TargetId.CURSOR)

    grok_skills = {
        f.relative_path: f for f in GrokTarget().render(grok_inputs) if f.relative_path.startswith(".agents/")
    }
    codex_skills = {
        f.relative_path: f
        for f in CodexTarget().render(codex_inputs)
        if f.relative_path.startswith(".agents/")
    }
    cursor_skills = {
        f.relative_path: f
        for f in CursorTarget().render(cursor_inputs)
        if f.relative_path.startswith(".agents/")
    }

    assert set(grok_skills) == set(codex_skills) == set(cursor_skills)
    for rel, grk_df in grok_skills.items():
        cdx_df = codex_skills[rel]
        cur_df = cursor_skills[rel]
        assert grk_df.boundary == cdx_df.boundary == cur_df.boundary
        assert grk_df.managed_bytes == cdx_df.managed_bytes == cur_df.managed_bytes
        assert grk_df.managed_digest == cdx_df.managed_digest == cur_df.managed_digest
        assert grk_df.managed_bytes == (CODEX_GOLDEN_DIR / rel).read_bytes()


def test_repeated_apply_idempotency_foreign_preservation_and_drift_skm_new(tmp_path: Path) -> None:
    """Second apply is NOOP, preserves foreign TOML/hook files, and writes ``.skm-new`` on drift."""
    checkout = tmp_path / "checkout"
    (checkout / ".grok" / "hooks").mkdir(parents=True)
    foreign_hook = checkout / ".grok" / "hooks" / "team-local.json"
    foreign_hook.write_text('{"description": "Team custom hook", "hooks": {}}\n', "utf-8")
    (checkout / ".grok" / "config.toml").write_text(
        "# Foreign user comment\n[mcp]\nmax_output_bytes = 65536\n\n"
        '[mcp_servers.docs-search]\ncommand = "npx"\nargs = ["-y", "@example/docs-mcp"]\n',
        "utf-8",
    )

    fs = LocalCheckoutFs(checkout, state_dir=tmp_path / "state")
    target = GrokTarget()
    desired_files = target.render(_golden_projection_inputs())
    applied_records: dict[str, AppliedFileRecord] = {}
    now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)

    # First pass: creates/updates all Grok files while keeping foreign TOML and team-local.json intact.
    for df in desired_files:
        obs, raw, _ = observe_path(fs, df.relative_path, df.boundary)
        dec = decide_file(df, None, obs, safe=True)
        pw = build_planned_write(dec, desired=df, applied=None, observed_bytes=raw)
        assert pw is not None
        assert pw.new_bytes is not None
        fs.write_atomic(pw.write_path, pw.new_bytes, expected_whole_digest=pw.expected_observed_whole_digest)
        applied_records[df.relative_path] = AppliedFileRecord(
            projection_id=TEST_PROJECTION_ID,
            relative_path=df.relative_path,
            surface=df.surface,
            boundary=df.boundary,
            applied_managed_digest=df.managed_digest,
            applied_whole_digest=sha256_tagged(pw.new_bytes),
            pre_image_file_version_id=None,
            renderer=df.renderer,
            applied_at=now,
        )

    assert foreign_hook.read_text("utf-8") == '{"description": "Team custom hook", "hooks": {}}\n'
    cfg_after_first = (checkout / ".grok" / "config.toml").read_text("utf-8")
    assert "# Foreign user comment" in cfg_after_first
    assert "max_output_bytes = 65536" in cfg_after_first
    assert "[mcp_servers.docs-search]" in cfg_after_first

    # Second pass: every file must reconcile to NOOP with zero planned writes.
    for df in desired_files:
        obs2, raw2, _ = observe_path(fs, df.relative_path, df.boundary)
        dec2 = decide_file(df, applied_records[df.relative_path], obs2, safe=True)
        assert dec2.kind is FileDecisionKind.NOOP
        assert (
            build_planned_write(
                dec2, desired=df, applied=applied_records[df.relative_path], observed_bytes=raw2
            )
            is None
        )

    # User edits owned [permission] deny in .grok/config.toml and source changes -> CONFLICT_WRITE_NEW.
    drifted_toml = cfg_after_first.replace(
        'deny = ["Read(.env*)"', 'deny = ["Read(custom.secret)", "Read(.env*)"'
    )
    (checkout / ".grok" / "config.toml").write_text(drifted_toml, "utf-8")

    updated_inputs = replace(
        _golden_projection_inputs(),
        mcp_servers={
            "skm": {
                "enabled": True,
                "type": "stdio",
                "command": "skm",
                "args": ["mcp", "--verbose"],
            }
        },
    )
    cfg_df_v2 = {f.relative_path: f for f in target.render(updated_inputs)}[".grok/config.toml"]
    obs_drift, raw_drift, _ = observe_path(fs, ".grok/config.toml", cfg_df_v2.boundary)
    dec_drift = decide_file(cfg_df_v2, applied_records[".grok/config.toml"], obs_drift, safe=True)
    assert dec_drift.kind is FileDecisionKind.CONFLICT_WRITE_NEW
    pw_drift = build_planned_write(
        dec_drift,
        desired=cfg_df_v2,
        applied=applied_records[".grok/config.toml"],
        observed_bytes=raw_drift,
    )
    assert pw_drift is not None
    assert pw_drift.new_bytes is not None
    assert pw_drift.write_path == ".grok/config.toml.skm-new"
    fs.write_atomic(pw_drift.write_path, pw_drift.new_bytes, expected_whole_digest=None)
    assert (checkout / ".grok" / "config.toml").read_text("utf-8") == drifted_toml
    assert (checkout / ".grok" / "config.toml.skm-new").exists()


def test_markdown_rule_validation() -> None:
    """``render_markdown_rule`` rejects unsafe slugs and blank bodies."""
    rule = render_markdown_rule("python-style", body="\r\n# Style\r\nUse typing.\r\n\n")
    assert rule.relative_path == ".grok/rules/python-style.md"
    assert rule.managed_bytes == b"# Style\nUse typing.\n"

    with pytest.raises(ValidationFailed) as exc_slug:
        render_markdown_rule("../escape", body="bad")
    assert exc_slug.value.code is ErrorCode.INTEGRATION_UNSAFE_TARGET

    with pytest.raises(ValidationFailed) as exc_empty:
        render_markdown_rule("empty-rule", body="   \n\t  ")
    assert exc_empty.value.code is ErrorCode.INTEGRATION_BOUNDARY_INVALID
