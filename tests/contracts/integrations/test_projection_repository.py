"""Dual-backend contract suite for ``ProjectionRepository`` (integrations §6, §11; DDL ``0020``)."""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from uuid import UUID

import pytest

from contracts.integrations.harness import INSTANCE, Side
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.ids import ProjectId, ScopeId
from skm.kernel.pagination import Cursor
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.integrations.domain.merged_json import OwnedKeyPath
from skm.modules.integrations.domain.observed import AppliedFileRecord
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.projection import Projection, ProjectionId, ProjectionState
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.ports import ProjectionRepository
from skm.modules.workspace.public import CheckoutBindingId

DIGEST_A = sha256_tagged(b"desired-a")
DIGEST_B = sha256_tagged(b"desired-b")


def _new_projection(
    side: Side,
    *,
    workspace_id: object,
    project_id: object,
    checkout_binding_id: object,
    target: TargetId = TargetId.CLAUDE_CODE,
    state: ProjectionState = ProjectionState.IN_SYNC,
    desired_digest: str | None = DIGEST_A,
    applied_desired_digest: str | None = DIGEST_A,
) -> Projection:
    from skm.kernel.ids import WorkspaceId

    now = side.clock.now()
    return Projection(
        id=ProjectionId(side.ids.new_id()),
        workspace_id=WorkspaceId(UUID(str(workspace_id))),
        project_id=ProjectId(UUID(str(project_id))),
        checkout_binding_id=CheckoutBindingId(UUID(str(checkout_binding_id))),
        target=target,
        state=state,
        desired_digest=desired_digest,
        applied_desired_digest=applied_desired_digest,
        renderer_version=f"{target.value}@1",
        applied_at=now,
        drift_checked_at=None,
        row_version=1,
    )


def test_projection_add_get_and_find(side: Side) -> None:
    seeded = side.seed_checkout("a")
    proj = _new_projection(
        side,
        workspace_id=seeded.workspace_id,
        project_id=seeded.project_id,
        checkout_binding_id=seeded.checkout_binding_id,
    )
    with side.uow() as uow:
        uow.repo(ProjectionRepository).add(proj)
        uow.commit()

    with side.uow(readonly=True) as uow:
        repo = uow.repo(ProjectionRepository)
        assert repo.get(proj.id) == proj
        assert repo.find(seeded.project_id, seeded.checkout_binding_id, TargetId.CLAUDE_CODE) == proj
        assert repo.find(seeded.project_id, seeded.checkout_binding_id, TargetId.CODEX) is None
        with pytest.raises(NotFound) as exc_info:
            repo.get(ProjectionId(side.ids.new_id()))
        assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_projection_duplicate_conflict(side: Side) -> None:
    seeded = side.seed_checkout("dup")
    first = _new_projection(
        side,
        workspace_id=seeded.workspace_id,
        project_id=seeded.project_id,
        checkout_binding_id=seeded.checkout_binding_id,
    )
    second_same_slot = _new_projection(
        side,
        workspace_id=seeded.workspace_id,
        project_id=seeded.project_id,
        checkout_binding_id=seeded.checkout_binding_id,
    )
    with side.uow() as uow:
        uow.repo(ProjectionRepository).add(first)
        uow.commit()

    with pytest.raises(Conflict) as exc_info, side.uow() as uow:
        uow.repo(ProjectionRepository).add(second_same_slot)
    assert exc_info.value.code is ErrorCode.ALREADY_EXISTS

    same_id_other_target = replace(first, target=TargetId.CODEX)
    with pytest.raises(Conflict) as id_exc, side.uow() as uow:
        uow.repo(ProjectionRepository).add(same_id_other_target)
    assert id_exc.value.code is ErrorCode.ALREADY_EXISTS


def test_projection_save_optimistic_lock(side: Side) -> None:
    seeded = side.seed_checkout("cas")
    proj = _new_projection(
        side,
        workspace_id=seeded.workspace_id,
        project_id=seeded.project_id,
        checkout_binding_id=seeded.checkout_binding_id,
    )
    with side.uow() as uow:
        uow.repo(ProjectionRepository).add(proj)
        uow.commit()

    side.tick(5.0)
    v2 = replace(
        proj,
        state=ProjectionState.DRIFTED,
        desired_digest=DIGEST_B,
        drift_checked_at=side.clock.now(),
        row_version=2,
    )
    with side.uow() as uow:
        uow.repo(ProjectionRepository).save(v2, expected_version=1)
        uow.commit()

    stale = replace(v2, state=ProjectionState.PENDING, row_version=3)
    with pytest.raises(Conflict) as exc_info, side.uow() as uow:
        uow.repo(ProjectionRepository).save(stale, expected_version=1)
    assert exc_info.value.code is ErrorCode.VERSION_CONFLICT

    with side.uow(readonly=True) as uow:
        loaded = uow.repo(ProjectionRepository).get(proj.id)
        assert loaded.row_version == 2
        assert loaded.state is ProjectionState.DRIFTED


def test_projection_replace_files_round_trip(side: Side) -> None:
    seeded = side.seed_checkout("files")
    pre_image_id = side.seed_file_version(seeded.workspace_id, seeded.project_id)
    proj = _new_projection(
        side,
        workspace_id=seeded.workspace_id,
        project_id=seeded.project_id,
        checkout_binding_id=seeded.checkout_binding_id,
    )
    now = side.clock.now()
    rec_file = AppliedFileRecord(
        projection_id=proj.id,
        relative_path=".claude/skills/skm-review/SKILL.md",
        surface=Surface.SKILLS,
        boundary=ManagedBoundary(ownership=Ownership.MANAGED_FILE),
        applied_managed_digest=sha256_tagged(b"skill-body"),
        applied_whole_digest=sha256_tagged(b"skill-body"),
        pre_image_file_version_id=None,
        renderer="claude_code.skills@1",
        applied_at=now,
    )
    rec_block = AppliedFileRecord(
        projection_id=proj.id,
        relative_path="CLAUDE.md",
        surface=Surface.INSTRUCTIONS,
        boundary=ManagedBoundary(
            ownership=Ownership.MANAGED_BLOCK,
            block_ids=("core", "project"),
        ),
        applied_managed_digest=sha256_tagged(b"blocks"),
        applied_whole_digest=sha256_tagged(b"whole-claude-md"),
        pre_image_file_version_id=pre_image_id,
        renderer="claude_code.instructions@1",
        applied_at=now,
    )
    rec_json = AppliedFileRecord(
        projection_id=proj.id,
        relative_path=".claude/settings.local.json",
        surface=Surface.PERMISSIONS,
        boundary=ManagedBoundary(
            ownership=Ownership.MERGED_JSON,
            owned_keys=(
                OwnedKeyPath(path=("permissions", "allow"), mode="list_union_tagged"),
                OwnedKeyPath(path=("hooks",), mode="replace"),
            ),
        ),
        applied_managed_digest=sha256_tagged(b"json-managed"),
        applied_whole_digest=sha256_tagged(b"json-whole"),
        pre_image_file_version_id=pre_image_id,
        renderer="claude_code.permissions@1",
        applied_at=now,
    )
    rec_toml = AppliedFileRecord(
        projection_id=proj.id,
        relative_path=".codex/config.toml",
        surface=Surface.MCP,
        boundary=ManagedBoundary(
            ownership=Ownership.MERGED_TOML,
            owned_keys=(OwnedKeyPath(path=("mcp_servers", "skm"), mode="replace"),),
        ),
        applied_managed_digest=sha256_tagged(b"toml-managed"),
        applied_whole_digest=sha256_tagged(b"toml-whole"),
        pre_image_file_version_id=None,
        renderer="codex.mcp@1",
        applied_at=now,
    )

    with side.uow() as uow:
        repo = uow.repo(ProjectionRepository)
        repo.add(proj)
        repo.replace_files(proj.id, (rec_json, rec_block, rec_toml, rec_file))
        uow.commit()

    with side.uow(readonly=True) as uow:
        stored = uow.repo(ProjectionRepository).files(proj.id)
        assert stored == (rec_json, rec_file, rec_toml, rec_block)

    with side.uow() as uow:
        uow.repo(ProjectionRepository).replace_files(proj.id, (rec_block,))
        uow.commit()

    with side.uow(readonly=True) as uow:
        assert uow.repo(ProjectionRepository).files(proj.id) == (rec_block,)


def test_projection_managed_file_paths(side: Side) -> None:
    seeded = side.seed_checkout("paths")
    host_b = side.host("host-paths-b")
    binding_b = side.bind_checkout(
        seeded.repository_id,
        host_b,
        local_locator="/work/repo-paths-b",
        remote="https://github.com/acme/repo-paths.git",
    )
    active_proj = _new_projection(
        side,
        workspace_id=seeded.workspace_id,
        project_id=seeded.project_id,
        checkout_binding_id=seeded.checkout_binding_id,
        target=TargetId.CLAUDE_CODE,
        state=ProjectionState.IN_SYNC,
    )
    removed_proj = _new_projection(
        side,
        workspace_id=seeded.workspace_id,
        project_id=seeded.project_id,
        checkout_binding_id=binding_b,
        target=TargetId.CLAUDE_CODE,
        state=ProjectionState.REMOVED,
    )
    other_target_proj = _new_projection(
        side,
        workspace_id=seeded.workspace_id,
        project_id=seeded.project_id,
        checkout_binding_id=seeded.checkout_binding_id,
        target=TargetId.CODEX,
        state=ProjectionState.IN_SYNC,
    )
    now = side.clock.now()
    with side.uow() as uow:
        repo = uow.repo(ProjectionRepository)
        repo.add(active_proj)
        repo.add(removed_proj)
        repo.add(other_target_proj)
        repo.replace_files(
            active_proj.id,
            (
                AppliedFileRecord(
                    projection_id=active_proj.id,
                    relative_path=".claude/skills/skm-a/SKILL.md",
                    surface=Surface.SKILLS,
                    boundary=ManagedBoundary(ownership=Ownership.MANAGED_FILE),
                    applied_managed_digest=DIGEST_A,
                    applied_whole_digest=DIGEST_A,
                    pre_image_file_version_id=None,
                    renderer="claude_code.skills@1",
                    applied_at=now,
                ),
                AppliedFileRecord(
                    projection_id=active_proj.id,
                    relative_path="CLAUDE.md",
                    surface=Surface.INSTRUCTIONS,
                    boundary=ManagedBoundary(ownership=Ownership.MANAGED_BLOCK, block_ids=("core",)),
                    applied_managed_digest=DIGEST_A,
                    applied_whole_digest=DIGEST_A,
                    pre_image_file_version_id=None,
                    renderer="claude_code.instructions@1",
                    applied_at=now,
                ),
            ),
        )
        repo.replace_files(
            removed_proj.id,
            (
                AppliedFileRecord(
                    projection_id=removed_proj.id,
                    relative_path=".claude/skills/skm-removed/SKILL.md",
                    surface=Surface.SKILLS,
                    boundary=ManagedBoundary(ownership=Ownership.MANAGED_FILE),
                    applied_managed_digest=DIGEST_A,
                    applied_whole_digest=DIGEST_A,
                    pre_image_file_version_id=None,
                    renderer="claude_code.skills@1",
                    applied_at=now,
                ),
            ),
        )
        repo.replace_files(
            other_target_proj.id,
            (
                AppliedFileRecord(
                    projection_id=other_target_proj.id,
                    relative_path=".agents/skills/skm-codex/SKILL.md",
                    surface=Surface.SKILLS,
                    boundary=ManagedBoundary(ownership=Ownership.MANAGED_FILE),
                    applied_managed_digest=DIGEST_A,
                    applied_whole_digest=DIGEST_A,
                    pre_image_file_version_id=None,
                    renderer="codex.skills@1",
                    applied_at=now,
                ),
            ),
        )
        uow.commit()

    with side.uow(readonly=True) as uow:
        paths = uow.repo(ProjectionRepository).managed_file_paths(seeded.project_id, TargetId.CLAUDE_CODE)
        assert paths == frozenset({".claude/skills/skm-a/SKILL.md"})


def test_projection_mark_pending_across_scopes(side: Side) -> None:
    s1 = side.seed_checkout("mp1")
    s2 = side.seed_checkout("mp2")
    p_in_sync = _new_projection(
        side,
        workspace_id=s1.workspace_id,
        project_id=s1.project_id,
        checkout_binding_id=s1.checkout_binding_id,
        target=TargetId.CLAUDE_CODE,
        state=ProjectionState.IN_SYNC,
    )
    p_removed = _new_projection(
        side,
        workspace_id=s1.workspace_id,
        project_id=s1.project_id,
        checkout_binding_id=s1.checkout_binding_id,
        target=TargetId.CODEX,
        state=ProjectionState.REMOVED,
    )
    p_drifted_ws2 = _new_projection(
        side,
        workspace_id=s2.workspace_id,
        project_id=s2.project_id,
        checkout_binding_id=s2.checkout_binding_id,
        target=TargetId.CLAUDE_CODE,
        state=ProjectionState.DRIFTED,
    )
    p_failed_ws2 = _new_projection(
        side,
        workspace_id=s2.workspace_id,
        project_id=s2.project_id,
        checkout_binding_id=s2.checkout_binding_id,
        target=TargetId.CURSOR,
        state=ProjectionState.FAILED,
        applied_desired_digest=None,
    )
    with side.uow() as uow:
        repo = uow.repo(ProjectionRepository)
        for item in (p_in_sync, p_removed, p_drifted_ws2, p_failed_ws2):
            repo.add(item)
        uow.commit()

    with side.uow() as uow:
        repo = uow.repo(ProjectionRepository)
        changed = repo.mark_pending(ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(str(s1.project_id)))))
        assert changed == 1
        assert repo.mark_pending(ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(str(s1.project_id))))) == 0
        uow.commit()

    with side.uow(readonly=True) as uow:
        repo = uow.repo(ProjectionRepository)
        assert repo.get(p_in_sync.id).state is ProjectionState.PENDING
        assert repo.get(p_in_sync.id).row_version == 2
        assert repo.get(p_removed.id).state is ProjectionState.REMOVED
        assert repo.get(p_drifted_ws2.id).state is ProjectionState.DRIFTED

    with side.uow() as uow:
        repo = uow.repo(ProjectionRepository)
        changed_inst = repo.mark_pending(ScopeRef(ScopeKind.INSTANCE, INSTANCE))
        assert changed_inst == 2
        uow.commit()

    with side.uow(readonly=True) as uow:
        repo = uow.repo(ProjectionRepository)
        assert repo.get(p_drifted_ws2.id).state is ProjectionState.PENDING
        assert repo.get(p_failed_ws2.id).state is ProjectionState.PENDING


def test_list_for_project_keyset_pagination(side: Side) -> None:
    seeded = side.seed_checkout("page")
    targets = (TargetId.CLAUDE_CODE, TargetId.CODEX, TargetId.CURSOR)
    created_ids: list[ProjectionId] = []
    for tgt in targets:
        side.tick(2.0)
        p = _new_projection(
            side,
            workspace_id=seeded.workspace_id,
            project_id=seeded.project_id,
            checkout_binding_id=seeded.checkout_binding_id,
            target=tgt,
        )
        with side.uow() as uow:
            uow.repo(ProjectionRepository).add(p)
            uow.commit()
        created_ids.append(p.id)

    with side.uow(readonly=True) as uow:
        repo = uow.repo(ProjectionRepository)
        p1 = repo.list_for_project(seeded.project_id, after=None, limit=2)
        assert [item.id for item in p1.items] == [created_ids[2], created_ids[1]]
        assert p1.next is not None

        p2 = repo.list_for_project(seeded.project_id, after=p1.next, limit=2)
        assert [item.id for item in p2.items] == [created_ids[0]]
        assert p2.next is None

        tampered = Cursor(
            base64.urlsafe_b64encode(json.dumps({"v": 1, "q": "deadbeef", "k": []}).encode()).decode()
        )
        with pytest.raises(ValidationFailed) as exc_info:
            repo.list_for_project(seeded.project_id, after=tampered, limit=2)
        assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
