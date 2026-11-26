"""Complete 17-row unit test suite for integrations file reconciliation (§4.4, §4.9)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from skm.modules.integrations.domain.decisions import (
    DIAG_ADOPTED_IDENTICAL,
    DIAG_LEFT_MODIFIED,
    DIAG_MISSING_RESTORED,
    DIAG_SOURCE_CHANGED,
    DIAG_UNMANAGED_TARGET,
    FileDecision,
    FileDecisionKind,
    decide_file,
    is_safe_relative_path,
)
from skm.modules.integrations.domain.desired import DesiredFile
from skm.modules.integrations.domain.managed_block import render_block
from skm.modules.integrations.domain.merged_json import OwnedKeyPath, dumps_merged_json_bytes
from skm.modules.integrations.domain.observed import AppliedFileRecord, FileKind, ObservedFile, observe_bytes
from skm.modules.integrations.domain.ownership import (
    ManagedBoundary,
    Ownership,
    empty_managed_digest,
    sha256_tagged,
)
from skm.modules.integrations.domain.projection import (
    PROJECTION_TRANSITIONS,
    ProjectionId,
    ProjectionState,
    build_planned_write,
    can_transition_projection,
    next_state_after_apply,
)
from skm.modules.integrations.domain.target import Surface, TargetId

FIXED_TIME = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
PROJ_ID = ProjectionId(UUID("00000000-0000-0000-0000-000000000101"))

WHOLE_BOUNDARY = ManagedBoundary(ownership=Ownership.MANAGED_FILE)
BLOCK_BOUNDARY = ManagedBoundary(
    ownership=Ownership.MANAGED_BLOCK,
    block_ids=("instructions.core",),
)
JSON_BOUNDARY = ManagedBoundary(
    ownership=Ownership.MERGED_JSON,
    owned_keys=(OwnedKeyPath(("permissions", "allow"), "replace"),),
)
TOML_BOUNDARY = ManagedBoundary(
    ownership=Ownership.MERGED_TOML,
    owned_keys=(OwnedKeyPath(("approval_policy",), "replace"),),
)


def _desired(
    path: str = ".claude/rules/skm.md",
    managed_bytes: bytes = b"desired-v1\n",
    boundary: ManagedBoundary = WHOLE_BOUNDARY,
) -> DesiredFile:
    return DesiredFile(
        target=TargetId.CLAUDE_CODE,
        surface=Surface.INSTRUCTIONS,
        relative_path=path,
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=(),
        renderer="renderer-v1",
    )


def _applied(
    path: str = ".claude/rules/skm.md",
    managed_bytes: bytes = b"applied-v0\n",
    whole_bytes: bytes | None = None,
    boundary: ManagedBoundary = WHOLE_BOUNDARY,
) -> AppliedFileRecord:
    whole = managed_bytes if whole_bytes is None else whole_bytes
    return AppliedFileRecord(
        projection_id=PROJ_ID,
        relative_path=path,
        surface=Surface.INSTRUCTIONS,
        boundary=boundary,
        applied_managed_digest=sha256_tagged(managed_bytes),
        applied_whole_digest=sha256_tagged(whole),
        pre_image_file_version_id=None,
        renderer="renderer-v1",
        applied_at=FIXED_TIME,
    )


def test_row_01_unsafe_target_when_not_safe_or_symlink_or_non_regular() -> None:
    des = _desired()
    obs_ok = observe_bytes(des.relative_path, b"desired-v1\n", WHOLE_BOUNDARY)
    r_unsafe_flag = decide_file(des, None, obs_ok, safe=False)
    assert r_unsafe_flag == FileDecision(
        relative_path=des.relative_path,
        kind=FileDecisionKind.UNSAFE_TARGET,
        diagnostic="INTEGRATION_UNSAFE_TARGET",
        expected_observed_managed_digest=obs_ok.managed_digest,
        expected_observed_whole_digest=obs_ok.whole_digest,
    )

    obs_symlink = observe_bytes(des.relative_path, b"target", WHOLE_BOUNDARY, is_symlink=True)
    r_symlink = decide_file(des, None, obs_symlink, safe=True)
    assert r_symlink.kind is FileDecisionKind.UNSAFE_TARGET
    assert r_symlink.diagnostic == "INTEGRATION_UNSAFE_TARGET"

    for bad_kind in (FileKind.DIRECTORY, FileKind.FIFO, FileKind.OTHER):
        obs_special = observe_bytes(des.relative_path, None, WHOLE_BOUNDARY, file_kind=bad_kind)
        res = decide_file(des, None, obs_special, safe=True)
        assert res.kind is FileDecisionKind.UNSAFE_TARGET
        assert res.diagnostic == "INTEGRATION_UNSAFE_TARGET"


def test_row_02_boundary_invalid_on_malformed_managed_boundary() -> None:
    block_bytes = render_block("instructions.core", "Core")
    des = _desired("AGENTS.md", block_bytes, BLOCK_BOUNDARY)
    obs = observe_bytes(
        "AGENTS.md",
        b"<!-- skm:begin id=instructions.core digest=0123456789ab -->\nunclosed\n",
        BLOCK_BOUNDARY,
    )
    assert obs.boundary_valid is False
    res = decide_file(des, None, obs, safe=True)
    assert res.kind is FileDecisionKind.BOUNDARY_INVALID
    assert res.diagnostic == "INTEGRATION_BOUNDARY_INVALID"
    assert res.expected_observed_managed_digest is None
    assert res.expected_observed_whole_digest == obs.whole_digest
    # force_conflicts must NOT override BOUNDARY_INVALID
    assert decide_file(des, None, obs, safe=True, force_conflicts=True) == res


def test_row_03_create_when_no_applied_and_missing_on_disk() -> None:
    des = _desired()
    obs = observe_bytes(des.relative_path, None, WHOLE_BOUNDARY)
    res = decide_file(des, None, obs, safe=True)
    assert res == FileDecision(
        relative_path=des.relative_path,
        kind=FileDecisionKind.CREATE,
        diagnostic=None,
        expected_observed_managed_digest=None,
        expected_observed_whole_digest=None,
    )


def test_row_04_adopt_clean_when_unmanaged_file_matches_desired() -> None:
    des = _desired()
    obs = observe_bytes(des.relative_path, b"desired-v1\n", WHOLE_BOUNDARY)
    res = decide_file(des, None, obs, safe=True)
    assert res == FileDecision(
        relative_path=des.relative_path,
        kind=FileDecisionKind.ADOPT_CLEAN,
        diagnostic=DIAG_ADOPTED_IDENTICAL,
        expected_observed_managed_digest=des.managed_digest,
        expected_observed_whole_digest=obs.whole_digest,
    )


def test_row_05_adopt_required_on_unmanaged_whole_file_even_with_force_conflicts() -> None:
    des = _desired()
    obs = observe_bytes(des.relative_path, b"foreign user content\n", WHOLE_BOUNDARY)
    res = decide_file(des, None, obs, safe=True)
    assert res.kind is FileDecisionKind.ADOPT_REQUIRED
    assert res.diagnostic == DIAG_UNMANAGED_TARGET
    # force_conflicts=True MUST NOT override Row 5!
    assert decide_file(des, None, obs, safe=True, force_conflicts=True) == res


def test_row_06_update_insert_managed_block_into_existing_file_without_blocks() -> None:
    block_bytes = render_block("instructions.core", "Core body")
    des = _desired("AGENTS.md", block_bytes, BLOCK_BOUNDARY)
    raw = b"# Team Handbook\nExisting user markdown.\n"
    obs = observe_bytes("AGENTS.md", raw, BLOCK_BOUNDARY)
    assert obs.managed_digest == empty_managed_digest(BLOCK_BOUNDARY)

    res = decide_file(des, None, obs, safe=True)
    assert res.kind is FileDecisionKind.UPDATE
    assert res.diagnostic is None
    assert res.needs_pre_image is True
    assert res.expected_observed_whole_digest == obs.whole_digest

    pw = build_planned_write(res, desired=des, observed_bytes=raw)
    assert pw is not None
    assert pw.needs_pre_image is True
    assert pw.new_bytes == raw + block_bytes


@pytest.mark.parametrize(
    ("path", "boundary", "raw_existing", "managed_bytes"),
    [
        (
            ".claude/settings.json",
            JSON_BOUNDARY,
            b'{\n  "theme": "dark"\n}\n',
            dumps_merged_json_bytes({"permissions": {"allow": ["Read(*)"]}}),
        ),
        (
            ".codex/config.toml",
            TOML_BOUNDARY,
            b'model = "o3"\n',
            b'approval_policy = "never"\n',
        ),
    ],
)
def test_row_07_update_initial_merge_into_json_and_toml_without_owned_keys(
    path: str,
    boundary: ManagedBoundary,
    raw_existing: bytes,
    managed_bytes: bytes,
) -> None:
    des = _desired(path, managed_bytes, boundary)
    obs = observe_bytes(path, raw_existing, boundary)
    assert obs.managed_digest == empty_managed_digest(boundary)

    res = decide_file(des, None, obs, safe=True)
    assert res.kind is FileDecisionKind.UPDATE
    assert res.diagnostic is None
    assert res.needs_pre_image is True

    pw = build_planned_write(res, desired=des, observed_bytes=raw_existing)
    assert pw is not None
    assert pw.needs_pre_image is True


@pytest.mark.parametrize(
    ("path", "boundary", "foreign_with_owned_part", "desired_managed"),
    [
        (
            "AGENTS.md",
            BLOCK_BOUNDARY,
            b"# Header\n" + render_block("instructions.core", "Foreign pre-existing block"),
            render_block("instructions.core", "Desired block"),
        ),
        (
            ".claude/settings.json",
            JSON_BOUNDARY,
            b'{\n  "permissions": {\n    "allow": ["Bash(foreign)"]\n  }\n}\n',
            dumps_merged_json_bytes({"permissions": {"allow": ["Read(*)"]}}),
        ),
        (
            ".codex/config.toml",
            TOML_BOUNDARY,
            b'approval_policy = "on-failure"\n',
            b'approval_policy = "never"\n',
        ),
    ],
)
def test_row_08_adopt_required_when_partial_boundary_already_has_foreign_owned_content(
    path: str,
    boundary: ManagedBoundary,
    foreign_with_owned_part: bytes,
    desired_managed: bytes,
) -> None:
    des = _desired(path, desired_managed, boundary)
    obs = observe_bytes(path, foreign_with_owned_part, boundary)
    res = decide_file(des, None, obs, safe=True)
    assert res.kind is FileDecisionKind.ADOPT_REQUIRED
    assert res.diagnostic == DIAG_UNMANAGED_TARGET
    # force_conflicts=True MUST NOT override Row 8!
    assert decide_file(des, None, obs, safe=True, force_conflicts=True) == res


def test_row_09_create_restores_deleted_previously_applied_file() -> None:
    des = _desired()
    app = _applied(managed_bytes=b"desired-v1\n")
    obs = observe_bytes(des.relative_path, None, WHOLE_BOUNDARY)
    res = decide_file(des, app, obs, safe=True)
    assert res == FileDecision(
        relative_path=des.relative_path,
        kind=FileDecisionKind.CREATE,
        diagnostic=DIAG_MISSING_RESTORED,
        expected_observed_managed_digest=None,
        expected_observed_whole_digest=None,
    )


def test_row_10_noop_when_observed_applied_and_desired_all_match() -> None:
    des = _desired(managed_bytes=b"same-v1\n")
    app = _applied(managed_bytes=b"same-v1\n")
    obs = observe_bytes(des.relative_path, b"same-v1\n", WHOLE_BOUNDARY)
    res = decide_file(des, app, obs, safe=True)
    assert res == FileDecision(
        relative_path=des.relative_path,
        kind=FileDecisionKind.NOOP,
        diagnostic=None,
        expected_observed_managed_digest=obs.managed_digest,
        expected_observed_whole_digest=obs.whole_digest,
    )


def test_row_11_update_when_desired_changed_and_disk_matches_applied() -> None:
    des = _desired(managed_bytes=b"desired-v2\n")
    app = _applied(managed_bytes=b"applied-v1\n")
    obs = observe_bytes(des.relative_path, b"applied-v1\n", WHOLE_BOUNDARY)
    res = decide_file(des, app, obs, safe=True)
    assert res == FileDecision(
        relative_path=des.relative_path,
        kind=FileDecisionKind.UPDATE,
        diagnostic=DIAG_SOURCE_CHANGED,
        expected_observed_managed_digest=obs.managed_digest,
        expected_observed_whole_digest=obs.whole_digest,
    )
    assert res.needs_pre_image is False


def test_row_12_adopt_clean_when_user_edited_to_exact_desired_bytes() -> None:
    des = _desired(managed_bytes=b"desired-v2\n")
    app = _applied(managed_bytes=b"applied-v1\n")
    obs = observe_bytes(des.relative_path, b"desired-v2\n", WHOLE_BOUNDARY)
    res = decide_file(des, app, obs, safe=True)
    assert res == FileDecision(
        relative_path=des.relative_path,
        kind=FileDecisionKind.ADOPT_CLEAN,
        diagnostic=None,
        expected_observed_managed_digest=obs.managed_digest,
        expected_observed_whole_digest=obs.whole_digest,
    )


def test_row_13_conflict_write_new_and_force_conflicts_override() -> None:
    des = _desired(managed_bytes=b"desired-v2\n")
    app = _applied(managed_bytes=b"applied-v1\n")
    obs = observe_bytes(des.relative_path, b"user-diverged-edit\n", WHOLE_BOUNDARY)

    conflict = decide_file(des, app, obs, safe=True, force_conflicts=False)
    assert conflict == FileDecision(
        relative_path=des.relative_path,
        kind=FileDecisionKind.CONFLICT_WRITE_NEW,
        diagnostic="PROJECTION_CONFLICT",
        expected_observed_managed_digest=obs.managed_digest,
        expected_observed_whole_digest=obs.whole_digest,
    )
    assert conflict.needs_pre_image is False
    pw_conflict = build_planned_write(
        conflict, desired=des, applied=app, observed_bytes=b"user-diverged-edit\n"
    )
    assert pw_conflict is not None
    assert pw_conflict.write_path == f"{des.relative_path}.skm-new"
    assert pw_conflict.needs_pre_image is False

    forced = decide_file(des, app, obs, safe=True, force_conflicts=True)
    assert forced == FileDecision(
        relative_path=des.relative_path,
        kind=FileDecisionKind.UPDATE,
        diagnostic="PROJECTION_CONFLICT",
        expected_observed_managed_digest=obs.managed_digest,
        expected_observed_whole_digest=obs.whole_digest,
    )
    assert forced.needs_pre_image is True
    pw_forced = build_planned_write(forced, desired=des, applied=app, observed_bytes=b"user-diverged-edit\n")
    assert pw_forced is not None
    assert pw_forced.write_path == des.relative_path
    assert pw_forced.needs_pre_image is True


def test_row_14_remove_owned_when_no_longer_desired_and_already_missing() -> None:
    app = _applied(managed_bytes=b"applied-v1\n")
    obs = observe_bytes(app.relative_path, None, WHOLE_BOUNDARY)
    res = decide_file(None, app, obs, safe=True)
    assert res == FileDecision(
        relative_path=app.relative_path,
        kind=FileDecisionKind.REMOVE_OWNED,
        diagnostic=None,
        expected_observed_managed_digest=None,
        expected_observed_whole_digest=None,
    )
    # Already absent on disk -> no filesystem delete write required
    assert build_planned_write(res, desired=None, applied=app, observed_bytes=None) is None


def test_row_15_remove_owned_when_no_longer_desired_and_disk_matches_applied() -> None:
    app = _applied(managed_bytes=b"applied-v1\n")
    obs = observe_bytes(app.relative_path, b"applied-v1\n", WHOLE_BOUNDARY)
    res = decide_file(None, app, obs, safe=True)
    assert res == FileDecision(
        relative_path=app.relative_path,
        kind=FileDecisionKind.REMOVE_OWNED,
        diagnostic=None,
        expected_observed_managed_digest=obs.managed_digest,
        expected_observed_whole_digest=obs.whole_digest,
    )
    pw = build_planned_write(res, desired=None, applied=app, observed_bytes=b"applied-v1\n")
    assert pw is not None
    assert pw.new_bytes is None  # MANAGED_FILE deletion


def test_row_16_leave_modified_when_no_longer_desired_but_user_modified() -> None:
    app = _applied(managed_bytes=b"applied-v1\n")
    obs = observe_bytes(app.relative_path, b"user-modified\n", WHOLE_BOUNDARY)
    res = decide_file(None, app, obs, safe=True)
    assert res == FileDecision(
        relative_path=app.relative_path,
        kind=FileDecisionKind.LEAVE_MODIFIED,
        diagnostic=DIAG_LEFT_MODIFIED,
        expected_observed_managed_digest=obs.managed_digest,
        expected_observed_whole_digest=obs.whole_digest,
    )
    assert decide_file(None, app, obs, safe=True, force_conflicts=True) == res
    assert build_planned_write(res, desired=None, applied=app, observed_bytes=b"user-modified\n") is None


def test_row_17_noop_foreign_file_neither_desired_nor_applied() -> None:
    obs = observe_bytes("README.md", b"# Foreign project readme\n", WHOLE_BOUNDARY)
    res = decide_file(None, None, obs, safe=True)
    assert res == FileDecision(
        relative_path="README.md",
        kind=FileDecisionKind.NOOP,
        diagnostic=None,
        expected_observed_managed_digest=obs.managed_digest,
        expected_observed_whole_digest=obs.whole_digest,
    )


def test_safe_relative_path_checks_and_decision_determinism_and_immutability() -> None:
    assert is_safe_relative_path("AGENTS.md") is True
    assert is_safe_relative_path(".claude/settings.json") is True
    assert is_safe_relative_path("") is False
    assert is_safe_relative_path("/etc/passwd") is False
    assert is_safe_relative_path("../escape.txt") is False
    assert is_safe_relative_path("a/../b.txt") is False
    assert is_safe_relative_path("./a.txt") is False
    assert is_safe_relative_path("a//b.txt") is False
    assert is_safe_relative_path("a\\b.txt") is False
    assert is_safe_relative_path("C:foo.txt") is False
    assert is_safe_relative_path("bad\x00name") is False

    des = _desired()
    obs = ObservedFile(
        relative_path=des.relative_path,
        exists=True,
        is_symlink=False,
        whole_digest=des.managed_digest,
        managed_digest=des.managed_digest,
        boundary_valid=True,
        has_conflict_file=False,
    )
    first = decide_file(des, None, obs, safe=True)
    second = decide_file(des, None, obs, safe=True)
    assert first == second

    with pytest.raises(FrozenInstanceError):
        first.kind = FileDecisionKind.NOOP  # type: ignore[misc]


def test_projection_state_transitions_and_next_state_after_apply() -> None:
    assert set(PROJECTION_TRANSITIONS.keys()) == set(ProjectionState)
    assert can_transition_projection(ProjectionState.PENDING, ProjectionState.IN_SYNC) is True
    assert can_transition_projection(ProjectionState.REMOVED, ProjectionState.FAILED) is False

    assert next_state_after_apply(conflicts=(), failed=()) is ProjectionState.IN_SYNC
    assert next_state_after_apply(conflicts=("a.md",), failed=()) is ProjectionState.DRIFTED
    assert next_state_after_apply(conflicts=("a.md",), failed=(("b.md", "ERR"),)) is ProjectionState.FAILED
    assert next_state_after_apply(conflicts=(), failed=(), left_modified=("c.md",)) is ProjectionState.IN_SYNC
