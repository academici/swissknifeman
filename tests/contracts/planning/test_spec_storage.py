"""Contract tests for planning repositories, queries and typed spec reader/writer."""

from __future__ import annotations

import json
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.planning import REPOSITORIES as MEMORY_REPOSITORIES
from skm.adapters.memory.planning.queries import MemoryPlanningQueries
from skm.adapters.memory.planning.repositories import (
    MemoryDraftRepository,
    MemoryPlanCounters,
    MemoryPlanRepository,
    MemoryRevisionRepository,
)
from skm.adapters.memory.planning.state import planning_state
from skm.adapters.postgres.core.scopes import PostgresScopeRegistry
from skm.adapters.postgres.planning import REPOSITORIES as POSTGRES_REPOSITORIES
from skm.adapters.postgres.planning.counters import PostgresPlanCounters
from skm.adapters.postgres.planning.drafts import PostgresDraftRepository
from skm.adapters.postgres.planning.plans import PostgresPlanRepository
from skm.adapters.postgres.planning.queries import PostgresPlanningQueries
from skm.adapters.postgres.planning.revisions import PostgresRevisionRepository
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import EntityId, PlanId, PrincipalId, ProjectId, RevisionId, ScopeId, WorkspaceId
from skm.kernel.pagination import Cursor
from skm.kernel.scopes import ScopeKind
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.draft import (
    DraftId,
    DraftState,
    abandon,
    open_draft,
)
from skm.modules.planning.domain.draft import (
    save as save_draft_domain,
)
from skm.modules.planning.domain.identity import assign_missing_ids, iter_entities
from skm.modules.planning.domain.plan import Plan, PlanPurpose, archive, new_plan, record_publication
from skm.modules.planning.domain.revision import RevisionOrigin, new_revision_meta
from skm.modules.planning.domain.specification import EntityKind, from_document, to_document
from skm.modules.planning.ports import (
    AliasKind,
    DraftRepository,
    MaterialPin,
    PlanCounters,
    PlanningQueries,
    PlanRepository,
    RevisionRecord,
    RevisionRepository,
    SpecificationDoc,
)
from support.pg import TestDatabase, pg_session, test_database  # noqa: F401
from support.seed import SEED

ROOT = Path(__file__).resolve().parents[3]
VALID_FIXTURES = sorted((ROOT / "tests/fixtures/planning/valid").glob("*.json"))
AUTH_REFRESH_PATH = ROOT / "tests/fixtures/corpus/examples/plans/auth-refresh.specification.json"

_INSTANCE_ID = SEED.instance_id
_WS_ID = WorkspaceId(UUID("0192f5c1-0000-7000-8000-000000000001"))
_PROJ_ID = ProjectId(UUID("0192f5c2-0000-7000-8000-000000000001"))
_PROJ2_ID = ProjectId(UUID("0192f5c2-0000-7000-8000-000000000002"))
_ACTOR_ID = PrincipalId(UUID("0192f5c3-0000-7000-8000-000000000001"))
_T0 = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)
_T1 = datetime(2026, 10, 21, 12, 5, 0, tzinfo=UTC)
_T2 = datetime(2026, 10, 21, 12, 10, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _ProjectRef:
    workspace_id: UUID
    project_id: UUID


_PROJ_REF = _ProjectRef(UUID(str(_WS_ID)), UUID(str(_PROJ_ID)))
_PROJ2_REF = _ProjectRef(UUID(str(_WS_ID)), UUID(str(_PROJ2_ID)))


@dataclass(frozen=True, slots=True)
class _Harness:
    backend: str
    counters: PlanCounters
    plans: PlanRepository
    drafts: DraftRepository
    revisions: RevisionRepository
    queries: PlanningQueries
    conn: psycopg.Connection | None = None

    def register_scope(self, plan: Plan) -> None:
        if self.conn is not None:
            PostgresScopeRegistry(self.conn).create(
                ScopeId(plan.id),
                ScopeKind.PLAN,
                parent=ScopeId(plan.project_id),
                workspace_id=plan.workspace_id,
            )

    def add_plan(self, plan: Plan) -> None:
        self.register_scope(plan)
        self.plans.add(plan)


def _seed_pg_workspace(conn: psycopg.Connection) -> None:
    conn.execute(
        "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id, created_at) "
        "VALUES (%s, 'instance', NULL, NULL, %s) ON CONFLICT (id) DO NOTHING",
        (_INSTANCE_ID, _T0),
    )
    conn.execute(
        "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id, created_at) "
        "VALUES (%s, 'workspace', %s, %s, %s) ON CONFLICT (id) DO NOTHING",
        (_WS_ID, _INSTANCE_ID, _WS_ID, _T0),
    )
    conn.execute(
        "INSERT INTO skm_workspace.workspaces (id, slug, title, state, row_version, created_at, updated_at) "
        "VALUES (%s, 'ws-main', 'Main', 'active', 1, %s, %s) ON CONFLICT (id) DO NOTHING",
        (_WS_ID, _T0, _T0),
    )
    for pid, slug in ((_PROJ_ID, "proj-one"), (_PROJ2_ID, "proj-two")):
        conn.execute(
            "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id, created_at) "
            "VALUES (%s, 'project', %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (pid, _WS_ID, _WS_ID, _T0),
        )
        conn.execute(
            "INSERT INTO skm_workspace.projects "
            "(id, workspace_id, slug, title, description, state, row_version, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'Project', '', 'active', 1, %s, %s) ON CONFLICT (id) DO NOTHING",
            (pid, _WS_ID, slug, _T0, _T0),
        )
    conn.execute(
        "INSERT INTO skm_access.principals "
        "(id, kind, display_name, state, row_version, created_at, created_by, updated_at) "
        "VALUES (%s, 'human', 'Test Actor', 'active', 1, %s, NULL, %s) ON CONFLICT (id) DO NOTHING",
        (_ACTOR_ID, _T0, _T0),
    )


def _seed_pg_file_versions(conn: psycopg.Connection, doc: SpecificationDoc) -> None:
    materials = cast("list[dict[str, object]]", doc.get("materials", []))
    for idx, mat in enumerate(materials):
        if mat.get("kind") != "file_version":
            continue
        fvid = UUID(str(mat["file_version_id"]))
        blob_id = UUID(f"0192f5c7-0000-7000-8000-{idx + 1:012x}")
        file_id = UUID(f"0192f5c8-0000-7000-8000-{idx + 1:012x}")
        digest = f"{idx + 1:064x}"
        conn.execute(
            "INSERT INTO skm_artifacts.blobs "
            "(id, workspace_id, hash_algorithm, content_digest, size_bytes, detected_media_type, "
            "availability, created_at, verified_at) "
            "VALUES (%s, %s, 'sha256', %s, 128, 'text/markdown', 'available', %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (blob_id, _WS_ID, digest, _T0, _T0),
        )
        conn.execute(
            "INSERT INTO skm_artifacts.files "
            "(id, workspace_id, project_id, title, origin, classification, current_version_id, "
            "state, row_version, created_at, created_by, updated_at) "
            "VALUES (%s, %s, %s, %s, 'upload', 'internal', %s, 'active', 1, %s, %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (file_id, _WS_ID, _PROJ_ID, f"doc-{fvid}.md", fvid, _T0, _ACTOR_ID, _T0),
        )
        conn.execute(
            "INSERT INTO skm_artifacts.file_versions "
            "(id, workspace_id, file_id, version_no, blob_id, original_filename, "
            "declared_media_type, description, source, safety, created_by, created_at) "
            "VALUES (%s, %s, %s, 1, %s, %s, 'text/markdown', '', '{}'::jsonb, '{}'::jsonb, %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (fvid, _WS_ID, file_id, blob_id, f"doc-{fvid}.md", _ACTOR_ID, _T0),
        )


@pytest.fixture
def pg_connection(request: pytest.FixtureRequest) -> Iterator[psycopg.Connection]:
    db = cast("TestDatabase", request.getfixturevalue("test_database"))
    with psycopg.connect(db.dsn) as conn:
        _seed_pg_workspace(conn)
        yield conn
        conn.rollback()


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def harness(request: pytest.FixtureRequest) -> _Harness:
    if request.param == "memory":
        state = MemoryBackendState()
        return _Harness(
            backend="memory",
            counters=MemoryPlanCounters(state),
            plans=MemoryPlanRepository(state),
            drafts=MemoryDraftRepository(state),
            revisions=MemoryRevisionRepository(state),
            queries=MemoryPlanningQueries(state),
        )
    conn = cast("psycopg.Connection", request.getfixturevalue("pg_connection"))
    return _Harness(
        backend="postgres",
        counters=PostgresPlanCounters(conn),
        plans=PostgresPlanRepository(conn),
        drafts=PostgresDraftRepository(conn),
        revisions=PostgresRevisionRepository(conn),
        queries=PostgresPlanningQueries(conn),
        conn=conn,
    )


class _SeqIds:
    def __init__(self) -> None:
        self._seq = 0

    def new_id(self) -> UUID:
        self._seq += 1
        return UUID(f"0192f5d0-0000-7000-8000-{self._seq:012x}")


def _build_revision_record(
    plan: Plan,
    raw_doc: SpecificationDoc,
    *,
    rev_id: RevisionId,
    known_identities: dict[EntityId, EntityKind] | None = None,
    plan_relation_targets: tuple[PlanId | None, ...] | None = None,
) -> RevisionRecord:
    with_ids, _ = assign_missing_ids(raw_doc, _SeqIds())
    norm_doc = normalize_document(with_ids)
    spec, findings = from_document(norm_doc)
    assert not findings, findings
    digest = specification_digest(norm_doc)
    meta = new_revision_meta(
        rev_id,
        plan,
        content_digest=digest,
        origin=RevisionOrigin.DRAFT,
        restored_from=None,
        change_reason="Publish specification",
        actor=_ACTOR_ID,
        now=_T1,
    )
    known = known_identities or {}
    collected = {EntityId(UUID(str(ent["id"]))): kind for kind, _, ent in iter_entities(norm_doc)}
    new_ids = tuple((eid, kind) for eid, kind in collected.items() if eid not in known)
    pins = tuple(
        MaterialPin(
            material_id=mat.id,
            file_version_id=UUID(str(mat.file_version_id)),
            role=mat.role,
            selector=mat.selector,
        )
        for mat in spec.materials
        if mat.file_version_id is not None
    )
    targets = (
        plan_relation_targets
        if plan_relation_targets is not None
        else tuple(None for _ in spec.plan_relations)
    )
    return RevisionRecord(
        meta=meta,
        spec=spec,
        document=to_document(spec),
        new_identities=new_ids,
        pins=pins,
        plan_relation_targets=targets,
    )


def test_repositories_mapping_registers_planning_queries() -> None:
    assert MEMORY_REPOSITORIES[PlanningQueries] is MemoryPlanningQueries
    assert POSTGRES_REPOSITORIES[PlanningQueries] is PostgresPlanningQueries


def test_counters_and_plan_repository_parity(harness: _Harness) -> None:
    assert harness.counters.allocate_plan_no(_WS_ID, _PROJ_ID) == 1
    assert harness.counters.allocate_plan_no(_WS_ID, _PROJ_ID) == 2
    assert harness.counters.allocate_plan_no(_WS_ID, _PROJ2_ID) == 1

    p1_id = PlanId(UUID("0192f5c4-0000-7000-8000-000000000001"))
    with pytest.raises(NotFound) as missing_plan:
        harness.plans.get(p1_id)
    assert missing_plan.value.details == {"kind": "plan", "ref": str(p1_id)}

    p1 = new_plan(p1_id, _PROJ_REF, "PLAN1", "First plan", _ACTOR_ID, _T0)
    harness.add_plan(p1)

    assert harness.plans.get(p1_id) == p1
    assert harness.plans.lock(p1_id) == p1
    assert harness.plans.lock_shared(p1_id) == p1
    assert harness.plans.find_by_alias(_PROJ_ID, "PLAN1") == p1
    assert harness.plans.find_by_alias(_PROJ_ID, "UNKNOWN") is None

    with pytest.raises(Conflict) as dup_plan:
        harness.plans.add(p1)
    assert dup_plan.value.code is ErrorCode.ALREADY_EXISTS
    assert dup_plan.value.details == {"kind": "plan", "ref": str(p1_id)}

    p_dup_alias = new_plan(
        PlanId(UUID("0192f5c4-0000-7000-8000-000000000009")),
        _PROJ_REF,
        "PLAN1",
        "Duplicate alias",
        _ACTOR_ID,
        _T0,
    )
    with pytest.raises(Conflict) as dup_alias:
        harness.add_plan(p_dup_alias)
    assert dup_alias.value.code is ErrorCode.ALREADY_EXISTS
    assert dup_alias.value.details == {"kind": "alias", "alias": "PLAN1"}

    harness.plans.add_alias(p1_id, "legacy-auth", AliasKind.LEGACY)
    assert harness.plans.find_by_alias(_PROJ_ID, "legacy-auth") == p1
    with pytest.raises(InternalError):
        harness.plans.add_alias(p1_id, "PLAN99", AliasKind.SHORT)

    refs = harness.plans.project_plan_refs(_PROJ_ID)
    assert refs["PLAN1"] == p1_id
    assert refs["legacy-auth"] == p1_id
    assert refs[f"plan:{p1_id}"] == p1_id

    assert harness.plans.find_by_id_prefix(_PROJ_ID, "0192f5c4-0000-7000-8000-00000000000", limit=5) == (p1,)

    sys_id = PlanId(UUID("0192f5c4-0000-7000-8000-000000000002"))
    sys_plan = new_plan(
        sys_id,
        _PROJ_REF,
        "review-requests",
        "Review requests",
        _ACTOR_ID,
        _T0,
        purpose=PlanPurpose.REVIEW_REQUESTS,
    )
    assert harness.plans.find_review_requests_plan(_PROJ_ID) is None
    harness.add_plan(sys_plan)
    assert harness.plans.find_review_requests_plan(_PROJ_ID) == sys_plan

    with pytest.raises(Conflict) as dup_sys:
        harness.add_plan(replace(sys_plan, id=PlanId(UUID("0192f5c4-0000-7000-8000-000000000003"))))
    assert dup_sys.value.code is ErrorCode.ALREADY_EXISTS
    assert dup_sys.value.details == {"kind": "plan", "alias": "review-requests"}

    with pytest.raises(Conflict) as ver_err:
        harness.plans.save(archive(p1, _T1), expected_version=99)
    assert ver_err.value.code is ErrorCode.VERSION_CONFLICT

    with pytest.raises(ValidationFailed) as owned_err:
        harness.plans.save(replace(p1, alias="PLAN2", row_version=2), expected_version=1)
    assert owned_err.value.code is ErrorCode.FIELD_OWNED

    archived = archive(p1, _T1)
    harness.plans.save(archived, expected_version=1)
    assert harness.plans.get(p1_id) == archived


def test_draft_repository_parity(harness: _Harness) -> None:
    plan_id = PlanId(UUID("0192f5c4-0000-7000-8000-000000000010"))
    plan = new_plan(plan_id, _PROJ_REF, "PLAN10", "Draft test", _ACTOR_ID, _T0)
    harness.add_plan(plan)

    minimal_doc = cast(
        "SpecificationDoc", json.loads((ROOT / "tests/fixtures/planning/valid/minimal.json").read_text())
    )
    d1_id = DraftId(UUID("0192f5c5-0000-7000-8000-000000000001"))
    with pytest.raises(NotFound) as missing_draft:
        harness.drafts.get(d1_id)
    assert missing_draft.value.details == {"kind": "draft", "ref": str(d1_id)}

    d1 = open_draft(d1_id, plan, None, minimal_doc, _ACTOR_ID, _T0)
    harness.drafts.add(d1)

    with pytest.raises(Conflict) as dup_draft:
        harness.drafts.add(d1)
    assert dup_draft.value.details == {"kind": "draft", "ref": str(d1_id)}

    loaded = harness.drafts.get(d1_id)
    assert loaded == d1
    loaded.document["title"] = "Mutated caller copy"
    assert harness.drafts.get(d1_id).document["title"] == "Fixture plan"

    assert harness.drafts.count_open(plan_id) == 1
    assert harness.drafts.lock_open_for_plan(plan_id) == (d1,)
    assert harness.drafts.list_for_plan(plan_id, state=DraftState.OPEN) == (d1,)

    edited_doc = {**minimal_doc, "title": "Updated title"}
    d1_v2 = save_draft_domain(d1, edited_doc, 1, _ACTOR_ID, _T1)
    with pytest.raises(Conflict) as ver_err:
        harness.drafts.save(d1_v2, expected_edit_version=9)
    assert ver_err.value.code is ErrorCode.VERSION_CONFLICT

    with pytest.raises(ValidationFailed) as schema_err:
        harness.drafts.save(
            replace(d1_v2, document={**edited_doc, "schema": "urn:other"}),
            expected_edit_version=1,
        )
    assert schema_err.value.code is ErrorCode.FIELD_OWNED

    harness.drafts.save(d1_v2, expected_edit_version=1)
    assert harness.drafts.get(d1_id) == d1_v2

    d1_closed = abandon(d1_v2, 2, _T2)
    harness.drafts.save(d1_closed, expected_edit_version=2)
    assert harness.drafts.count_open(plan_id) == 0
    assert harness.drafts.list_for_plan(plan_id, state=DraftState.ABANDONED) == (d1_closed,)

    with pytest.raises(PreconditionFailed) as closed_err:
        harness.drafts.save(d1_v2, expected_edit_version=999)
    assert closed_err.value.code is ErrorCode.DRAFT_NOT_OPEN


@pytest.mark.parametrize("fixture_path", VALID_FIXTURES, ids=lambda p: p.stem)
def test_revision_round_trip_valid_corpus_and_work_policy(harness: _Harness, fixture_path: Path) -> None:
    raw_doc = cast("SpecificationDoc", json.loads(fixture_path.read_text()))
    if harness.conn is not None:
        _seed_pg_file_versions(harness.conn, raw_doc)

    plan_id = PlanId(uuid4())
    plan = new_plan(plan_id, _PROJ_REF, f"PLAN{uuid4().int % 9000 + 100}", "Corpus plan", _ACTOR_ID, _T0)
    harness.add_plan(plan)

    rev_id = RevisionId(uuid4())
    record = _build_revision_record(plan, raw_doc, rev_id=rev_id)
    harness.revisions.add(record)

    assert harness.revisions.get_meta(rev_id) == record.meta
    assert harness.revisions.find_by_number(plan_id, 1) == record.meta
    assert harness.revisions.list_for_plan(plan_id, before_revision_no=None, limit=10) == (record.meta,)

    payload_doc = harness.revisions.get_document(rev_id)
    typed_doc = harness.revisions.load_typed_document(rev_id)

    assert typed_doc == payload_doc == record.document
    assert specification_digest(typed_doc) == record.meta.content_digest


def test_external_source_selector_and_local_criterion_checks_round_trip(harness: _Harness) -> None:
    raw_doc = cast("SpecificationDoc", json.loads(AUTH_REFRESH_PATH.read_text()))
    materials = cast("list[dict[str, object]]", raw_doc["materials"])
    ext_mat = next(m for m in materials if m["kind"] == "external_source")
    ext_mat["selector"] = {"kind": "markdown_heading", "value": "Refresh Token Rotation"}
    materials[0]["applies_to"] = ["P1.2", "P1.1"]

    requirements = cast("list[dict[str, object]]", raw_doc["requirements"])
    requirements[0]["owners"] = ["P1.2", "P1.1"]

    items = cast("list[dict[str, object]]", raw_doc["items"])
    items[1]["implements"] = ["R2", "R1"]
    items[4]["depends_on"] = ["P2.2", "P2.1"]

    units = cast("list[dict[str, object]]", raw_doc["units"])
    units[0]["checks"] = ["V2", "V1"]
    units[0]["implements"] = ["R2", "R1"]

    decisions = cast("list[dict[str, object]]", raw_doc["decisions"])
    decisions[0]["applies_to"] = ["P1.2", "P1.1"]

    criteria = cast("list[dict[str, object]]", raw_doc["criteria"])
    criteria[0]["checks"] = ["V1"]
    criteria[0]["requirements"] = ["R2", "R1"]

    if harness.conn is not None:
        _seed_pg_file_versions(harness.conn, raw_doc)

    plan_id = PlanId(uuid4())
    plan = new_plan(plan_id, _PROJ_REF, "PLAN77", "Selector and local check ref", _ACTOR_ID, _T0)
    harness.add_plan(plan)

    rev_id = RevisionId(uuid4())
    record = _build_revision_record(plan, raw_doc, rev_id=rev_id)
    harness.revisions.add(record)

    typed_doc = harness.revisions.load_typed_document(rev_id)
    payload_doc = harness.revisions.get_document(rev_id)

    typed_crits = cast("list[dict[str, object]]", typed_doc["criteria"])
    assert typed_crits[0]["checks"] == ["V1"]
    assert typed_crits[0]["requirements"] == ["R2", "R1"]

    typed_reqs = cast("list[dict[str, object]]", typed_doc["requirements"])
    assert typed_reqs[0]["owners"] == ["P1.2", "P1.1"]

    typed_items = cast("list[dict[str, object]]", typed_doc["items"])
    assert typed_items[1]["implements"] == ["R2", "R1"]
    assert typed_items[4]["depends_on"] == ["P2.2", "P2.1"]

    typed_units = cast("list[dict[str, object]]", typed_doc["units"])
    assert typed_units[0]["checks"] == ["V2", "V1"]
    assert typed_units[0]["implements"] == ["R2", "R1"]

    typed_decs = cast("list[dict[str, object]]", typed_doc["decisions"])
    assert typed_decs[0]["applies_to"] == ["P1.2", "P1.1"]

    typed_mats = cast("list[dict[str, object]]", typed_doc["materials"])
    assert typed_mats[0]["applies_to"] == ["P1.2", "P1.1"]
    typed_ext = next(m for m in typed_mats if m["kind"] == "external_source")
    assert typed_ext["selector"] == {"kind": "markdown_heading", "value": "Refresh Token Rotation"}
    assert typed_doc == payload_doc == record.document
    assert specification_digest(typed_doc) == record.meta.content_digest


@pytest.mark.pg
def test_missing_material_pin_rejected_on_commit(request: pytest.FixtureRequest) -> None:
    db = cast("TestDatabase", request.getfixturevalue("test_database"))
    auth_doc = cast("SpecificationDoc", json.loads(AUTH_REFRESH_PATH.read_text()))
    plan_id = PlanId(UUID("0192f5c4-0000-7000-8000-0000000000e1"))
    plan = new_plan(plan_id, _PROJ_REF, "PLAN88", "Missing pin test", _ACTOR_ID, _T0)
    rev_id = RevisionId(UUID("0192f5c6-0000-7000-8000-0000000000e1"))
    rec = replace(_build_revision_record(plan, auth_doc, rev_id=rev_id), pins=())

    with psycopg.connect(db.dsn) as conn:
        _seed_pg_workspace(conn)
        _seed_pg_file_versions(conn, auth_doc)
        PostgresScopeRegistry(conn).create(
            ScopeId(plan.id), ScopeKind.PLAN, parent=ScopeId(_PROJ_ID), workspace_id=_WS_ID
        )
        PostgresPlanRepository(conn).add(plan)
        PostgresRevisionRepository(conn).add(rec)
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.commit()
        conn.rollback()


@pytest.mark.pg
def test_work_policy_sql_null_vs_empty_object_and_typed_reader_source_of_truth(
    pg_connection: psycopg.Connection,
) -> None:
    scopes = PostgresScopeRegistry(pg_connection)
    plans = PostgresPlanRepository(pg_connection)
    revisions = PostgresRevisionRepository(pg_connection)

    p1_id = PlanId(UUID("0192f5c4-0000-7000-8000-00000000000a"))
    p1 = new_plan(p1_id, _PROJ_REF, "PLAN3", "Predecessor plan", _ACTOR_ID, _T0)
    scopes.create(ScopeId(p1.id), ScopeKind.PLAN, parent=ScopeId(_PROJ_ID), workspace_id=_WS_ID)
    plans.add(p1)

    p2_id = PlanId(UUID("0192f5c4-0000-7000-8000-000000000020"))
    p2 = new_plan(p2_id, _PROJ_REF, "PLAN4", "Auth Refresh Plan", _ACTOR_ID, _T0)
    scopes.create(ScopeId(p2.id), ScopeKind.PLAN, parent=ScopeId(_PROJ_ID), workspace_id=_WS_ID)
    plans.add(p2)

    auth_doc = cast("SpecificationDoc", json.loads(AUTH_REFRESH_PATH.read_text()))
    _seed_pg_file_versions(pg_connection, auth_doc)

    rev1_id = RevisionId(UUID("0192f5c6-0000-7000-8000-000000000001"))
    rec1 = _build_revision_record(
        p2,
        auth_doc,
        rev_id=rev1_id,
        plan_relation_targets=(p1_id, None),
    )
    revisions.add(rec1)
    p2_pub = record_publication(p2, rev1_id, rec1.spec.title, _T1)
    plans.save(p2_pub, expected_version=1)

    assert plans.superseded_by(p1_id) == ()
    assert revisions.load_typed_document(rev1_id) == revisions.get_document(rev1_id)
    assert specification_digest(revisions.load_typed_document(rev1_id)) == rec1.meta.content_digest

    rev2_id = RevisionId(UUID("0192f5c6-0000-7000-8000-000000000011"))
    rec2 = _build_revision_record(
        p2_pub,
        {**rec1.document, "title": "Refresh token rotation v2"},
        rev_id=rev2_id,
        known_identities=dict(revisions.identities(p2_id)),
        plan_relation_targets=(p1_id, None),
    )
    revisions.add(rec2)
    first_revs = {
        row[0]
        for row in pg_connection.execute(
            "SELECT first_revision_id FROM skm_planning.plan_entity_identities WHERE plan_id = %s",
            (p2_id,),
        ).fetchall()
    }
    assert first_revs == {UUID(str(rev1_id))}

    wp_rows = pg_connection.execute(
        "SELECT m.display_key, i.work_policy FROM skm_planning.item_specs i "
        "JOIN skm_planning.revision_members m "
        "ON m.revision_id = i.revision_id AND m.entity_id = i.item_id "
        "WHERE i.revision_id = %s ORDER BY i.position",
        (rev1_id,),
    ).fetchall()
    assert dict(wp_rows)["P1.1"] is None

    empty_wp_doc = cast(
        "SpecificationDoc",
        json.loads((ROOT / "tests/fixtures/planning/valid/work-policy-empty.json").read_text()),
    )
    p3_id = PlanId(UUID("0192f5c4-0000-7000-8000-000000000030"))
    p3 = new_plan(p3_id, _PROJ_REF, "PLAN5", "Work Policy Empty", _ACTOR_ID, _T2)
    scopes.create(ScopeId(p3.id), ScopeKind.PLAN, parent=ScopeId(_PROJ_ID), workspace_id=_WS_ID)
    plans.add(p3)
    rev_wp_id = RevisionId(UUID("0192f5c6-0000-7000-8000-000000000002"))
    rec_wp = _build_revision_record(p3, empty_wp_doc, rev_id=rev_wp_id)
    revisions.add(rec_wp)

    item_wp_rows = dict(
        pg_connection.execute(
            "SELECT m.display_key, i.work_policy FROM skm_planning.item_specs i "
            "JOIN skm_planning.revision_members m "
            "ON m.revision_id = i.revision_id AND m.entity_id = i.item_id "
            "WHERE i.revision_id = %s",
            (rev_wp_id,),
        ).fetchall()
    )
    assert item_wp_rows["P1.1"] == {}
    assert item_wp_rows["P1.2"] == {"role_intensity": {}}
    unit_wp_row = pg_connection.execute(
        "SELECT work_policy FROM skm_planning.unit_specs WHERE revision_id = %s",
        (rev_wp_id,),
    ).fetchone()
    assert unit_wp_row is not None
    assert unit_wp_row[0] == {}
    assert revisions.load_typed_document(rev_wp_id) == rec_wp.document

    pg_connection.execute(
        "ALTER TABLE skm_planning.revision_specs DISABLE TRIGGER tg_revision_specs__immutable"
    )
    pg_connection.execute(
        "UPDATE skm_planning.revision_specs SET title = 'Relational Table Title' WHERE revision_id = %s",
        (rev_wp_id,),
    )
    pg_connection.execute(
        "ALTER TABLE skm_planning.revision_specs ENABLE TRIGGER tg_revision_specs__immutable"
    )
    assert revisions.get_document(rev_wp_id)["title"] == "Fixture plan"
    assert revisions.load_typed_document(rev_wp_id)["title"] == "Relational Table Title"


def test_planning_queries_and_identity_conflict_guards(harness: _Harness) -> None:
    p1_id = PlanId(UUID("0192f5c4-0000-7000-8000-00000000000a"))
    p1 = new_plan(p1_id, _PROJ_REF, "PLAN3", "Predecessor plan", _ACTOR_ID, _T0)
    harness.add_plan(p1)

    p2_id = PlanId(UUID("0192f5c4-0000-7000-8000-000000000020"))
    p2 = new_plan(p2_id, _PROJ_REF, "PLAN4", "Auth Refresh Plan", _ACTOR_ID, _T0)
    harness.add_plan(p2)

    auth_doc = cast("SpecificationDoc", json.loads(AUTH_REFRESH_PATH.read_text()))
    auth_doc["plan_relations"] = [
        {"kind": "supersedes", "target": "PLAN3", "note": "Replaces legacy plan by alias."},
        {"kind": "supersedes", "target": f"plan:{p1_id}", "note": "Duplicate supersedes target by UUID."},
    ]
    if harness.conn is not None:
        _seed_pg_file_versions(harness.conn, auth_doc)

    rev1_id = RevisionId(UUID("0192f5c6-0000-7000-8000-000000000001"))
    rec1 = _build_revision_record(p2, auth_doc, rev_id=rev1_id, plan_relation_targets=(p1_id, p1_id))
    harness.revisions.add(rec1)
    harness.plans.save(record_publication(p2, rev1_id, rec1.spec.title, _T1), expected_version=1)
    assert harness.plans.superseded_by(p1_id) == (p2_id,)

    bad_rec = replace(rec1, meta=replace(rec1.meta, id=RevisionId(uuid4()), plan_id=p1_id))
    with pytest.raises(Conflict) as id_conflict:
        harness.revisions.add(bad_rec)
    assert id_conflict.value.code is ErrorCode.ID_CONFLICT

    if harness.conn is not None:
        p2_item_id = rec1.spec.items[0].id
        kind_changed_doc = deepcopy_doc(rec1.document)
        cast("list[dict[str, object]]", kind_changed_doc["phases"])[0]["id"] = str(p2_item_id)
        cast("list[dict[str, object]]", kind_changed_doc["items"])[0]["id"] = str(uuid4())
        spec_bad, _ = from_document(kind_changed_doc)
        meta2 = new_revision_meta(
            RevisionId(uuid4()),
            record_publication(p2, rev1_id, "AR", _T2),
            content_digest=specification_digest(kind_changed_doc),
            origin=RevisionOrigin.DRAFT,
            restored_from=None,
            change_reason="Second",
            actor=_ACTOR_ID,
            now=_T2,
        )
        bad_kind_rec = RevisionRecord(
            meta=meta2,
            spec=spec_bad,
            document=kind_changed_doc,
            new_identities=(),
            pins=(),
            plan_relation_targets=(),
        )
        with pytest.raises(ValidationFailed) as kind_err:
            harness.revisions.add(bad_kind_rec)
        assert kind_err.value.code is ErrorCode.SCHEMA_INVALID

    sys_plan = new_plan(
        PlanId(uuid4()),
        _PROJ_REF,
        "review-requests",
        "System RR",
        _ACTOR_ID,
        _T2,
        purpose=PlanPurpose.REVIEW_REQUESTS,
    )
    harness.add_plan(sys_plan)

    page1 = harness.queries.list_plans(_PROJ_ID, state="active", cursor=None, limit=1)
    assert len(page1.items) == 1
    assert all(item["purpose"] == "standard" for item in page1.items)
    assert page1.next is not None
    page2 = harness.queries.list_plans(_PROJ_ID, state="active", cursor=Cursor(str(page1.next)), limit=2)
    assert len(page2.items) == 1

    with pytest.raises(ValidationFailed) as bad_cur:
        harness.queries.list_plans(_PROJ_ID, state="archived", cursor=Cursor(str(page1.next)), limit=2)
    assert bad_cur.value.code is ErrorCode.SCHEMA_INVALID

    summary = harness.queries.plan_summary(p2_id)
    assert summary["plan_id"] == str(p2_id)
    assert summary["current_revision_id"] == str(rev1_id)
    assert summary["current_revision_no"] == 1
    assert summary["open_drafts"] == 0

    member = harness.queries.find_member(rev1_id, "P1.2")
    assert member is not None
    assert harness.queries.find_member_by_id(rev1_id, member.entity_id) == member

    links = harness.queries.entity_links(rev1_id, member.entity_id)
    assert [m.display_key for m in links.prerequisites] == ["P1.1"]
    assert [m.display_key for m in links.criteria] == ["AC1"]
    assert [m.display_key for m in links.checks] == ["P1.2:V1"]
    assert [m.display_key for m in links.decisions] == ["D1"]
    assert [m.display_key for m in links.requirements] == ["R1"]

    m23 = harness.queries.find_member(rev1_id, "P2.3")
    assert m23 is not None
    links23 = harness.queries.entity_links(rev1_id, m23.entity_id)
    assert [m.display_key for m in links23.prerequisites] == ["P2.1", "P2.2"]
    assert [m.display_key for m in links23.materials] == ["material/oauth-threats"]


@pytest.mark.pg
def test_find_review_requests_plan_locks_row_for_update_and_add_requires_scope(
    request: pytest.FixtureRequest,
) -> None:
    db = cast("TestDatabase", request.getfixturevalue("test_database"))
    unscoped_plan = new_plan(
        PlanId(uuid4()),
        _PROJ_REF,
        "PLAN99",
        "Missing scope",
        _ACTOR_ID,
        _T0,
    )
    with psycopg.connect(db.dsn) as conn:
        _seed_pg_workspace(conn)
        with pytest.raises(ValidationFailed) as fk_err:
            PostgresPlanRepository(conn).add(unscoped_plan)
        assert fk_err.value.code is ErrorCode.INVALID_REFERENCE
        conn.rollback()

    sys_id = PlanId(UUID("0192f5c4-0000-7000-8000-0000000000f1"))
    sys_plan = new_plan(
        sys_id,
        _PROJ2_REF,
        "review-requests",
        "Locked RR",
        _ACTOR_ID,
        _T0,
        purpose=PlanPurpose.REVIEW_REQUESTS,
    )
    with psycopg.connect(db.dsn) as conn1, psycopg.connect(db.dsn) as conn2:
        try:
            _seed_pg_workspace(conn1)
            PostgresScopeRegistry(conn1).create(
                ScopeId(sys_id),
                ScopeKind.PLAN,
                parent=ScopeId(_PROJ2_ID),
                workspace_id=_WS_ID,
            )
            PostgresPlanRepository(conn1).add(sys_plan)
            conn1.commit()

            found = PostgresPlanRepository(conn1).find_review_requests_plan(_PROJ2_ID)
            assert found == sys_plan
            with pytest.raises(psycopg.errors.LockNotAvailable):
                conn2.execute("SELECT id FROM skm_planning.plans WHERE id = %s FOR UPDATE NOWAIT", (sys_id,))
            conn2.rollback()
            conn1.rollback()
        finally:
            conn1.rollback()
            conn1.execute("DELETE FROM skm_planning.plan_aliases WHERE plan_id = %s", (sys_id,))
            conn1.execute("DELETE FROM skm_planning.plans WHERE id = %s", (sys_id,))
            conn1.execute("DELETE FROM skm_core.scopes WHERE id = %s", (sys_id,))
            conn1.commit()


def deepcopy_doc(doc: SpecificationDoc) -> SpecificationDoc:
    return cast("SpecificationDoc", json.loads(json.dumps(doc)))


def test_memory_working_copy_shares_planning_rows_but_never_the_tables() -> None:
    tables = planning_state(MemoryBackendState())
    row = cast("Plan", object())  # rows are immutable values: sharing one is observable only by identity
    tables.plans[PlanId(uuid4())] = row
    working = deepcopy(tables)
    assert working.plans is not tables.plans
    assert working.revisions is not tables.revisions
    assert next(iter(working.plans.values())) is row
