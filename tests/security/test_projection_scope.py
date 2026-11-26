"""Security tests for ``integrations`` scope, pre-image ownership, path traversal, and RBAC (P10.01.b)."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest

from contracts.integrations.harness import Side, memory_side, postgres_side
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import ScopeId
from skm.modules.access.public import Role
from skm.modules.integrations.domain.ownership import sha256_tagged
from skm.modules.integrations.public import (
    GetAppliedState,
    GetDesiredProjection,
    ListProjections,
    RecordDrift,
    RecordDriftFilesItem,
    RecordProjectionApplied,
    RecordProjectionAppliedDefsAppliedFileInput,
    RemoveProjection,
)
from support.pg import clean_test_database, pg_session, test_database  # noqa: F401 - pytest fixtures

DIGEST = sha256_tagged(b"security-desired")
INPUTS = sha256_tagged(b"security-inputs")


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def sec_side(request: pytest.FixtureRequest) -> Iterator[Side]:
    made = (
        memory_side()
        if request.param == "memory"
        else postgres_side(request.getfixturevalue("clean_test_database"))
    )
    try:
        yield made
    finally:
        made.close()


def _managed_file(
    path: str = ".claude/skills/skm-sec/SKILL.md",
    *,
    pre_image_id: UUID | None = None,
) -> RecordProjectionAppliedDefsAppliedFileInput:
    return RecordProjectionAppliedDefsAppliedFileInput(
        relative_path=path,
        surface="skills",
        ownership="managed_file",
        block_ids=(),
        owned_keys=(),
        applied_managed_digest=DIGEST,
        applied_whole_digest=DIGEST,
        pre_image_file_version_id=pre_image_id,
        renderer="claude_code.skills@1",
    )


def _apply_cmd(
    project_id: object,
    checkout_binding_id: object,
    *,
    base_row_version: int | None = None,
    files: tuple[RecordProjectionAppliedDefsAppliedFileInput, ...] | None = None,
    removed: tuple[str, ...] = (),
) -> RecordProjectionApplied:
    return RecordProjectionApplied(
        project_id=UUID(str(project_id)),
        checkout_binding_id=UUID(str(checkout_binding_id)),
        target="claude_code",
        desired_digest=DIGEST,
        inputs_digest=INPUTS,
        renderer_version="claude_code@1",
        base_row_version=base_row_version,
        files=(_managed_file(),) if files is None else files,
        removed=removed,
        conflicts=(),
        failed=(),
        adopted=(),
        left_modified=(),
    )


def test_cross_project_checkout_binding_rejected(sec_side: Side) -> None:
    proj_a = sec_side.seed_checkout("sec-a")
    proj_b = sec_side.seed_checkout("sec-b")
    same_ws_proj_c = sec_side.project(proj_a.workspace_id, slug="proj-sec-c", title="Project Sec C")

    with pytest.raises(NotFound) as apply_exc:
        sec_side.run(
            _apply_cmd(proj_a.project_id, proj_b.checkout_binding_id),
            key="sec-foreign-binding-1",
        )
    assert apply_exc.value.code is ErrorCode.NOT_FOUND

    with pytest.raises(NotFound) as query_exc:
        sec_side.ask(
            GetDesiredProjection(
                project_id=UUID(str(proj_a.project_id)),
                checkout_binding_id=UUID(str(proj_b.checkout_binding_id)),
                target="claude_code",
            )
        )
    assert query_exc.value.code is ErrorCode.NOT_FOUND

    with pytest.raises(NotFound) as drift_exc:
        sec_side.run(
            RecordDrift(
                project_id=UUID(str(proj_a.project_id)),
                checkout_binding_id=UUID(str(proj_b.checkout_binding_id)),
                target="claude_code",
                desired_digest=DIGEST,
                base_row_version=1,
                files=(),
            )
        )
    assert drift_exc.value.code is ErrorCode.NOT_FOUND

    with pytest.raises(NotFound) as unattached_exc:
        sec_side.run(
            _apply_cmd(same_ws_proj_c, proj_a.checkout_binding_id),
            key="sec-unattached-binding",
        )
    assert unattached_exc.value.code is ErrorCode.NOT_FOUND


def test_cross_workspace_or_unready_pre_image_rejected(sec_side: Side) -> None:
    proj_a = sec_side.seed_checkout("pre-a")
    proj_b = sec_side.seed_checkout("pre-b")

    foreign_version = UUID(str(sec_side.seed_file_version(proj_b.workspace_id, proj_b.project_id)))
    trashed_version = UUID(
        str(sec_side.seed_file_version(proj_a.workspace_id, proj_a.project_id, trashed=True))
    )
    missing_blob_version = UUID(
        str(sec_side.seed_file_version(proj_a.workspace_id, proj_a.project_id, blob_missing=True))
    )

    with pytest.raises(NotFound) as foreign_exc:
        sec_side.run(
            _apply_cmd(
                proj_a.project_id,
                proj_a.checkout_binding_id,
                files=(_managed_file(pre_image_id=foreign_version),),
            ),
            key="sec-pre-foreign",
        )
    assert foreign_exc.value.code is ErrorCode.NOT_FOUND

    for idx, bad_ver in enumerate((trashed_version, missing_blob_version)):
        with pytest.raises(PreconditionFailed) as unready_exc:
            sec_side.run(
                _apply_cmd(
                    proj_a.project_id,
                    proj_a.checkout_binding_id,
                    files=(_managed_file(pre_image_id=bad_ver),),
                ),
                key=f"sec-pre-unready-{idx}",
            )
        assert unready_exc.value.code is ErrorCode.FILE_VERSION_NOT_READY


def test_remove_projection_cross_project_leak_prevention(sec_side: Side) -> None:
    proj_a = sec_side.seed_checkout("leak-a")
    proj_b = sec_side.seed_checkout("leak-b")

    applied_b = sec_side.run(
        _apply_cmd(proj_b.project_id, proj_b.checkout_binding_id),
        key="sec-leak-init",
    )

    with pytest.raises(NotFound) as rm_exc:
        sec_side.run(
            RemoveProjection(
                project_id=UUID(str(proj_a.project_id)),
                projection_id=applied_b.projection_id,
                base_row_version=1,
                removed=(".claude/skills/skm-sec/SKILL.md",),
                left_modified=(),
                failed=(),
            ),
            key="sec-leak-rm",
        )
    assert rm_exc.value.code is ErrorCode.NOT_FOUND

    state_b = sec_side.ask(
        GetAppliedState(
            project_id=UUID(str(proj_b.project_id)),
            checkout_binding_id=UUID(str(proj_b.checkout_binding_id)),
            target="claude_code",
        )
    )
    assert state_b.projection is not None
    assert state_b.projection.state == "in_sync"
    assert len(state_b.files) == 1


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.md",
        "/etc/passwd",
        ".git/config",
        "dir/../../escape.json",
        "bad\npath.md",
    ],
)
def test_unsafe_relative_paths_rejected(sec_side: Side, unsafe_path: str) -> None:
    seeded = sec_side.seed_checkout("paths-sec")
    applied = sec_side.run(
        _apply_cmd(seeded.project_id, seeded.checkout_binding_id),
        key="sec-paths-init",
    )

    with pytest.raises(ValidationFailed) as apply_exc:
        sec_side.run(
            _apply_cmd(
                seeded.project_id,
                seeded.checkout_binding_id,
                base_row_version=1,
                files=(_managed_file(path=unsafe_path),),
                removed=(".claude/skills/skm-sec/SKILL.md",),
            ),
            key="sec-paths-apply",
        )
    assert apply_exc.value.code is ErrorCode.SCHEMA_INVALID

    with pytest.raises(ValidationFailed) as drift_exc:
        sec_side.run(
            RecordDrift(
                project_id=UUID(str(seeded.project_id)),
                checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
                target="claude_code",
                base_row_version=1,
                desired_digest=DIGEST,
                files=(
                    RecordDriftFilesItem(
                        relative_path=unsafe_path,
                        decision="adopt_required",
                        diagnostic=None,
                    ),
                ),
            )
        )
    assert drift_exc.value.code is ErrorCode.SCHEMA_INVALID

    with pytest.raises(ValidationFailed) as rm_exc:
        sec_side.run(
            RemoveProjection(
                project_id=UUID(str(seeded.project_id)),
                projection_id=applied.projection_id,
                base_row_version=1,
                removed=(unsafe_path,),
                left_modified=(),
                failed=(),
            ),
            key="sec-paths-rm",
        )
    assert rm_exc.value.code is ErrorCode.SCHEMA_INVALID


def test_permissions_enforcement(sec_side: Side) -> None:
    seeded = sec_side.seed_checkout("rbac")
    applied = sec_side.run(
        _apply_cmd(seeded.project_id, seeded.checkout_binding_id),
        key="sec-rbac-init",
    )

    sec_side.person("viewer", {ScopeId(UUID(str(seeded.project_id))): Role.VIEWER})
    sec_side.person("outsider", {})

    assert sec_side.ask(
        GetDesiredProjection(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        ),
        actor="viewer",
    ).project_id == UUID(str(seeded.project_id))
    assert (
        sec_side.ask(
            GetAppliedState(
                project_id=UUID(str(seeded.project_id)),
                checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
                target="claude_code",
            ),
            actor="viewer",
        ).projection
        is not None
    )
    listed = sec_side.ask(ListProjections(project_id=UUID(str(seeded.project_id))), actor="viewer")
    assert len(listed.items) == 1
    assert (
        sec_side.run(
            RecordDrift(
                project_id=UUID(str(seeded.project_id)),
                checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
                target="claude_code",
                base_row_version=1,
                desired_digest=DIGEST,
                files=(),
            ),
            actor="viewer",
        ).state
        == "in_sync"
    )

    with pytest.raises(Forbidden) as viewer_apply_exc:
        sec_side.run(
            _apply_cmd(seeded.project_id, seeded.checkout_binding_id, base_row_version=2),
            actor="viewer",
            key="sec-viewer-apply",
        )
    assert viewer_apply_exc.value.code is ErrorCode.FORBIDDEN

    with pytest.raises(Forbidden) as viewer_rm_exc:
        sec_side.run(
            RemoveProjection(
                project_id=UUID(str(seeded.project_id)),
                projection_id=applied.projection_id,
                base_row_version=2,
                removed=(),
                left_modified=(),
                failed=(),
            ),
            actor="viewer",
            key="sec-viewer-rm",
        )
    assert viewer_rm_exc.value.code is ErrorCode.FORBIDDEN

    for query_dto in (
        GetDesiredProjection(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        ),
        GetAppliedState(
            project_id=UUID(str(seeded.project_id)),
            checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
            target="claude_code",
        ),
        ListProjections(project_id=UUID(str(seeded.project_id))),
    ):
        with pytest.raises(Forbidden):
            sec_side.ask(query_dto, actor="outsider")

    with pytest.raises(Forbidden):
        sec_side.run(
            RecordDrift(
                project_id=UUID(str(seeded.project_id)),
                checkout_binding_id=UUID(str(seeded.checkout_binding_id)),
                target="claude_code",
                base_row_version=2,
                desired_digest=DIGEST,
                files=(),
            ),
            actor="outsider",
        )
