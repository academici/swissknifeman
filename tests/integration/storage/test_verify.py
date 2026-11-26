"""Storage verification through the composed bus, HTTP and CLI."""

import io
import json
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from psycopg import sql

from contracts.context.harness import CHK_ID
from contracts.execution.harness import ExecSide
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.repository_fixtures import assignment, effect
from contracts.execution.seed_helpers import (
    DIGEST_A,
    seed_attempt,
    seed_output,
    seed_run,
    seed_stage,
    seed_task,
)
from integration.artifacts.test_janitor import Harness, _add_file_dto, _dispatch, _make_harness, _object_loc
from security.api.harness import BASE, TestClient
from skm.adapters.blobs.local.store import LocalBlobStore
from skm.adapters.memory.blob_store import MemoryBlobStore
from skm.adapters.memory.core.storage_inspector import MemoryStorageInspector
from skm.adapters.memory.execution.state import execution_state
from skm.adapters.memory.planning.state import planning_state
from skm.application_bus.platform.storage import StorageInspector
from skm.bootstrap.composition_resources import LazyBlobStore
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routing import build_route_table
from skm.entrypoints.cli.main import Backend, main
from skm.kernel.ids import EntityId, FileVersionId, RevisionId, ScopeId
from skm.kernel.json_types import JsonObject
from skm.modules.artifacts.domain.binding import BindingRole
from skm.modules.artifacts.ports import BlobRepository, BlobStore, FileVersionRepository
from skm.modules.execution.domain.attempt import AttemptState
from skm.modules.execution.domain.check_execution import CheckExecution, CheckKind, CheckState
from skm.modules.execution.domain.ids import CheckExecutionId, RecoveryRecordId, ReviewId
from skm.modules.execution.domain.lease import Lease
from skm.modules.execution.domain.recovery import RecoveryRecord
from skm.modules.execution.domain.review import Freshness, Review, ReviewerKind, ReviewState, Verdict
from skm.modules.execution.domain.run import RunKind
from skm.modules.execution.ports import (
    CheckRepository,
    EvidenceBindingRepository,
    RecoveryRepository,
    ReviewRepository,
)
from skm.modules.knowledge.domain.lesson import (
    ConfidenceTier,
    LessonId,
    LessonKind,
    new_lesson_from_candidate,
)
from skm.modules.knowledge.domain.promotion import CandidateForPromotion
from skm.modules.knowledge.ports import LessonRepository
from skm.modules.planning.domain.canonical import specification_digest
from skm.modules.planning.domain.specification import from_document, to_document
from skm.modules.planning.ports import PlanningQueries, RevisionRecord, RevisionRepository
from skm.platform.generated.commands import RepairStorageSafe
from skm.platform.generated.queries import VerifyStorage
from skm.platform.generated.results import RepairStorageSafeResult, VerifyStorageResult
from skm.platform.storage.verify import LEVELS, has_cycle
from support.pg import TestDatabase
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def storage_side(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Harness]:
    dsn = None
    if request.param == "postgres":
        database: TestDatabase = request.getfixturevalue("clean_test_database")
        dsn = database.dsn
    yield from _make_harness(request.param, tmp_path, dsn)


def verify(side: Harness, query: VerifyStorage | None = None) -> VerifyStorageResult:
    result = side.client.ask(VerifyStorage() if query is None else query)
    assert isinstance(result, VerifyStorageResult)
    return result


def test_missing_and_orphan_objects(storage_side: Harness) -> None:
    h = storage_side
    assert verify(h).checked_levels == LEVELS
    assert verify(h).findings == ()

    data = b"referenced storage payload\n"
    staged = h.client.upload_blob(h.ws, [data], size=len(data), media_type="text/plain")
    added = _dispatch(h.client, _add_file_dto(h.ws, h.proj, staged))
    h.store.delete_unreferenced(_object_loc(h.ws, data))
    h.store.promote(h.store.stage(h.ws, [b"orphan storage payload"]))

    result = verify(h, VerifyStorage(levels=("files",)))
    assert result.checked_levels == ("files",)
    assert (result.counts.error, result.counts.warning, result.counts.info) == (1, 1, 0)
    missing, orphan = result.findings
    assert (missing.code, missing.severity, missing.level, missing.repairability) == (
        "MISSING_OBJECT",
        "error",
        "files",
        "none",
    )
    assert missing.target.workspace_id == h.ws
    assert [(ref.kind, ref.id) for ref in missing.referenced_by] == [
        ("file_version", str(added.file_version_id)),
    ]
    assert (orphan.code, orphan.target.kind, orphan.target.workspace_id, orphan.repairability) == (
        "ORPHAN_OBJECT",
        "blob_object",
        h.ws,
        "none",
    )
    assert verify(h, VerifyStorage(levels=("relational",))).findings == ()

    stdout, stderr = io.StringIO(), io.StringIO()
    backend = lambda _, __: Backend(h.client)  # noqa: E731 - reused by both CLI modes
    assert (
        main(
            ["storage", "verify", "--level", "files", "--json"],
            stdout=stdout,
            stderr=stderr,
            backend=backend,
            environ={},
        )
        == 6
    )
    assert json.loads(stdout.getvalue())["result"]["counts"]["error"] == 1
    stdout.seek(0)
    stdout.truncate(0)
    assert (
        main(
            ["storage", "verify", "--level", "relational"],
            stdout=stdout,
            stderr=stderr,
            backend=backend,
            environ={},
        )
        == 0
    )
    assert "Errors: 0" in stdout.getvalue()


def test_http_level_filter_and_required_repair_key(storage_side: Harness) -> None:
    import os
    from uuid import uuid4

    from skm.kernel.ports_uow import RequestMeta, Surface
    from skm.modules.access import public as access
    from skm.modules.access.domain.token import ApiToken, TokenId, TokenKind, generate_secret, hash_secret
    from skm.modules.access.ports import TokenRepository

    h = storage_side
    pepper = b"storage-verify-http-test-pepper!"
    now = h.clock.now()
    secret = generate_secret(os.urandom)
    with h.app.uow_factory(RequestMeta("storage-http-seed", Surface.TEST, None, now), readonly=False) as uow:
        uow.repo(TokenRepository).add(
            ApiToken(
                id=TokenId(uuid4()),
                principal_id=h.owner.principal_id,
                kind=TokenKind.PERSONAL,
                name="storage-http",
                prefix=secret.prefix,
                secret_hash=hash_secret(secret, pepper),
                scope_id=None,
                permissions=None,
                expires_at=now + timedelta(hours=1),
                created_at=now,
                created_by=h.owner.principal_id,
                last_used_at=None,
                revoked_at=None,
                revoked_by=None,
                assignment_id=None,
                step_id=None,
                superseded_by=None,
            )
        )
        uow.commit()

    def authenticate(secret_text: str):
        meta = RequestMeta("storage-http-auth", Surface.API, None, h.clock.now())
        with h.app.uow_factory(meta, readonly=True) as uow:
            return access.authenticate_token(uow, secret_text, pepper=pepper, now=h.clock.now())

    # The actual bus still uses the existing RBAC authorizer for this resolved actor.
    api = create_app(
        replace(h.app, authenticator=authenticate),
        route_table=build_route_table(("access", "settings", "workspace")),
        registry=h.app.bus._registry,
        schema_check=lambda: None,
        no_background=True,
    )
    with TestClient(api, base_url=BASE, headers={"Authorization": f"Bearer {secret}"}) as http:
        response = http.get("/api/v1/admin/storage/verify?level=files&level=recovery")
        assert response.status_code == 200, response.text
        assert response.json()["checked_levels"] == ["files", "recovery"]
        assert http.get("/api/v1/admin/storage/verify?level=unknown").status_code == 422
        response = http.post("/api/v1/admin/storage/repair", json={"dry_run": True})
        assert response.status_code == 422
        assert response.json()["code"] == "SCHEMA_INVALID"
        response = http.post(
            "/api/v1/admin/storage/repair",
            json={"dry_run": True},
            headers={"Idempotency-Key": "storage-dry-run"},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"repaired": [], "skipped": []}


def test_relational_storage_verify_accepts_project_owned_run(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        seed_run(exec_side, uow)
        seed_run(exec_side, uow, kind=RunKind.ADHOC, inline_spec_file_version_id=exec_side.fv1)
        uow.commit()

    result = exec_side.client.ask(VerifyStorage(levels=("relational",)))
    assert isinstance(result, VerifyStorageResult)
    assert result.findings == ()


def test_corrupt_metadata_and_accepted_evidence(exec_side: ExecSide) -> None:
    side = exec_side
    clean = side.client.ask(VerifyStorage())
    assert isinstance(clean, VerifyStorageResult)
    assert clean.findings == ()

    now = side.clock.now()
    with side.uow() as uow:
        run = seed_run(side, uow)
        task = seed_task(side, uow, run.id)
        attempt = seed_attempt(side, uow, run.id, task.id, state=AttemptState.COMPLETED)
        stage = seed_stage(side, uow, attempt)
        assigned = assignment(side, uow, attempt)
        effect_row = effect(side, uow, attempt)
        recovery = RecoveryRecord(
            RecoveryRecordId(side.new_id()),
            run.id,
            task.id,
            attempt.id,
            stage.id,
            None,
            "hung",
            (),
            None,
            None,
            (),
            now - timedelta(hours=2),
        )
        uow.repo(RecoveryRepository).add(recovery)
        uow.repo(EvidenceBindingRepository).bind("attempt", attempt.id, (side.fv1,), BindingRole.EVIDENCE)
        version = uow.repo(FileVersionRepository).get(side.fv1)
        [location] = uow.repo(BlobRepository).locations(version.blob_id)
        lesson = new_lesson_from_candidate(
            CandidateForPromotion(
                candidate_id=side.new_id(),
                workspace_id=side.ws,
                scope_id=ScopeId(side.ws),
                kind=LessonKind.HEURISTIC,
                trigger="A diagnostic fixture",
                action="Inspect the test store",
                evidence=(),
                confidence=0.6,
                tier=ConfidenceTier.MODERATE,
            ),
            lesson_id=LessonId(side.new_id()),
            actor=side.owner,
            now=now,
        )
        uow.repo(LessonRepository).add(lesson)
        if side.dsn is None:
            inspector = uow.repo(StorageInspector)
            assert isinstance(inspector, MemoryStorageInspector)
            state = inspector._state
            scope = state.core.scopes[ScopeId(run.id)]
            state.core.scopes[scope.id] = replace(scope, parent_id=ScopeId(side.plan2_ws2))
            execution_state(state).leases[assigned.id] = Lease(
                assigned.id,
                side.worker1,
                1,
                now + timedelta(hours=1),
                now,
                None,
            )
            planning = planning_state(state)
            stored = planning.revisions[side.rev1]
            document = deepcopy(stored.document)
            items = document["items"]
            assert isinstance(items, list)
            first = items[0]
            assert isinstance(first, dict)
            second = {**first, "id": str(side.new_id()), "key": "P1.2", "depends_on": ["P1.1"]}
            first["depends_on"] = ["P1.2"]
            items.append(second)
            # Memory keeps the normalized document and only the material pins independently.
            # Change a pin as well so the typed reconstruction disagrees with the payload.
            [pin] = stored.pins
            planning.revisions[side.rev1] = replace(
                stored,
                document=document,
                _pins=(replace(pin, file_version_id=side.fv2),),
            )
        uow.commit()
    if side.dsn is not None:
        with psycopg.connect(side.dsn) as conn:
            conn.execute("ALTER TABLE skm_core.scopes DISABLE TRIGGER tg_scopes__immutable")
            conn.execute("UPDATE skm_core.scopes SET parent_id = %s WHERE id = %s", (side.plan2_ws2, run.id))
            conn.execute("ALTER TABLE skm_core.scopes ENABLE TRIGGER tg_scopes__immutable")
            conn.execute(
                "UPDATE skm_execution.assignments SET state = 'leased', last_fencing_token = 1 WHERE id = %s",
                (assigned.id,),
            )
            conn.execute(
                """
                INSERT INTO skm_execution.assignment_leases
                    (assignment_id, workspace_id, worker_id, fencing_token, expires_at, last_heartbeat_at)
                VALUES (%s, %s, %s, 1, %s, %s)
            """,
                (assigned.id, side.ws, side.worker1, now + timedelta(hours=1), now),
            )
            conn.execute(
                "ALTER TABLE skm_planning.revision_payloads DISABLE TRIGGER tg_revision_payloads__immutable"
            )
            conn.execute(
                """
                UPDATE skm_planning.revision_payloads
                SET document = jsonb_set(document, '{title}', '"tampered"')
                WHERE revision_id = %s
            """,
                (side.rev1,),
            )
            conn.execute(
                "ALTER TABLE skm_planning.revision_payloads ENABLE TRIGGER tg_revision_payloads__immutable"
            )
            conn.execute(
                """
                INSERT INTO skm_planning.dependency_edges
                    (workspace_id, plan_id, revision_id, dependent_entity_id,
                     prerequisite_entity_id, dependency_kind)
                SELECT a.workspace_id, a.plan_id, a.revision_id, a.entity_id, b.entity_id, 'item_depends_on'
                FROM skm_planning.revision_members a JOIN skm_planning.revision_members b USING (revision_id)
                WHERE a.revision_id = %s AND
                  (a.entity_kind, b.entity_kind) IN (('item', 'unit'), ('unit', 'item'))
            """,
                (side.rev1,),
            )

    side.app.gateways.get(BlobStore).delete_unreferenced(
        {
            "backend_id": location.backend_id,
            "storage_key": location.storage_key,
            "storage_version": location.storage_version,
        }
    )
    result = side.client.ask(VerifyStorage())
    assert isinstance(result, VerifyStorageResult)
    required = {
        "SCOPE_LINEAGE_BROKEN": run.id,
        "DANGLING_REFERENCE": lesson.id,
        "TYPED_SPEC_MISMATCH": side.rev1,
        "DEPENDENCY_CYCLE": side.rev1,
        "LEASE_INCONSISTENT": assigned.id,
        "ACCEPTED_EVIDENCE_MISSING": attempt.id,
        "PAYLOAD_DIGEST_MISMATCH": side.rev1,
        "CROSS_WORKSPACE_LINK": run.id,
        "EFFECT_OUTCOME_UNKNOWN": effect_row.id,
        "RECOVERY_STALLED": recovery.id,
    }
    for code, ident in required.items():
        match = next(item for item in result.findings if item.code == code and item.target.id == str(ident))
        assert match.target.workspace_id == side.ws
        assert match.repairability == "none"
    _assert_report_only(side, result, tuple(required))


def _assert_report_only(side: ExecSide, result: VerifyStorageResult, codes: tuple[str, ...]) -> None:
    repair = side.client.dispatch(RepairStorageSafe(codes=codes), idempotency_key="manual-findings")
    assert isinstance(repair, RepairStorageSafeResult)
    assert repair.repaired == ()
    assert {row.code for row in repair.skipped} == set(codes)
    assert side.client.ask(VerifyStorage()) == result


def test_missing_revision_pin(exec_side: ExecSide) -> None:
    side = exec_side
    missing = [side.rev1, side.rev2]
    if side.dsn is None:
        with side.uow() as uow:
            inspector = uow.repo(StorageInspector)
            assert isinstance(inspector, MemoryStorageInspector)
            revisions = planning_state(inspector._state).revisions
            for ident in missing:
                assert revisions[ident].pins
                revisions[ident] = replace(revisions[ident], _pins=())
            uow.commit()
    else:
        with psycopg.connect(side.dsn) as conn:
            conn.execute("SET LOCAL session_replication_role = replica")
            deleted = conn.execute(
                "DELETE FROM skm_planning.revision_file_bindings WHERE revision_id = ANY(%s)", (missing,)
            )
            assert deleted.rowcount == len(missing)

    result = side.client.ask(VerifyStorage(levels=("specification", "cryptographic")))
    assert isinstance(result, VerifyStorageResult)
    assert {
        (item.code, item.level, item.target.id, item.target.workspace_id) for item in result.findings
    } == {("TYPED_SPEC_MISMATCH", "specification", str(ident), side.ws) for ident in missing}


def test_cycle_through_compiled_phase_gate(exec_side: ExecSide) -> None:
    side = exec_side
    # P2 depends on P1, while an item in P1 depends on an item in P2. Stored edges have no cycle.
    item: JsonObject = {
        "title": "Work",
        "summary": "Fixture item",
        "why": "Exercise dependencies",
        "review": {"mode": "self", "reason": "Fixture"},
    }
    phase: JsonObject = {"title": "Phase", "goal": "Fixture phase", "design_state": "detailed"}
    document: JsonObject = {
        "title": "Phase gate cycle",
        "goal": "Verify the compiled graph",
        "phases": [
            {**phase, "id": str(side.new_id()), "key": "P1", "depends_on": []},
            {**phase, "id": str(side.new_id()), "key": "P2", "depends_on": ["P1"]},
        ],
        "items": [
            {
                **item,
                "id": str(side.new_id()),
                "key": "P1.1",
                "phase": "P1",
                "depends_on": ["P2.1"],
            },
            {**item, "id": str(side.new_id()), "key": "P2.1", "phase": "P2"},
        ],
    }
    spec, _ = from_document(document)
    document = to_document(spec)
    ident = RevisionId(side.new_id())
    with side.uow() as uow:
        revisions = uow.repo(RevisionRepository)
        meta = replace(
            revisions.get_meta(side.rev2),
            id=ident,
            revision_no=3,
            parent_revision_id=side.rev2,
            content_digest=specification_digest(document),
        )
        revisions.add(RevisionRecord(meta, spec, document, (), (), ()))
        uow.commit()
    if side.dsn is not None:
        with psycopg.connect(side.dsn) as conn:
            edges = conn.execute(
                "SELECT dependent_entity_id, prerequisite_entity_id "
                "FROM skm_planning.dependency_edges WHERE revision_id = %s",
                (ident,),
            ).fetchall()
            assert len(edges) == 2
            assert not has_cycle((str(dependent), str(prerequisite)) for dependent, prerequisite in edges)
    result = side.client.ask(VerifyStorage(levels=("specification",)))
    assert isinstance(result, VerifyStorageResult)
    assert [(item.code, item.target.id) for item in result.findings] == [("DEPENDENCY_CYCLE", str(ident))]


def test_evidence_bindings_cannot_cross_workspaces(exec_side: ExecSide) -> None:
    side = exec_side
    now = side.clock.now()
    with side.uow() as uow:
        [pin] = uow.repo(PlanningQueries).revision_pins(side.rev_ws2)
        foreign = FileVersionId(pin.file_version_id)
        run = seed_run(side, uow)
        task = seed_task(side, uow, run.id)
        attempt = seed_attempt(side, uow, run.id, task.id)
        output = seed_output(side, uow, attempt)
        check = CheckExecution(
            id=CheckExecutionId(side.new_id()),
            workspace_id=side.ws,
            run_id=run.id,
            task_id=task.id,
            attempt_id=attempt.id,
            output_id=output.id,
            check_spec_id=EntityId(UUID(CHK_ID)),
            check_key="pytest",
            kind=CheckKind.COMMAND,
            required=True,
            state=CheckState.PASSED,
            exit_code=0,
            summary="passed",
            error_code=None,
            reused_from_id=None,
            fingerprint=DIGEST_A,
            started_at=now,
            finished_at=now,
            round_no=1,
        )
        uow.repo(CheckRepository).add_many((check,))
        review = Review(
            id=ReviewId(side.new_id()),
            workspace_id=side.ws,
            run_id=run.id,
            task_id=task.id,
            attempt_id=attempt.id,
            output_id=output.id,
            round_no=1,
            reviewer_kind=ReviewerKind.HUMAN,
            reviewer_ref={"principal_id": str(side.owner.principal_id)},
            profile_key="reviewer",
            profile_version_id=side.workflow_rv_id,
            audit_scope="full",
            state=ReviewState.COMPLETED,
            verdict=Verdict.GREEN,
            freshness=Freshness.FRESH,
            base_output_id=None,
            residual_risk="low",
            completed_at=now,
        )
        uow.repo(ReviewRepository).add(review)
        evidence = uow.repo(EvidenceBindingRepository)
        version = foreign if side.dsn is None else side.fv1
        evidence.bind("attempt", attempt.id, (version,), BindingRole.EVIDENCE)
        evidence.bind("output", output.id, (version,), BindingRole.EVIDENCE)
        evidence.bind("check_execution", check.id, (version,), BindingRole.EVIDENCE)
        evidence.bind("review", review.id, (version,), BindingRole.EVIDENCE)
        uow.commit()

    if side.dsn is not None:
        with psycopg.connect(side.dsn) as conn:
            conn.execute("SET LOCAL session_replication_role = replica")
            for table, column, owner in (
                ("attempt_file_bindings", "attempt_id", attempt.id),
                ("output_file_bindings", "output_id", output.id),
                ("check_evidence_bindings", "check_execution_id", check.id),
                ("review_evidence_bindings", "review_id", review.id),
            ):
                conn.execute(
                    sql.SQL("UPDATE skm_execution.{} SET file_version_id = %s WHERE {} = %s").format(
                        sql.Identifier(table), sql.Identifier(column)
                    ),
                    (foreign, owner),
                )
    result = side.client.ask(VerifyStorage(levels=("authorization",)))
    assert isinstance(result, VerifyStorageResult)
    assert {(item.target.kind, item.target.id) for item in result.findings} == {
        ("attempt", str(attempt.id)),
        ("attempt_output", str(output.id)),
        ("check_execution", str(check.id)),
        ("review", str(review.id)),
    }
    for item in result.findings:
        assert (item.code, item.level, item.target.workspace_id) == (
            "CROSS_WORKSPACE_LINK",
            "authorization",
            side.ws,
        )
        assert [(row.kind, row.id) for row in item.referenced_by] == [("file_version", str(foreign))]


def test_corrupt_object_bytes(storage_side: Harness) -> None:
    h = storage_side
    data = b"expected contents"
    bad = b"modified contents"
    staged = h.client.upload_blob(h.ws, [data], size=len(data), media_type="text/plain")
    _dispatch(h.client, _add_file_dto(h.ws, h.proj, staged))
    key = str(_object_loc(h.ws, data)["storage_key"])
    if isinstance(h.store, MemoryBlobStore):
        h.store._objects[key] = replace(h.store._objects[key], data=bad)
    else:
        assert isinstance(h.store, LazyBlobStore)
        local = h.store._store
        assert isinstance(local, LocalBlobStore)
        path = local._object_path(key)
        damaged = path.with_suffix(".damaged")
        damaged.write_bytes(bad)
        damaged.chmod(0o400)
        damaged.replace(path)

    assert verify(h, VerifyStorage(levels=("files",))).findings == ()
    result = verify(h, VerifyStorage(levels=("cryptographic",)))
    assert result.counts.error == 1
    assert [item.code for item in result.findings] == ["PAYLOAD_DIGEST_MISMATCH"]


@pytest.mark.parametrize("as_json", [False, True])
def test_cli_escapes_and_redacts_finding(
    storage_side: Harness,
    monkeypatch: pytest.MonkeyPatch,
    as_json: bool,
) -> None:
    h = storage_side
    secret = "skm-test-sensitive-storage-value"
    detail = "\x1b]52;clipboard\x07\n\rfake line\u202e " + secret
    report = VerifyStorageResult.from_json(
        {
            "checked_levels": ["files"],
            "findings": [
                {
                    "code": "MISSING_OBJECT",
                    "severity": "error",
                    "level": "files",
                    "target": {"kind": "blob", "id": "test-blob"},
                    "referenced_by": [],
                    "repairability": "none",
                    "detail": detail,
                }
            ],
            "counts": {"error": 1, "warning": 0, "info": 0},
        }
    )
    monkeypatch.setattr(type(h.client), "ask", lambda *_: report)
    stdout = io.StringIO()
    args = ["--as-token", secret, "storage", "verify"]
    if as_json:
        args.append("--json")
    assert (
        main(args, environ={}, stdout=stdout, stderr=io.StringIO(), backend=lambda *_: Backend(h.client)) == 6
    )
    output = stdout.getvalue()
    for sensitive in (secret, "\x1b", "\x07", "\r", "\u202e", "\nfake line"):
        assert sensitive not in output
    if as_json:
        assert "fake line" in json.loads(output)["result"]["findings"][0]["detail"]
    else:
        assert "MISSING_OBJECT" in output
