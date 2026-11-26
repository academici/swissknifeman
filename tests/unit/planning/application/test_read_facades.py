"""Unit tests for the planning public read/validation facades (planning §13)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from fakes.ids import SequentialIds
from integration.artifacts.test_upload_flow import (
    OWNER_ID,
    Harness,
    add_file_dto,
    dispatch_new,
    open_test_app,
    seed_principals,
)
from integration.planning.publication import StaticPlanningConfig, req_meta, strict_planning_settings
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import EntityId, FileVersionId, PlanId, ProjectId, RevisionId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.kernel.scopes import ScopeRegistry
from skm.modules.access.public import Role
from skm.modules.artifacts import public as artifacts
from skm.modules.planning import public as planning
from skm.modules.planning.domain.compile_graph import TaskKind
from skm.modules.planning.domain.material import MaterialStage
from skm.modules.planning.domain.material_status import MaterialObservation, MaterialState
from skm.modules.planning.domain.plan import PlanLifecycle, PlanPurpose
from skm.modules.planning.domain.review_request import CommitReviewTarget, ReviewRequestSpec
from skm.modules.planning.domain.specification import SPECIFICATION_URN, EntityKind, from_document
from skm.modules.planning.domain.validation.context import FileVersionObservation, FileVersionStatus
from skm.modules.planning.generated.commands import (
    ArchivePlan,
    CreatePlan,
    OpenDraft,
    PublishRevision,
    SaveDraft,
)
from skm.modules.planning.generated.queries import PreviewPublication
from skm.modules.workspace.public import (
    AttachRepository,
    CreateProject,
    CreateWorkspace,
    RegisterRepository,
)
from support.seed import SEED

PHASE_UUID, ITEM_UUID, UNIT_UUID, REQ_UUID, CRIT_UUID = (
    UUID(f"01900000-0000-7000-8000-00000000010{i}") for i in range(1, 6)
)
CHECK_UUID, DEC_UUID, MAT_FV_UUID, MAT_REPO_UUID = (
    UUID(f"01900000-0000-7000-8000-00000000010{i}") for i in range(6, 10)
)
MISSING_UUID = UUID("01900000-0000-7000-8000-000000009999")


def _ask(h: Harness, query: object) -> Any:
    return h.client.ask(query)


@pytest.fixture
def mem_h(tmp_path: Path) -> Iterator[Harness]:
    app, clock, blobs_root = open_test_app("memory", tmp_path)
    try:
        actor = seed_principals(
            app,
            "memory",
            people=((OWNER_ID, PrincipalKind.HUMAN, "owner"),),
            roles=((SEED.instance_id, OWNER_ID, Role.OWNER),),
        )
        client = app.client(actor=actor, surface=Surface.CLI)
        ws = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        repo_res = dispatch_new(
            client,
            RegisterRepository(
                workspace_id=ws,
                title="skm-repo",
                remote_url="https://example.com/skm.git",
                external_id=None,
            ),
        )
        dispatch_new(
            client,
            AttachRepository(
                project_id=proj, repository_id=repo_res.repository_id, mount_name="skm", role="primary"
            ),
        )
        yield Harness(app, clock, actor, client, ws, proj, blobs_root, None)
    finally:
        app.close()


def _upload_ready_file(h: Harness, content: bytes = b"reference guide\n") -> tuple[UUID, FileVersionId]:
    staged = h.client.upload_blob(h.ws, [content], size=len(content), media_type="text/plain")
    dto = replace(add_file_dto(h.ws, h.proj, staged), title="guide.md", original_filename="guide.md")
    res = dispatch_new(h.client, dto)
    return UUID(str(res.file_id)), FileVersionId(UUID(str(res.file_version_id)))


def _rich_spec_doc(fv_id: FileVersionId) -> JsonObject:
    return {
        "schema": SPECIFICATION_URN,
        "title": "Auth Refresh Plan",
        "goal": "Implement deterministic token refresh across services.",
        "requirements": [
            {
                "id": str(REQ_UUID),
                "key": "R1",
                "statement": "Refresh tokens rotate atomically.",
                "priority": "must",
                "source": {"kind": "owner"},
                "owners": ["P1.1"],
            }
        ],
        "phases": [
            {
                "id": str(PHASE_UUID),
                "key": "P1",
                "title": "Core Refresh",
                "goal": "Deliver core rotation handler and tests.",
                "design_state": "detailed",
                "depends_on": [],
            }
        ],
        "items": [
            {
                "id": str(ITEM_UUID),
                "key": "P1.1",
                "phase": "P1",
                "title": "Rotation Handler",
                "summary": "Implement rotation command and unit tests.",
                "why": "Prevent token replay.",
                "work_kind": "code",
                "scope": {"include": ["src/auth/refresh.py"], "exclude": []},
                "implements": ["R1"],
                "decisions": ["D1"],
                "deliverables": ["Rotation handler and unit tests"],
                "guidance_md": "Follow transactional repository pattern.",
                "review": {"mode": "self", "reason": "Covered by deterministic check."},
            }
        ],
        "units": [
            {
                "id": str(UNIT_UUID),
                "key": "P1.1/U1",
                "title": "Write handler and tests",
                "goal": "Implement refresh rotation and test suite.",
                "work_kind": "code",
                "write_scope": [
                    {"mount": "skm", "pattern": "src/auth/refresh.py"},
                    {"mount": "skm", "pattern": "tests/test_refresh.py"},
                ],
                "checks": ["V1"],
                "implements": ["R1"],
            }
        ],
        "criteria": [
            {
                "id": str(CRIT_UUID),
                "key": "AC1",
                "owner": "P1.1",
                "statement": "Unit tests verify atomic refresh rotation.",
                "verification_mode": "check",
                "checks": ["V1"],
                "requirements": ["R1"],
            }
        ],
        "checks": [
            {
                "id": str(CHECK_UUID),
                "key": "V1",
                "owner": "P1.1",
                "title": "Refresh unit tests",
                "category": "acceptance",
                "kind": "command",
                "definition": {
                    "argv": ["pytest", "-q", "tests/test_refresh.py"],
                    "cwd": {"mount": "skm", "path": "."},
                },
            }
        ],
        "decisions": [
            {
                "id": str(DEC_UUID),
                "key": "D1",
                "title": "Single-use refresh tokens",
                "state": "accepted",
                "question": "Reuse or rotate refresh tokens?",
                "decision": "Rotate on every refresh.",
                "rationale": "Bounds replay window.",
                "applies_to": ["P1.1"],
            }
        ],
        "materials": [
            {
                "id": str(MAT_FV_UUID),
                "key": "api-guide",
                "title": "API Guide",
                "kind": "file_version",
                "file_version_id": str(fv_id),
                "role": "input",
                "required_for": ["execution"],
                "freshness": {"policy": "must_refresh", "max_age_seconds": 3600},
                "selector": {"kind": "line_range", "from": 1, "to": 10},
                "applies_to": ["P1.1"],
            },
            {
                "id": str(MAT_REPO_UUID),
                "key": "arch-doc",
                "title": "Architecture Doc",
                "kind": "repository_path",
                "mount": "skm",
                "path": "docs/arch.md",
                "role": "reference",
                "required_for": ["review"],
                "applies_to": ["P1"],
            },
        ],
    }


def _publish_rich_plan(h: Harness) -> tuple[PlanId, RevisionId, UUID, FileVersionId]:
    file_id, fv_id = _upload_ready_file(h)
    created = dispatch_new(h.client, CreatePlan(project_id=h.proj, title="Auth Refresh Plan"))
    opened = dispatch_new(h.client, OpenDraft(plan_id=created.plan_id, base="empty"))
    saved = dispatch_new(
        h.client,
        SaveDraft(
            plan_id=created.plan_id,
            draft_id=opened.draft_id,
            expected_edit_version=opened.edit_version,
            document=cast("Any", _rich_spec_doc(fv_id)),
        ),
    )
    preview = _ask(
        h,
        PreviewPublication(
            plan_id=created.plan_id, draft_id=opened.draft_id, expected_edit_version=saved.edit_version
        ),
    )
    assert preview.publishable
    published = dispatch_new(
        h.client,
        PublishRevision(
            plan_id=created.plan_id,
            draft_id=opened.draft_id,
            expected_edit_version=saved.edit_version,
            expected_content_digest=preview.content_digest,
            reason="Initial publication",
        ),
    )
    return PlanId(created.plan_id), RevisionId(published.revision_id), file_id, fv_id


def test_read_facades_retrieve_specification_and_meta(mem_h: Harness) -> None:
    plan_id, rev_id, _file_id, _fv_id = _publish_rich_plan(mem_h)

    with mem_h.app.uow_factory(req_meta(mem_h, 1), readonly=True) as uow:
        spec = planning.get_revision_specification(uow, rev_id)
        assert (spec.title, spec.entity(EntityId(ITEM_UUID)).key) == ("Auth Refresh Plan", "P1.1")
        assert (len(spec.units_of("P1.1")), len(spec.materials)) == (1, 2)

        meta = planning.get_revision_meta(uow, rev_id)
        assert (meta.revision_id, meta.plan_id, meta.project_id, meta.workspace_id, meta.revision_no) == (
            rev_id,
            plan_id,
            mem_h.proj,
            mem_h.ws,
            1,
        )
        assert meta.digest.startswith("sha256:")
        assert (meta.plan_purpose, meta.plan_lifecycle) == (PlanPurpose.STANDARD, PlanLifecycle.ACTIVE)

        graph = planning.compile_execution_graph(spec, rev_id)
        assert graph.revision_id == rev_id
        assert tuple((t.task_key, t.task_kind) for t in graph.tasks) == (
            ("P1.1/U1", TaskKind.UNIT),
            ("P1.1#gate", TaskKind.ITEM_GATE),
            ("P1#gate", TaskKind.PHASE_GATE),
        )

        for fn in (planning.get_revision_specification, planning.get_revision_meta):
            with pytest.raises(NotFound) as missing_exc:
                fn(uow, RevisionId(MISSING_UUID))
            assert missing_exc.value.details.get("kind") == "revision"

    def _cyc_item(uid: UUID, key: str, dep: str) -> JsonObject:
        return {
            "id": str(uid),
            "key": key,
            "phase": "P1",
            "title": key,
            "summary": "S",
            "why": "W",
            "depends_on": [dep],
            "review": {"mode": "self", "reason": "ok"},
        }

    cyclic_doc: JsonObject = {
        "schema": SPECIFICATION_URN,
        "title": "Cycle",
        "goal": "Cycle check",
        "phases": [
            {"id": str(PHASE_UUID), "key": "P1", "title": "P1", "goal": "G", "design_state": "detailed"}
        ],
        "items": [_cyc_item(ITEM_UUID, "P1.1", "P1.2"), _cyc_item(UNIT_UUID, "P1.2", "P1.1")],
    }
    cyclic_spec, _ = from_document(cyclic_doc)
    with pytest.raises(ValidationFailed) as cyc_err:
        planning.compile_execution_graph(cyclic_spec)
    assert cyc_err.value.code is ErrorCode.DEPENDENCY_CYCLE


def test_resolve_entity_by_display_key_and_uuid(mem_h: Harness) -> None:
    _plan_id, rev_id, _file_id, _fv_id = _publish_rich_plan(mem_h)

    expected_entities: tuple[tuple[str, UUID, EntityKind], ...] = (
        ("P1", PHASE_UUID, EntityKind.PHASE),
        ("P1.1", ITEM_UUID, EntityKind.ITEM),
        ("P1.1/U1", UNIT_UUID, EntityKind.UNIT),
        ("R1", REQ_UUID, EntityKind.REQUIREMENT),
        ("AC1", CRIT_UUID, EntityKind.CRITERION),
        ("P1.1:V1", CHECK_UUID, EntityKind.CHECK),
        ("D1", DEC_UUID, EntityKind.DECISION),
        ("material/api-guide", MAT_FV_UUID, EntityKind.MATERIAL),
    )

    with mem_h.app.uow_factory(req_meta(mem_h, 10), readonly=True) as uow:
        for display_key, expected_uuid, expected_kind in expected_entities:
            by_key = planning.resolve_entity(uow, rev_id, display_key)
            assert by_key == planning.EntityRef(
                entity_id=EntityId(expected_uuid),
                entity_kind=expected_kind,
                display_key=display_key,
            )
            assert planning.resolve_entity(uow, rev_id, f"entity:{expected_uuid}") == by_key

        for bad_ref in ("", "   ", "entity:not-a-uuid", "PLAN1", "P1.1/"):
            with pytest.raises(ValidationFailed) as exc_bad:
                planning.resolve_entity(uow, rev_id, bad_ref)
            assert exc_bad.value.code is ErrorCode.INVALID_REFERENCE

        for missing_ref in ("P99", "material/unknown", f"entity:{MISSING_UUID}"):
            with pytest.raises(NotFound) as exc_nf:
                planning.resolve_entity(uow, rev_id, missing_ref)
            assert exc_nf.value.details.get("kind") == "entity"

        with pytest.raises(NotFound) as exc_rev_nf:
            planning.resolve_entity(uow, RevisionId(MISSING_UUID), "P1")
        assert exc_rev_nf.value.details.get("kind") == "revision"


def test_revision_materials_and_assess_material(mem_h: Harness) -> None:
    _plan_id, rev_id, _file_id, fv_id = _publish_rich_plan(mem_h)
    now = mem_h.clock.now()

    with mem_h.app.uow_factory(req_meta(mem_h, 20), readonly=True) as uow:
        mats = planning.revision_materials(uow, rev_id)
        assert [m["key"] for m in mats] == ["api-guide", "arch-doc"]
        fv_mat, repo_mat = mats
        assert (fv_mat["file_version_id"], fv_mat["applies_to"], fv_mat["applies_to_entity_ids"]) == (
            str(fv_id),
            ["P1.1"],
            [str(ITEM_UUID)],
        )

    ready_recent = MaterialObservation(
        FileVersionObservation(FileVersionStatus.READY, now - timedelta(seconds=120)), None
    )
    ready_stale = MaterialObservation(
        FileVersionObservation(FileVersionStatus.READY, now - timedelta(seconds=7200)), None
    )
    assert planning.assess_material(fv_mat, ready_recent, now=now).state == MaterialState.AVAILABLE
    stale_fv = planning.assess_material(fv_mat, ready_stale, now=now)
    assert (stale_fv.state, stale_fv.blocks) == (MaterialState.STALE, frozenset({MaterialStage.EXECUTION}))

    assert planning.assess_material(repo_mat, MaterialObservation(None, None), now=now).state == (
        MaterialState.UNKNOWN
    )
    missing_repo = planning.assess_material(repo_mat, MaterialObservation(None, False), now=now)
    assert (missing_repo.state, missing_repo.blocks) == (
        MaterialState.MISSING,
        frozenset({MaterialStage.REVIEW}),
    )


def test_require_active_plan_enforces_active_state(mem_h: Harness) -> None:
    plan_id, rev_id, _file_id, _fv_id = _publish_rich_plan(mem_h)

    with mem_h.app.uow_factory(req_meta(mem_h, 30), readonly=False) as uow:
        active_ref = planning.require_active_plan(uow, plan_id)
        expected_ref = planning.PlanRef(
            plan_id,
            mem_h.ws,
            mem_h.proj,
            "PLAN1",
            "Auth Refresh Plan",
            PlanPurpose.STANDARD,
            PlanLifecycle.ACTIVE,
            rev_id,
        )
        assert active_ref == expected_ref
        assert planning.get_plan_ref(uow, plan_id) == expected_ref

    dispatch_new(mem_h.client, ArchivePlan(plan_id=UUID(str(plan_id))))

    with mem_h.app.uow_factory(req_meta(mem_h, 31), readonly=False) as uow:
        with pytest.raises(PreconditionFailed) as exc_arch:
            planning.require_active_plan(uow, plan_id)
        assert exc_arch.value.code is ErrorCode.PLAN_ARCHIVED

        archived_ref = planning.get_plan_ref(uow, plan_id)
        assert (archived_ref.lifecycle, archived_ref.current_revision_id) == (PlanLifecycle.ARCHIVED, rev_id)
        assert planning.get_revision_meta(uow, rev_id).plan_lifecycle is PlanLifecycle.ARCHIVED

        for fn in (planning.require_active_plan, planning.get_plan_ref):
            with pytest.raises(NotFound):
                fn(uow, PlanId(MISSING_UUID))


def test_get_plan_summary_and_validate_revision(mem_h: Harness) -> None:
    empty_created = dispatch_new(mem_h.client, CreatePlan(project_id=mem_h.proj, title="Empty Plan"))
    with mem_h.app.uow_factory(req_meta(mem_h, 40), readonly=True) as uow:
        es = planning.get_plan_summary(uow, PlanId(empty_created.plan_id))
        assert (es.plan_id, es.alias, es.lifecycle_state, es.current_revision_id, es.archived_at) == (
            empty_created.plan_id,
            "PLAN1",
            "active",
            None,
            None,
        )
        assert (es.workspace_id, es.project_id) == (UUID(str(mem_h.ws)), UUID(str(mem_h.proj)))

    plan_id, rev_id, file_id, _fv_id = _publish_rich_plan(mem_h)
    dispatch_new(mem_h.client, OpenDraft(plan_id=UUID(str(plan_id)), base="current"))

    with mem_h.app.uow_factory(req_meta(mem_h, 41), readonly=False) as uow:
        svc_req = ReviewRequestSpec(
            UUID("01900000-0000-7000-8000-000000000999"),
            "skm",
            CommitReviewTarget("commits", "aaa", "bbb"),
            "code-review",
            "Check service plan summary.",
        )
        svc_meta = planning.publish_review_request_revision(
            uow, mem_h.owner, mem_h.proj, svc_req, ids=SequentialIds(), now=mem_h.clock.now()
        )
        uow.commit()

    with mem_h.app.uow_factory(req_meta(mem_h, 42), readonly=True) as uow:
        ps = planning.get_plan_summary(uow, plan_id)
        assert (ps.plan_id, ps.alias, ps.current_revision_id, ps.current_revision_no, ps.open_drafts) == (
            UUID(str(plan_id)),
            "PLAN2",
            UUID(str(rev_id)),
            1,
            1,
        )
        assert [(a.alias, a.kind) for a in ps.aliases] == [("PLAN2", "short")]

        ss = planning.get_plan_summary(uow, svc_meta.plan_id)
        assert (ss.purpose, ss.alias) == ("review_requests", "review-requests")
        assert [(a.alias, a.kind) for a in ss.aliases] == [("review-requests", "system")]

        with pytest.raises(NotFound) as nf_err:
            planning.get_plan_summary(uow, PlanId(MISSING_UUID))
        assert nf_err.value.details.get("kind") == "plan"

        cfg = cast("Any", StaticPlanningConfig(strict_planning_settings()))
        scope_chain = uow.repo(ScopeRegistry).ancestors(ScopeId(plan_id))
        valid_report = planning.validate_revision(
            uow, rev_id, scope_chain=scope_chain, config=cfg, now=mem_h.clock.now()
        )
        assert not valid_report.has_errors(plugin_failures_block=False)

    file_view = _ask(mem_h, artifacts.GetFile(file_id=file_id))
    dispatch_new(
        mem_h.client,
        artifacts.TrashFile(file_id, file_view.row_version, "Trash test file"),
    )
    dispatch_new(mem_h.client, ArchivePlan(plan_id=UUID(str(plan_id))))

    with mem_h.app.uow_factory(req_meta(mem_h, 43), readonly=True) as uow:
        arch = planning.get_plan_summary(uow, plan_id)
        assert (arch.lifecycle_state, arch.open_drafts, arch.current_revision_id) == (
            "archived",
            0,
            UUID(str(rev_id)),
        )
        assert arch.archived_at is not None

        scope_chain = uow.repo(ScopeRegistry).ancestors(ScopeId(plan_id))
        trashed_report = planning.validate_revision(
            uow, rev_id, scope_chain=scope_chain, config=cfg, now=mem_h.clock.now()
        )
        assert any(f.code == "material_unavailable" for f in trashed_report.findings)
