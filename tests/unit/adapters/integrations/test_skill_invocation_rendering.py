"""Native invocation metadata, managed ownership and resident skill budgets."""

from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from integration.integrations.codex.test_host_apply import _LiveCodexEnv
from integration.integrations.codex.test_host_apply import live_codex_env as live_codex_env
from skm.adapters.checkout_fs.user_home import LocalUserHomeReader
from skm.adapters.integrations.registry import default_target_registry
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import ProjectId
from skm.modules.extensions.domain.skill import parse_skill_frontmatter
from skm.modules.integrations.domain.budget import (
    FirstTurnSource,
    FirstTurnSourceKind,
    first_turn_sources,
    frontmatter_field,
)
from skm.modules.integrations.domain.decisions import FileDecisionKind
from skm.modules.integrations.domain.desired import ProjectionInputs
from skm.modules.integrations.domain.ownership import Ownership, sha256_tagged
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.integrations.domain.projection import ProjectionState
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.host.adopt_file import adopt_file
from skm.modules.integrations.host.apply_projection import apply_projection
from skm.modules.integrations.host.first_turn_budget import first_turn_budget
from skm.modules.integrations.host.plan_projection import plan_projection
from skm.modules.integrations.ports import CheckoutFs, IntegrationTargetRegistry, UserHomeReader

_MARKDOWN = '---\r\nname: release-notes\r\ndescription: "Release notes: draft"\r\n---\r\n# Notes\r\n'
_CODEX_SKILL = ".agents/skills/to-spec/SKILL.md"
_CODEX_METADATA = ".agents/skills/to-spec/agents/openai.yaml"


def _inputs(target: TargetId, *, markdown: str = _MARKDOWN) -> ProjectionInputs:
    return ProjectionInputs(
        project_id=ProjectId(UUID(int=1)),
        target=target,
        instructions_core={},
        instructions_project={},
        skills=(
            {
                "key": "release-notes",
                "manifest": {
                    "description": "Use the markdown description",
                    "invocation": {"user_only": True, "argument_hint": '[draft "name"]'},
                },
                "bodies": {"SKILL.md": markdown},
            },
            {
                "key": "checks",
                "manifest": {"description": "Run checks", "invocation": {"user_only": False}},
                "bodies": {"SKILL.md": "# Checks\n"},
            },
            {
                "key": "publish",
                "manifest": {
                    "description": "Publish a release",
                    "invocation": {"user_only": True, "display_name": 'Publish "now"'},
                },
                "files": [{"path": "SKILL.md", "content": "# Publish\r\n"}],
            },
        ),
        permissions={},
        profile=PermissionProfile.WORKSPACE_CONTAINED,
        hook_modes={},
        host_subscription_events=(),
        mcp_servers={},
        agents=(),
        inputs_digest="",
        config_generation=0,
        diagnostics=(),
    )


@pytest.mark.parametrize(
    "targets",
    [
        (TargetId.CLAUDE_CODE,),
        (TargetId.CODEX,),
        (TargetId.CLAUDE_CODE, TargetId.CODEX, TargetId.ANTIGRAVITY, TargetId.CURSOR, TargetId.GROK),
    ],
    ids=["claude-only", "codex-only", "combined"],
)
def test_render_invocation_metadata(targets: tuple[TargetId, ...]) -> None:
    registry = default_target_registry()
    markdowns: dict[TargetId, bytes] = {}
    for target in targets:
        rendered = registry.get(target).render(_inputs(target))
        files = {file.relative_path: file for file in rendered if file.surface is Surface.SKILLS}
        prefix = ".claude/skills" if target is TargetId.CLAUDE_CODE else ".agents/skills"
        release = files[f"{prefix}/release-notes/SKILL.md"]
        markdowns[target] = release.managed_bytes
        assert release.managed_bytes.endswith(b"---\n# Notes\n")
        assert release.managed_digest == sha256_tagged(release.managed_bytes)
        assert frontmatter_field(release.managed_bytes.decode(), "disable-model-invocation") == "true"
        assert frontmatter_field(release.managed_bytes.decode(), "argument-hint") == '[draft "name"]'
        assert (
            frontmatter_field(
                files[f"{prefix}/checks/SKILL.md"].managed_bytes.decode(), "disable-model-invocation"
            )
            is None
        )
        assert f"{prefix}/checks/agents/openai.yaml" not in files

        publish = files[f"{prefix}/publish/SKILL.md"]
        assert publish.managed_bytes.endswith(b"---\n\n# Publish\n")
        assert frontmatter_field(publish.managed_bytes.decode(), "argument-hint") is None

        metadata_path = f"{prefix}/release-notes/agents/openai.yaml"
        if target is TargetId.CODEX:
            metadata = files[metadata_path]
            assert metadata.boundary.ownership is Ownership.MANAGED_FILE
            assert metadata.source_refs == release.source_refs
            assert metadata.managed_digest == sha256_tagged(metadata.managed_bytes)
            assert metadata.managed_bytes == (
                b'interface:\n  display_name: "Release Notes"\n  short_description: "Release notes: draft"\n'
                b"policy:\n  allow_implicit_invocation: false\n"
            )
            assert (
                b'  display_name: "Publish \\"now\\""\n'
                in files[f"{prefix}/publish/agents/openai.yaml"].managed_bytes
            )
        else:
            assert metadata_path not in files
    assert len(set(markdowns.values())) == 1


@pytest.mark.parametrize(
    ("header", "description"),
    [
        ("--- \nname: release-notes\ndescription: Draft notes\n---\n", "Draft notes"),
        ("---\nname: release-notes\ndescription: Draft notes\n--- \n", "Draft notes"),
        ("---\nname: release-notes\ndescription : Draft notes\n---\n", "Draft notes"),
        ('---\nname: release-notes\ndescription: "Draft notes" # Summary\n---\n', "Draft notes"),
        (
            "---\nname: release-notes\ndescription: 'Draft team''s notes #1' # Summary\n---\n",
            "Draft team's notes #1",
        ),
    ],
    ids=[
        "opening-fence-space",
        "closing-fence-space",
        "space-before-colon",
        "double-quoted-with-comment",
        "single-quoted-with-comment",
    ],
)
def test_codex_render_accepts_validated_skill_frontmatter(header: str, description: str) -> None:
    target = TargetId.CODEX
    markdown = header + "# Notes\n"
    frontmatter, _ = parse_skill_frontmatter(markdown, key="release-notes")
    rendered = default_target_registry().get(target).render(_inputs(target, markdown=markdown))
    files = {file.relative_path: file.managed_bytes for file in rendered if file.surface is Surface.SKILLS}
    path = ".agents/skills/release-notes"
    skill = files[f"{path}/SKILL.md"].decode()

    assert frontmatter["description"] == frontmatter_field(skill, "description") == description
    assert frontmatter_field(skill, "disable-model-invocation") == "true"
    assert skill.endswith("---\n# Notes\n")
    assert f'  short_description: "{description}"\n'.encode() in files[f"{path}/agents/openai.yaml"]


@pytest.mark.integration
def test_codex_metadata_conflicts_follow_managed_file_reconciliation(live_codex_env: _LiveCodexEnv) -> None:
    env = live_codex_env
    metadata = env.checkout_dir / _CODEX_METADATA
    metadata.parent.mkdir(parents=True)
    local = b"policy:\n  allow_implicit_invocation: true\n"
    metadata.write_bytes(local)
    target = TargetId.CODEX

    plans = plan_projection(env.ctx, project_id=env.project_id, targets=(target,))
    decision = next(item for item in plans[0].decisions if item.relative_path == _CODEX_METADATA)
    assert decision.kind is FileDecisionKind.ADOPT_REQUIRED
    assert _CODEX_METADATA in apply_projection(env.ctx, plans)[0].conflicts
    assert metadata.read_bytes() == local

    adopt_file(
        env.ctx,
        project_id=env.project_id,
        target=target,
        relative_path=_CODEX_METADATA,
        reason="adopt skill policy",
    )
    plans = plan_projection(env.ctx, project_id=env.project_id, targets=(target,))
    assert apply_projection(env.ctx, plans)[0].state is ProjectionState.IN_SYNC
    managed = metadata.read_bytes()
    assert b"  allow_implicit_invocation: false\n" in managed

    metadata.write_bytes(local)
    plans = plan_projection(env.ctx, project_id=env.project_id, targets=(target,))
    decision = next(item for item in plans[0].decisions if item.relative_path == _CODEX_METADATA)
    assert decision.kind is FileDecisionKind.CONFLICT_WRITE_NEW
    assert _CODEX_METADATA in apply_projection(env.ctx, plans)[0].conflicts
    assert metadata.read_bytes() == local

    plans = plan_projection(env.ctx, project_id=env.project_id, targets=(target,), force_conflicts=True)
    assert apply_projection(env.ctx, plans)[0].state is ProjectionState.IN_SYNC
    assert metadata.read_bytes() == managed


@pytest.mark.integration
def test_codex_budget_reads_sidecar_from_checkout(live_codex_env: _LiveCodexEnv, tmp_path: Path) -> None:
    env = live_codex_env
    target = TargetId.CODEX
    plans = plan_projection(env.ctx, project_id=env.project_id, targets=(TargetId.CLAUDE_CODE, target))
    outcomes = apply_projection(env.ctx, plans)
    assert all(outcome.state is ProjectionState.IN_SYNC for outcome in outcomes)
    claude_skill = env.checkout_dir / ".claude/skills/to-spec/SKILL.md"
    assert claude_skill.read_bytes() == (env.checkout_dir / _CODEX_SKILL).read_bytes()
    gateways = GatewayTable(
        {
            CheckoutFs: env.ctx.gateways.get(CheckoutFs),
            IntegrationTargetRegistry: env.ctx.gateways.get(IntegrationTargetRegistry),
            UserHomeReader: LocalUserHomeReader(tmp_path / "home"),
        },
        "host_gateway",
    )
    ctx = replace(env.ctx, gateways=gateways)
    metadata = env.checkout_dir / _CODEX_METADATA

    def skills_budget() -> FirstTurnSource:
        report = first_turn_budget(ctx, project_id=env.project_id, target=target)
        return next(source for source in report.sources if source.kind is FirstTurnSourceKind.SKILLS)

    manual = skills_budget()
    manual_files = manual.detail["files"]
    assert isinstance(manual_files, list)
    assert _CODEX_SKILL not in manual_files
    for policy in (
        "policy: {\n  allow_implicit_invocation: false\n}\n",
        "policy: {\n  allow_implicit_invocation:\n    false\n}\n",
        '{"policy":{"allow_implicit_invocation":false}}',
    ):
        metadata.write_text(policy, encoding="utf-8")
        assert skills_budget() == manual

    metadata.write_text("policy:\n  allow_implicit_invocation: true\n", encoding="utf-8")
    implicit = skills_budget()
    implicit_files = implicit.detail["files"]
    assert isinstance(implicit_files, list)
    assert _CODEX_SKILL in implicit_files
    assert manual.tokens is not None
    assert implicit.tokens is not None
    assert implicit.tokens > manual.tokens
    metadata.write_text('policy: {\n  allow_implicit_invocation:\n    "false"\n}\n', encoding="utf-8")
    assert skills_budget() == implicit
    metadata.unlink()
    assert skills_budget() == implicit

    tdd = env.checkout_dir / ".agents/skills/tdd/agents/openai.yaml"
    tdd.parent.mkdir()
    tdd.write_text("policy: # local policy\n  allow_implicit_invocation: false # manual\n", encoding="utf-8")
    files = skills_budget().detail["files"]
    assert isinstance(files, list)
    assert ".agents/skills/tdd/SKILL.md" in implicit_files
    assert ".agents/skills/tdd/SKILL.md" not in files


@pytest.mark.parametrize(("flag", "count"), [("true", 0), ("false", 1)])
def test_claude_budget_uses_skill_frontmatter(flag: str, count: int) -> None:
    skills, *_ = first_turn_sources(
        target=TargetId.CLAUDE_CODE,
        skills={
            "SKILL.md": f"---\nname: notes\ndescription: Draft notes\ndisable-model-invocation: {flag}\n---\n"
        },
        agents={},
        instructions={},
        session_start_template="",
        mcp_servers={},
    )
    assert skills.detail["skills"] == count
