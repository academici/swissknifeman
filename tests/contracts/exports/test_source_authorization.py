"""An execution read grant exposes structural facts and no source artifact content."""

import base64
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from contracts.execution.harness import PEPPER, ExecSide, exec_side
from contracts.execution.seed_helpers import (
    seed_attempt,
    seed_bundle,
    seed_run,
    seed_stage,
    seed_step,
    seed_task,
)
from contracts.knowledge.harness import KnowledgeSide, knowledge_side
from integration.artifacts.test_upload_flow import dispatch_new
from security.api.harness import BASE, TestClient
from skm.adapters.postgres.exports import repositories as postgres_exports
from skm.application_bus.ports import EventReader
from skm.application_bus.subscribers import DeliveryOutcome
from skm.bootstrap.lifecycle import upload_for_api
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.blobs import mount_blobs
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import FileVersionId, HostId, PrincipalId, RunId
from skm.modules.access.public import CreateToken, CreateTokenResult, authenticate_token
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.generated.commands import (
    AddFileVersionDefsStagedBlobRef,
    AddFileVersionDefsVersionSource,
)
from skm.modules.artifacts.ports import BlobLocationRef
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.step import RoleId, StepState
from skm.modules.execution.ports import StepRepository
from skm.modules.exports.domain.events import VaultNoteQueued
from skm.modules.exports.domain.note import NoteKind, VaultNote, VaultNoteId
from skm.modules.exports.ports import VaultNoteRepository
from skm.modules.exports.public import (
    ListPendingNotes,
    ListVaultNotes,
    PendingNotesView,
    RecordNoteWritten,
    RecordNoteWrittenResult,
    RenderRunReport,
    RequeueNote,
    RunReportView,
    VaultNotesView,
    VaultRequestMeta,
)
from skm.modules.runtimes.public import SubagentUsage, UsageReport, UsageStatus
from skm.modules.settings.public import SetValue
from skm.modules.workspace.public import BindCheckout, RegisterWorker, RegisterWorkerResult
from support.pg import clean_test_database, pg_session, test_database

from .test_vault_ledger import archive_and_queue, bound_host, deliver_note

__all__ = ["clean_test_database", "exec_side", "knowledge_side", "pg_session", "test_database"]


def _meta(side: KnowledgeSide, host: HostId, key: str | None = None) -> VaultRequestMeta:
    request = side.meta(key)
    return VaultRequestMeta(request.request_id, request.surface, key, request.received_at, host_id=host)


@pytest.fixture
def run_with_pinned_source(exec_side: ExecSide) -> tuple[RunId, UUID, UUID]:
    side = exec_side
    manifest = side.make_final_manifest()
    with side.uow() as uow:
        run = seed_run(side, uow, status=RunStatus.FAILED)
        seed_bundle(side, uow, run.id)
        task = seed_task(side, uow, run.id)
        attempt = seed_attempt(side, uow, run.id, task.id)
        stage = seed_stage(side, uow, attempt)
        step = seed_step(
            side,
            uow,
            attempt,
            stage,
            manifest_id=manifest,
            state=StepState.SUCCEEDED,
            raw_fv_id=side.fv1,
            transcript_fv_id=side.fv1,
            result={
                "prompt": "RAW-PRIVATE-PROMPT",
                "tool_arguments": "RAW-PRIVATE-ARGS",
                "summary": f"private source: {side.fv1}",
                "logs": "RAW-PRIVATE-LOGS",
            },
        )
        measured = seed_step(
            side,
            uow,
            attempt,
            stage,
            seq=2,
            role=RoleId.REVIEWER,
            manifest_id=manifest,
            state=StepState.SUCCEEDED,
        )
        uow.repo(StepRepository).save(
            replace(
                measured,
                finished_at=measured.started_at + timedelta(seconds=13),
                usage=UsageReport(
                    11, 5, 3, None, None, 125_001, UsageStatus.REPORTED, "test", SubagentUsage(False, False)
                ),
            )
        )
        emit(uow, run, "run-finished", {"outcome": "failed", "counts_by_status": {}}, cause("stage_outcome"))
        uow.commit()
    return run.id, step.id, manifest


def test_run_read_does_not_admit_raw_step_data_or_source_artifacts(
    exec_side: ExecSide, run_with_pinned_source: tuple[RunId, UUID, UUID]
) -> None:
    run_id, step_id, manifest = run_with_pinned_source
    reader = exec_side.restricted_client(("run.read",), scope_id=run_id, owner_token=True)
    for query in (RenderRunReport(run_id), RenderRunReport(run_id, "summary")):
        result = reader.ask(query)
        assert isinstance(result, RunReportView)
        assert str(run_id) in result.markdown
        assert "Source material and execution traces are unavailable" in result.markdown
        assert all(
            marker not in result.markdown
            for marker in ("RAW-PRIVATE", str(exec_side.fv1), str(step_id), str(manifest), "private source")
        )
        assert result.metrics.tokens == {"input": 11, "cached": 3, "output": 5, "unknown_steps": 1}
        assert result.metrics.active_seconds_by_group["review"] == 13
        assert result.metrics.usd is None
    with pytest.raises(SkmError) as denied:
        reader.ask(RenderRunReport(uuid4()))
    assert denied.value.code in {ErrorCode.NOT_FOUND, ErrorCode.FORBIDDEN}


def _finished_note(side: ExecSide, run_id: RunId) -> VaultNote:
    dispatch_new(
        side.client,
        SetValue.from_json(
            {"scope": {"level": "instance"}, "key": "exports.notes.run_finished", "value": "all"}
        ),
    )
    vault_side = KnowledgeSide(side.kind, side.app, side.clock, side.owner, side.ws, side.proj, count())
    outcome, event_id = deliver_note(vault_side, "exports.run_finished_note")
    assert outcome is DeliveryOutcome.DELIVERED
    with side.uow(readonly=True) as uow:
        note = uow.repo(VaultNoteRepository).by_event(event_id, NoteKind.RUN_FINISHED)
    assert note is not None
    assert note.source_id == run_id
    return note


def _register_source_reader(side: ExecSide, host: HostId) -> RegisterWorkerResult:
    worker = side.client.dispatch(
        RegisterWorker.from_json(
            {
                "workspace_id": str(side.ws),
                "host_id": str(host),
                "display_name": "exports source reader",
                "capabilities": {
                    "platform": {"os": "linux", "arch": "x86_64"},
                    "runtimes": [],
                    "isolation_profiles": ["worktree"],
                    "max_concurrency": 1,
                    "labels": [],
                    "skm_version": "2.0.0",
                },
            }
        )
    )
    assert isinstance(worker, RegisterWorkerResult)
    with side.uow() as uow:
        assert (
            artifacts.grant_access(
                uow,
                principal_id=PrincipalId(worker.principal_id),
                version_ids=(side.fv1,),
                reason=artifacts.GrantReason.ASSIGNMENT,
                ref="exports-source",
                expires_at=side.clock.now() + timedelta(hours=1),
                ids=side.ids,
                now=side.clock.now(),
            )
            == 1
        )
        uow.commit()
    return worker


def _new_source_version(
    side: ExecSide, source: artifacts.GetFileVersionView
) -> artifacts.AddFileVersionResult:
    latest = b"newer source bytes\n"
    blob = side.client.upload_blob(side.ws, [latest], size=len(latest), media_type="text/plain")
    result = dispatch_new(
        side.client,
        artifacts.AddFileVersion(
            file_id=source.file_id,
            expected_row_version=2,
            blob=AddFileVersionDefsStagedBlobRef.from_json(blob.to_json()),
            original_filename="replacement.txt",
            declared_media_type="text/plain",
            source=AddFileVersionDefsVersionSource(kind="upload"),
        ),
    )
    assert isinstance(result, artifacts.AddFileVersionResult)
    with side.client.open_file_version_content(FileVersionId(result.file_version_id)) as content:
        assert content.read() == latest
    return result


@pytest.mark.parametrize("source_state", ["revoked_file_grant", "missing_pinned_blob"])
def test_pinned_source_failure_stays_private_across_export_surfaces(
    exec_side: ExecSide, run_with_pinned_source: tuple[RunId, UUID, UUID], source_state: str
) -> None:
    side = exec_side
    run_id, step_id, manifest = run_with_pinned_source
    host = side.host1
    dispatch_new(
        side.client,
        BindCheckout(
            side.repo_id,
            host,
            "/opt/exports-fixture",
            "/opt/exports-fixture",
            ("example.invalid/skm",),
            None,
            False,
            side.clock.now(),
        ),
    )
    note = _finished_note(side, run_id)
    worker = _register_source_reader(side, host)
    source = side.client.ask(artifacts.GetFileVersion(side.fv1))
    assert isinstance(source, artifacts.GetFileVersionView)
    latest = _new_source_version(side, source)
    pinned = side.client.ask(artifacts.OpenFileVersionContent(side.fv1))
    assert isinstance(pinned, artifacts.OpenFileVersionContentView)

    def authenticate(secret: str) -> Actor:
        with side.uow(readonly=True) as uow:
            return authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())

    registry = side.app.bus._registry
    api = create_app(
        replace(side.app, authenticator=authenticate),
        route_table=build_route_table(("exports",)),
        registry=registry,
        no_background=True,
    )
    mount_blobs(api, upload_for_api(side.app))
    owner = side.client.dispatch(CreateToken("vault-owner"))
    narrowed = side.client.dispatch(CreateToken("vault-without-run", permissions=("export.run", "plan.read")))
    assert isinstance(owner, CreateTokenResult)
    assert isinstance(narrowed, CreateTokenResult)
    worker_auth = {"Authorization": "Bearer " + worker.token_secret}
    report_path = f"/api/v1/runs/{run_id}/report.md"
    source_path = f"/api/v1/file-versions/{side.fv1}/content"
    source_refs = (
        str(source.file_id),
        str(latest.file_version_id),
        pinned.digest,
        str(pinned.location["storage_key"]),
    )
    hidden = (*source_refs, str(side.fv1), str(step_id), str(manifest))
    private = ("RAW-PRIVATE", "private source", "Artifact 1", "Artifact 2", "newer source bytes")

    with TestClient(api, base_url=BASE) as http:
        before = http.get(source_path, headers=worker_auth)
        assert before.status_code == 200, before.text
        assert before.content == b"Artifact 1\n"
        if source_state == "revoked_file_grant":
            with side.uow() as uow:
                assert (
                    artifacts.revoke_grants(
                        uow,
                        reason=artifacts.GrantReason.ASSIGNMENT,
                        ref="exports-source",
                        now=side.clock.now(),
                    )
                    == 1
                )
                uow.commit()
            expected_error = ErrorCode.FORBIDDEN
        else:
            # Remove only the pinned object in the isolated test store, leaving its metadata and v2 intact.
            side.app.gateways.get(artifacts.BlobStore).delete_unreferenced(
                cast("BlobLocationRef", pinned.location)
            )
            expected_error = ErrorCode.FILE_VERSION_NOT_READY

        refused = http.get(source_path, headers=worker_auth)
        assert refused.status_code == (403 if expected_error == ErrorCode.FORBIDDEN else 409), refused.text
        assert refused.json()["code"] == expected_error
        assert all(marker not in refused.text for marker in (*source_refs, *private))
        if expected_error == ErrorCode.FORBIDDEN:
            assert refused.json()["details"]["reason"] == "no_active_grant"
        else:
            assert refused.json()["detail"] == "File version content is unavailable"
            assert refused.json()["details"] == {}

        report = http.get(report_path, headers=worker_auth)
        assert report.status_code == 200, report.text
        assert report.headers["content-type"] == "text/markdown; charset=utf-8"
        assert str(run_id) in report.text
        assert "Source material and execution traces are unavailable" in report.text
        assert all(marker not in report.text for marker in (*hidden, *private))
        denied_report = http.get(report_path, headers={"Authorization": "Bearer " + narrowed.secret})
        assert denied_report.status_code == 403
        assert all(marker not in denied_report.text for marker in (*hidden, *private))
        _assert_vault_source_gate(http, side, note, host, owner.secret, narrowed.secret, (*hidden, *private))


def _assert_vault_source_gate(
    http: TestClient,
    side: ExecSide,
    note: VaultNote,
    host: HostId,
    owner_secret: str,
    narrowed_secret: str,
    private: tuple[str, ...],
) -> None:
    vault = str(uuid4())
    pending = f"/api/v1/workspaces/{side.ws}/vault-notes/pending"
    ledger = f"/api/v1/projects/{side.proj}/vault-notes"
    ack = f"{ledger}/{note.id}/writes"
    params = {"vault_id": vault, "host_id": str(host)}
    owner = {"Authorization": "Bearer " + owner_secret, "SKM-Host-Id": str(host)}
    narrowed = {**owner, "Authorization": "Bearer " + narrowed_secret}
    payload = {
        "vault_id": vault,
        "generation": 1,
        "relative_path": "Runs/private-receipt.md",
        "outcome": "created",
        "expected_digest": note.body_digest,
        "observed_digest": note.body_digest,
    }
    page = http.get(pending, params=params, headers=owner)
    assert page.status_code == 200, page.text
    (visible,) = page.json()["items"]
    assert visible["body"] == note.body
    assert "Source material and execution traces are unavailable" in visible["body"]
    assert all(marker not in page.text for marker in private)
    accepted = http.post(ack, json=payload, headers={**owner, "Idempotency-Key": "source-write"})
    assert accepted.status_code == 201, accepted.text
    dispatch_new(side.client, RequeueNote(side.proj, note.id, 1))
    visible_ledger = http.get(ledger, headers=owner)
    assert visible_ledger.status_code == 200, visible_ledger.text
    (entry,) = visible_ledger.json()["items"]
    assert entry["writes"][0]["relative_path"] == payload["relative_path"]
    assert "body" not in entry
    assert all(marker not in visible_ledger.text for marker in private)

    for path, query in ((pending, params), (ledger, {})):
        hidden = http.get(path, params=query, headers=narrowed)
        assert hidden.status_code == 200, hidden.text
        assert hidden.json() == {"items": [], "next_cursor": None, "has_more": False}
    for key, generation in (("source-write", 1), ("new-source-write", 2)):
        rejected = http.post(
            ack, json={**payload, "generation": generation}, headers={**narrowed, "Idempotency-Key": key}
        )
        assert rejected.status_code == 403, rejected.text
        assert rejected.json()["detail"] == "Vault note source access denied"
        assert rejected.json()["details"] == {}
        assert all(marker not in rejected.text for marker in (*private, payload["relative_path"], vault))
    with side.uow(readonly=True) as uow:
        (receipt,) = uow.repo(VaultNoteRepository).writes(note.id)
    assert receipt.generation == 1


def test_live_bus_vault_admission_and_historical_ack_replay(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    host = bound_host(side)
    note = archive_and_queue(side)
    vault = uuid4()
    query = ListPendingNotes(side.workspace, host, vault)
    with pytest.raises(SkmError) as denied:
        side.app.bus.ask(query, actor=side.owner, meta=_meta(side, HostId(uuid4())))
    assert denied.value.code == ErrorCode.FORBIDDEN
    page = side.app.bus.ask(query, actor=side.owner, meta=_meta(side, host))
    assert isinstance(page, PendingNotesView)
    assert tuple(item.note_id for item in page.items) == (note.id,)

    cmd = RecordNoteWritten(
        side.project,
        note.id,
        vault,
        "Plans/note.md",
        1,
        "created",
        note.body_digest,
        note.body_digest,
    )
    ack = side.app.bus.dispatch(cmd, actor=side.owner, meta=_meta(side, host, "ack-one"))
    assert ack == RecordNoteWrittenResult(True, note.id, vault, 1)
    side.app.bus.dispatch(RequeueNote(side.project, note.id, 1), actor=side.owner, meta=side.meta("requeue"))
    assert side.app.bus.dispatch(cmd, actor=side.owner, meta=_meta(side, host, "ack-one")) == ack
    with pytest.raises(SkmError) as stale:
        side.app.bus.dispatch(cmd, actor=side.owner, meta=_meta(side, host, "ack-stale"))
    assert stale.value.code == ErrorCode.VERSION_CONFLICT

    ledger = side.app.bus.ask(ListVaultNotes(side.project), actor=side.owner, meta=side.meta())
    assert isinstance(ledger, VaultNotesView)
    (entry,) = ledger.items
    assert entry.generation == 2
    assert entry.writes[0].generation == 1
    assert "body" not in entry.to_json()


def test_hidden_candidates_advance_cursor_without_losing_the_next_allowed_note(
    knowledge_side: KnowledgeSide,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    side = knowledge_side
    host = bound_host(side)
    note = archive_and_queue(side)
    hidden_at = note.created_at - timedelta(seconds=1)
    hidden_ids: list[VaultNoteId] = []
    with side.uow() as uow:
        cursor = uow.repo(EventReader).head_workspace_seq(side.workspace)
        for _ in range(500):
            uow.record(VaultNoteQueued(note))
        uow.commit()
    with side.uow() as uow:
        events = uow.repo(EventReader).after_workspace_seq(
            side.workspace,
            cursor,
            types=frozenset({VaultNoteQueued.event_type}),
            limit=500,
        )
        assert len(events) == 500
        repo = uow.repo(VaultNoteRepository)
        for event in events:
            hidden_id = VaultNoteId(uuid4())
            hidden_ids.append(hidden_id)
            assert repo.add(
                replace(
                    note,
                    id=hidden_id,
                    event_id=event.id,
                    source_id=uuid4(),
                    created_at=hidden_at,
                )
            )
        uow.commit()

    fetched: list[VaultNoteId] = []
    original = postgres_exports.note_from_row

    def observe_body_row(row: dict[str, Any]) -> VaultNote:
        candidate = original(row)
        fetched.append(candidate.id)
        return candidate

    query = ListPendingNotes(side.workspace, host, uuid4())
    with monkeypatch.context() as patch:
        patch.setattr(postgres_exports, "note_from_row", observe_body_row)
        first = side.app.bus.ask(query, actor=side.owner, meta=_meta(side, host))
    if side.backend == "postgres":
        assert fetched == sorted(hidden_ids)
    assert isinstance(first, PendingNotesView)
    assert first.items == ()
    assert first.has_more
    assert first.next_cursor is not None
    _assert_opaque_cursor(first.next_cursor, max(hidden_ids), hidden_at)

    ledger = side.app.bus.ask(ListVaultNotes(side.project, limit=1), actor=side.owner, meta=side.meta())
    assert isinstance(ledger, VaultNotesView)
    assert ledger.items == ()
    assert ledger.has_more
    assert ledger.next_cursor is not None
    _assert_opaque_cursor(ledger.next_cursor, min(hidden_ids), hidden_at)

    raw = bytearray(base64.urlsafe_b64decode(first.next_cursor))
    raw[len(raw) // 2] ^= 1
    tampered = base64.urlsafe_b64encode(raw).decode("ascii")
    for wrong in (
        replace(query, after=tampered),
        replace(query, after=first.next_cursor, vault_id=uuid4()),
        replace(query, after=ledger.next_cursor),
        ListVaultNotes(side.project, after=first.next_cursor),
    ):
        with pytest.raises(SkmError) as invalid:
            side.app.bus.ask(wrong, actor=side.owner, meta=_meta(side, host))
        assert invalid.value.code == ErrorCode.SCHEMA_INVALID
        assert invalid.value.details == {}
    second = side.app.bus.ask(
        replace(query, after=first.next_cursor), actor=side.owner, meta=_meta(side, host)
    )
    assert isinstance(second, PendingNotesView)
    assert tuple(item.note_id for item in second.items) == (note.id,)
    assert not second.has_more
    assert second.next_cursor is None


def _assert_opaque_cursor(cursor: str, hidden_id: VaultNoteId, hidden_at: datetime) -> None:
    decoded = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    micros = (hidden_at - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(microseconds=1)
    for private in (
        hidden_id.bytes,
        str(hidden_id).encode("ascii"),
        hidden_id.hex.encode("ascii"),
        hidden_at.isoformat().encode("ascii"),
        micros.to_bytes(8, "big", signed=True),
    ):
        assert private not in decoded
