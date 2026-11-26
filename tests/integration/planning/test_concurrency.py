"""PostgreSQL concurrency and race tests for ``planning`` publication and drafts (planning §7.10, §15)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import psycopg
import pytest

from contracts.planning.test_publish_revision_parity import _compute_expected_digest
from integration.artifacts.test_upload_flow import (
    NOW,
    OWNER_ID,
    Harness,
    clean_test_database,
    dispatch_new,
    open_test_app,
    pg_session,
    seed_principals,
    test_database,
)
from integration.planning.publication import (
    two_file_materials,
    upload_next_version,
    upload_v1,
)
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed, SkmError
from skm.kernel.ids import FileVersionId, PlanId, ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import Role
from skm.modules.planning.domain.draft import DraftId, DraftState
from skm.modules.planning.domain.events import PlanRevisionPublished
from skm.modules.planning.domain.specification import SPECIFICATION_URN
from skm.modules.planning.generated.commands import CreatePlan, OpenDraft, PublishRevision, SaveDraft
from skm.modules.planning.generated.results import (
    CreatePlanResult,
    OpenDraftResult,
    PublishRevisionResult,
    SaveDraftResult,
)
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from support.pg import TestDatabase
from support.seed import SEED

__all__ = ["clean_test_database", "pg_session", "test_database"]

pytestmark = pytest.mark.pg

WAIT_SECONDS: Final = 5.0
PHASE_ID = "01900000-0000-7000-8000-000000000101"
ITEM_ID = "01900000-0000-7000-8000-000000000102"


@pytest.fixture
def pg_h(clean_test_database: TestDatabase, tmp_path: Path) -> Iterator[Harness]:
    app, clock, blobs_root = open_test_app("postgres", tmp_path, clean_test_database.dsn, max_uow=6)
    try:
        actor = seed_principals(
            app,
            "postgres",
            people=((OWNER_ID, PrincipalKind.HUMAN, "owner"),),
            roles=((SEED.instance_id, OWNER_ID, Role.OWNER),),
        )
        client = app.client(actor=actor, surface=Surface.CLI)
        ws = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        yield Harness(app, clock, actor, client, ws, proj, blobs_root, clean_test_database.dsn)
    finally:
        app.close()


def _build_spec_doc(
    *,
    title: str = "Spec v1",
    summary: str = "Implement handler",
    fv_1_id: FileVersionId,
    fv_2_id: FileVersionId,
) -> JsonObject:
    materials = two_file_materials(fv_1_id, fv_2_id)
    return {
        "schema": SPECIFICATION_URN,
        "title": title,
        "goal": "Deliver concurrency-safe revision publication",
        "materials": materials,
        "phases": [
            {
                "id": PHASE_ID,
                "key": "P1",
                "title": "Phase 1",
                "goal": "Build feature",
                "design_state": "skeleton",
            }
        ],
        "items": [
            {
                "id": ITEM_ID,
                "key": "P1.1",
                "phase": "P1",
                "title": "Item 1",
                "summary": summary,
                "why": "Required by spec",
                "review": {"mode": "self", "reason": "focused test spec"},
            }
        ],
        "execution_constraints": {"strategy": "dag"},
    }


def _run_barrier_pair(fn_a: Callable[[], object], fn_b: Callable[[], object]) -> tuple[object, object]:
    """Run ``fn_a`` and ``fn_b`` concurrently after synchronizing at a 2-thread barrier."""
    barrier = threading.Barrier(2, timeout=WAIT_SECONDS)
    outcomes: list[object] = [None, None]

    def worker(idx: int, fn: Callable[[], object]) -> None:
        try:
            barrier.wait()
            outcomes[idx] = fn()
        except BaseException as exc:  # noqa: BLE001
            outcomes[idx] = exc

    t1 = threading.Thread(target=worker, args=(0, fn_a))
    t2 = threading.Thread(target=worker, args=(1, fn_b))
    t1.start()
    t2.start()
    t1.join(WAIT_SECONDS)
    t2.join(WAIT_SECONDS)
    assert not t1.is_alive()
    assert not t2.is_alive()
    return outcomes[0], outcomes[1]


def _wait_for_tuple_waiter(dsn: str) -> bool:
    """Wait until at least one PostgreSQL backend is blocked waiting on a row/transaction lock."""
    deadline = time.monotonic() + WAIT_SECONDS
    with psycopg.connect(dsn, autocommit=True) as conn:
        while time.monotonic() < deadline:
            row = conn.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            ).fetchone()
            if row is not None and int(row[0]) > 0:
                return True
            time.sleep(0.01)
    return False


def test_concurrency_two_publishes_one_base(pg_h: Harness) -> None:
    """Two drafts branched from Revision R(n) publish simultaneously: one creates R(n+1), one fails."""
    assert pg_h.dsn is not None
    _, fv_1 = upload_v1(pg_h, b"guideline-v1", filename="guide.txt")
    _, fv_2 = upload_v1(pg_h, b"reference-v1", filename="ref.txt")
    plan_id = PlanId(dispatch_new(pg_h.client, CreatePlan(project_id=pg_h.proj, title="Race Plan")).plan_id)

    # First publish R1 so we test branching from a concrete Revision R(1)
    d0_res = dispatch_new(pg_h.client, OpenDraft(plan_id=plan_id, base="empty"))
    d0_id = DraftId(d0_res.draft_id)
    doc_r1 = _build_spec_doc(title="Spec R1", summary="Base R1", fv_1_id=fv_1, fv_2_id=fv_2)
    s0_res = dispatch_new(pg_h.client, SaveDraft(plan_id, d0_id, d0_res.edit_version, merge_patch=doc_r1))
    digest_r1 = _compute_expected_digest(pg_h, d0_id, seq=700)
    r1: PublishRevisionResult = dispatch_new(
        pg_h.client,
        PublishRevision(plan_id, d0_id, s0_res.edit_version, digest_r1, reason="Publish R1"),
    )
    assert r1.revision_no == 1

    # Branch Draft A and Draft B from R(1)
    da_res = dispatch_new(pg_h.client, OpenDraft(plan_id=plan_id, base="current"))
    db_res = dispatch_new(pg_h.client, OpenDraft(plan_id=plan_id, base="current"))
    da_id, db_id = DraftId(da_res.draft_id), DraftId(db_res.draft_id)

    sa_res = dispatch_new(
        pg_h.client, SaveDraft(plan_id, da_id, da_res.edit_version, merge_patch={"title": "Spec A"})
    )
    sb_res = dispatch_new(
        pg_h.client, SaveDraft(plan_id, db_id, db_res.edit_version, merge_patch={"title": "Spec B"})
    )
    digest_a = _compute_expected_digest(pg_h, da_id, seq=701)
    digest_b = _compute_expected_digest(pg_h, db_id, seq=702)

    client_a = pg_h.app.client(actor=pg_h.owner, surface=Surface.CLI)
    client_b = pg_h.app.client(actor=pg_h.owner, surface=Surface.CLI)

    out_a, out_b = _run_barrier_pair(
        lambda: client_a.dispatch(
            PublishRevision(plan_id, da_id, sa_res.edit_version, digest_a, reason="Concurrent publish A"),
            idempotency_key=client_a.new_idempotency_key(),
        ),
        lambda: client_b.dispatch(
            PublishRevision(plan_id, db_id, sb_res.edit_version, digest_b, reason="Concurrent publish B"),
            idempotency_key=client_b.new_idempotency_key(),
        ),
    )

    successes = [x for x in (out_a, out_b) if isinstance(x, PublishRevisionResult)]
    failures = [x for x in (out_a, out_b) if isinstance(x, SkmError)]
    assert len(successes) == 1, f"Expected 1 winner, got: {(out_a, out_b)}"
    assert len(failures) == 1, f"Expected 1 loser, got: {(out_a, out_b)}"

    winner, loser = successes[0], failures[0]
    assert winner.revision_no == 2
    assert winner.parent_revision_id == r1.revision_id
    assert isinstance(loser, Conflict)
    assert loser.code is ErrorCode.BASE_REVISION_CHANGED
    assert loser.details == {
        "base_revision_id": str(r1.revision_id),
        "current_revision_id": str(winner.revision_id),
    }

    with psycopg.connect(pg_h.dsn, autocommit=True) as conn:
        revs_sql = (
            "SELECT revision_no FROM skm_planning.plan_revisions WHERE plan_id = %s ORDER BY revision_no"
        )
        assert [r[0] for r in conn.execute(revs_sql, (plan_id,)).fetchall()] == [1, 2]
        plan_sql = (
            "SELECT current_revision_id, next_revision_no, row_version FROM skm_planning.plans WHERE id = %s"
        )
        assert conn.execute(plan_sql, (plan_id,)).fetchone() == (UUID(str(winner.revision_id)), 3, 3)
        ev_sql = "SELECT count(*) FROM skm_core.domain_events WHERE workspace_id = %s AND event_type = %s"
        assert conn.execute(ev_sql, (pg_h.ws, PlanRevisionPublished.event_type)).fetchone() == (2,)
        loser_draft_id = db_id if winner.content_digest == digest_a else da_id
        draft_sql = (
            "SELECT state, edit_version, published_revision_id, closed_at "
            "FROM skm_planning.plan_drafts WHERE id = %s"
        )
        assert conn.execute(draft_sql, (loser_draft_id,)).fetchone() == ("open", 2, None, None)


def _assert_save_blocks_publish_with_version_conflict(
    pg_h: Harness, *, plan_id: PlanId, fv_1: FileVersionId, fv_2: FileVersionId
) -> None:
    from skm.adapters.postgres.planning.drafts import PostgresDraftRepository

    assert pg_h.dsn is not None
    draft_2_res = dispatch_new(pg_h.client, OpenDraft(plan_id=plan_id, base="empty"))
    draft_2_id = DraftId(draft_2_res.draft_id)
    doc_2 = _build_spec_doc(title="Draft 2", fv_1_id=fv_1, fv_2_id=fv_2)
    save_2_init = dispatch_new(
        pg_h.client, SaveDraft(plan_id, draft_2_id, draft_2_res.edit_version, merge_patch=doc_2)
    )
    ver_2 = int(save_2_init.edit_version)
    digest_2 = _compute_expected_digest(pg_h, draft_2_id, seq=721)

    entered_save, release_save = threading.Event(), threading.Event()
    orig_pg_save = PostgresDraftRepository.save

    def _hooked_save(self: PostgresDraftRepository, draft: Any, *, expected_edit_version: int) -> None:
        orig_pg_save(self, draft, expected_edit_version=expected_edit_version)
        if draft.id == draft_2_id and draft.state is DraftState.OPEN and not entered_save.is_set():
            entered_save.set()
            release_save.wait(WAIT_SECONDS)

    client_save = pg_h.app.client(actor=pg_h.owner, surface=Surface.CLI)
    client_pub = pg_h.app.client(actor=pg_h.owner, surface=Surface.CLI)
    PostgresDraftRepository.save = _hooked_save
    pub_outcome: list[object] = []
    save_outcome: list[object] = []
    try:

        def _run_pub() -> None:
            assert entered_save.wait(WAIT_SECONDS)
            try:
                pub_cmd = PublishRevision(plan_id, draft_2_id, ver_2, digest_2, reason="Blocked behind save")
                pub_outcome.append(dispatch_new(client_pub, pub_cmd))
            except BaseException as exc:  # noqa: BLE001
                pub_outcome.append(exc)

        save_cmd = SaveDraft(plan_id, draft_2_id, ver_2, merge_patch={"title": "Updated while publish waits"})
        t_save = threading.Thread(target=lambda: save_outcome.append(dispatch_new(client_save, save_cmd)))
        t_pub = threading.Thread(target=_run_pub)
        t_save.start()
        t_pub.start()
        assert entered_save.wait(WAIT_SECONDS)
        assert _wait_for_tuple_waiter(pg_h.dsn)
        release_save.set()
        t_save.join(WAIT_SECONDS)
        t_pub.join(WAIT_SECONDS)
    finally:
        release_save.set()
        PostgresDraftRepository.save = orig_pg_save

    assert len(save_outcome) == 1
    assert isinstance(save_outcome[0], SaveDraftResult)
    assert save_outcome[0].edit_version == ver_2 + 1
    assert len(pub_outcome) == 1
    assert isinstance(pub_outcome[0], Conflict)
    assert pub_outcome[0].code is ErrorCode.VERSION_CONFLICT
    assert pub_outcome[0].details == {"expected": ver_2, "actual": ver_2 + 1}


def test_concurrency_save_and_publish_same_draft(pg_h: Harness) -> None:
    """Concurrent ``save_draft`` and ``publish_revision`` on the same draft serialize via FOR UPDATE."""
    assert pg_h.dsn is not None
    _, fv_1 = upload_v1(pg_h, b"guideline-v1", filename="guide.txt")
    _, fv_2 = upload_v1(pg_h, b"reference-v1", filename="ref.txt")
    doc = _build_spec_doc(fv_1_id=fv_1, fv_2_id=fv_2)

    plan_id = PlanId(dispatch_new(pg_h.client, CreatePlan(project_id=pg_h.proj, title="Save vs Pub")).plan_id)
    draft_res = dispatch_new(pg_h.client, OpenDraft(plan_id=plan_id, base="empty"))
    draft_id = DraftId(draft_res.draft_id)
    save_1 = dispatch_new(pg_h.client, SaveDraft(plan_id, draft_id, draft_res.edit_version, merge_patch=doc))
    ver_before = int(save_1.edit_version)
    digest_before = _compute_expected_digest(pg_h, draft_id, seq=720)

    client_save = pg_h.app.client(actor=pg_h.owner, surface=Surface.CLI)
    client_pub = pg_h.app.client(actor=pg_h.owner, surface=Surface.CLI)

    out_save, out_pub = _run_barrier_pair(
        lambda: client_save.dispatch(
            SaveDraft(plan_id, draft_id, ver_before, merge_patch={"title": "Concurrent edit"}),
            idempotency_key=client_save.new_idempotency_key(),
        ),
        lambda: client_pub.dispatch(
            PublishRevision(plan_id, draft_id, ver_before, digest_before, reason="Concurrent publish"),
            idempotency_key=client_pub.new_idempotency_key(),
        ),
    )

    if isinstance(out_save, SaveDraftResult):
        assert out_save.edit_version == ver_before + 1
        assert isinstance(out_pub, Conflict)
        assert out_pub.code is ErrorCode.VERSION_CONFLICT
    else:
        assert isinstance(out_pub, PublishRevisionResult)
        assert isinstance(out_save, PreconditionFailed | Conflict)
        assert out_save.code in {ErrorCode.DRAFT_NOT_OPEN, ErrorCode.VERSION_CONFLICT}

    _assert_save_blocks_publish_with_version_conflict(pg_h, plan_id=plan_id, fv_1=fv_1, fv_2=fv_2)


def _set_max_open_drafts_in_pg(dsn: str, max_open: int) -> None:
    sql_upsert = (
        "INSERT INTO skm_config.entries "
        "(id, scope_id, key, op, value, locked, row_version, reason, "
        "created_by, created_at, updated_by, updated_at) "
        "VALUES (%s, %s, 'planning.drafts.max_open', 'set', %s::jsonb, false, 1, 'test', %s, %s, %s, %s) "
        "ON CONFLICT (scope_id, key) DO UPDATE "
        "SET value = EXCLUDED.value, row_version = skm_config.entries.row_version + 1"
    )
    row_id = UUID("01900000-0000-7000-8000-000000000999")
    params = (row_id, SEED.instance_id, str(max_open), OWNER_ID, NOW, OWNER_ID, NOW)
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql_upsert, params)
        conn.execute("UPDATE skm_config.generation SET value = value + 1 WHERE id = 1")


def test_open_draft_limit_race(pg_h: Harness) -> None:
    """Two concurrent ``open_draft`` calls when open drafts count is ``max_open - 1`` (§7.10)."""
    assert pg_h.dsn is not None
    _set_max_open_drafts_in_pg(pg_h.dsn, 2)
    plan_id = PlanId(dispatch_new(pg_h.client, CreatePlan(project_id=pg_h.proj, title="Limit Plan")).plan_id)
    first_draft = dispatch_new(pg_h.client, OpenDraft(plan_id=plan_id, base="empty"))
    assert isinstance(first_draft, OpenDraftResult)

    client_1 = pg_h.app.client(actor=pg_h.owner, surface=Surface.CLI)
    client_2 = pg_h.app.client(actor=pg_h.owner, surface=Surface.CLI)

    out_1, out_2 = _run_barrier_pair(
        lambda: client_1.dispatch(
            OpenDraft(plan_id=plan_id, base="empty"), idempotency_key=client_1.new_idempotency_key()
        ),
        lambda: client_2.dispatch(
            OpenDraft(plan_id=plan_id, base="empty"), idempotency_key=client_2.new_idempotency_key()
        ),
    )

    winners = [x for x in (out_1, out_2) if isinstance(x, OpenDraftResult)]
    losers = [x for x in (out_1, out_2) if isinstance(x, SkmError)]
    assert len(winners) == 1, f"Expected 1 winner, got: {(out_1, out_2)}"
    assert len(losers) == 1, f"Expected 1 loser, got: {(out_1, out_2)}"

    loser = losers[0]
    assert isinstance(loser, Conflict)
    assert loser.code is ErrorCode.ALREADY_EXISTS
    assert loser.details == {"open_drafts": 2, "limit": 2}

    with psycopg.connect(pg_h.dsn, autocommit=True) as conn:
        open_count = conn.execute(
            "SELECT count(*) FROM skm_planning.plan_drafts WHERE plan_id = %s AND state = 'open'",
            (plan_id,),
        ).fetchone()
        assert open_count == (2,)


def test_concurrency_open_draft_limit(pg_h: Harness) -> None:
    """Alias for ``test_open_draft_limit_race`` matching the mandatory scenario checklist."""
    test_open_draft_limit_race(pg_h)


def test_concurrency_candidate_changed_cas(pg_h: Harness) -> None:
    """Barrier test: new ``latest_at_publish`` version after candidate prepare triggers CAS error."""
    assert pg_h.dsn is not None
    file_1, fv_1_v1 = upload_v1(pg_h, b"guideline-v1", filename="guide.txt")
    _, fv_2 = upload_v1(pg_h, b"reference-v1", filename="ref.txt")

    doc = _build_spec_doc(fv_1_id=fv_1_v1, fv_2_id=fv_2)
    plan_id = PlanId(dispatch_new(pg_h.client, CreatePlan(project_id=pg_h.proj, title="CAS Plan")).plan_id)
    draft_res = dispatch_new(pg_h.client, OpenDraft(plan_id=plan_id, base="empty"))
    draft_id = DraftId(draft_res.draft_id)
    save_res = dispatch_new(
        pg_h.client, SaveDraft(plan_id, draft_id, draft_res.edit_version, merge_patch=doc)
    )
    draft_ver = int(save_res.edit_version)

    barrier_prepared = threading.Barrier(2, timeout=WAIT_SECONDS)
    barrier_uploaded = threading.Barrier(2, timeout=WAIT_SECONDS)
    pub_result: list[object] = []
    uploaded_v2: list[FileVersionId] = []

    def _publisher_thread() -> None:
        try:
            client_pub = pg_h.app.client(actor=pg_h.owner, surface=Surface.CLI)
            prepared_digest = _compute_expected_digest(pg_h, draft_id, seq=750)
            barrier_prepared.wait()
            barrier_uploaded.wait()
            pub_cmd = PublishRevision(plan_id, draft_id, draft_ver, prepared_digest, reason="CAS publish")
            pub_result.append(client_pub.dispatch(pub_cmd, idempotency_key=client_pub.new_idempotency_key()))
        except BaseException as exc:  # noqa: BLE001
            pub_result.append(exc)

    def _uploader_thread() -> None:
        barrier_prepared.wait()
        uploaded_v2.append(upload_next_version(pg_h, file_1, 2, b"guideline-v2", filename="guide-v2.txt"))
        barrier_uploaded.wait()

    t_pub = threading.Thread(target=_publisher_thread)
    t_up = threading.Thread(target=_uploader_thread)
    t_pub.start()
    t_up.start()
    t_pub.join(WAIT_SECONDS)
    t_up.join(WAIT_SECONDS)
    assert not t_pub.is_alive()
    assert not t_up.is_alive()

    assert len(uploaded_v2) == 1
    assert uploaded_v2[0] != fv_1_v1
    assert len(pub_result) == 1
    err = pub_result[0]
    assert isinstance(err, Conflict)
    assert err.code is ErrorCode.VERSION_CONFLICT
    assert err.details["reason"] == "candidate_changed"
    new_digest = _compute_expected_digest(pg_h, draft_id, seq=751)
    assert err.details["actual_content_digest"] == new_digest
    assert err.details["expected_content_digest"] != new_digest

    with psycopg.connect(pg_h.dsn, autocommit=True) as conn:
        rev_cnt = conn.execute(
            "SELECT count(*) FROM skm_planning.plan_revisions WHERE plan_id = %s", (plan_id,)
        )
        assert rev_cnt.fetchone() == (0,)
        plan_sql = (
            "SELECT current_revision_id, next_revision_no, row_version FROM skm_planning.plans WHERE id = %s"
        )
        assert conn.execute(plan_sql, (plan_id,)).fetchone() == (None, 1, 1)
        draft_sql = (
            "SELECT state, edit_version, published_revision_id, closed_at "
            "FROM skm_planning.plan_drafts WHERE id = %s"
        )
        assert conn.execute(draft_sql, (draft_id,)).fetchone() == ("open", draft_ver, None, None)
        ev_sql = "SELECT count(*) FROM skm_core.domain_events WHERE workspace_id = %s AND event_type = %s"
        assert conn.execute(ev_sql, (pg_h.ws, PlanRevisionPublished.event_type)).fetchone() == (0,)


def test_concurrency_create_plan_counter_allocation(pg_h: Harness) -> None:
    """Two concurrent ``create_plan`` calls in one project allocate distinct sequential aliases (§7.10)."""
    client_1 = pg_h.app.client(actor=pg_h.owner, surface=Surface.CLI)
    client_2 = pg_h.app.client(actor=pg_h.owner, surface=Surface.CLI)

    out_1, out_2 = _run_barrier_pair(
        lambda: client_1.dispatch(
            CreatePlan(project_id=pg_h.proj, title="Plan One"),
            idempotency_key=client_1.new_idempotency_key(),
        ),
        lambda: client_2.dispatch(
            CreatePlan(project_id=pg_h.proj, title="Plan Two"),
            idempotency_key=client_2.new_idempotency_key(),
        ),
    )
    assert isinstance(out_1, CreatePlanResult)
    assert isinstance(out_2, CreatePlanResult)
    assert sorted([out_1.alias, out_2.alias]) == ["PLAN1", "PLAN2"]
