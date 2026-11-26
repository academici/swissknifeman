"""Unit tests for planning queries, domain diff/stats/id_space, and source_reader."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Mapping
from functools import partial
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
from skm.kernel.actor import Actor, PrincipalKind, TokenGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, NotFound, Unauthenticated, ValidationFailed
from skm.kernel.ids import EntityId, PlanId, PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access.domain.token import ApiToken
from skm.modules.access.ports import TokenRepository
from skm.modules.access.public import RevokeToken, Role, TokenId, TokenKind, grant_initial_membership
from skm.modules.planning.domain.canonical import normalize_document
from skm.modules.planning.domain.compile_graph import compile_execution_graph
from skm.modules.planning.domain.diff import diff_specifications
from skm.modules.planning.domain.draft import DraftId
from skm.modules.planning.domain.id_space import from_id_space, to_id_space
from skm.modules.planning.domain.specification import SPECIFICATION_URN, EntityKind, from_document
from skm.modules.planning.domain.stats import compute_stats
from skm.modules.planning.generated import queries as q
from skm.modules.planning.generated.commands import CreatePlan, OpenDraft, PublishRevision, SaveDraft
from skm.modules.planning.ports import AliasKind, DraftRepository, PlanRepository
from skm.modules.workspace import public as ws_pub
from support.seed import SEED

ROOT = Path(__file__).resolve().parents[4]
EXAMPLES_PLANS = ROOT / "tests/fixtures/corpus/examples" / "plans"
READ_PERMS = ("plan.read", "project.read", "workspace.read")

VIEWER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d2"))
FOREIGN_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d3"))
NO_PERM_TOKEN_ID, PLAN_READ_ONLY_TOKEN_ID, VIEWER_TOKEN_ID, FOREIGN_TOKEN_ID = (
    UUID(f"01900000-0000-7000-8000-0000000000e{i}") for i in range(1, 5)
)
P1_ID, P2_ID, I1_ID, I2_ID, U1_ID, U2_ID, R1_ID, AC1_ID, CHK1_ID, DEC1_ID, MAT1_ID = (
    f"0195f0a1-0000-7000-8000-{i:012x}" for i in range(1, 12)
)


def ask_query(client: Any, query: object) -> Any:
    return client.ask(query)


def _issue_actor(
    h: Harness,
    token_id: UUID,
    permissions: tuple[str, ...],
    principal_id: PrincipalId = OWNER_ID,
    seq: int = 800,
) -> Actor:
    prefix = f"toka{chr(ord('a') + (seq % 20)) * 4}"
    token = ApiToken(
        TokenId(token_id),
        principal_id,
        TokenKind.PERSONAL,
        prefix,
        prefix,
        b"\x02" * 32,
        None,
        frozenset(permissions),
        None,
        h.clock.now(),
        OWNER_ID,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    with h.app.uow_factory(req_meta(h, seq), readonly=False) as uow:
        uow.repo(TokenRepository).add(token)
        uow.commit()
    grant = TokenGrant(token_id, "personal", None, frozenset(permissions), None)
    return Actor(principal_id=principal_id, kind=PrincipalKind.HUMAN, display_name=prefix, grant=grant)


def _add_project_with_repo(client: Any, ws: WorkspaceId, slug: str) -> ProjectId:
    proj = ProjectId(dispatch_new(client, ws_pub.CreateProject(ws, slug, slug)).project_id)
    repo = dispatch_new(client, ws_pub.RegisterRepository(ws, slug, f"https://example.com/{slug}.git", None))
    dispatch_new(client, ws_pub.AttachRepository(proj, repo.repository_id, "repo", "primary"))
    return proj


@pytest.fixture
def mem_h(tmp_path: Path) -> Iterator[Harness]:
    app, clock, blobs_root = open_test_app("memory", tmp_path)
    try:
        people = (
            (OWNER_ID, PrincipalKind.HUMAN, "owner"),
            (VIEWER_ID, PrincipalKind.HUMAN, "viewer"),
            (FOREIGN_ID, PrincipalKind.HUMAN, "foreign"),
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


def _base_spec_doc(*, title: str = "Plan Alpha", goal: str = "Ship queries — fast.") -> JsonObject:
    raw = f"""{{
      "schema": "{SPECIFICATION_URN}", "title": {json.dumps(title)}, "goal": {json.dumps(goal)},
      "context_md": "Context with UTF-8: Привет 🚀!",
      "requirements": [{{"id": "{R1_ID}", "key": "R1", "statement": "Must support queries.",
        "priority": "must", "source": {{"kind": "owner"}}, "owners": ["P1.1"]}}],
      "phases": [
        {{"id": "{P1_ID}", "key": "P1", "title": "Phase One", "goal": "Core phase.",
          "design_state": "detailed", "depends_on": []}},
        {{"id": "{P2_ID}", "key": "P2", "title": "Phase Two", "goal": "Skeleton phase.",
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
      "materials": [{{"id": "{MAT1_ID}", "key": "spec-doc", "title": "Spec Doc",
        "kind": "repository_path", "role": "reference", "required_for": ["execution", "review"],
        "freshness": {{"policy": "pinned"}}, "mount": "repo", "path": "README.md",
        "why": "Reference.", "applies_to": ["P1.1"]}}]
    }}"""
    return cast("JsonObject", json.loads(raw))


def _strip_entity_ids(doc: JsonObject) -> JsonObject:
    copied: dict[str, Any] = copy.deepcopy(dict(doc))
    for arr in ("requirements", "phases", "items", "units", "criteria", "checks", "decisions", "materials"):
        for ent in copied.get(arr, ()):
            ent.pop("id", None)
    return copied


def _save(h: Harness, plan_id: UUID, draft_id: UUID, ver: int, patch: Mapping[str, Any]) -> Any:
    return dispatch_new(
        h.client, SaveDraft(plan_id=plan_id, draft_id=draft_id, expected_edit_version=ver, merge_patch=patch)
    )


def _create_published_plan(
    h: Harness, doc: JsonObject | None = None, *, project_id: ProjectId | None = None, strip_ids: bool = False
) -> tuple[UUID, UUID, UUID]:
    pid = h.proj if project_id is None else project_id
    payload = _strip_entity_ids(doc or _base_spec_doc()) if strip_ids else (doc or _base_spec_doc())
    created = dispatch_new(h.client, CreatePlan(project_id=pid, title="Plan Alpha"))
    opened = dispatch_new(h.client, OpenDraft(plan_id=created.plan_id, base="empty"))
    saved = _save(h, created.plan_id, opened.draft_id, opened.edit_version, payload)
    prev = ask_query(h.client, q.PreviewPublication(created.plan_id, opened.draft_id, saved.edit_version))
    cmd = PublishRevision(created.plan_id, opened.draft_id, saved.edit_version, prev.content_digest, "Init")
    return created.plan_id, opened.draft_id, dispatch_new(h.client, cmd).revision_id


def test_id_space_and_golden_diff_and_ready_preview(mem_h: Harness) -> None:
    doc = _base_spec_doc()
    id_doc = to_id_space(doc)
    assert id_doc.entities[EntityKind.ITEM][EntityId(UUID(I1_ID))].id_record["phase"] == P1_ID
    assert id_doc.entities[EntityKind.ITEM][EntityId(UUID(I1_ID))].id_record["key"] == "1"
    assert id_doc.entities[EntityKind.UNIT][EntityId(UUID(U1_ID))].id_record["key"] == [I1_ID, "U1"]
    assert id_doc.entities[EntityKind.CHECK][EntityId(UUID(CHK1_ID))].id_record["key"] == [I1_ID, "V1"]
    assert from_id_space(id_doc) == normalize_document(doc)

    reparented = copy.deepcopy(doc)
    cast("list[dict[str, Any]]", reparented["units"])[0]["key"] = "P2.1/U1"
    u1_diff = next(e for e in diff_specifications(doc, reparented).entities if str(e.entity_id) == U1_ID)
    assert (u1_diff.rekeyed, u1_diff.moved) == (True, True)

    auth_r1: dict[str, Any] = json.loads(
        (EXAMPLES_PLANS / "auth-refresh.specification.json").read_text("utf-8")
    )
    assert from_id_space(to_id_space(cast("JsonObject", auth_r1))) == normalize_document(
        cast("JsonObject", auth_r1)
    )
    auth_r1["checks"] = [
        dict(c) for c in auth_r1["checks"] if not (c["owner"] == "P2.3" and c["key"] == "V2")
    ]
    auth_r2: dict[str, Any] = copy.deepcopy(auth_r1)
    auth_r2["rules"] = [*auth_r2["rules"], "Feature flag auth.rotation guards the rollout."]
    auth_r2["requirements"][2]["owners"] = ["P2.5"]
    auth_r2["phases"][1]["batches"][1]["items"] = ["P2.5"]
    auth_r2["items"][1]["title"] = "Token rotation service"
    auth_r2["items"][4]["key"] = "P2.5"
    auth_r2["items"][4]["depends_on"] = [*auth_r2["items"][4]["depends_on"], "P2.4"]
    p24 = json.loads(
        '{"id": "0192f5c4-0000-7000-8000-000000000099", "key": "P2.4", "phase": "P2",'
        ' "title": "Feature flag rollout", "summary": "Guard.", "why": "Safe.",'
        ' "work_kind": "code", "review": {"mode": "self", "reason": "small"}}'
    )
    auth_r2["items"].insert(-1, p24)
    auth_r2["units"] = [dict(u) for u in auth_r2["units"] if u["key"] != "P2.2/U2"]
    auth_r2["criteria"][3]["owner"] = "P2.5"
    auth_r2["criteria"][3]["checks"] = ["P2.5:V1"]
    auth_r2["materials"][2]["applies_to"] = ["P2.5"]
    auth_r2["checks"][2]["definition"] = {**auth_r2["checks"][2]["definition"], "timeout_seconds": 300}
    auth_r2["checks"][6]["owner"] = "P2.5"
    auth_r2["decisions"][1].update(
        state="accepted", decision="A", rationale="Product keeps 15 minutes; silent refresh hides it."
    )

    diff_example = json.loads((EXAMPLES_PLANS / "diff-r1-r2.json").read_text("utf-8"))
    computed = diff_specifications(cast("JsonObject", auth_r1), cast("JsonObject", auth_r2))
    for k in ("added", "removed", "changed", "rekeyed", "moved"):
        assert computed.summary[k] == diff_example["summary"][k]
    assert [(f.pointer, f.op, f.before, f.after) for f in computed.plan_fields] == [
        (f["pointer"], f["op"], f.get("from"), f.get("to")) for f in diff_example["plan_fields"]
    ]
    by_keys = {(e.entity_kind.value, e.key_before, e.key_after): e for e in computed.entities}
    assert len(by_keys) == len(diff_example["entities"])
    for exp_e in diff_example["entities"]:
        act_e = by_keys[(exp_e["entity_kind"], exp_e["key_from"], exp_e["key_to"])]
        assert (act_e.rekeyed, act_e.moved) == ("rekeyed" in exp_e["changes"], "moved" in exp_e["changes"])
        assert [(f.pointer, f.op, f.before, f.after) for f in act_e.fields] == [
            (f["pointer"], f["op"], f.get("from"), f.get("to")) for f in exp_e["fields"]
        ]

    auth_plan = dispatch_new(mem_h.client, CreatePlan(project_id=mem_h.proj, title="Refresh token rotation"))
    auth_draft = dispatch_new(mem_h.client, OpenDraft(plan_id=auth_plan.plan_id, base="empty"))
    auth_saved = _save(
        mem_h, auth_plan.plan_id, auth_draft.draft_id, auth_draft.edit_version, cast("JsonObject", auth_r1)
    )
    ready_golden = json.loads((EXAMPLES_PLANS / "ready-preview.json").read_text("utf-8"))
    for scen in ready_golden["scenarios"]:
        done, granted = tuple(scen["assume_done"]), tuple(scen["assume_granted"])
        rp_view = ask_query(
            mem_h.client,
            q.ReadyPreview(
                auth_plan.plan_id,
                None,
                auth_draft.draft_id,
                auth_saved.edit_version,
                done,
                granted,
                scen["limit"],
            ),
        )
        lanes_actual = [
            (ln.kind, list(ln.tasks), ln.batch_key, ln.route.class_ if ln.route else None)
            for ln in rp_view.lanes
        ]
        lanes_expected = [
            (ln["kind"], ln["tasks"], ln.get("batch"), ln["route"]["class"]) for ln in scen["lanes"]
        ]
        assert lanes_actual == lanes_expected
        assert [(w.task, w.reason, list(w.detail)) for w in rp_view.waiting] == [
            (w["task"], w["reason"], w["detail"]) for w in scen["waiting"]
        ]
        assert (list(rp_view.deferred), len(rp_view.route_groups)) == (
            scen["deferred"],
            len(scen["route_groups"]),
        )


def test_plan_list_aliases_supersedes_and_revisions(mem_h: Harness) -> None:
    p1_id, pub_draft_id, r1_id = _create_published_plan(mem_h)
    doc2 = _strip_entity_ids(_base_spec_doc(title="Plan Beta"))
    doc2["plan_relations"] = [{"kind": "supersedes", "target": "PLAN1"}]
    p2_id, _, _ = _create_published_plan(mem_h, doc2)

    with mem_h.app.uow_factory(req_meta(mem_h, 50), readonly=False) as uow:
        uow.repo(PlanRepository).add_alias(PlanId(p1_id), "LEGACY-01", AliasKind.LEGACY)
        uow.repo(PlanRepository).add_alias(PlanId(p1_id), "ext/plan-1", AliasKind.EXTERNAL)
        uow.commit()

    pv = ask_query(mem_h.client, q.GetPlan(plan_id=p1_id))
    assert [(a.alias, a.kind) for a in pv.aliases] == [
        ("PLAN1", "short"),
        ("ext/plan-1", "external"),
        ("LEGACY-01", "legacy"),
    ]

    for purpose in ("standard", "all"):
        pg1 = ask_query(mem_h.client, q.ListPlans(project_id=mem_h.proj, purpose=purpose, limit=1))
        assert (len(pg1.items), pg1.next_cursor is not None) == (1, True)
        pg2 = ask_query(
            mem_h.client, q.ListPlans(project_id=mem_h.proj, purpose=purpose, after=pg1.next_cursor, limit=1)
        )
        assert {pg1.items[0].plan_id, pg2.items[0].plan_id} == {p1_id, p2_id}

    resolved_chain = ask_query(
        mem_h.client, q.ResolvePlanRef(project_id=mem_h.proj, ref="plan1", follow_supersedes=True)
    )
    assert resolved_chain.superseded_chain == ("PLAN1", "PLAN2")
    with pytest.raises(ValidationFailed) as amb_err:
        ask_query(mem_h.client, q.ResolvePlanRef(project_id=mem_h.proj, ref=f"plan:{str(p1_id)[:14]}"))
    assert amb_err.value.code is ErrorCode.AMBIGUOUS_REFERENCE
    assert (
        ask_query(
            mem_h.client, q.ResolvePlanRef(project_id=mem_h.proj, ref=f"plan:{str(p1_id)[:24]}")
        ).plan_id
        == p1_id
    )
    assert [
        d.draft_id for d in ask_query(mem_h.client, q.ListDrafts(plan_id=p1_id, state="published")).items
    ] == [pub_draft_id]
    rv = ask_query(
        mem_h.client, q.GetRevision(plan_id=p1_id, current=True, include_document=True, include_tree=True)
    )
    assert (rv.revision_id, rv.tree is not None) == (r1_id, True)
    assert [
        r.revision_no for r in ask_query(mem_h.client, q.ListRevisions(plan_id=p1_id, limit=5)).items
    ] == [1]

    d_val = dispatch_new(mem_h.client, OpenDraft(plan_id=p1_id, base="current"))
    sub_doc = _strip_entity_ids(_base_spec_doc())
    cast("list[dict[str, Any]]", sub_doc["phases"])[0]["id"] = "0195f0ff-ffff-7000-8000-000000000001"
    rep = ask_query(mem_h.client, q.ValidateDraft(p1_id, d_val.draft_id, 1, sub_doc))
    assert (rep.publishable, rep.schema_issues) == (True, ())


def test_entities_pagination_cursor_security_read_text_and_preview(mem_h: Harness) -> None:
    plan_id, _, r1_id = _create_published_plan(mem_h)
    rt = partial(q.ReadText, plan_id=plan_id, revision_id=r1_id, target="plan", pointer="/context_md")
    le = partial(q.ListEntities, plan_id=plan_id, revision_id=r1_id, limit=3)

    seen_ids: list[UUID] = []
    cursor: str | None = None
    while True:
        page = ask_query(mem_h.client, le(after=cursor))
        seen_ids.extend(i.entity_id for i in page.items)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert (len(seen_ids), len(set(seen_ids))) == (11, 11)

    d_open = dispatch_new(mem_h.client, OpenDraft(plan_id=plan_id, base="current"))
    le_dr = partial(q.ListEntities, plan_id=plan_id, draft_id=d_open.draft_id, limit=2)
    rt_dr = partial(
        q.ReadText, plan_id=plan_id, draft_id=d_open.draft_id, target="plan", pointer="/context_md"
    )
    draft_doc = copy.deepcopy(_base_spec_doc())
    cast("list[dict[str, Any]]", draft_doc["items"])[1]["depends_on"] = []
    s_open = _save(mem_h, plan_id, d_open.draft_id, d_open.edit_version, draft_doc)
    ev_rev = ask_query(mem_h.client, q.GetEntity(plan_id=plan_id, revision_id=r1_id, ref="P1.1"))
    ev_draft = ask_query(
        mem_h.client,
        q.GetEntity(
            plan_id=plan_id, draft_id=d_open.draft_id, expected_edit_version=s_open.edit_version, ref="P1.1"
        ),
    )
    assert (ev_rev.links.dependents, ev_draft.links.dependents) == (("P2.1",), ())

    dp1 = ask_query(mem_h.client, le_dr(expected_edit_version=s_open.edit_version))
    s_open2 = _save(mem_h, plan_id, d_open.draft_id, s_open.edit_version, {"goal": "Updated goal"})
    for drift_q in (
        le_dr(expected_edit_version=s_open.edit_version, after=dp1.next_cursor),
        rt_dr(expected_edit_version=s_open.edit_version),
    ):
        with pytest.raises(Conflict) as drift_err:
            ask_query(mem_h.client, drift_q)
        assert drift_err.value.code is ErrorCode.VERSION_CONFLICT

    rev_p1 = ask_query(mem_h.client, le(limit=2))
    viewer_actor = _issue_actor(mem_h, VIEWER_TOKEN_ID, READ_PERMS, VIEWER_ID, 810)
    viewer_client = mem_h.app.client(actor=viewer_actor, surface=Surface.CLI)
    for client_i, tamper_q in (
        (mem_h.client, le_dr(expected_edit_version=s_open2.edit_version, after=rev_p1.next_cursor)),
        (mem_h.client, le(kinds=("phase",), after=rev_p1.next_cursor)),
        (viewer_client, le(after=rev_p1.next_cursor)),
    ):
        with pytest.raises(ValidationFailed) as tamper_err:
            ask_query(client_i, tamper_q)
        assert tamper_err.value.code is ErrorCode.INVALID_REFERENCE

    vp1 = ask_query(viewer_client, le(limit=2))
    dispatch_new(mem_h.client, RevokeToken(token_id=VIEWER_TOKEN_ID))
    with pytest.raises(Unauthenticated):
        ask_query(viewer_client, le(after=vp1.next_cursor))

    for off, mx, exp_slice in (
        (0, 35, ("Context with UTF-8: Привет ", True, 33)),
        (33, 5, ("🚀!", True, None)),
        (38, 16, ("", True, None)),
    ):
        frag = ask_query(mem_h.client, rt(offset_bytes=off, max_bytes=mx))
        assert (frag.text, frag.truncated, frag.next_offset_bytes) == exp_slice
    with mem_h.app.uow_factory(req_meta(mem_h, 60), readonly=False) as uow:
        dr_repo = uow.repo(DraftRepository)
        st_dr = dr_repo.get(DraftId(d_open.draft_id))
        st_dr.document["context_md"] = ""
        dr_repo.save(st_dr, expected_edit_version=st_dr.edit_version)
        uow.commit()
    empty_frag = ask_query(mem_h.client, rt_dr(expected_edit_version=s_open2.edit_version))
    assert (empty_frag.text, empty_frag.total_bytes, empty_frag.next_offset_bytes) == ("", 0, None)

    with pytest.raises(ValidationFailed) as mid_err:
        ask_query(mem_h.client, rt(offset_bytes=34, max_bytes=4))
    assert mid_err.value.code is ErrorCode.INVALID_REFERENCE
    with pytest.raises(ValidationFailed) as small_win:
        ask_query(mem_h.client, rt(offset_bytes=33, max_bytes=3))
    assert (small_win.value.code, small_win.value.details["min_required_bytes"]) == (
        ErrorCode.SCHEMA_INVALID,
        4,
    )

    bad_doc = copy.deepcopy(_base_spec_doc())
    cast("list[dict[str, Any]]", bad_doc["items"])[0]["depends_on"] = ["P9.9"]
    s_bad = _save(mem_h, plan_id, d_open.draft_id, s_open2.edit_version, bad_doc)
    prev_bad = ask_query(mem_h.client, q.PreviewPublication(plan_id, d_open.draft_id, s_bad.edit_version))
    assert (prev_bad.publishable, len(prev_bad.validation.findings) > 0) == (False, True)
    assert ask_query(mem_h.client, q.GetPlan(plan_id=plan_id)).current_revision_id == r1_id


def test_stats_counts_and_ench6_authorization_matrix(mem_h: Harness) -> None:
    plan_id, _, r1_id = _create_published_plan(mem_h)
    st = ask_query(mem_h.client, q.PlanStats(plan_id=plan_id, revision_id=r1_id))
    assert (st.counts["phases"], st.counts["items"], st.counts["units"]) == (2, 2, 2)
    assert st.counts["checks"] == {
        "by_kind": {"command": 1, "shell": 0, "manual": 0, "external": 0},
        "by_category": {"acceptance": 1, "impact": 0, "live": 0},
    }
    assert st.counts["decisions"]["by_state"]["accepted"] == 1
    assert st.counts["materials"]["by_kind"]["repository_path"] == 1
    base_spec = from_document(_base_spec_doc())[0]
    assert compute_stats(base_spec, compile_execution_graph(base_spec)).counts["units"] == 2

    proj2 = _add_project_with_repo(mem_h.client, mem_h.ws, "skm2")
    p2_id, _, r2_id = _create_published_plan(mem_h, project_id=proj2, strip_ids=True)
    d1 = dispatch_new(mem_h.client, OpenDraft(plan_id=plan_id, base="current"))
    d2 = dispatch_new(mem_h.client, OpenDraft(plan_id=p2_id, base="current"))

    viewer_actor = _issue_actor(mem_h, VIEWER_TOKEN_ID, READ_PERMS, VIEWER_ID, 820)
    v_client = mem_h.app.client(actor=viewer_actor, surface=Surface.CLI)
    assert ask_query(v_client, q.GetPlan(plan_id=plan_id)).plan_id == plan_id
    assert ask_query(v_client, q.GetPlan(plan_id=p2_id)).plan_id == p2_id
    assert len(ask_query(v_client, q.ListPlans(project_id=mem_h.proj)).items) == 1
    assert len(ask_query(v_client, q.ListPlans(project_id=proj2)).items) == 1

    for cross_q in (
        q.GetRevision(plan_id=plan_id, revision_id=r2_id),
        q.GetDraft(plan_id=plan_id, draft_id=d2.draft_id),
        q.GetEntity(plan_id=plan_id, revision_id=r2_id, ref="P1.1"),
        q.ListEntities(plan_id=plan_id, draft_id=d2.draft_id, expected_edit_version=1),
        q.ReadText(plan_id=plan_id, revision_id=r2_id, target="plan", pointer="/context_md"),
        q.DiffRevisions(plan_id=plan_id, to_revision_id=r2_id),
        q.PreviewPublication(plan_id=plan_id, draft_id=d2.draft_id, expected_edit_version=1),
        q.ValidateDraft(plan_id=plan_id, draft_id=d2.draft_id, expected_edit_version=1),
        q.ReadyPreview(plan_id=plan_id, revision_id=r2_id),
        q.PlanStats(plan_id=plan_id, revision_id=r2_id),
    ):
        with pytest.raises(NotFound):
            ask_query(mem_h.client, cross_q)

    foreign_actor = _issue_actor(mem_h, FOREIGN_TOKEN_ID, READ_PERMS, FOREIGN_ID, 821)
    no_perm_actor = _issue_actor(mem_h, NO_PERM_TOKEN_ID, (), OWNER_ID, 822)
    matrix_queries = (
        q.GetPlan(plan_id=plan_id),
        q.ListPlans(project_id=mem_h.proj),
        q.ResolvePlanRef(project_id=mem_h.proj, ref="PLAN1"),
        q.GetDraft(plan_id=plan_id, draft_id=d1.draft_id),
        q.ListDrafts(plan_id=plan_id),
        q.GetRevision(plan_id=plan_id, revision_id=r1_id),
        q.ListRevisions(plan_id=plan_id),
        q.GetEntity(plan_id=plan_id, revision_id=r1_id, ref="P1.1"),
        q.ListEntities(plan_id=plan_id, revision_id=r1_id),
        q.ReadText(plan_id=plan_id, revision_id=r1_id, target="plan", pointer="/context_md"),
        q.DiffRevisions(plan_id=plan_id, to_revision_id=r1_id),
        q.PreviewPublication(plan_id=plan_id, draft_id=d1.draft_id, expected_edit_version=1),
        q.ValidateDraft(plan_id=plan_id, draft_id=d1.draft_id, expected_edit_version=1),
        q.ReadyPreview(plan_id=plan_id, revision_id=r1_id),
        q.PlanStats(plan_id=plan_id, revision_id=r1_id),
    )
    for denied_actor in (foreign_actor, no_perm_actor):
        denied_client = mem_h.app.client(actor=denied_actor, surface=Surface.CLI)
        for mq in matrix_queries:
            with pytest.raises(Forbidden) as exc_info:
                ask_query(denied_client, mq)
            assert "Привет" not in str(exc_info.value.details)

    payload_bytes = b"pinned content\n"
    ref = mem_h.client.upload_blob(
        mem_h.ws, [payload_bytes], size=len(payload_bytes), media_type="text/plain"
    )
    file_res = dispatch_new(mem_h.client, add_file_dto(mem_h.ws, mem_h.proj, ref))
    doc_mat: dict[str, Any] = dict(_base_spec_doc(title="With Pin"))
    doc_mat["materials"] = [
        json.loads(
            f'{{"id": "{MAT1_ID}", "key": "pinned-file", "title": "Pinned", "kind": "file_version",'
            f' "role": "input", "required_for": ["execution"], "freshness": {{"policy": "pinned"}},'
            f' "file_version_id": "{file_res.file_version_id}", "why": "Pin test"}}'
        )
    ]
    s_mat = _save(mem_h, plan_id, d1.draft_id, d1.edit_version, doc_mat)
    plan_only_actor = _issue_actor(mem_h, PLAN_READ_ONLY_TOKEN_ID, ("plan.read",), OWNER_ID, 823)
    plan_only_client = mem_h.app.client(actor=plan_only_actor, surface=Surface.CLI)
    with pytest.raises(Forbidden):
        dispatch_new(
            plan_only_client,
            PublishRevision(plan_id, d1.draft_id, s_mat.edit_version, "sha256:" + "0" * 64, "denied"),
        )
    for mat_q in (
        q.PreviewPublication(plan_id, d1.draft_id, s_mat.edit_version),
        q.ValidateDraft(plan_id, d1.draft_id, s_mat.edit_version),
    ):
        with pytest.raises(Forbidden):
            ask_query(plan_only_client, mat_q)


def test_save_draft_reports_the_findings_validate_draft_reports(mem_h: Harness) -> None:
    # save_draft once built its own context with skills and the runtime catalog left out, so a saved draft
    # looked clean while validate_draft and the publication preview reported the same document as unknown.
    doc: dict[str, Any] = dict(_base_spec_doc(title="Skill Parity"))
    items = [dict(item) for item in cast("list[dict[str, Any]]", doc["items"])]
    items[0]["skills"] = [{"key": "no-such-skill"}]
    doc["items"] = items
    created = dispatch_new(mem_h.client, CreatePlan(project_id=mem_h.proj, title="Skill Parity"))
    opened = dispatch_new(mem_h.client, OpenDraft(plan_id=created.plan_id, base="empty"))
    saved = _save(mem_h, created.plan_id, opened.draft_id, opened.edit_version, doc)
    validated = ask_query(mem_h.client, q.ValidateDraft(created.plan_id, opened.draft_id, saved.edit_version))
    assert "skill_unknown" in {found.code for found in validated.findings}
    assert sorted((f.code, f.pointer) for f in saved.findings) == sorted(
        (f.code, f.pointer) for f in validated.findings
    )
