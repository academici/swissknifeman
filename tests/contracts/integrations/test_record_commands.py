"""Dual-backend contract suite for ``integrations`` Bus commands and queries (P10.01.b)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import pytest

from contracts.extensions.harness import PROMPT_BLOCKS, profile_toml
from contracts.integrations.harness import INSTANCE, Side, pack_payload
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed, ValidationFailed
from skm.kernel.generated.defs import ScopeRefDto
from skm.modules.extensions.generated.commands import QuarantineResource
from skm.modules.extensions.generated.queries import ResolveResource, ResourceKind
from skm.modules.integrations.domain.ownership import sha256_tagged
from skm.modules.integrations.public import (
    GetAppliedState,
    GetDesiredProjection,
    ListProjections,
    RecordDrift,
    RecordDriftFilesItem,
    RecordProjectionApplied,
    RecordProjectionAppliedDefsAppliedFileInput,
    RecordProjectionAppliedDefsOwnedKeyPath,
    RecordProjectionAppliedFailedItem,
    RemoveProjection,
    RemoveProjectionFailedItem,
)

DIGEST_1 = sha256_tagged(b"desired-v1")
DIGEST_2 = sha256_tagged(b"desired-v2")
INPUTS_1 = sha256_tagged(b"inputs-v1")
INPUTS_2 = sha256_tagged(b"inputs-v2")

type _TargetLiteral = Literal["claude_code", "codex", "cursor", "grok"]
type _SurfaceLiteral = Literal["instructions", "skills", "permissions", "hooks", "mcp", "agents"]
type _OwnershipLiteral = Literal["managed_file", "managed_block", "merged_json", "merged_toml"]


def _file_input(
    path: str,
    *,
    surface: _SurfaceLiteral = "instructions",
    ownership: _OwnershipLiteral = "managed_block",
    block_ids: tuple[str, ...] = ("core",),
    owned_keys: tuple[RecordProjectionAppliedDefsOwnedKeyPath, ...] = (),
    managed_digest: str | None = None,
    whole_digest: str | None = None,
    pre_image_id: UUID | None = None,
    renderer: str | None = None,
) -> RecordProjectionAppliedDefsAppliedFileInput:
    md = managed_digest or sha256_tagged(f"managed:{path}".encode())
    wd = whole_digest or sha256_tagged(f"whole:{path}".encode())
    return RecordProjectionAppliedDefsAppliedFileInput(
        relative_path=path,
        surface=surface,
        ownership=ownership,
        block_ids=block_ids,
        owned_keys=owned_keys,
        applied_managed_digest=md,
        applied_whole_digest=wd,
        pre_image_file_version_id=pre_image_id,
        renderer=renderer or f"claude_code.{surface}@1",
    )


def _apply_cmd(
    *,
    project_id: object,
    checkout_binding_id: object,
    target: _TargetLiteral = "claude_code",
    base_row_version: int | None = None,
    desired_digest: str = DIGEST_1,
    inputs_digest: str = INPUTS_1,
    renderer_version: str | None = None,
    files: tuple[RecordProjectionAppliedDefsAppliedFileInput, ...],
    removed: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
    failed: tuple[RecordProjectionAppliedFailedItem, ...] = (),
    adopted: tuple[str, ...] = (),
    left_modified: tuple[str, ...] = (),
) -> RecordProjectionApplied:
    return RecordProjectionApplied(
        project_id=UUID(str(project_id)),
        checkout_binding_id=UUID(str(checkout_binding_id)),
        target=target,
        desired_digest=desired_digest,
        inputs_digest=inputs_digest,
        renderer_version=renderer_version or f"{target}@1",
        base_row_version=base_row_version,
        files=files,
        removed=removed,
        conflicts=conflicts,
        failed=failed,
        adopted=adopted,
        left_modified=left_modified,
    )


def _remove_cmd(
    *,
    project_id: object,
    projection_id: UUID,
    base_row_version: int,
    removed: tuple[str, ...] = (),
    left_modified: tuple[str, ...] = (),
    failed: tuple[RemoveProjectionFailedItem, ...] = (),
) -> RemoveProjection:
    return RemoveProjection(
        project_id=UUID(str(project_id)),
        projection_id=projection_id,
        base_row_version=base_row_version,
        removed=removed,
        left_modified=left_modified,
        failed=failed,
    )


def test_record_projection_applied_fresh_in_sync_and_queries(side: Side) -> None:
    seeded = side.seed_checkout("fresh")
    pre_id = UUID(str(side.seed_file_version(seeded.workspace_id, seeded.project_id)))

    res = side.run(
        _apply_cmd(
            project_id=seeded.project_id,
            checkout_binding_id=seeded.checkout_binding_id,
            files=(
                _file_input("CLAUDE.md", pre_image_id=pre_id),
                _file_input(
                    ".claude/settings.local.json",
                    surface="permissions",
                    ownership="merged_json",
                    block_ids=(),
                    owned_keys=(
                        RecordProjectionAppliedDefsOwnedKeyPath(
                            path=("permissions", "allow"),
                            mode="list_union_tagged",
                        ),
                    ),
                ),
            ),
        ),
        key="idem-apply-1",
    )
    assert res.state == "in_sync"
    assert res.row_version == 1

    events = side.events("urn:skm:integrations:event:projection-applied:v1")
    assert len(events) == 1
    assert events[0][1]["projection_id"] == str(res.projection_id)
    assert events[0][1]["state"] == "in_sync"
    assert events[0][1]["applied"] == 2

    applied_view = side.ask(
        GetAppliedState(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        )
    )
    assert applied_view.projection is not None
    assert applied_view.projection.projection_id == res.projection_id
    assert applied_view.projection.host_id == UUID(str(seeded.host_id))
    assert applied_view.projection.state == "in_sync"
    assert applied_view.projection.desired_digest == DIGEST_1
    assert applied_view.projection.applied_desired_digest == DIGEST_1
    assert [f.relative_path for f in applied_view.files] == [
        ".claude/settings.local.json",
        "CLAUDE.md",
    ]
    assert applied_view.files[1].pre_image_file_version_id == pre_id

    listed = side.ask(ListProjections(project_id=UUID(str(seeded.project_id))))
    assert len(listed.items) == 1
    assert listed.items[0].projection_id == res.projection_id
    assert listed.has_more is False


def test_record_projection_applied_stale_cas_rejected(side: Side) -> None:
    seeded = side.seed_checkout("cas-cmd")

    with pytest.raises(Conflict) as missing_exc:
        side.run(
            _apply_cmd(
                project_id=seeded.project_id,
                checkout_binding_id=seeded.checkout_binding_id,
                base_row_version=1,
                files=(_file_input("CLAUDE.md"),),
            ),
            key="idem-cas-0",
        )
    assert missing_exc.value.code is ErrorCode.VERSION_CONFLICT

    side.run(
        _apply_cmd(
            project_id=seeded.project_id,
            checkout_binding_id=seeded.checkout_binding_id,
            base_row_version=None,
            files=(_file_input("CLAUDE.md"),),
        ),
        key="idem-cas-1",
    )

    with pytest.raises(Conflict) as stale_exc:
        side.run(
            _apply_cmd(
                project_id=seeded.project_id,
                checkout_binding_id=seeded.checkout_binding_id,
                base_row_version=99,
                desired_digest=DIGEST_2,
                inputs_digest=INPUTS_2,
                files=(_file_input("CLAUDE.md"),),
            ),
            key="idem-cas-2",
        )
    assert stale_exc.value.code is ErrorCode.VERSION_CONFLICT


def test_record_projection_applied_partial_failure_retains_prior_records(side: Side) -> None:
    seeded = side.seed_checkout("partial")
    pre_b = UUID(str(side.seed_file_version(seeded.workspace_id, seeded.project_id)))
    old_b_managed = sha256_tagged(b"file-b-v1-managed")
    old_b_whole = sha256_tagged(b"file-b-v1-whole")

    side.run(
        _apply_cmd(
            project_id=seeded.project_id,
            checkout_binding_id=seeded.checkout_binding_id,
            files=(
                _file_input("CLAUDE.md", managed_digest=sha256_tagged(b"a-v1")),
                _file_input(
                    ".claude/settings.local.json",
                    surface="permissions",
                    ownership="merged_json",
                    block_ids=(),
                    owned_keys=(RecordProjectionAppliedDefsOwnedKeyPath(path=("hooks",), mode="replace"),),
                    managed_digest=old_b_managed,
                    whole_digest=old_b_whole,
                    pre_image_id=pre_b,
                ),
            ),
        ),
        key="idem-part-1",
    )
    t0 = side.clock.now()
    side.tick(10.0)

    res2 = side.run(
        _apply_cmd(
            project_id=seeded.project_id,
            checkout_binding_id=seeded.checkout_binding_id,
            base_row_version=1,
            desired_digest=DIGEST_2,
            inputs_digest=INPUTS_2,
            files=(
                _file_input("CLAUDE.md", managed_digest=sha256_tagged(b"a-v2")),
                _file_input(
                    ".claude/settings.local.json",
                    surface="permissions",
                    ownership="merged_json",
                    block_ids=(),
                    owned_keys=(RecordProjectionAppliedDefsOwnedKeyPath(path=("hooks",), mode="replace"),),
                    managed_digest=old_b_managed,
                    whole_digest=old_b_whole,
                    pre_image_id=pre_b,
                ),
            ),
            failed=(
                RecordProjectionAppliedFailedItem(
                    relative_path=".claude/settings.local.json",
                    error_code="INTEGRATION_RECHECK_FAILED",
                ),
            ),
        ),
        key="idem-part-2",
    )
    assert res2.state == "failed"
    assert res2.row_version == 2

    view = side.ask(
        GetAppliedState(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        )
    )
    assert view.projection is not None
    assert view.projection.state == "failed"
    assert view.projection.desired_digest == DIGEST_2
    assert view.projection.applied_desired_digest == DIGEST_1
    files_by_path = {f.relative_path: f for f in view.files}
    assert files_by_path[".claude/settings.local.json"].applied_managed_digest == old_b_managed
    assert files_by_path[".claude/settings.local.json"].pre_image_file_version_id == pre_b
    assert files_by_path[".claude/settings.local.json"].applied_at == t0
    assert files_by_path["CLAUDE.md"].applied_at == side.clock.now()


def test_record_projection_applied_conflicts_and_prior_accounting(side: Side) -> None:
    seeded = side.seed_checkout("acct")
    side.run(
        _apply_cmd(
            project_id=seeded.project_id,
            checkout_binding_id=seeded.checkout_binding_id,
            files=(
                _file_input("CLAUDE.md"),
                _file_input(
                    ".claude/skills/skm-old/SKILL.md",
                    surface="skills",
                    ownership="managed_file",
                    block_ids=(),
                ),
            ),
        ),
        key="idem-acct-1",
    )

    with pytest.raises(ValidationFailed) as unacc_exc:
        side.run(
            _apply_cmd(
                project_id=seeded.project_id,
                checkout_binding_id=seeded.checkout_binding_id,
                base_row_version=1,
                desired_digest=DIGEST_2,
                inputs_digest=INPUTS_2,
                files=(_file_input("CLAUDE.md"),),
            ),
            key="idem-acct-missing",
        )
    assert unacc_exc.value.code is ErrorCode.SCHEMA_INVALID

    with pytest.raises(ValidationFailed) as overlap_exc:
        side.run(
            _apply_cmd(
                project_id=seeded.project_id,
                checkout_binding_id=seeded.checkout_binding_id,
                base_row_version=1,
                desired_digest=DIGEST_2,
                inputs_digest=INPUTS_2,
                files=(_file_input("CLAUDE.md"),),
                removed=("CLAUDE.md", ".claude/skills/skm-old/SKILL.md"),
            ),
            key="idem-acct-overlap",
        )
    assert overlap_exc.value.code is ErrorCode.SCHEMA_INVALID

    res_conflict = side.run(
        _apply_cmd(
            project_id=seeded.project_id,
            checkout_binding_id=seeded.checkout_binding_id,
            base_row_version=1,
            desired_digest=DIGEST_2,
            inputs_digest=INPUTS_2,
            files=(_file_input("CLAUDE.md"),),
            left_modified=(".claude/skills/skm-old/SKILL.md",),
            conflicts=("CLAUDE.md",),
        ),
        key="idem-acct-conflict",
    )
    assert res_conflict.state == "drifted"
    view = side.ask(
        GetAppliedState(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        )
    )
    assert view.projection is not None
    assert view.projection.applied_desired_digest == DIGEST_1
    assert [f.relative_path for f in view.files] == ["CLAUDE.md"]


def test_record_drift_transitions_and_events(side: Side) -> None:
    seeded = side.seed_checkout("drift")
    side.run(
        _apply_cmd(
            project_id=seeded.project_id,
            checkout_binding_id=seeded.checkout_binding_id,
            files=(_file_input("CLAUDE.md"),),
        ),
        key="idem-drift-init",
    )

    side.tick(3.0)
    d1 = side.run(
        RecordDrift(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
            base_row_version=1,
            desired_digest=DIGEST_1,
            files=(
                RecordDriftFilesItem(
                    relative_path="CLAUDE.md",
                    decision="adopt_required",
                    diagnostic="managed block modified",
                ),
            ),
        )
    )
    assert d1.state == "drifted"
    assert d1.drifted == 1
    drift_events = side.events("urn:skm:integrations:event:projection-drift-detected:v1")
    assert len(drift_events) == 1
    assert drift_events[0][1]["files"] == [{"path": "CLAUDE.md", "decision": "adopt_required"}]

    d2 = side.run(
        RecordDrift(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
            base_row_version=2,
            desired_digest=DIGEST_1,
            files=(),
        )
    )
    assert d2.state == "in_sync"

    d3 = side.run(
        RecordDrift(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
            base_row_version=3,
            desired_digest=DIGEST_2,
            files=(),
        )
    )
    assert d3.state == "pending"


def test_remove_projection_idempotent_and_invalid_transition(side: Side) -> None:
    seeded = side.seed_checkout("rm")
    applied = side.run(
        _apply_cmd(
            project_id=seeded.project_id,
            checkout_binding_id=seeded.checkout_binding_id,
            files=(
                _file_input("CLAUDE.md"),
                _file_input(
                    ".claude/skills/skm-a/SKILL.md",
                    surface="skills",
                    ownership="managed_file",
                    block_ids=(),
                ),
            ),
        ),
        key="idem-rm-init",
    )

    rm_cmd = _remove_cmd(
        project_id=seeded.project_id,
        projection_id=applied.projection_id,
        base_row_version=1,
        removed=(".claude/skills/skm-a/SKILL.md",),
        left_modified=("CLAUDE.md",),
    )
    r1 = side.run(rm_cmd, key="idem-rm-1")
    assert r1.state == "removed"

    r_retry = side.run(rm_cmd, key="idem-rm-1")
    assert r_retry == r1
    assert len(side.events("urn:skm:integrations:event:projection-removed:v1")) == 1

    view = side.ask(
        GetAppliedState(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        )
    )
    assert view.projection is not None
    assert view.projection.state == "removed"
    assert view.files == ()

    with pytest.raises(PreconditionFailed) as exc_info:
        side.run(
            _remove_cmd(
                project_id=seeded.project_id,
                projection_id=applied.projection_id,
                base_row_version=2,
            ),
            key="idem-rm-second",
        )
    assert exc_info.value.code is ErrorCode.INVALID_TRANSITION


def test_get_desired_projection_neutral_inputs_and_trusted_narrowing(side: Side) -> None:
    seeded = side.seed_checkout("desired")
    skill_manifest = (
        'schema = "urn:skm:extensions:skill-manifest:v1"\n'
        'key = "review"\n'
        'version = "1.0.0"\n'
        'adapters = ["claude_code"]\n'
    )
    client_core_prompt = (
        "+++\n"
        'schema = "urn:skm:extensions:prompt-block:v1"\n'
        'block_type = "repo_instructions"\n'
        "variables = []\n"
        "+++\n"
        "Core client instructions.\n"
    )
    steering_high = (
        "+++\n"
        'schema = "urn:skm:extensions:steering:v1"\n'
        'key = "zeta"\n'
        'version = "1.0.0"\n'
        'title = "Zeta High Priority"\n'
        "priority = 80\n"
        "[scope]\n"
        "global = true\n"
        "+++\n"
        "High-priority rule.\n"
    )
    steering_conventions = (
        "+++\n"
        'schema = "urn:skm:extensions:steering:v1"\n'
        'key = "conventions"\n'
        'version = "1.0.0"\n'
        'title = "Conventions"\n'
        "priority = 50\n"
        "[scope]\n"
        "global = true\n"
        "+++\n"
        "Follow repo rules.\n"
    )
    steering_alpha = (
        "+++\n"
        'schema = "urn:skm:extensions:steering:v1"\n'
        'key = "alpha"\n'
        'version = "1.0.0"\n'
        'title = "Alpha Project"\n'
        "priority = 50\n"
        "[scope]\n"
        'projects = ["proj-desired"]\n'
        "+++\n"
        "Alpha project rule.\n"
    )
    steering_other_project = (
        "+++\n"
        'schema = "urn:skm:extensions:steering:v1"\n'
        'key = "other-proj"\n'
        'version = "1.0.0"\n'
        'title = "Other Project"\n'
        "priority = 95\n"
        "[scope]\n"
        'projects = ["proj-other"]\n'
        "+++\n"
        "Foreign project rule.\n"
    )
    profile_manifest = profile_toml(key="reviewer", role="executor", policy_profile="read-only")
    catalog_toml = 'schema = "urn:skm:runtimes:model-catalog:v1"\ncatalog_version = "1.0.0"\n[runtimes]\n'
    side.install_pack(
        pack_payload(
            "core",
            "1.0.0",
            files={
                **PROMPT_BLOCKS,
                "prompts/instructions/client-core.md": client_core_prompt,
                "steering/zeta.md": steering_high,
                "steering/conventions.md": steering_conventions,
                "steering/alpha.md": steering_alpha,
                "steering/other-proj.md": steering_other_project,
                "skills/review/SKILL.md": "# Review Skill\n",
                "skills/review/manifest.toml": skill_manifest,
                "agent-profiles/reviewer.toml": profile_manifest,
                "runtimes/models.toml": catalog_toml,
            },
        )
    )

    side.set_setting(
        "project",
        seeded.project_id,
        "integrations.instructions.project_text",
        "Project-local guidance.",
    )
    side.set_setting(
        "instance",
        INSTANCE,
        "integrations.permission_profile",
        "trusted_full_access",
    )
    side.set_setting(
        "project",
        seeded.project_id,
        "hooks.subscriptions",
        {
            "fmt_on_write": {
                "enabled": True,
                "class": "observation",
                "kind": "command",
                "execution_location": "host",
                "event_types": ["client:post_tool"],
                "target": {"argv": ["ruff", "format", "--check"]},
            }
        },
    )

    narrowed = side.ask(
        GetDesiredProjection(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        )
    )
    assert narrowed.profile == "workspace_contained"
    assert len(narrowed.diagnostics) == 1
    assert narrowed.diagnostics[0]["code"] == "INTEGRATION_TRUSTED_REFUSED"
    assert narrowed.instructions_core["key"] == "instructions/client-core"
    assert narrowed.instructions_core["content"] == "Core client instructions."
    assert narrowed.instructions_project["content"] == (
        "High-priority rule.\n\nAlpha project rule.\n\nFollow repo rules.\n\nProject-local guidance."
    )
    assert len(narrowed.skills) == 1
    assert narrowed.skills[0]["key"] == "review"
    assert len(narrowed.agents) == 1
    assert narrowed.agents[0]["name"] == "skm-reviewer"
    assert "skm" in narrowed.mcp_servers
    assert len(narrowed.host_subscription_events) == 1
    assert narrowed.host_subscription_events[0].kind == "post_tool"
    assert narrowed.host_subscription_events[0].classes == ("observation",)

    codex_view = side.ask(
        GetDesiredProjection(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="codex",
        )
    )
    assert codex_view.skills == ()

    side.set_setting("host", seeded.host_id, "integrations.trusted_full_access.allowed", True)
    trusted = side.ask(
        GetDesiredProjection(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        )
    )
    assert trusted.profile == "trusted_full_access"
    assert trusted.diagnostics == ()
    assert trusted.inputs_digest != narrowed.inputs_digest


def _skill_toml(
    key: str,
    *,
    requires: tuple[str, ...] = (),
    adapters: tuple[str, ...] = ("claude_code",),
) -> str:
    req_list = ", ".join(f'"{item}"' for item in requires)
    adp_list = ", ".join(f'"{item}"' for item in adapters)
    return (
        'schema = "urn:skm:extensions:skill-manifest:v1"\n'
        f'key = "{key}"\n'
        'version = "1.0.0"\n'
        f"requires = [{req_list}]\n"
        f"adapters = [{adp_list}]\n"
    )


def test_get_desired_projection_exceeds_max_bytes_raises_desired_too_large(side: Side) -> None:
    seeded = side.seed_checkout("desired-large")
    catalog_toml = 'schema = "urn:skm:runtimes:model-catalog:v1"\ncatalog_version = "1.0.0"\n[runtimes]\n'
    side.install_pack(
        pack_payload(
            "core",
            "1.0.0",
            files={
                **PROMPT_BLOCKS,
                "skills/big/SKILL.md": "# Big Skill\n",
                "skills/big/manifest.toml": _skill_toml("big"),
                "skills/big/references/guide.md": "x" * 70_000,
                "runtimes/models.toml": catalog_toml,
            },
        )
    )
    side.set_setting("instance", INSTANCE, "integrations.desired.max_bytes", 65536)

    with pytest.raises(PreconditionFailed) as exc_info:
        side.ask(
            GetDesiredProjection(
                project_id=UUID(str(seeded.project_id)),
                checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
                target="claude_code",
            )
        )
    assert exc_info.value.code is ErrorCode.INTEGRATION_DESIRED_TOO_LARGE
    size_bytes = exc_info.value.details["size_bytes"]
    assert isinstance(size_bytes, int)
    assert size_bytes > 65536

    # Raising the configured ceiling admits the same content through the real query path.
    side.set_setting("instance", INSTANCE, "integrations.desired.max_bytes", 2 * size_bytes)
    view = side.ask(
        GetDesiredProjection(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        )
    )
    assert [skill["key"] for skill in view.skills] == ["big"]


def test_get_desired_projection_skill_selection_presets_closure_core_and_exclude(side: Side) -> None:
    seeded = side.seed_checkout("skill-sel")
    catalog_toml = 'schema = "urn:skm:runtimes:model-catalog:v1"\ncatalog_version = "1.0.0"\n[runtimes]\n'
    side.install_pack(
        pack_payload(
            "core",
            "1.0.0",
            files={
                **PROMPT_BLOCKS,
                "skills/core-base/SKILL.md": "# Core Base\n",
                "skills/core-base/manifest.toml": _skill_toml("core-base"),
                "skills/core-skip/SKILL.md": "# Core Skip\n",
                "skills/core-skip/manifest.toml": _skill_toml("core-skip"),
                "runtimes/models.toml": catalog_toml,
            },
        )
    )
    side.install_pack(
        pack_payload(
            "extra",
            "1.0.0",
            files={
                "skills/py-leaf/SKILL.md": "# Py Leaf\n",
                "skills/py-leaf/manifest.toml": _skill_toml("py-leaf"),
                "skills/py-blocked/SKILL.md": "# Py Blocked\n",
                "skills/py-blocked/manifest.toml": _skill_toml("py-blocked"),
                "skills/py-helper/SKILL.md": "# Py Helper\n",
                "skills/py-helper/manifest.toml": _skill_toml(
                    "py-helper", requires=("py-leaf", "py-blocked")
                ),
                "skills/inc-root/SKILL.md": "# Included Root\n",
                "skills/inc-root/manifest.toml": _skill_toml("inc-root"),
                "skills/unselected/SKILL.md": "# Unselected\n",
                "skills/unselected/manifest.toml": _skill_toml("unselected"),
            },
        )
    )
    side.install_pack(
        pack_payload(
            "python-preset",
            "1.0.0",
            files={
                "skills/py-lint/SKILL.md": "# Py Lint\n",
                "skills/py-lint/manifest.toml": _skill_toml("py-lint", requires=("py-helper",)),
                "skills/py-extra/SKILL.md": "# Py Extra\n",
                "skills/py-extra/manifest.toml": _skill_toml("py-extra"),
            },
        )
    )
    side.set_setting(
        "project",
        seeded.project_id,
        "extensions.packs.enabled",
        ["extra", "python-preset"],
    )

    default_view = side.ask(
        GetDesiredProjection(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        )
    )
    assert [s["key"] for s in default_view.skills] == ["core-base", "core-skip"]

    side.set_setting("project", seeded.project_id, "integrations.skills.presets", ["python-preset"])
    side.set_setting("project", seeded.project_id, "integrations.skills.include", ["inc-root"])
    side.set_setting(
        "project",
        seeded.project_id,
        "integrations.skills.exclude",
        ["core-skip", "py-extra", "py-blocked"],
    )

    combined_view = side.ask(
        GetDesiredProjection(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        )
    )
    assert [s["key"] for s in combined_view.skills] == [
        "core-base",
        "inc-root",
        "py-helper",
        "py-leaf",
        "py-lint",
    ]

    side.set_setting("project", seeded.project_id, "integrations.skills.include_core", False)
    side.set_setting("project", seeded.project_id, "integrations.skills.presets", [])
    side.set_setting("project", seeded.project_id, "integrations.skills.include", ["py-lint"])
    side.set_setting("project", seeded.project_id, "integrations.skills.exclude", ["py-blocked"])

    no_core_view = side.ask(
        GetDesiredProjection(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        )
    )
    assert [s["key"] for s in no_core_view.skills] == ["py-helper", "py-leaf", "py-lint"]


def test_get_desired_projection_quarantined_candidates_excluded_with_diagnostics(side: Side) -> None:
    seeded = side.seed_checkout("quarantine")
    catalog_toml = 'schema = "urn:skm:runtimes:model-catalog:v1"\ncatalog_version = "1.0.0"\n[runtimes]\n'
    client_core_prompt = (
        "+++\n"
        'schema = "urn:skm:extensions:prompt-block:v1"\n'
        'block_type = "repo_instructions"\n'
        "variables = []\n"
        "+++\n"
        "Quarantined core instructions.\n"
    )
    steering_rules = (
        "+++\n"
        'schema = "urn:skm:extensions:steering:v1"\n'
        'key = "rules"\n'
        'version = "1.0.0"\n'
        'title = "Rules"\n'
        "priority = 60\n"
        "[scope]\n"
        "global = true\n"
        "+++\n"
        "Quarantined steering body.\n"
    )
    side.install_pack(
        pack_payload(
            "core",
            "1.0.0",
            files={
                **PROMPT_BLOCKS,
                "prompts/instructions/client-core.md": client_core_prompt,
                "steering/rules.md": steering_rules,
                "skills/core-ok/SKILL.md": "# Core OK\n",
                "skills/core-ok/manifest.toml": _skill_toml("core-ok"),
                "skills/core-quarantined/SKILL.md": "# Core Quarantined\n",
                "skills/core-quarantined/manifest.toml": _skill_toml("core-quarantined"),
                "runtimes/models.toml": catalog_toml,
            },
        )
    )
    side.install_pack(
        pack_payload(
            "extra",
            "1.0.0",
            files={
                "skills/dep-quarantined/SKILL.md": "# Dep Quarantined\n",
                "skills/dep-quarantined/manifest.toml": _skill_toml("dep-quarantined"),
                "skills/entry/SKILL.md": "# Entry Skill\n",
                "skills/entry/manifest.toml": _skill_toml("entry", requires=("dep-quarantined",)),
                "skills/unused-quarantined/SKILL.md": "# Unused Quarantined\n",
                "skills/unused-quarantined/manifest.toml": _skill_toml("unused-quarantined"),
            },
        )
    )
    side.set_setting("project", seeded.project_id, "extensions.packs.enabled", ["extra"])
    side.set_setting("project", seeded.project_id, "integrations.skills.include", ["entry"])

    proj_scope = ScopeRefDto(kind="project", id=UUID(str(seeded.project_id)))
    for kind, key in (
        (ResourceKind.PROMPT_BLOCK, "instructions/client-core"),
        (ResourceKind.STEERING, "rules"),
        (ResourceKind.SKILL, "core-quarantined"),
        (ResourceKind.SKILL, "dep-quarantined"),
        (ResourceKind.SKILL, "unused-quarantined"),
    ):
        resolved = side.ask(ResolveResource(kind=kind, key=key, scope=proj_scope))
        assert resolved.chosen is not None
        side.run(
            QuarantineResource(
                resource_version_id=resolved.chosen.resource_version_id,
                reason=f"quarantine {kind.value}:{key}",
            )
        )

    view = side.ask(
        GetDesiredProjection(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        )
    )
    assert view.instructions_core["content"] == ""
    assert view.instructions_project["content"] == ""
    assert [s["key"] for s in view.skills] == ["core-ok", "entry"]

    quarantine_diags = [d for d in view.diagnostics if d["code"] == "RESOURCE_QUARANTINED"]
    assert all(d["severity"] == "warning" for d in quarantine_diags)
    assert {d["target"] for d in quarantine_diags} == {
        "prompt_block:instructions/client-core",
        "steering:rules",
        "skill:core-quarantined",
        "skill:dep-quarantined",
    }
