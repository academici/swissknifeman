"""Unit tests for the service review-requests plan and facade publication (planning §7.11)."""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from fakes.ids import SequentialIds
from integration.artifacts.test_upload_flow import (
    OWNER_ID,
    Harness,
    dispatch_new,
    open_test_app,
    seed_principals,
)
from integration.planning.publication import StaticPlanningConfig, req_meta, strict_planning_settings
from skm.application_bus.ports import EventReader
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import FileVersionId, PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.public import Role, grant_initial_membership
from skm.modules.planning import module as planning_module
from skm.modules.planning import public as planning
from skm.modules.planning.application import revision_writer
from skm.modules.planning.domain.canonical import specification_digest
from skm.modules.planning.domain.events import PlanCreated, PlanRevisionPublished
from skm.modules.planning.domain.item import WorkKind
from skm.modules.planning.domain.plan import PlanLifecycle, PlanPurpose
from skm.modules.planning.domain.review_request import (
    REVIEW_REQUEST_EXTENSION_NS,
    REVIEW_REQUESTS_ALIAS,
    REVIEW_REQUESTS_GOAL,
    REVIEW_REQUESTS_TITLE,
    CommitReviewTarget,
    ReviewRequestSpec,
    WorkingTreeReviewTarget,
)
from skm.modules.planning.domain.revision import RevisionOrigin
from skm.modules.planning.domain.specification import SPECIFICATION_URN
from skm.modules.planning.domain.validation.findings import Finding, Severity, ValidationReport
from skm.modules.planning.generated.commands import (
    ArchivePlan,
    CreatePlan,
    ImportSpecification,
    OpenDraft,
    RestoreRevision,
)
from skm.modules.planning.generated.queries import GetPlan, GetRevision, ListPlans, ResolvePlanRef
from skm.modules.planning.ports import AliasKind, PlanRepository, RevisionRepository
from skm.modules.workspace.public import ArchiveProject, CreateProject, CreateWorkspace
from support.seed import SEED

WORKER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d3"))
REQ_ID_1 = UUID("01900000-0000-7000-8000-000000000901")
REQ_ID_2 = UUID("01900000-0000-7000-8000-000000000902")
PATCH_FV_ID = FileVersionId(UUID("01900000-0000-7000-8000-000000000950"))


def _ask(h: Harness, query: object) -> Any:
    return h.client.ask(query)


@pytest.fixture
def mem_h(tmp_path: Path) -> Iterator[Harness]:
    app, clock, blobs_root = open_test_app("memory", tmp_path)
    try:
        actor = seed_principals(
            app,
            "memory",
            people=(
                (OWNER_ID, PrincipalKind.HUMAN, "owner"),
                (WORKER_ID, PrincipalKind.WORKER, "worker"),
            ),
            roles=((SEED.instance_id, OWNER_ID, Role.OWNER),),
        )
        client = app.client(actor=actor, surface=Surface.CLI)
        ws = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        with app.uow_factory(
            RequestMeta("req_" + "0" * 26, Surface.CLI, None, clock.now()), readonly=False
        ) as uow:
            grant_initial_membership(
                uow,
                scope_id=ScopeId(ws),
                principal_id=WORKER_ID,
                role=Role.WORKER,
                now=clock.now(),
            )
            uow.commit()
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        yield Harness(app, clock, actor, client, ws, proj, blobs_root, None)
    finally:
        app.close()


def test_publish_review_request_creates_service_plan(mem_h: Harness) -> None:
    ids = SequentialIds()
    now = mem_h.clock.now()
    req_spec = ReviewRequestSpec(
        request_id=REQ_ID_1,
        mount="skm",
        target=CommitReviewTarget(kind="commits", base_commit="abc1234", head_commit="def5678"),
        profile="code-review",
        reason="Verify security boundary changes before merge.",
    )

    with mem_h.app.uow_factory(req_meta(mem_h, 1), readonly=False) as uow:
        rev_meta = planning.publish_review_request_revision(
            uow,
            mem_h.owner,
            mem_h.proj,
            req_spec,
            ids=ids,
            now=now,
        )
        uow.commit()

    assert rev_meta.project_id == mem_h.proj
    assert rev_meta.workspace_id == mem_h.ws
    assert rev_meta.revision_no == 1
    assert rev_meta.published_at == now
    assert rev_meta.plan_purpose is PlanPurpose.REVIEW_REQUESTS
    assert rev_meta.plan_lifecycle is PlanLifecycle.ACTIVE

    # Human plan allocation still starts at PLAN1 because the service plan never consumes PlanCounters.
    human_plan = dispatch_new(mem_h.client, CreatePlan(project_id=mem_h.proj, title="Feature Plan"))
    assert human_plan.alias == "PLAN1"

    with mem_h.app.uow_factory(req_meta(mem_h, 2), readonly=True) as uow:
        plan_repo = uow.repo(PlanRepository)
        service_plan = plan_repo.get(rev_meta.plan_id)
        assert (service_plan.alias, service_plan.title, service_plan.purpose) == (
            REVIEW_REQUESTS_ALIAS,
            REVIEW_REQUESTS_TITLE,
            PlanPurpose.REVIEW_REQUESTS,
        )
        assert (service_plan.current_revision_id, service_plan.next_revision_no) == (
            rev_meta.revision_id,
            2,
        )
        assert plan_repo.list_aliases(service_plan.id) == ((REVIEW_REQUESTS_ALIAS, AliasKind.SYSTEM),)

        ancestors = uow.repo(ScopeRegistry).ancestors(ScopeId(service_plan.id))
        assert (ancestors[-1].kind, ancestors[-1].id, ancestors[-2].id) == (
            ScopeKind.PLAN,
            ScopeId(service_plan.id),
            ScopeId(mem_h.proj),
        )

        raw_doc = uow.repo(RevisionRepository).get_document(rev_meta.revision_id)
        assert rev_meta.digest == specification_digest(raw_doc)
        assert raw_doc["extensions"] == {
            REVIEW_REQUEST_EXTENSION_NS: {"schema_version": 1, "value": {"request_id": str(REQ_ID_1)}}
        }

        spec = planning.get_revision_specification(uow, rev_meta.revision_id)
        assert (spec.title, spec.goal) == (REVIEW_REQUESTS_TITLE, REVIEW_REQUESTS_GOAL)
        assert (len(spec.phases), spec.phases[0].key, spec.phases[0].depends_on) == (1, "P1", ())
        item = spec.items[0]
        assert (item.key, item.title, item.work_kind) == (
            "P1.1",
            "Review abc1234..def5678 of skm",
            WorkKind.REVIEW,
        )
        assert (item.summary, item.guidance_md, item.deliverables) == (
            req_spec.reason,
            req_spec.reason,
            ("Review report",),
        )
        assert item.scope is not None
        assert item.scope.include == ("skm:abc1234..def5678",)
        assert (len(spec.criteria), spec.criteria[0].key, spec.criteria[0].owner) == (1, "AC1", "P1.1")

        report = planning.validate_revision(
            uow,
            rev_meta.revision_id,
            scope_chain=ancestors,
            config=cast("Any", StaticPlanningConfig(strict_planning_settings())),
            now=now,
        )
        assert not report.has_errors(plugin_failures_block=False)
        assert report.graph is not None
        assert tuple(t.task_key for t in report.graph.tasks) == ("P1.1", "P1#gate")

        ws_events = uow.repo(EventReader).after_workspace_seq(
            mem_h.ws,
            0,
            types=frozenset({PlanCreated.event_type, PlanRevisionPublished.event_type}),
            limit=50,
        )
        events = [ev for ev in ws_events if ev.stream_id == UUID(str(service_plan.id))]
        assert [ev.type for ev in events] == [PlanCreated.event_type, PlanRevisionPublished.event_type]
        pub_payload = events[1].payload
        assert (pub_payload["origin"], pub_payload["draft_id"], pub_payload["revision_no"]) == (
            RevisionOrigin.SYSTEM.value,
            None,
            1,
        )


def test_publish_review_request_reuses_service_plan_and_supports_working_tree(mem_h: Harness) -> None:
    ids = SequentialIds()
    now = mem_h.clock.now()
    first_spec = ReviewRequestSpec(
        request_id=REQ_ID_1,
        mount="skm",
        target=CommitReviewTarget(kind="commits", base_commit="1111111", head_commit="2222222"),
        profile="security/audit",
        reason="Audit commit range.",
    )
    second_spec = ReviewRequestSpec(
        request_id=REQ_ID_2,
        mount="skm",
        target=WorkingTreeReviewTarget(
            kind="working_tree",
            base_commit="1111111",
            patch_file_version_id=PATCH_FV_ID,
        ),
        profile="code-review",
        reason="Inspect local uncommitted changes.",
    )

    with mem_h.app.uow_factory(req_meta(mem_h, 10), readonly=False) as uow:
        meta_1 = planning.publish_review_request_revision(
            uow, mem_h.owner, mem_h.proj, first_spec, ids=ids, now=now
        )
        meta_2 = planning.publish_review_request_revision(
            uow, mem_h.owner, mem_h.proj, second_spec, ids=ids, now=now
        )
        uow.commit()

    assert meta_2.plan_id == meta_1.plan_id
    assert meta_1.revision_no == 1
    assert meta_2.revision_no == 2
    assert meta_2.digest != meta_1.digest

    with mem_h.app.uow_factory(req_meta(mem_h, 11), readonly=True) as uow:
        rev_repo = uow.repo(RevisionRepository)
        persisted_2 = rev_repo.get_meta(meta_2.revision_id)
        assert persisted_2.parent_revision_id == meta_1.revision_id
        assert persisted_2.change_reason == f"review request {REQ_ID_2}"

        spec_1 = planning.get_revision_specification(uow, meta_1.revision_id)
        spec_2 = planning.get_revision_specification(uow, meta_2.revision_id)
        # Phase P1 keeps its stable entity ID across revisions; item and criterion get fresh IDs per request.
        assert spec_2.phases[0].id == spec_1.phases[0].id
        assert spec_2.items[0].id != spec_1.items[0].id
        assert spec_2.criteria[0].id != spec_1.criteria[0].id
        assert spec_2.items[0].title == "Review 1111111..working tree of skm"
        assert spec_2.items[0].scope is not None
        assert spec_2.items[0].scope.include == ("skm:1111111..working tree",)

        ws_events = uow.repo(EventReader).after_workspace_seq(
            mem_h.ws,
            0,
            types=frozenset({PlanCreated.event_type, PlanRevisionPublished.event_type}),
            limit=50,
        )
        events = [ev for ev in ws_events if ev.stream_id == UUID(str(meta_1.plan_id))]
        assert [ev.type for ev in events] == [
            PlanCreated.event_type,
            PlanRevisionPublished.event_type,
            PlanRevisionPublished.event_type,
        ]

    # A second project in the same workspace receives its own isolated review-requests service plan.
    proj_2 = ProjectId(
        dispatch_new(mem_h.client, CreateProject(workspace_id=mem_h.ws, slug="docs", title="Docs")).project_id
    )
    with mem_h.app.uow_factory(req_meta(mem_h, 12), readonly=False) as uow:
        meta_other = planning.publish_review_request_revision(
            uow, mem_h.owner, proj_2, first_spec, ids=ids, now=now
        )
        uow.commit()
    assert meta_other.plan_id != meta_1.plan_id
    assert meta_other.project_id == proj_2
    assert meta_other.revision_no == 1


def test_service_plan_hidden_from_general_queries(mem_h: Harness) -> None:
    std_plan = dispatch_new(mem_h.client, CreatePlan(project_id=mem_h.proj, title="Standard Plan"))
    with mem_h.app.uow_factory(req_meta(mem_h, 20), readonly=False) as uow:
        svc_meta = planning.publish_review_request_revision(
            uow,
            mem_h.owner,
            mem_h.proj,
            ReviewRequestSpec(
                request_id=REQ_ID_1,
                mount="skm",
                target=CommitReviewTarget(kind="commits", base_commit="aaa", head_commit="bbb"),
                profile="code-review",
                reason="Check visibility filtering.",
            ),
            ids=SequentialIds(),
            now=mem_h.clock.now(),
        )
        uow.commit()

    default_list = _ask(mem_h, ListPlans(project_id=mem_h.proj))
    assert [item.plan_id for item in default_list.items] == [std_plan.plan_id]

    svc_only_list = _ask(mem_h, ListPlans(project_id=mem_h.proj, purpose="review_requests"))
    assert [item.plan_id for item in svc_only_list.items] == [UUID(str(svc_meta.plan_id))]

    all_list = _ask(mem_h, ListPlans(project_id=mem_h.proj, purpose="all"))
    assert {item.plan_id for item in all_list.items} == {std_plan.plan_id, UUID(str(svc_meta.plan_id))}

    resolved = _ask(mem_h, ResolvePlanRef(project_id=mem_h.proj, ref="review-requests"))
    assert resolved.plan_id == UUID(str(svc_meta.plan_id))
    assert resolved.purpose == "review_requests"

    plan_view = _ask(mem_h, GetPlan(plan_id=UUID(str(svc_meta.plan_id))))
    assert plan_view.alias == "review-requests"
    assert plan_view.current_revision_no == 1

    rev_view = _ask(mem_h, GetRevision(plan_id=UUID(str(svc_meta.plan_id)), current=True, include_tree=True))
    assert rev_view.revision_id == UUID(str(svc_meta.revision_id))
    assert rev_view.origin == "system"


def test_service_plan_not_authorable_via_draft(mem_h: Harness) -> None:
    ids = SequentialIds()
    now = mem_h.clock.now()
    with mem_h.app.uow_factory(req_meta(mem_h, 30), readonly=False) as uow:
        meta_1 = planning.publish_review_request_revision(
            uow,
            mem_h.owner,
            mem_h.proj,
            ReviewRequestSpec(
                request_id=REQ_ID_1,
                mount="skm",
                target=CommitReviewTarget(kind="commits", base_commit="aaa", head_commit="bbb"),
                profile="code-review",
                reason="First request.",
            ),
            ids=ids,
            now=now,
        )
        meta_2 = planning.publish_review_request_revision(
            uow,
            mem_h.owner,
            mem_h.proj,
            ReviewRequestSpec(
                request_id=REQ_ID_2,
                mount="skm",
                target=CommitReviewTarget(kind="commits", base_commit="bbb", head_commit="ccc"),
                profile="code-review",
                reason="Second request.",
            ),
            ids=ids,
            now=now,
        )
        uow.commit()

    plan_uuid = UUID(str(meta_1.plan_id))
    portable_doc = {
        "schema": SPECIFICATION_URN,
        "title": "Imported",
        "goal": "Attempt import into system plan.",
        "phases": [{"key": "P1", "title": "Phase 1", "goal": "Goal", "design_state": "skeleton"}],
        "items": [],
    }

    commands: tuple[Any, ...] = (
        OpenDraft(plan_id=plan_uuid, base="current"),
        ArchivePlan(plan_id=plan_uuid),
        RestoreRevision(
            plan_id=plan_uuid,
            revision_no=1,
            expected_current_revision_id=UUID(str(meta_2.revision_id)),
            reason="Attempt restore on system plan",
        ),
        ImportSpecification(
            project_id=UUID(str(mem_h.proj)),
            mode="new_draft",
            plan_id=plan_uuid,
            source_base_revision_id=UUID(str(meta_2.revision_id)),
            keep_ids=False,
            document=cast("Any", portable_doc),
        ),
    )

    for cmd in commands:
        with pytest.raises(PreconditionFailed) as exc_info:
            dispatch_new(mem_h.client, cmd)
        assert exc_info.value.code is ErrorCode.INVALID_TRANSITION
        assert exc_info.value.details.get("reason") == "system_plan"

    after_view = _ask(mem_h, GetPlan(plan_id=plan_uuid))
    assert after_view.lifecycle_state == "active"
    assert after_view.open_drafts == 0
    assert after_view.current_revision_id == UUID(str(meta_2.revision_id))


def test_publish_review_request_rejects_invalid_inputs_and_inactive_project(
    mem_h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = SequentialIds()
    now = mem_h.clock.now()
    bad_specs: tuple[Any, ...] = (
        ReviewRequestSpec(
            request_id=REQ_ID_1,
            mount="../invalid",
            target=CommitReviewTarget(kind="commits", base_commit="aaa", head_commit="bbb"),
            profile="code-review",
            reason="Bad mount.",
        ),
        ReviewRequestSpec(
            request_id=REQ_ID_1,
            mount="skm",
            target=CommitReviewTarget(kind="commits", base_commit="aaa", head_commit="bbb"),
            profile="INVALID_PROFILE",
            reason="Bad profile.",
        ),
        ReviewRequestSpec(
            request_id=REQ_ID_1,
            mount="skm",
            target=CommitReviewTarget(kind="commits", base_commit="aaa", head_commit="bbb"),
            profile="code-review",
            reason="   ",
        ),
        ReviewRequestSpec(
            request_id=REQ_ID_1,
            mount="skm",
            target=CommitReviewTarget(kind="commits", base_commit="bad ref", head_commit="bbb"),
            profile="code-review",
            reason="Whitespace in commit ref.",
        ),
    )

    for bad in bad_specs:
        with (
            mem_h.app.uow_factory(req_meta(mem_h, 40), readonly=False) as uow,
            pytest.raises(ValidationFailed) as exc_val,
        ):
            planning.publish_review_request_revision(uow, mem_h.owner, mem_h.proj, bad, ids=ids, now=now)
        assert exc_val.value.code is ErrorCode.SCHEMA_INVALID

    valid_spec = ReviewRequestSpec(
        request_id=REQ_ID_1,
        mount="skm",
        target=CommitReviewTarget(kind="commits", base_commit="aaa", head_commit="bbb"),
        profile="code-review",
        reason="Valid review request.",
    )
    unknown_project = ProjectId(UUID("01900000-0000-7000-8000-000000009999"))
    with (
        mem_h.app.uow_factory(req_meta(mem_h, 41), readonly=False) as uow,
        pytest.raises(NotFound),
    ):
        planning.publish_review_request_revision(
            uow, mem_h.owner, unknown_project, valid_spec, ids=ids, now=now
        )

    # Fail-closed PLAN_NOT_READY guard if domain validation reports an error finding.
    def _fake_validate(_ctx: Any) -> ValidationReport:
        err_finding = Finding("incomplete", Severity.ERROR, "forced error", "P1.1", None, "/items/0", {})
        return ValidationReport((err_finding,), (), None)

    monkeypatch.setattr(revision_writer, "validate", _fake_validate)
    with (
        mem_h.app.uow_factory(req_meta(mem_h, 42), readonly=False) as uow,
        pytest.raises(PreconditionFailed) as exc_not_ready,
    ):
        planning.publish_review_request_revision(uow, mem_h.owner, mem_h.proj, valid_spec, ids=ids, now=now)
    assert exc_not_ready.value.code is ErrorCode.PLAN_NOT_READY
    monkeypatch.undo()

    # Archiving the project blocks service revision publication with PROJECT_ARCHIVED.
    dispatch_new(
        mem_h.client,
        ArchiveProject(project_id=mem_h.proj, expected_row_version=1, reason="Archive project"),
    )
    with (
        mem_h.app.uow_factory(req_meta(mem_h, 43), readonly=False) as uow,
        pytest.raises(PreconditionFailed) as exc_archived,
    ):
        planning.publish_review_request_revision(uow, mem_h.owner, mem_h.proj, valid_spec, ids=ids, now=now)
    assert exc_archived.value.code is ErrorCode.PROJECT_ARCHIVED


def test_no_execution_imports_in_planning() -> None:
    assert "execution" not in planning_module.MODULE.depends_on
    planning_root = Path(planning_module.__file__).resolve().parent
    src_root = planning_root.parents[2]

    for py_path in sorted(planning_root.rglob("*.py")):
        rel_parts = py_path.relative_to(src_root).with_suffix("").parts
        pkg = ".".join(rel_parts[:-1])
        tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("skm.modules.execution"), f"{py_path}: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if node.level:
                    mod = importlib.util.resolve_name("." * node.level + mod, pkg)
                assert not mod.startswith("skm.modules.execution"), f"{py_path}: {mod}"
                if mod == "skm.modules":
                    for alias in node.names:
                        assert alias.name != "execution", f"{py_path}: from skm.modules import execution"
