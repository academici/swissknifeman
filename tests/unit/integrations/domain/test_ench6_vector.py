"""Ench6 verification matrix: 3-way reconciliation vectors, unsafe targets, and boundary codecs."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from skm.adapters.integrations._render import json_doc, toml_doc
from skm.modules.integrations.domain.decisions import (
    DIAG_SOURCE_CHANGED,
    FileDecisionKind,
    decide_file,
)
from skm.modules.integrations.domain.desired import DesiredFile
from skm.modules.integrations.domain.managed_block import render_block, replace_blocks
from skm.modules.integrations.domain.merged_json import OwnedKeyPath, merge_owned_json
from skm.modules.integrations.domain.merged_toml import merge_owned_toml
from skm.modules.integrations.domain.observed import AppliedFileRecord, FileKind, observe_bytes
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.projection import ProjectionId, build_planned_write
from skm.modules.integrations.domain.target import Surface, TargetId

APPLIED_AT = datetime(2026, 2, 1, 0, 0, tzinfo=UTC)
PROJ_ID = ProjectionId(UUID("00000000-0000-0000-0000-000000000606"))


def _run_three_way_vector(
    *,
    path: str,
    boundary: ManagedBoundary,
    managed_a: bytes,
    managed_b: bytes,
    disk_when_a: bytes,
    disk_when_b: bytes,
    disk_when_c: bytes,
) -> None:
    desired_b = DesiredFile(
        target=TargetId.CLAUDE_CODE,
        surface=Surface.INSTRUCTIONS,
        relative_path=path,
        boundary=boundary,
        managed_bytes=managed_b,
        managed_digest=sha256_tagged(managed_b),
        source_refs=(),
        renderer="ench6-v1",
    )
    applied_a = AppliedFileRecord(
        projection_id=PROJ_ID,
        relative_path=path,
        surface=Surface.INSTRUCTIONS,
        boundary=boundary,
        applied_managed_digest=sha256_tagged(managed_a),
        applied_whole_digest=sha256_tagged(disk_when_a),
        pre_image_file_version_id=None,
        renderer="ench6-v1",
        applied_at=APPLIED_AT,
    )

    # 1) current == A -> UPDATE (frozen retry / source changed)
    obs_a = observe_bytes(path, disk_when_a, boundary)
    dec_a = decide_file(desired_b, applied_a, obs_a, safe=True)
    assert dec_a.kind is FileDecisionKind.UPDATE
    assert dec_a.diagnostic == DIAG_SOURCE_CHANGED
    pw_a = build_planned_write(dec_a, desired=desired_b, applied=applied_a, observed_bytes=disk_when_a)
    assert pw_a is not None
    assert pw_a.write_path == path
    assert pw_a.new_bytes == disk_when_b
    assert pw_a.expected_observed_whole_digest == sha256_tagged(disk_when_a)

    # 2) current == B -> ADOPT_CLEAN (converged without rewrite)
    obs_b = observe_bytes(path, disk_when_b, boundary)
    dec_b = decide_file(desired_b, applied_a, obs_b, safe=True)
    assert dec_b.kind is FileDecisionKind.ADOPT_CLEAN
    assert dec_b.diagnostic is None
    assert (
        build_planned_write(dec_b, desired=desired_b, applied=applied_a, observed_bytes=disk_when_b) is None
    )

    # 3) current == C -> CONFLICT_WRITE_NEW (C untouched, write goes to <path>.skm-new)
    obs_c = observe_bytes(path, disk_when_c, boundary)
    dec_c = decide_file(desired_b, applied_a, obs_c, safe=True)
    assert dec_c.kind is FileDecisionKind.CONFLICT_WRITE_NEW
    assert dec_c.diagnostic == "PROJECTION_CONFLICT"
    pw_c = build_planned_write(dec_c, desired=desired_b, applied=applied_a, observed_bytes=disk_when_c)
    assert pw_c is not None
    assert pw_c.write_path == f"{path}.skm-new"
    assert pw_c.write_path != path


def test_ench6_three_way_vector_across_all_four_ownership_modes() -> None:
    # 1. MANAGED_FILE
    _run_three_way_vector(
        path=".claude/rules/skm-core.md",
        boundary=ManagedBoundary(ownership=Ownership.MANAGED_FILE),
        managed_a=b"# Core A\n",
        managed_b=b"# Core B\n",
        disk_when_a=b"# Core A\n",
        disk_when_b=b"# Core B\n",
        disk_when_c=b"# User edited C\n",
    )

    # 2. MANAGED_BLOCK (preserving outside bytes verbatim!)
    block_ids = ("instructions.core", "instructions.project")
    block_boundary = ManagedBoundary(ownership=Ownership.MANAGED_BLOCK, block_ids=block_ids)
    outside_prefix = b"# User Header\r\nKeep exact CRLF & unicode \xf0\x9f\x9b\xa0\r\n"
    outside_suffix = b"\r\n# User Footer\r\n"
    blocks_a = render_block("instructions.core", "A1") + render_block("instructions.project", "A2")
    blocks_b = render_block("instructions.core", "B1") + render_block("instructions.project", "B2")
    blocks_c = render_block("instructions.core", "User C1") + render_block("instructions.project", "A2")
    _run_three_way_vector(
        path="AGENTS.md",
        boundary=block_boundary,
        managed_a=blocks_a,
        managed_b=blocks_b,
        disk_when_a=replace_blocks(outside_prefix + blocks_a + outside_suffix, blocks_a, block_ids),
        disk_when_b=replace_blocks(outside_prefix + blocks_a + outside_suffix, blocks_b, block_ids),
        disk_when_c=outside_prefix + blocks_c + outside_suffix,
    )

    # 3. MERGED_JSON (preserving foreign keys and explicit `false`)
    json_owned = (OwnedKeyPath(("permissions", "allow"), "replace"),)
    json_boundary = ManagedBoundary(ownership=Ownership.MERGED_JSON, owned_keys=json_owned)
    base_foreign = '{"enabledPlugins": {"telemetry": false}, "customKey": "keep"}'
    mg_json_a = {"permissions": {"allow": ["Read(a)"]}}
    mg_json_b = {"permissions": {"allow": ["Read(b)"]}}
    mg_json_c = {"permissions": {"allow": ["Read(user-c)"]}}
    _run_three_way_vector(
        path=".claude/settings.json",
        boundary=json_boundary,
        managed_a=json_doc.dumps_bytes(mg_json_a),
        managed_b=json_doc.dumps_bytes(mg_json_b),
        disk_when_a=merge_owned_json(base_foreign, mg_json_a, json_owned).encode("utf-8"),
        disk_when_b=merge_owned_json(base_foreign, mg_json_b, json_owned).encode("utf-8"),
        disk_when_c=merge_owned_json(base_foreign, mg_json_c, json_owned).encode("utf-8"),
    )

    # 4. MERGED_TOML (preserving foreign comments & sections verbatim)
    toml_owned = (
        OwnedKeyPath(("approval_policy",), "replace"),
        OwnedKeyPath(("mcp_servers", "skm"), "replace"),
    )
    toml_boundary = ManagedBoundary(ownership=Ownership.MERGED_TOML, owned_keys=toml_owned)
    base_toml = '# Keep comment\nmodel = "o3"\n\n[mcp_servers.foreign]\ncommand = "keep"\n'
    mg_toml_a = {"approval_policy": "on-request", "mcp_servers": {"skm": {"command": "skm-a"}}}
    mg_toml_b = {"approval_policy": "never", "mcp_servers": {"skm": {"command": "skm-b"}}}
    mg_toml_c = {"approval_policy": "untrusted", "mcp_servers": {"skm": {"command": "skm-c"}}}
    _run_three_way_vector(
        path=".codex/config.toml",
        boundary=toml_boundary,
        managed_a=toml_doc.dumps_bytes(mg_toml_a),
        managed_b=toml_doc.dumps_bytes(mg_toml_b),
        disk_when_a=merge_owned_toml(base_toml, mg_toml_a, toml_owned).encode("utf-8"),
        disk_when_b=merge_owned_toml(base_toml, mg_toml_b, toml_owned).encode("utf-8"),
        disk_when_c=merge_owned_toml(base_toml, mg_toml_c, toml_owned).encode("utf-8"),
    )


@pytest.mark.parametrize(
    ("file_kind", "is_symlink", "outside_root", "rel_path"),
    [
        (FileKind.DIRECTORY, False, False, ".claude/rules/skm.md"),
        (FileKind.SYMLINK, True, False, ".claude/rules/skm.md"),
        (FileKind.FIFO, False, False, ".claude/rules/skm.md"),
        (FileKind.REGULAR, False, True, ".claude/rules/skm.md"),
        (FileKind.REGULAR, False, False, "../outside/skm.md"),
    ],
)
def test_ench6_unsafe_targets_produce_zero_writes_restores_or_deletions(
    file_kind: FileKind,
    is_symlink: bool,
    outside_root: bool,
    rel_path: str,
) -> None:
    boundary = ManagedBoundary(ownership=Ownership.MANAGED_FILE)
    desired = DesiredFile(
        target=TargetId.CLAUDE_CODE,
        surface=Surface.INSTRUCTIONS,
        relative_path=rel_path,
        boundary=boundary,
        managed_bytes=b"managed\n",
        managed_digest=sha256_tagged(b"managed\n"),
        source_refs=(),
        renderer="ench6-v1",
    )
    applied = AppliedFileRecord(
        projection_id=PROJ_ID,
        relative_path=rel_path,
        surface=Surface.INSTRUCTIONS,
        boundary=boundary,
        applied_managed_digest=sha256_tagged(b"managed\n"),
        applied_whole_digest=sha256_tagged(b"managed\n"),
        pre_image_file_version_id=None,
        renderer="ench6-v1",
        applied_at=APPLIED_AT,
    )
    observed = observe_bytes(
        rel_path,
        b"managed\n" if file_kind is FileKind.REGULAR else None,
        boundary,
        is_symlink=is_symlink,
        file_kind=file_kind,
        outside_root=outside_root,
    )

    for des_arg, app_arg in ((desired, None), (desired, applied), (None, applied), (None, None)):
        for force in (False, True):
            decision = decide_file(des_arg, app_arg, observed, safe=True, force_conflicts=force)
            assert decision.kind is FileDecisionKind.UNSAFE_TARGET
            assert decision.diagnostic == "INTEGRATION_UNSAFE_TARGET"
            assert build_planned_write(decision, desired=des_arg, applied=app_arg) is None
