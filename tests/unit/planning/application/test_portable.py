"""Unit tests for portable specification export and import (planning §7.7, §8.4)."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from integration.artifacts.test_upload_flow import (
    OWNER_ID,
    Harness,
    add_file_dto,
    dispatch_new,
    open_test_app,
    seed_principals,
)
from integration.planning.publication import req_meta
from skm.application_bus.ports import AuditLog
from skm.kernel.actor import Actor, PrincipalKind, TokenGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import PlanId, PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access.domain.token import ApiToken
from skm.modules.access.ports import TokenRepository
from skm.modules.access.public import Role, TokenId, TokenKind, grant_initial_membership
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.events import DraftOpened, PlanCreated, PlanRevisionPublished
from skm.modules.planning.domain.specification import SPECIFICATION_URN
from skm.modules.planning.generated import queries as q
from skm.modules.planning.generated.commands import (
    CreatePlan,
    ImportSpecification,
    ImportSpecificationDefsExportMeta,
    ImportSpecificationDefsExportMetaSourceVariant1,
    ImportSpecificationMaterialRebindItem,
    OpenDraft,
    PublishRevision,
    SaveDraft,
)
from skm.modules.planning.ports import DraftRepository, PlanRepository
from skm.modules.workspace import public as ws_pub
from skm.platform.schema.registry import SchemaRegistry
from support.seed import SEED

VIEWER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d2"))
WS2_EDITOR_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d3"))
P1_ID, P2_ID, I1_ID, I2_ID, U1_ID, U2_ID, R1_ID, AC1_ID, CHK1_ID, DEC1_ID, MAT1_ID = (
    f"0195f0a1-0000-7000-8000-{i:012x}" for i in range(1, 12)
)


def _ask(client: Any, query: object) -> Any:
    return client.ask(query)


def _issue_actor(
    h: Harness, token_id: UUID, permissions: tuple[str, ...], principal_id: PrincipalId = OWNER_ID
) -> Actor:
    prefix, perms = f"tokpaaa{'abcdefghijklmnopqrstuvwxyz234567'[token_id.int & 31]}", frozenset(permissions)
    t_args: Any = (TokenId(token_id), principal_id, TokenKind.PERSONAL, prefix, prefix, b"\x02" * 32)
    token = cast("Any", ApiToken)(*t_args, None, perms, None, h.clock.now(), OWNER_ID, *(None,) * 6)
    with h.app.uow_factory(req_meta(h, 800), readonly=False) as uow:
        uow.repo(TokenRepository).add(token)
        uow.commit()
    grant = TokenGrant(token_id, "personal", None, perms, None)
    return Actor(principal_id=principal_id, kind=PrincipalKind.HUMAN, display_name=prefix, grant=grant)


def _add_project_with_repo(client: Any, ws: WorkspaceId, slug: str) -> ProjectId:
    proj = ProjectId(dispatch_new(client, ws_pub.CreateProject(ws, slug, slug)).project_id)
    repo = dispatch_new(client, ws_pub.RegisterRepository(ws, slug, f"https://example.com/{slug}.git", None))
    dispatch_new(client, ws_pub.AttachRepository(proj, repo.repository_id, "repo", "primary"))
    return proj


def _make_ws2_client(h: Harness, slug: str, token_suffix: str) -> tuple[WorkspaceId, ProjectId, Any]:
    ws2 = WorkspaceId(dispatch_new(h.client, ws_pub.CreateWorkspace(slug, slug)).workspace_id)
    proj2 = _add_project_with_repo(h.client, ws2, f"{slug}-proj")
    with h.app.uow_factory(req_meta(h, 77), readonly=False) as uow:
        grant_initial_membership(
            uow, scope_id=ScopeId(ws2), principal_id=WS2_EDITOR_ID, role=Role.OWNER, now=h.clock.now()
        )
        uow.commit()
    perms = (
        "plan.create",
        "plan.edit",
        "plan.publish",
        "plan.read",
        "file.read",
        "project.read",
        "workspace.read",
    )
    actor = _issue_actor(h, UUID(f"01900000-0000-7000-8000-0000000000{token_suffix}"), perms, WS2_EDITOR_ID)
    return ws2, proj2, h.app.client(actor=actor, surface=Surface.CLI)


def _upload_file_version(
    h: Harness, content: bytes, filename: str, *, ws: WorkspaceId | None = None, proj: ProjectId | None = None
) -> UUID:
    tws, tproj = (h.ws if ws is None else ws), (h.proj if proj is None else proj)
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    ref = h.client.upload_blob(
        tws, [content], size=len(content), expected_digest=digest, media_type="text/plain"
    )
    cmd = replace(add_file_dto(tws, tproj, ref), original_filename=filename)
    return cast("UUID", dispatch_new(h.client, cmd).file_version_id)


@pytest.fixture
def mem_h(tmp_path: Path) -> Iterator[Harness]:
    app, clock, blobs_root = open_test_app("memory", tmp_path)
    try:
        people = (
            (OWNER_ID, PrincipalKind.HUMAN, "owner"),
            (VIEWER_ID, PrincipalKind.HUMAN, "viewer"),
            (WS2_EDITOR_ID, PrincipalKind.HUMAN, "ws2-editor"),
        )
        roles = ((SEED.instance_id, OWNER_ID, Role.OWNER),)
        actor = seed_principals(app, "memory", people=people, roles=roles)
        client = app.client(actor=actor, surface=Surface.CLI)
        ws = WorkspaceId(dispatch_new(client, ws_pub.CreateWorkspace("main", "Main")).workspace_id)
        meta0 = RequestMeta("req_" + "0" * 26, Surface.CLI, None, clock.now())
        with app.uow_factory(meta0, readonly=False) as uow:
            grant_initial_membership(
                uow, scope_id=ScopeId(ws), principal_id=VIEWER_ID, role=Role.VIEWER, now=clock.now()
            )
            uow.commit()
        proj = _add_project_with_repo(client, ws, "skm")
        yield Harness(app, clock, actor, client, ws, proj, blobs_root, None)
    finally:
        app.close()


def _base_spec_doc(
    *,
    title: str = "Plan Portable",
    goal: str = "Verify portable export and import.",
    file_version_id: UUID | None = None,
) -> JsonObject:
    mat_json = (
        f'{{"id": "{MAT1_ID}", "key": "design-doc", "title": "Design Doc",'
        f' "kind": "file_version", "role": "reference", "required_for": ["execution"],'
        f' "freshness": {{"policy": "pinned"}}, "file_version_id": "{file_version_id}",'
        f' "why": "Architecture reference.", "applies_to": ["P1.1"]}}'
        if file_version_id is not None
        else f'{{"id": "{MAT1_ID}", "key": "spec-doc", "title": "Spec Doc",'
        f' "kind": "repository_path", "role": "reference", "required_for": ["execution", "review"],'
        f' "freshness": {{"policy": "pinned"}}, "mount": "repo", "path": "README.md",'
        f' "why": "Reference.", "applies_to": ["P1.1"]}}'
    )
    raw = f"""{{
      "schema": "{SPECIFICATION_URN}", "title": {json.dumps(title)}, "goal": {json.dumps(goal)},
      "context_md": "Portable context with UTF-8: Привет!",
      "requirements": [{{"id": "{R1_ID}", "key": "R1", "statement": "Must support portable roundtrip.",
        "priority": "must", "source": {{"kind": "owner"}}, "owners": ["P1.1"]}}],
      "phases": [
        {{"id": "{P1_ID}", "key": "P1", "title": "Phase One", "goal": "Core phase.",
          "design_state": "detailed", "depends_on": []}},
        {{"id": "{P2_ID}", "key": "P2", "title": "Phase Two", "goal": "Followup phase.",
          "design_state": "skeleton"}}
      ],
      "items": [
        {{"id": "{I1_ID}", "key": "P1.1", "phase": "P1", "title": "Item One",
          "summary": "First item.", "why": "Needed.", "work_kind": "code",
          "scope": {{"include": ["src/a.py"], "exclude": ["docs"]}}, "deliverables": ["src/a.py"],
          "review": {{"mode": "self", "reason": "small"}},
          "route": {{"class": "implementation", "effort": "high"}},
          "implements": ["R1"], "decisions": ["D1"],
          "change_hints": [{{"mount": "repo", "pattern": "src/a.py", "change": "modify"}},
            {{"mount": "repo", "pattern": "tests/test_a.py", "change": "modify"}}]}},
        {{"id": "{I2_ID}", "key": "P2.1", "phase": "P2", "title": "Item Two",
          "summary": "Second item.", "why": "Followup.", "work_kind": "test",
          "depends_on": ["P1.1"], "review": {{"mode": "self", "reason": "small"}},
          "route": {{"class": "economy", "effort": "medium"}},
          "change_hints": [{{"mount": "repo", "pattern": "tests/test_b.py", "change": "create"}}]}}
      ],
      "units": [
        {{"id": "{U1_ID}", "key": "P1.1/U1", "title": "Unit One", "goal": "Write code.",
          "unit_kind": "implementation", "work_kind": "code", "mode": "either",
          "write_scope": [{{"mount": "repo", "pattern": "src/a.py"}}],
          "checks": ["V1"], "implements": ["R1"]}},
        {{"id": "{U2_ID}", "key": "P1.1/U2", "title": "Unit Two", "goal": "Verify code.",
          "unit_kind": "verification", "work_kind": "test", "mode": "either",
          "depends_on": ["U1"], "write_scope": [{{"mount": "repo", "pattern": "tests/test_a.py"}}]}}
      ],
      "criteria": [{{"id": "{AC1_ID}", "key": "AC1", "owner": "P1.1", "statement": "Tests pass.",
        "verification_mode": "check", "checks": ["P1.1:V1"], "requirements": ["R1"]}}],
      "checks": [{{"id": "{CHK1_ID}", "key": "V1", "owner": "P1.1", "title": "Pytest check",
        "category": "acceptance", "kind": "command", "required": true,
        "definition": {{"argv": ["pytest", "-q"], "cwd": {{"mount": "repo", "path": "."}}}}}}],
      "decisions": [{{"id": "{DEC1_ID}", "key": "D1", "title": "Use stable IDs",
        "state": "accepted", "question": "Which key?", "decision": "UUIDv7.",
        "rationale": "Renames stay safe.", "applies_to": ["P1.1"]}}],
      "materials": [{mat_json}]
    }}"""
    return cast("JsonObject", json.loads(raw))


def _create_published_plan(
    h: Harness, doc: JsonObject | None = None, *, project_id: ProjectId | None = None
) -> tuple[UUID, UUID, UUID]:
    pid = h.proj if project_id is None else project_id
    payload = doc or _base_spec_doc()
    created = dispatch_new(h.client, CreatePlan(project_id=pid, title="Plan Portable"))
    opened = dispatch_new(h.client, OpenDraft(plan_id=created.plan_id, base="empty"))
    saved = dispatch_new(
        h.client, SaveDraft(created.plan_id, opened.draft_id, opened.edit_version, merge_patch=payload)
    )
    prev = _ask(h.client, q.PreviewPublication(created.plan_id, opened.draft_id, saved.edit_version))
    pub = dispatch_new(
        h.client,
        PublishRevision(created.plan_id, opened.draft_id, saved.edit_version, prev.content_digest, "Initial"),
    )
    return created.plan_id, opened.draft_id, pub.revision_id


def _meta(view_meta: Any) -> ImportSpecificationDefsExportMeta:
    return ImportSpecificationDefsExportMeta.from_json(view_meta.to_json())


def test_export_import_roundtrip_digest(mem_h: Harness) -> None:
    plan_id, _draft_id, rev_id = _create_published_plan(mem_h)
    exp_rev = _ask(mem_h.client, q.ExportSpecification(plan_id=plan_id, revision_id=rev_id))
    assert exp_rev.export_meta.format == SPECIFICATION_URN
    assert exp_rev.export_meta.source.kind == "revision"
    assert exp_rev.export_meta.source.revision_id == rev_id
    assert exp_rev.export_meta.content_digest == specification_digest(normalize_document(_base_spec_doc()))

    imp_cmd = ImportSpecification(
        mem_h.proj,
        exp_rev.document,
        "new_draft",
        plan_id,
        rev_id,
        True,
        export_meta=_meta(exp_rev.export_meta),
    )
    imp_draft = dispatch_new(mem_h.client, imp_cmd)
    assert (imp_draft.plan_id, imp_draft.edit_version, imp_draft.base_revision_id) == (plan_id, 1, rev_id)
    assert (imp_draft.stale, imp_draft.id_map, imp_draft.counts.error) == (False, (), 0)

    exp_draft = _ask(
        mem_h.client, q.ExportSpecification(plan_id, draft_id=imp_draft.draft_id, expected_edit_version=1)
    )
    assert (exp_draft.export_meta.source.kind, exp_draft.export_meta.source.base_revision_id) == (
        "draft",
        rev_id,
    )
    assert exp_draft.export_meta.content_digest == exp_rev.export_meta.content_digest
    assert exp_draft.document == exp_rev.document

    # Publish R2 on plan_id, then import exported R1 as a stale draft (planning.md §17)
    s_r2 = dispatch_new(
        mem_h.client,
        SaveDraft(plan_id, imp_draft.draft_id, 1, merge_patch={"goal": "Updated goal in R2."}),
    )
    prev_r2 = _ask(mem_h.client, q.PreviewPublication(plan_id, imp_draft.draft_id, s_r2.edit_version))
    pub_r2 = dispatch_new(
        mem_h.client,
        PublishRevision(plan_id, imp_draft.draft_id, s_r2.edit_version, prev_r2.content_digest, "R2"),
    )
    assert pub_r2.revision_no == 2
    stale_r1 = dispatch_new(mem_h.client, imp_cmd)
    assert (stale_r1.base_revision_id, stale_r1.stale) == (rev_id, True)
    with pytest.raises(Conflict) as base_exc:
        dispatch_new(
            mem_h.client,
            PublishRevision(plan_id, stale_r1.draft_id, 1, exp_rev.export_meta.content_digest, "Stale R1"),
        )
    assert base_exc.value.code is ErrorCode.BASE_REVISION_CHANGED

    fresh_proj = _add_project_with_repo(mem_h.client, mem_h.ws, "fresh-proj")
    imp_rekeyed = dispatch_new(
        mem_h.client, ImportSpecification(fresh_proj, exp_rev.document, "new_plan", keep_ids=False)
    )
    re_exp = _ask(
        mem_h.client,
        q.ExportSpecification(imp_rekeyed.plan_id, draft_id=imp_rekeyed.draft_id, expected_edit_version=1),
    )
    src_json = re_exp.export_meta.to_json()["source"]
    assert src_json.get("base_revision_id", "missing") is None

    ws_rt = WorkspaceId(dispatch_new(mem_h.client, ws_pub.CreateWorkspace("ws-rt", "WS RT")).workspace_id)
    proj_rt = _add_project_with_repo(mem_h.client, ws_rt, "proj-rt")
    imp_keep = dispatch_new(
        mem_h.client, ImportSpecification(proj_rt, re_exp.document, "new_plan", keep_ids=True)
    )
    exp_again = _ask(
        mem_h.client,
        q.ExportSpecification(imp_keep.plan_id, draft_id=imp_keep.draft_id, expected_edit_version=1),
    )
    assert exp_again.export_meta.content_digest == re_exp.export_meta.content_digest
    assert exp_again.document == re_exp.document


def test_export_rejects_host_paths_and_secrets(mem_h: Harness) -> None:
    created = dispatch_new(mem_h.client, CreatePlan(project_id=mem_h.proj, title="Unsafe Plan"))
    opened = dispatch_new(mem_h.client, OpenDraft(plan_id=created.plan_id, base="empty"))
    ev = opened.edit_version
    cases = (
        ("/home/developer/secret-checkout/README.md", "CS-ABSOLUTE-PATH"),
        ("Use token ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8 for deploy", "CS-SECRET-CONTENT"),
        ("my dir/.env", "CS-SECRET-NAME"),
    )
    for val, expected_rule in cases:
        doc = _base_spec_doc()
        doc["context_md"] = val
        ev = dispatch_new(
            mem_h.client, SaveDraft(created.plan_id, opened.draft_id, ev, merge_patch=doc)
        ).edit_version
        with pytest.raises(ValidationFailed) as exc_exp:
            _ask(
                mem_h.client,
                q.ExportSpecification(created.plan_id, draft_id=opened.draft_id, expected_edit_version=ev),
            )
        assert exc_exp.value.code is ErrorCode.CONTENT_UNSAFE
        assert any(f["rule"] == expected_rule for f in cast("Any", exc_exp.value.details)["findings"])
        with pytest.raises(ValidationFailed) as exc_imp:
            dispatch_new(
                mem_h.client, ImportSpecification(mem_h.proj, cast("Any", doc), "new_plan", keep_ids=False)
            )
        assert exc_imp.value.code is ErrorCode.CONTENT_UNSAFE
        assert any(f["rule"] == expected_rule for f in cast("Any", exc_imp.value.details)["findings"])


def test_import_new_plan_success(mem_h: Harness) -> None:
    doc = _base_spec_doc(title="Imported Plan Title")
    res = dispatch_new(
        mem_h.client,
        ImportSpecification(
            mem_h.proj, cast("Any", doc), "new_plan", keep_ids=True, title="Custom Override Title"
        ),
    )
    assert res.alias.startswith("PLAN")
    assert (res.edit_version, res.base_revision_id, res.stale, res.id_map, res.counts.error) == (
        1,
        None,
        False,
        (),
        0,
    )

    plan_view = _ask(mem_h.client, q.GetPlan(plan_id=res.plan_id))
    assert plan_view.title == "Custom Override Title"
    assert (plan_view.current_revision_id, plan_view.open_drafts) == (None, 1)

    draft_view = _ask(mem_h.client, q.GetDraft(plan_id=res.plan_id, draft_id=res.draft_id))
    assert (draft_view.state, draft_view.edit_version, draft_view.published_revision_id) == ("open", 1, None)
    assert draft_view.document_digest == specification_digest(normalize_document(doc))

    with mem_h.app.uow_factory(req_meta(mem_h, 55), readonly=True) as uow:
        mem_log: Any = uow.repo(AuditLog)
        plan_events = [e for e in mem_log._core.events if e.stream_id == res.plan_id]
        assert [e.type for e in plan_events] == [PlanCreated.event_type, DraftOpened.event_type]
        assert plan_events[1].payload["source"] == "import"
        assert all(e.type != PlanRevisionPublished.event_type for e in mem_log._core.events)

    cmd = ImportSpecification(mem_h.proj, cast("Any", doc), "new_plan", keep_ids=False)
    assert mem_h.client.dispatch(cmd, idempotency_key="idem-001") == mem_h.client.dispatch(
        cmd, idempotency_key="idem-001"
    )


def test_import_keep_ids_false_maps_entities(mem_h: Harness) -> None:
    plan_id, _draft_id, rev_id = _create_published_plan(mem_h)
    exp = _ask(mem_h.client, q.ExportSpecification(plan_id=plan_id, revision_id=rev_id))
    meta = _meta(exp.export_meta)

    other_proj = _add_project_with_repo(mem_h.client, mem_h.ws, "other-in-ws")
    for target_proj, opt_meta in ((mem_h.proj, meta), (other_proj, None)):
        with pytest.raises(Conflict) as conflict_exc:
            dispatch_new(
                mem_h.client,
                ImportSpecification(
                    target_proj, exp.document, "new_plan", keep_ids=True, export_meta=opt_meta
                ),
            )
        assert conflict_exc.value.code is ErrorCode.ID_CONFLICT
        cdetails: Any = conflict_exc.value.details
        assert (cdetails.get("hint"), P1_ID in cdetails["entity_ids"]) == ("keep_ids=false", True)

    res = dispatch_new(
        mem_h.client,
        ImportSpecification(mem_h.proj, exp.document, "new_plan", keep_ids=False, export_meta=meta),
    )
    assert (res.plan_id != plan_id, len(res.id_map), res.counts.error) == (True, 11, 0)
    expected_keys = [
        "P1",
        "P2",
        "P1.1",
        "P2.1",
        "P1.1/U1",
        "P1.1/U2",
        "R1",
        "AC1",
        "P1.1:V1",
        "D1",
        "material/spec-doc",
    ]
    assert [m.key for m in res.id_map] == expected_keys
    assert [m.entity_kind for m in res.id_map[:3]] == ["phase", "phase", "item"]
    assert all(m.old_id is not None and m.new_id != m.old_id for m in res.id_map)

    draft_view = _ask(mem_h.client, q.GetDraft(plan_id=res.plan_id, draft_id=res.draft_id))
    assert draft_view.document["phases"][0]["id"] == str(res.id_map[0].new_id)


def test_import_foreign_workspace_without_rebind(mem_h: Harness) -> None:
    ws1_vid = _upload_file_version(mem_h, b"Design spec bytes\n", "design.md")
    plan1_id, _d1_id, rev1_id = _create_published_plan(mem_h, _base_spec_doc(file_version_id=ws1_vid))

    for idx, perms in enumerate((("project.read",), ("plan.read", "project.read"))):
        limited = _issue_actor(mem_h, UUID(f"01900000-0000-7000-8000-0000000000f{idx}"), perms, VIEWER_ID)
        with pytest.raises(Forbidden):
            _ask(
                mem_h.app.client(actor=limited, surface=Surface.CLI),
                q.ExportSpecification(plan_id=plan1_id, revision_id=rev1_id),
            )

    exp = _ask(mem_h.client, q.ExportSpecification(plan_id=plan1_id, revision_id=rev1_id))
    mat_meta = exp.export_meta.materials[0]
    assert (mat_meta.material_key, mat_meta.file_version_id, mat_meta.original_filename) == (
        "design-doc",
        ws1_vid,
        "design.md",
    )

    _ws2, proj2, ws2_client = _make_ws2_client(mem_h, "ws-two", "f5")
    imp = dispatch_new(
        ws2_client,
        ImportSpecification(
            proj2, exp.document, "new_plan", keep_ids=True, export_meta=_meta(exp.export_meta)
        ),
    )
    assert imp.counts.error >= 1
    exp_ws2 = _ask(
        ws2_client, q.ExportSpecification(imp.plan_id, draft_id=imp.draft_id, expected_edit_version=1)
    )
    assert exp_ws2.export_meta.materials == ()

    val_report = _ask(mem_h.client, q.ValidateDraft(imp.plan_id, imp.draft_id, expected_edit_version=1))
    assert val_report.publishable is False
    assert any(f.code == "material_unavailable" for f in val_report.findings)

    draft_view = _ask(mem_h.client, q.GetDraft(plan_id=imp.plan_id, draft_id=imp.draft_id))
    with pytest.raises(PreconditionFailed) as pub_exc:
        dispatch_new(
            mem_h.client, PublishRevision(imp.plan_id, imp.draft_id, 1, draft_view.document_digest, "Fail")
        )
    assert pub_exc.value.code is ErrorCode.PLAN_NOT_READY


def test_import_foreign_workspace_with_rebind(mem_h: Harness) -> None:
    ws1_vid = _upload_file_version(mem_h, b"Portable content\n", "arch.md")
    plan1_id, _d1_id, rev1_id = _create_published_plan(mem_h, _base_spec_doc(file_version_id=ws1_vid))
    exp = _ask(mem_h.client, q.ExportSpecification(plan_id=plan1_id, revision_id=rev1_id))

    ws2, proj2, ws2_client = _make_ws2_client(mem_h, "ws-rebind", "f6")
    ws2_vid = _upload_file_version(mem_h, b"Portable content\n", "arch.md", ws=ws2, proj=proj2)

    rebind_ws1 = (ImportSpecificationMaterialRebindItem(material_key="design-doc", file_version_id=ws1_vid),)
    with pytest.raises(NotFound) as nf_exc:
        dispatch_new(
            ws2_client,
            ImportSpecification(proj2, exp.document, "new_plan", keep_ids=False, material_rebind=rebind_ws1),
        )
    assert nf_exc.value.code is ErrorCode.NOT_FOUND

    rebind_ws2 = (ImportSpecificationMaterialRebindItem(material_key="design-doc", file_version_id=ws2_vid),)
    imp = dispatch_new(
        ws2_client,
        ImportSpecification(
            proj2,
            exp.document,
            "new_plan",
            keep_ids=False,
            export_meta=_meta(exp.export_meta),
            material_rebind=rebind_ws2,
        ),
    )
    assert imp.counts.error == 0
    prev = _ask(ws2_client, q.PreviewPublication(imp.plan_id, imp.draft_id, imp.edit_version))
    assert prev.publishable is True
    pub = dispatch_new(
        ws2_client,
        PublishRevision(imp.plan_id, imp.draft_id, imp.edit_version, prev.content_digest, "Rebound"),
    )
    assert (pub.revision_no, pub.pinned_materials[0].file_version_id) == (1, ws2_vid)


def test_import_schema_invalid_rejected(mem_h: Harness) -> None:
    plan_id, _draft_id, rev_id = _create_published_plan(mem_h)
    bad_doc: dict[str, Any] = {
        **_base_spec_doc(),
        "phases": [{"key": "invalid_key", "title": "Bad", "goal": "Bad", "design_state": "detailed"}],
    }
    float_doc: dict[str, Any] = {
        **_base_spec_doc(),
        "extensions": {"x-custom": {"schema_version": 1, "value": {"ratio": 1.25}}},
    }
    for invalid_doc in (bad_doc, float_doc):
        with pytest.raises(ValidationFailed) as exc_bad:
            dispatch_new(
                mem_h.client,
                ImportSpecification(mem_h.proj, cast("Any", invalid_doc), "new_plan", keep_ids=False),
            )
        assert exc_bad.value.code is ErrorCode.SCHEMA_INVALID

    missing_id_doc: dict[str, Any] = copy.deepcopy(dict(_base_spec_doc()))
    del missing_id_doc["phases"][0]["id"]
    with pytest.raises(ValidationFailed) as exc3:
        dispatch_new(
            mem_h.client,
            ImportSpecification(
                mem_h.proj, cast("Any", missing_id_doc), "new_draft", plan_id, rev_id, keep_ids=True
            ),
        )
    assert exc3.value.code is ErrorCode.SCHEMA_INVALID
    assert cast("Any", exc3.value.details)["issues"][0]["pointer"] == "/phases/0/id"

    bad_meta = ImportSpecificationDefsExportMeta(
        format=SPECIFICATION_URN,
        source=ImportSpecificationDefsExportMetaSourceVariant1(
            kind="revision", plan_id=plan_id, plan_alias="PLAN1", revision_id=rev_id, revision_no=1
        ),
        content_digest=specification_digest(normalize_document(_base_spec_doc())),
        exported_at=mem_h.clock.now(),
        exported_by=UUID(str(OWNER_ID)),
        skm_version="2.0.0",
        materials=(),
    )
    bad_cmd = ImportSpecification(
        mem_h.proj, cast("Any", _base_spec_doc()), "new_draft", plan_id, None, True, export_meta=bad_meta
    )
    with pytest.raises(ValidationFailed) as exc4:
        dispatch_new(mem_h.client, bad_cmd)
    assert exc4.value.code is ErrorCode.SCHEMA_INVALID

    schemas = SchemaRegistry.load_default()
    cmd_urn = "urn:skm:planning:command:import-specification:v1"
    raw_no_base = bad_cmd.to_json()
    del raw_no_base["source_base_revision_id"]
    raw_extra_meta = bad_cmd.to_json()
    raw_extra_meta["export_meta"]["unknown_field"] = 1
    for bad_raw in (raw_no_base, raw_extra_meta):
        with pytest.raises(ValidationFailed):
            schemas.require_valid(cmd_urn, bad_raw)
    with pytest.raises(ValueError, match="source_base_revision_id"):
        ImportSpecification.from_json(raw_no_base)

    stale_res = dispatch_new(
        mem_h.client,
        ImportSpecification(mem_h.proj, cast("Any", _base_spec_doc()), "new_draft", plan_id, None, True),
    )
    assert (stale_res.stale, stale_res.base_revision_id) == (True, None)

    viewer_actor = _issue_actor(
        mem_h,
        UUID("01900000-0000-7000-8000-0000000000e9"),
        ("plan.read", "project.read", "workspace.read"),
        VIEWER_ID,
    )
    with pytest.raises(Forbidden):
        dispatch_new(
            mem_h.app.client(actor=viewer_actor, surface=Surface.CLI),
            ImportSpecification(mem_h.proj, cast("Any", _base_spec_doc()), "new_plan", keep_ids=False),
        )

    with mem_h.app.uow_factory(req_meta(mem_h, 99), readonly=True) as uow:
        assert len(uow.repo(PlanRepository).project_plan_refs(mem_h.proj)) == 2
        assert len(uow.repo(DraftRepository).list_for_plan(PlanId(plan_id), state=None)) == 2


def test_import_into_new_draft_writes_and_requires_an_explicit_null_base() -> None:
    # new_draft requires the nullable source_base_revision_id: absence must not stand for null.
    schemas = SchemaRegistry.load_default()
    project, plan = UUID(int=1), UUID(int=2)
    draft = ImportSpecification(project, cast("Any", _base_spec_doc()), "new_draft", plan, None, True)
    raw = draft.to_json()
    assert raw["source_base_revision_id"] is None
    schemas.require_valid(ImportSpecification.SCHEMA_URN, raw)
    assert ImportSpecification.from_json(raw) == draft

    fresh = ImportSpecification(project, cast("Any", _base_spec_doc()), "new_plan")
    assert "source_base_revision_id" not in fresh.to_json()
    assert ImportSpecification.from_json(fresh.to_json()) == fresh

    del raw["source_base_revision_id"]
    with pytest.raises(ValueError, match="'source_base_revision_id' required when 'mode' is 'new_draft'"):
        ImportSpecification.from_json(raw)
