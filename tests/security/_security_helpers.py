"""Shared authenticated boundary and canary fixtures for diagnostic privacy tests."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from contracts.execution.event_helpers import emit_core_history
from contracts.execution.harness import ExecSide
from contracts.execution.seed_helpers import (
    seed_attempt,
    seed_bundle,
    seed_run,
    seed_stage,
    seed_step,
    seed_task,
)
from contracts.runtimes.conftest import build
from integration.artifacts.test_upload_flow import add_file_dto
from integration.mcp.test_tools import authenticate
from security.api.harness import BASE, TestClient
from skm.adapters.secrets.env import EnvSecretResolver
from skm.application_bus.ports import AuditLog, AuditRecord
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.blobs import mount_blobs
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.ids import AttemptId, FileVersionId, RunId, TaskId
from skm.modules.access.public import CreateToken, CreateTokenResult
from skm.modules.artifacts.application.upload import bind_embedded_upload
from skm.modules.execution.domain.attempt import ContinuationCause, SelectedStage, StageContinuation
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.exports.domain.run_report import RunReportMetrics
from skm.platform.config.secrets import SecretResolvers
from skm.platform.logging.redaction import MASK, Redactor

REFERENCE = "secret://env/SKM_CANARY"
OWNER_AUDIT_BODY = "Owner-restricted operational audit evidence."


@dataclass(frozen=True, slots=True)
class Canaries:
    secret: str
    document: str
    redactor: Redactor


def canaries() -> Canaries:
    secret = f"fixture.value_{uuid4().hex}"
    document = f"The periwinkle fern lives beneath the staircase, inventory {uuid4()}."
    redactor = Redactor()
    resolver = SecretResolvers(
        [EnvSecretResolver({"SKM_CANARY": secret})], on_reveal=redactor.register_secret
    )
    return Canaries(resolver.resolve(REFERENCE).reveal(), document, redactor)


@contextmanager
def http_for(side: ExecSide, redactor: Redactor) -> Iterator[TestClient]:
    app = create_app(
        replace(side.app, authenticator=lambda secret: authenticate(side, secret)),
        route_table=build_route_table(MODULE_IDS),
        registry=side.app.bus._registry,
        no_background=True,
        redactor=redactor,
    )
    bus = side.app.bus
    upload, _ = bind_embedded_upload(
        side.app.uow_factory,
        bus._authorizer,
        bus._scopes,
        side.app.config,
        side.app.gateways,
        bus._clock,
        bus._ids,
        bus.dispatch,
        bus.ask,
    )
    mount_blobs(app, upload)
    with TestClient(app, base_url=BASE) as http:
        yield http


def token_for(side: ExecSide, **limits: Any) -> CreateTokenResult:
    token = side.client.dispatch(CreateToken(f"privacy-{uuid4()}", **limits))
    assert isinstance(token, CreateTokenResult)
    return token


def bearer(token: CreateTokenResult) -> dict[str, str]:
    return {"Authorization": f"Bearer {token.secret}"}


def web_metadata(http: TestClient, reader: CreateTokenResult, run: "PrivateRun") -> tuple[str, ...]:
    # These are the scoped metadata feeds used by RunPage and AttemptPage through useExecutionDetail.
    responses = [
        http.get("/api/v1/execution/detail", params={selector: str(identifier)}, headers=bearer(reader))
        for selector, identifier in (("run_id", run.run), ("attempt_id", run.attempt))
    ]
    assert all(response.status_code == 200 for response in responses)
    run_detail, attempt_detail = (response.json() for response in responses)
    assert run_detail["workflow"]["key"]
    assert run_detail["workflow"]["digest"]
    assert run_detail["run_id"] == attempt_detail["run_id"] == str(run.run)
    tasks = http.get(f"/api/v1/runs/{run.run}/tasks", headers=bearer(reader))
    assert tasks.status_code == 200
    assert [task["task_id"] for task in tasks.json()["tasks"]] == [str(run.task)]
    return (*[response.text for response in responses], tasks.text)


def run_metric_labels(metrics: RunReportMetrics) -> None:
    assert set(asdict(metrics)) == {
        "tasks_total",
        "tasks_accepted",
        "tasks_failed",
        "tasks_skipped",
        "first_pass_rate",
        "attempts_per_task",
        "check_fix_rounds",
        "review_rounds",
        "rework_rounds",
        "checks",
        "findings",
        "deviations_accepted",
        "decisions",
        "tokens",
        "usd",
        "known_usd_micros",
        "unknown_cost_steps",
        "active_seconds_by_group",
        "wall_seconds",
    }
    assert metrics.tasks_total == 1
    assert set(metrics.active_seconds_by_group) == {"executor"}
    assert metrics.checks == {}
    assert set(metrics.findings) == {"confirmed", "rejected", "by_severity"}
    severities = metrics.findings["by_severity"]
    assert isinstance(severities, dict)
    assert set(severities) == {"blocker", "major", "minor", "nit"}
    assert set(metrics.tokens) == {"input", "cached", "output", "unknown_steps"}
    assert set(metrics.decisions) == {"asked", "answered", "open"}


@dataclass(frozen=True, slots=True)
class PrivateRun:
    run: RunId
    task: TaskId
    attempt: AttemptId
    document_version: FileVersionId
    digest: str
    transcript_version: FileVersionId


def seed_private_run(side: ExecSide, root: Path, values: Canaries) -> PrivateRun:
    output = (
        json.dumps({"type": "text_delta", "text": f"observed {values.secret}"}).encode()
        + b'\n{"type":"fake_result","final_text":"done"}\n'
    )
    runtime = build(root, stdout=output, stderr=f"diagnostic {values.secret}\n".encode())
    resolver = SecretResolvers(
        [EnvSecretResolver({"SKM_CANARY": values.secret})], on_reveal=runtime.writer.register_secret
    )
    assert resolver.resolve(REFERENCE).reveal() == values.secret
    assert runtime.session.result().outcome == "completed"
    transcript = (runtime.writer.step_dir / "stream.jsonl").read_bytes()
    assert values.secret.encode() not in transcript
    assert MASK.encode() in transcript

    def upload(payload: bytes) -> tuple[FileVersionId, str]:
        ref = side.client.upload_blob(side.ws, [payload], size=len(payload), media_type="text/plain")
        added = cast("Any", side.client.dispatch(add_file_dto(side.ws, side.proj, ref)))
        return FileVersionId(added.file_version_id), ref.digest

    version, digest = upload(values.document.encode())
    transcript_version, _ = upload(transcript)
    manifest = side.make_final_manifest()
    with side.uow() as uow:
        run = seed_run(side, uow)
        seed_bundle(side, uow, run.id)
        task = seed_task(side, uow, run.id)
        selection = SelectedStage(
            "execute",
            "agent_step",
            StageMode.NORMAL,
            1,
            {"document": {"body": values.document}, "argv": ["read", values.secret]},
            side.clock.now(),
            None,
            FeedbackRefs(),
            None,
            None,
        )
        cursor = StageContinuation(1, side.new_id(), "stage", ContinuationCause("run_start", None), selection)
        attempt = seed_attempt(side, uow, run.id, task.id, continuation=cursor)
        stage = seed_stage(side, uow, attempt)
        step = seed_step(
            side,
            uow,
            attempt,
            stage,
            manifest_id=manifest,
            state=StepState.SUCCEEDED,
            transcript_fv_id=transcript_version,
            result={"nested": {"stdout": values.document, "error": values.secret}},
        )
        emit_core_history(side, uow, run.id, task.id, attempt.id, stage.id, step.id, manifest)
        uow.repo(AuditLog).append(
            AuditRecord(
                side.new_id(),
                side.ws,
                side.owner.principal_id,
                "execution.get_run_history",
                {"run_id": str(run.id), "owner_note": OWNER_AUDIT_BODY},
                "allowed",
                None,
                "audit-fixture",
                side.clock.now(),
            )
        )
        uow.commit()
    return PrivateRun(run.id, task.id, attempt.id, version, digest, transcript_version)


def check_run_metric_dimensions(exec_side: ExecSide, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from skm.modules.exports.application.queries import render_run_report
    from skm.modules.exports.domain.run_report import RunReportData
    from skm.modules.workspace.ports import ProjectRepository
    from skm.platform.logging.envelope import context_fields

    side, values = exec_side, canaries()
    token = token_for(side)
    processed = []
    aggregate = render_run_report.compute_metrics

    def observe(view: RunReportData) -> RunReportMetrics:
        metrics = aggregate(view)
        context = context_fields()
        processed.append(
            (view.run_id, view.project, context["request_id"], context["correlation_id"], metrics)
        )
        return metrics

    monkeypatch.setattr(render_run_report, "compute_metrics", observe)
    with http_for(side, values.redactor) as http:
        for i in range(4):
            request_id, correlation = str(uuid4()), str(uuid4())
            title = f"Project {uuid4()} / {values.document} {values.secret}"
            with side.uow() as uow:
                projects = uow.repo(ProjectRepository)
                project = projects.get(side.proj)
                projects.save(
                    replace(project, title=title, row_version=project.row_version + 1),
                    expected_version=project.row_version,
                )
                uow.commit()
            run = seed_private_run(side, tmp_path / str(i), values)
            report = http.get(
                f"/api/v1/runs/{run.run}/report.md",
                params={"variant": "full"},
                headers={**bearer(token), "X-Request-Id": request_id, "SKM-Correlation-Id": correlation},
            )
            assert report.status_code == 200, report.text
            assert report.headers["x-request-id"] == request_id
            assert len(processed) == i + 1
            run_id, project_title, actual_request, actual_correlation, metrics = processed[-1]
            assert (run_id, project_title, actual_request, actual_correlation) == (
                run.run,
                title,
                request_id,
                correlation,
            )
            run_metric_labels(metrics)
            encoded = json.dumps(asdict(metrics))
            for value in (
                request_id,
                correlation,
                title,
                values.document,
                values.secret,
                *map(str, (run.run, run.task, run.attempt)),
            ):
                assert value not in encoded


def check_uppercase_correlation_header(monkeypatch: pytest.MonkeyPatch) -> None:
    from io import StringIO

    from starlette.requests import Request
    from starlette.responses import JSONResponse

    from skm.entrypoints.api.request_context import RequestContext, request_meta
    from skm.platform.logging import setup
    from skm.platform.logging.logger import get_logger

    stream, correlation = StringIO(), str(uuid4())
    monkeypatch.setattr(setup._state, "settings", setup._state.settings)
    setup.configure_logging(
        level="info", detail="normal", fmt="json", stream=stream, redactor=Redactor(), host="local"
    )

    async def record(scope, receive, send):
        get_logger("entrypoints.api").info("api.request.completed")
        meta = request_meta(Request(scope))
        await JSONResponse({"correlation_id": meta.correlation_id})(scope, receive, send)

    client = TestClient(RequestContext(record, {}, Redactor()), base_url=BASE)
    response = client.get("/", headers={"SKM-Correlation-Id": correlation.upper()})
    assert response.status_code == 200
    assert response.json()["correlation_id"] == json.loads(stream.getvalue())["correlation_id"] == correlation
