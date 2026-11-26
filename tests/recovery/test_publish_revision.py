"""Fault-injection and crash recovery tests for ``planning.publish_revision`` (planning §7.5, §7.10)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, cast
from uuid import UUID

import psycopg
import pytest
from psycopg import sql

from integration.artifacts.test_upload_flow import (
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
    make_prepare_ctx,
    req_meta,
    two_file_materials,
    upload_next_version,
    upload_v1,
)
from skm.adapters.postgres.planning import spec_writer as pg_spec_writer
from skm.adapters.postgres.planning.drafts import PostgresDraftRepository
from skm.adapters.postgres.planning.plans import PostgresPlanRepository
from skm.application_bus.ports import EventReader
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError
from skm.kernel.ids import FileVersionId, PlanId, ProjectId, RevisionId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import Role
from skm.modules.planning.application import revision_writer as app_revision_writer
from skm.modules.planning.application.publication_candidate import prepare
from skm.modules.planning.domain.canonical import specification_digest
from skm.modules.planning.domain.draft import DraftId, DraftState
from skm.modules.planning.domain.events import PlanRevisionPublished
from skm.modules.planning.domain.specification import SPECIFICATION_URN
from skm.modules.planning.generated.commands import CreatePlan, OpenDraft, PublishRevision, SaveDraft
from skm.modules.planning.generated.results import PublishRevisionResult
from skm.modules.planning.ports import DraftRepository, PlanningQueries, PlanRepository, RevisionRepository
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from support.fault_injection import FaultPlan, FaultPoint, InjectedFault, faulty_uow_factory
from support.pg import TestDatabase
from support.seed import SEED

__all__ = ["clean_test_database", "pg_session", "test_database"]

PHASE_ID = "01900000-0000-7000-8000-000000000101"
ITEM_ID = "01900000-0000-7000-8000-000000000102"
UNIT_ID = "01900000-0000-7000-8000-000000000103"

_PG_REVISION_TABLES: Final = (
    "plan_revisions",
    "plan_entity_identities",
    "revision_members",
    "revision_specs",
    "phase_specs",
    "item_specs",
    "unit_specs",
    "material_specs",
    "material_bindings",
    "revision_file_bindings",
    "review_requirements",
    "revision_payloads",
)


class _MidStepFault(StrEnum):
    SPEC_WRITER_MID_TABLES = "spec_writer_mid_tables"
    REVISION_FILE_BINDINGS = "revision_file_bindings"
    PLAN_ADVANCE = "plan_advance"
    DRAFT_CLOSE = "draft_close"
    OUTBOX_EVENT = "outbox_event"


def _open_recovery_harness(backend: str, tmp_path: Path, dsn: str | None) -> Iterator[Harness]:
    app, clock, blobs_root = open_test_app(backend, tmp_path, dsn, max_uow=4)
    try:
        actor = seed_principals(
            app,
            backend,
            people=((OWNER_ID, PrincipalKind.HUMAN, "owner"),),
            roles=((SEED.instance_id, OWNER_ID, Role.OWNER),),
        )
        client = app.client(actor=actor, surface=Surface.CLI)
        ws = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        yield Harness(app, clock, actor, client, ws, proj, blobs_root, dsn)
    finally:
        app.close()


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def rec_h(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Harness]:
    backend = str(request.param)
    dsn = (
        cast("TestDatabase", request.getfixturevalue("clean_test_database")).dsn
        if backend == "postgres"
        else None
    )
    yield from _open_recovery_harness(backend, tmp_path, dsn)


@pytest.fixture
def pg_rec_h(clean_test_database: TestDatabase, tmp_path: Path) -> Iterator[Harness]:
    yield from _open_recovery_harness("postgres", tmp_path, clean_test_database.dsn)


def _build_spec_doc(
    *,
    title: str = "Recovery Spec v1",
    fv_1_id: FileVersionId,
    fv_2_id: FileVersionId,
) -> JsonObject:
    materials = two_file_materials(fv_1_id, fv_2_id)
    return {
        "schema": SPECIFICATION_URN,
        "title": title,
        "goal": "Prove all-or-none transaction recovery for publish_revision",
        "materials": materials,
        "phases": [
            {
                "id": PHASE_ID,
                "key": "P1",
                "title": "Phase 1",
                "goal": "Build recovery slice",
                "design_state": "skeleton",
            }
        ],
        "items": [
            {
                "id": ITEM_ID,
                "key": "P1.1",
                "phase": "P1",
                "title": "Item 1",
                "summary": "Implement recovery",
                "why": "Required by spec",
                "review": {"mode": "self", "reason": "focused test spec"},
            }
        ],
        "units": [
            {
                "id": UNIT_ID,
                "key": "P1.1/U1",
                "title": "Unit 1",
                "goal": "Execute unit",
                "unit_kind": "implementation",
                "work_kind": "code",
                "mode": "either",
            }
        ],
        "execution_constraints": {"strategy": "dag"},
    }


def _setup_publishable_draft(
    h: Harness,
) -> tuple[PlanId, DraftId, int, str, FileVersionId, FileVersionId]:
    file_1, fv_1_v1 = upload_v1(h, b"guideline-v1", filename="guide.txt")
    fv_1_v2 = upload_next_version(h, file_1, 2, b"guideline-v2", filename="guide-v2.txt")
    _, fv_2 = upload_v1(h, b"reference-v1", filename="ref.txt")

    doc = _build_spec_doc(fv_1_id=fv_1_v1, fv_2_id=fv_2)
    plan_id = PlanId(dispatch_new(h.client, CreatePlan(project_id=h.proj, title="Recovery Plan")).plan_id)
    draft_res = dispatch_new(h.client, OpenDraft(plan_id=plan_id, base="empty"))
    draft_id = DraftId(draft_res.draft_id)
    save_res = dispatch_new(
        h.client,
        SaveDraft(
            plan_id=plan_id,
            draft_id=draft_id,
            expected_edit_version=draft_res.edit_version,
            merge_patch=doc,
        ),
    )
    draft_ver = int(save_res.edit_version)
    with h.app.uow_factory(req_meta(h, 800), readonly=True) as uow:
        draft = uow.repo(DraftRepository).get(draft_id)
        plan = uow.repo(PlanRepository).get(plan_id)
        ctx = make_prepare_ctx(uow, h, plan_id, seq=800)
        digest = prepare(uow, ctx, plan, draft).content_digest
        uow.rollback()
    return plan_id, draft_id, draft_ver, digest, fv_1_v2, fv_2


def _assert_uncommitted_after_crash(
    h: Harness,
    *,
    plan_id: PlanId,
    draft_id: DraftId,
    expected_draft_ver: int,
) -> None:
    with h.app.uow_factory(req_meta(h, 810), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        assert plan.current_revision_id is None
        assert plan.next_revision_no == 1
        assert plan.row_version == 1

        draft = uow.repo(DraftRepository).get(draft_id)
        assert draft.state is DraftState.OPEN
        assert draft.edit_version == expected_draft_ver
        assert draft.published_revision_id is None
        assert draft.closed_at is None

        assert uow.repo(RevisionRepository).list_for_plan(plan_id, before_revision_no=None, limit=10) == ()
        events = uow.repo(EventReader).after_workspace_seq(
            h.ws,
            0,
            types=frozenset({PlanRevisionPublished.event_type}),
            limit=50,
        )
        assert events == ()
        uow.rollback()

    if h.dsn is not None:
        with psycopg.connect(h.dsn, autocommit=True) as conn:
            for table in _PG_REVISION_TABLES:
                count_row = conn.execute(
                    sql.SQL("SELECT count(*) FROM {} WHERE plan_id = %s").format(
                        sql.Identifier("skm_planning", table)
                    ),
                    (plan_id,),
                ).fetchone()
                assert count_row == (0,), f"Table skm_planning.{table} has uncommitted rows: {count_row}"
            outbox_pub = conn.execute(
                "SELECT count(*) FROM skm_core.outbox o "
                "JOIN skm_core.domain_events e ON e.id = o.event_id "
                "WHERE e.workspace_id = %s AND e.event_type = %s",
                (h.ws, PlanRevisionPublished.event_type),
            ).fetchone()
            assert outbox_pub == (0,)


def test_recovery_crash_before_commit(rec_h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """Crash at ``UOW_BEFORE_COMMIT`` rolls back all tables; retry with same key publishes cleanly."""
    plan_id, draft_id, draft_ver, digest, fv_1_v2, fv_2 = _setup_publishable_draft(rec_h)

    fault_plan = FaultPlan({FaultPoint.UOW_BEFORE_COMMIT: 1})
    monkeypatch.setattr(rec_h.app.bus, "_uow_factory", faulty_uow_factory(rec_h.app.uow_factory, fault_plan))

    idem_key = rec_h.client.new_idempotency_key()
    cmd = PublishRevision(plan_id, draft_id, draft_ver, digest, reason="Crash before commit")

    with pytest.raises(InternalError) as exc_info:
        rec_h.client.dispatch(cmd, idempotency_key=idem_key)
    assert isinstance(exc_info.value.__cause__, InjectedFault)
    assert exc_info.value.__cause__.point is FaultPoint.UOW_BEFORE_COMMIT

    _assert_uncommitted_after_crash(rec_h, plan_id=plan_id, draft_id=draft_id, expected_draft_ver=draft_ver)

    pub_res = cast("PublishRevisionResult", rec_h.client.dispatch(cmd, idempotency_key=idem_key))
    assert pub_res.revision_no == 1
    assert pub_res.parent_revision_id is None
    assert pub_res.content_digest == digest

    rev_id = RevisionId(pub_res.revision_id)
    with rec_h.app.uow_factory(req_meta(rec_h, 811), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        assert plan.current_revision_id == rev_id
        assert plan.next_revision_no == 2
        assert plan.row_version == 2

        draft = uow.repo(DraftRepository).get(draft_id)
        assert draft.state is DraftState.PUBLISHED
        assert draft.published_revision_id == rev_id

        revs = uow.repo(RevisionRepository)
        assert revs.load_typed_document(rev_id) == revs.get_document(rev_id)
        assert specification_digest(revs.load_typed_document(rev_id)) == digest
        assert len(uow.repo(PlanningQueries).revision_pins(rev_id)) == 2
        assert {p.file_version_id for p in uow.repo(PlanningQueries).revision_pins(rev_id)} == {
            UUID(str(fv_1_v2)),
            UUID(str(fv_2)),
        }
        uow.rollback()


def test_recovery_retry_idempotent(rec_h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """Crash at ``UOW_AFTER_COMMIT`` keeps committed revision; retry with same key replays receipt."""
    plan_id, draft_id, draft_ver, digest, _, _ = _setup_publishable_draft(rec_h)

    fault_plan = FaultPlan({FaultPoint.UOW_AFTER_COMMIT: 1})
    monkeypatch.setattr(rec_h.app.bus, "_uow_factory", faulty_uow_factory(rec_h.app.uow_factory, fault_plan))

    idem_key = rec_h.client.new_idempotency_key()
    cmd = PublishRevision(plan_id, draft_id, draft_ver, digest, reason="Crash after commit")

    with pytest.raises(InternalError) as exc_info:
        rec_h.client.dispatch(cmd, idempotency_key=idem_key)
    assert isinstance(exc_info.value.__cause__, InjectedFault)
    assert exc_info.value.__cause__.point is FaultPoint.UOW_AFTER_COMMIT

    replayed = cast("PublishRevisionResult", rec_h.client.dispatch(cmd, idempotency_key=idem_key))
    assert replayed.revision_no == 1
    assert replayed.content_digest == digest
    assert fault_plan.hits[FaultPoint.UOW_AFTER_COMMIT] == 1

    with rec_h.app.uow_factory(req_meta(rec_h, 820), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        assert plan.current_revision_id == RevisionId(replayed.revision_id)
        assert plan.next_revision_no == 2
        assert plan.row_version == 2
        assert (
            len(uow.repo(RevisionRepository).list_for_plan(plan_id, before_revision_no=None, limit=10)) == 1
        )
        events = uow.repo(EventReader).after_workspace_seq(
            rec_h.ws, 0, types=frozenset({PlanRevisionPublished.event_type}), limit=50
        )
        assert len(events) == 1
        uow.rollback()

    with pytest.raises(Conflict) as exc_reused:
        rec_h.client.dispatch(replace(cmd, reason="Different reason"), idempotency_key=idem_key)
    assert exc_reused.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED


def _install_mid_step_fault(
    monkeypatch: pytest.MonkeyPatch,
    fault_step: _MidStepFault,
    *,
    plan_id: PlanId,
    draft_id: DraftId,
    fired: list[_MidStepFault],
) -> None:
    if fault_step is _MidStepFault.SPEC_WRITER_MID_TABLES:
        orig_write_links = pg_spec_writer._write_links

        def _fail_in_links(*args: Any, **kwargs: Any) -> None:
            if not fired:
                fired.append(fault_step)
                raise RuntimeError("simulated crash inside spec_writer after member/typed inserts")
            orig_write_links(*args, **kwargs)

        monkeypatch.setattr(pg_spec_writer, "_write_links", _fail_in_links)

    elif fault_step is _MidStepFault.REVISION_FILE_BINDINGS:
        orig_file_bindings = pg_spec_writer._file_binding_rows

        def _fail_in_pins(*args: Any, **kwargs: Any) -> list[tuple[object, ...]]:
            if not fired:
                fired.append(fault_step)
                raise RuntimeError("simulated crash while building revision_file_bindings")
            return orig_file_bindings(*args, **kwargs)

        monkeypatch.setattr(pg_spec_writer, "_file_binding_rows", _fail_in_pins)

    elif fault_step is _MidStepFault.PLAN_ADVANCE:
        orig_plan_save = PostgresPlanRepository.save

        def _fail_plan_save(self: PostgresPlanRepository, plan: Any, *, expected_version: int) -> None:
            if not fired and plan.id == plan_id:
                fired.append(fault_step)
                raise RuntimeError("simulated crash while advancing plan pointer")
            orig_plan_save(self, plan, expected_version=expected_version)

        monkeypatch.setattr(PostgresPlanRepository, "save", _fail_plan_save)

    elif fault_step is _MidStepFault.DRAFT_CLOSE:
        orig_draft_save = PostgresDraftRepository.save

        def _fail_draft_save(
            self: PostgresDraftRepository, draft: Any, *, expected_edit_version: int
        ) -> None:
            if not fired and draft.id == draft_id and draft.state is DraftState.PUBLISHED:
                fired.append(fault_step)
                raise RuntimeError("simulated crash while marking draft published")
            orig_draft_save(self, draft, expected_edit_version=expected_edit_version)

        monkeypatch.setattr(PostgresDraftRepository, "save", _fail_draft_save)

    elif fault_step is _MidStepFault.OUTBOX_EVENT:
        orig_write_rev = app_revision_writer.write_revision

        def _fail_after_event(*args: Any, **kwargs: Any) -> Any:
            written = orig_write_rev(*args, **kwargs)
            if not fired:
                fired.append(fault_step)
                raise RuntimeError("simulated crash after recording PlanRevisionPublished event")
            return written

        monkeypatch.setattr(app_revision_writer, "write_revision", _fail_after_event)
        from skm.modules.planning.application.commands import publish_revision as pub_cmd_mod

        monkeypatch.setattr(pub_cmd_mod, "write_revision", _fail_after_event)


@pytest.mark.pg
@pytest.mark.parametrize("fault_step", list(_MidStepFault))
def test_recovery_mid_sequence_step_failures_postgres(
    pg_rec_h: Harness,
    monkeypatch: pytest.MonkeyPatch,
    fault_step: _MidStepFault,
) -> None:
    """Failures at intermediate steps in ``publish_revision`` roll back completely and recover cleanly."""
    plan_id, draft_id, draft_ver, digest, _, _ = _setup_publishable_draft(pg_rec_h)
    fired: list[_MidStepFault] = []
    _install_mid_step_fault(monkeypatch, fault_step, plan_id=plan_id, draft_id=draft_id, fired=fired)

    idem_key = pg_rec_h.client.new_idempotency_key()
    cmd = PublishRevision(plan_id, draft_id, draft_ver, digest, reason=f"Fault test {fault_step.value}")

    with pytest.raises(InternalError):
        pg_rec_h.client.dispatch(cmd, idempotency_key=idem_key)
    assert fired == [fault_step]

    _assert_uncommitted_after_crash(
        pg_rec_h, plan_id=plan_id, draft_id=draft_id, expected_draft_ver=draft_ver
    )

    pub_1 = cast("PublishRevisionResult", pg_rec_h.client.dispatch(cmd, idempotency_key=idem_key))
    assert pub_1.revision_no == 1
    assert pub_1.content_digest == digest

    draft_2_res = dispatch_new(pg_rec_h.client, OpenDraft(plan_id=plan_id, base="current"))
    draft_2_id = DraftId(draft_2_res.draft_id)
    save_2 = dispatch_new(
        pg_rec_h.client,
        SaveDraft(plan_id, draft_2_id, draft_2_res.edit_version, merge_patch={"title": "Recovery Spec v2"}),
    )
    with pg_rec_h.app.uow_factory(req_meta(pg_rec_h, 830), readonly=True) as uow:
        d2 = uow.repo(DraftRepository).get(draft_2_id)
        p2 = uow.repo(PlanRepository).get(plan_id)
        digest_2 = prepare(uow, make_prepare_ctx(uow, pg_rec_h, plan_id, seq=830), p2, d2).content_digest
        uow.rollback()

    pub_2: PublishRevisionResult = dispatch_new(
        pg_rec_h.client,
        PublishRevision(plan_id, draft_2_id, save_2.edit_version, digest_2, reason="Second publish"),
    )
    assert pub_2.revision_no == 2
    assert pub_2.parent_revision_id == pub_1.revision_id


def test_publish_response_lost_after_server_commit_replays_exact_pins_and_event(rec_h: Harness) -> None:
    from support.fault_injection import FaultyClient

    h = rec_h
    plan_id, draft_id, draft_ver, digest, first_file, second_file = _setup_publishable_draft(h)
    cmd = PublishRevision(plan_id, draft_id, draft_ver, digest, reason="Lost transport response")
    fault = FaultPlan({FaultPoint.CLIENT_AFTER_SERVER_COMMIT: 1})
    client = FaultyClient(h.client, fault, operations=("PublishRevision",))
    key = h.client.new_idempotency_key()
    with pytest.raises(InjectedFault) as lost:
        client.dispatch(cmd, idempotency_key=key)
    assert lost.value.point is FaultPoint.CLIENT_AFTER_SERVER_COMMIT

    def durable_receipt() -> tuple[RevisionId, set[UUID], list[UUID]]:
        with h.app.uow_factory(req_meta(h, 821), readonly=True) as uow:
            current = uow.repo(PlanRepository).get(plan_id).current_revision_id
            assert current is not None
            pins = {p.file_version_id for p in uow.repo(PlanningQueries).revision_pins(current)}
            events = uow.repo(EventReader).after_workspace_seq(
                h.ws, 0, types=frozenset({PlanRevisionPublished.event_type}), limit=50
            )
            assert len(events) == 1
            return current, pins, [event.id for event in events]

    committed = durable_receipt()
    assert committed[1] == {first_file, second_file}
    result = cast("PublishRevisionResult", client.dispatch(cmd, idempotency_key=key))
    assert result.revision_id == committed[0]
    assert result.content_digest == digest
    assert durable_receipt() == committed
