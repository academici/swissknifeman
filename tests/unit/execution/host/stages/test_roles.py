"""Seven role contracts through the real stage and subprocess result pipeline."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from contracts.context.harness import core_pack
from contracts.execution._worker_protocol_support import ROOT, begin, claim, make_case
from contracts.execution.harness import exec_side as exec_side
from contracts.extensions.harness import pack_payload
from integration.artifacts.test_upload_flow import dispatch_new
from integration.worker._support import make_host, result_scenario
from integration.worker.test_worker_loop import documents
from skm.adapters.runtimes.codex.runtime import CodexRuntime
from skm.bootstrap.host_services import build_runtime_request, worker_concurrency, worker_schema_issues
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.isolation import IsolationProfile
from skm.modules.access import public as access
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.host.stages.agent_review import AgentReviewStage
from skm.modules.execution.host.stages.agent_step import AgentStepStage
from skm.modules.execution.host.stages.base import StageCapture
from skm.modules.execution.host.worker_loop import run
from skm.modules.execution.ports import RunRepository
from skm.modules.extensions import public as extensions
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.runtimes import public as runtimes
from skm.modules.runtimes.domain.catalog_records import HostModelAvailability, WorkerModelSnapshot
from skm.modules.runtimes.domain.detection import VerificationRecord
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.ports import (
    CapabilityCatalog,
    CapabilityVerificationRepository,
    HostModelAvailabilityRepository,
)
from skm.modules.settings import public as settings
from skm.modules.workspace import public as workspace
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database


def exercise(tmp_path: Any, monkeypatch: Any, role: str, document: Any, **options: Any) -> Any:
    """Observe real requests/outcomes without substituting the handler or result validator."""
    handler_type = AgentReviewStage if role == "reviewer" else AgentStepStage
    handler = handler_type(
        concurrency=worker_concurrency(),
        validate_result=worker_schema_issues,
        registrar_llm=options.pop("registrar_llm", True),
        output_manifest=lambda *_: {"tree_digest": "sha256:" + "f" * 64},
        **options,
    )
    fixture = make_host(
        tmp_path, monkeypatch, role=role, handler=handler, scenario=result_scenario(tmp_path, role, document)
    )
    fixture.requests, fixture.outcomes = [], []
    fixture.failures = []
    original = handler.run

    def observed(request: Any, deps: Any) -> Any:
        fixture.requests.append((request, deps))
        try:
            outcome = original(request, deps)
        except Exception as error:
            fixture.failures.append(repr(error))
            raise
        fixture.outcomes.append(outcome)
        return outcome

    handler.run = observed
    if role == "reviewer":
        fixture.client.response["instruction"]["stage_type"] = "agent_review"
        fixture.client.begin["review"] = {"review_id": fixture.ids["stage"]}
    fixture.client.response["task"].update(title="fix(execution): Preserve result evidence", work_kind="code")
    return fixture


@pytest.mark.parametrize("role", list(documents()))
def test_seven_roles_run_the_real_pipeline(tmp_path: Any, monkeypatch: Any, role: str) -> None:
    document = documents()[role]
    fixture = exercise(tmp_path, monkeypatch, role, document)
    run(fixture.ctx, fixture.request)
    outcome = fixture.outcomes[0]
    assert outcome.payload["role_result"] == document
    assert not worker_schema_issues(
        f"urn:skm:execution:stage-outcome-{'agent-review' if role == 'reviewer' else 'agent-step'}:v1",
        dict(outcome.payload),
    )
    assert json.loads(outcome.files[0].path.read_text()) == document
    assert outcome.usage.input_tokens == 10
    assert fixture.requests[0][0].context.rendered_prompt is not None
    assert (outcome.output_manifest is not None) == (role == "executor")


@pytest.mark.parametrize(
    ("verdict", "kind"),
    [
        ("green", StageOutcomeKind.VERDICT_GREEN),
        ("attention", StageOutcomeKind.VERDICT_ATTENTION),
        ("red", StageOutcomeKind.VERDICT_RED),
    ],
)
def test_review_verdict_and_report_identity(
    tmp_path: Any, monkeypatch: Any, verdict: str, kind: StageOutcomeKind
) -> None:
    document = {**documents()["reviewer"], "verdict": verdict}
    if verdict != "green":
        document["findings"] = [
            {
                "id": "F1",
                "severity": "blocker" if verdict == "red" else "major",
                "confidence": "high",
                "basis": "correctness",
                "category": "logic",
                "message": "Missing invariant",
                "failure_scenario": "Invalid input is accepted",
                "location": {"mount": "repo", "path": "src/app.py"},
            }
        ]
    fixture = exercise(tmp_path, monkeypatch, "reviewer", document)
    run(fixture.ctx, fixture.request)
    outcome = fixture.outcomes[0]
    assert outcome.kind is kind
    assert outcome.payload["review_id"] == fixture.ids["stage"]
    assert outcome.payload["session_ref"] is None
    assert outcome.files[-1].owner == f"review:{fixture.ids['stage']}"


def test_registrar_defaults_to_deterministic_without_starting_a_process(
    tmp_path: Any, monkeypatch: Any
) -> None:
    fixture = exercise(tmp_path, monkeypatch, "registrar", documents()["registrar"], registrar_llm=False)
    run(fixture.ctx, fixture.request)
    outcome = fixture.outcomes[0]
    assert outcome.kind is StageOutcomeKind.SUCCESS
    assert outcome.payload["role_result"]["commit"] == {
        "type": "fix",
        "scope": "execution",
        "subject": "Preserve result evidence",
        "body": "",
    }
    assert outcome.usage is None
    assert not list(fixture.services.state_dir.rglob("*.intent.json"))
    assert not any(c.get("progress", {}).get("process") for c, _ in fixture.client.calls)


def test_registrar_accepts_real_claim_assignment_task(
    exec_side: Any,
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    make_case(exec_side, stage_id="register", stage_type="agent_step", params={"role": "registrar"}, env=True)
    claimed = claim(exec_side)
    assert claimed.get("outcome") is None, claimed
    task = claimed["task"]
    assert set(task) == {
        "revision_id",
        "entity_id",
        "display_key",
        "kind",
        "declared_write_scope",
        "project_id",
        "integration_branch",
    }
    fixture = exercise(tmp_path, monkeypatch, "registrar", documents()["registrar"], registrar_llm=False)
    fixture.client.response["task"] = task
    run(fixture.ctx, fixture.request)
    assert fixture.outcomes, fixture.failures
    outcome = fixture.outcomes[0]
    assert outcome.kind is StageOutcomeKind.SUCCESS
    assert outcome.payload["role_result"]["commit"] == {
        "type": "chore",
        "subject": task["display_key"],
        "body": "",
    }
    request, _ = fixture.requests[0]
    assert "title" not in request.task
    assert "work_kind" not in request.task
    assert not any(c.get("progress", {}).get("process") for c, _ in fixture.client.calls)


@pytest.mark.parametrize(
    "verified_capability",
    [None, runtimes.Capability.USAGE_REPORTING, runtimes.Capability.CONFIG_ISOLATION],
    ids=["pure-degraded", "unrelated-evidence", "partially-degraded"],
)
def test_degraded_route_binds_only_relied_on_verification(
    exec_side: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    verified_capability: runtimes.Capability | None,
) -> None:
    caps = CodexRuntime().capabilities()
    verified_isolation = verified_capability is runtimes.Capability.CONFIG_ISOLATION
    if not verified_isolation:
        # Use an adapter declaration with no project settings to suppress.
        caps = replace(
            caps, self_loads=tuple(load for load in caps.self_loads if load.kind != "project_settings")
        )
    monkeypatch.setitem(
        exec_side.app.gateways.entries,
        CapabilityCatalog,
        runtimes.StaticCapabilityCatalog({"codex": caps}, {}),
    )
    pack = core_pack("1.2.0")
    files = {file.path: file.content.decode() for file in pack.files}
    files["runtimes/models.toml"] = (ROOT / "resources/packs/core/runtimes/models.toml").read_text()
    files["workflows/reviewed-development.toml"] = (
        (ROOT / "tests/fixtures/corpus/examples/execution/workflows/quick-fix.toml")
        .read_text()
        .replace('id = "quick-fix"', 'id = "reviewed-development"')
    )
    profile = "agent-profiles/executor.toml"
    files[profile] = files[profile].replace(
        "required_capabilities = []",
        'required_capabilities = ["workspace_binding", "reliable_cancellation"]',
    )
    exec_side.app.gateways.get(BuiltinPacks).current = (pack_payload("core", "1.2.0", files=files),)
    dispatch_new(exec_side.client, extensions.SyncBuiltinPacks())
    for key, value in {
        "runtimes.allowed": ["codex"],
        "runtimes.preference": ["codex"],
        "runtimes.degraded.allow": ["workspace_binding", "reliable_cancellation", "config_isolation"],
    }.items():
        exec_side.client.dispatch(
            settings.SetValue.from_json(
                {"scope": {"level": "instance"}, "key": key, "value": value, "expected_row_version": 0}
            ),
            idempotency_key=f"degraded-route:{key}",
        )
    context = runtimes.VerificationContext(
        exec_side.host1,
        "sha256:" + "a" * 64,
        "Linux",
        "test",
        "0.1.0",
        IsolationProfile.WORKTREE,
        "sha256:" + "b" * 64,
    )
    key = runtimes.verification_context_key(context)
    publisher = exec_side.worker1_client.ask(access.WhoAmI()).token
    assert publisher is not None
    with exec_side.uow() as uow:
        if exec_side.dsn is not None:
            exec_side.clock.set(uow.repo(RunRepository).now())
        registered = workspace.get_worker(uow, exec_side.worker1).capabilities
        now = exec_side.clock.now()
        expires = now + timedelta(minutes=5)
        installation = RuntimeInstallation(
            exec_side.host1,
            "codex",
            "0.165.0",
            None,
            AuthState.OK,
            now,
            {
                "binary_sha256": context.binary_sha256,
                "launch_config_digest": context.launch_config_digest,
                "adapter_version": context.adapter_version,
                "os_kernel": f"{context.os}/{context.kernel}",
                "verification_key": key,
            },
        )
        offer = HostModelAvailability(
            exec_side.host1, "codex", "gpt-6-sol", runtimes.Effort.HIGH, now, expires
        )
        assert uow.repo(HostModelAvailabilityRepository).replace_worker_snapshot(
            WorkerModelSnapshot(
                exec_side.worker1, publisher.token_id, now, expires, (installation,), (offer,)
            )
        )
        if verified_capability is not None:
            uow.repo(CapabilityVerificationRepository).add(
                VerificationRecord(
                    "codex",
                    "0.165.0",
                    context,
                    key,
                    runtimes.CapabilityRecord(
                        verified_capability,
                        runtimes.CapabilityStatus.ADAPTED,
                        "fixture:capability-verification",
                        "0.165.0",
                        "",
                        now.date(),
                        context,
                    ),
                    exec_side.owner.principal_id,
                )
            )
        uow.commit()
    exec_side.worker1_client.dispatch(
        workspace.RecordWorkerHeartbeat(
            exec_side.worker1, replace(registered, runtimes=(*registered.runtimes, "codex"))
        )
    )
    make_case(exec_side, stage_id="execute", stage_type="agent_step", params={"role": "executor"}, env=True)
    claimed = claim(exec_side, runtime_id="codex")
    assert "instruction" in claimed, claimed
    secret = str(access.generate_secret(lambda n: bytes([17]) * n))
    admitted = begin(exec_side, claimed, secret=secret)
    assert admitted["outcome"] == "ready", admitted
    step = admitted["step"]
    assert step["route"]["runtime_id"] == "codex"
    degraded = {"workspace_binding", "reliable_cancellation"}
    if not verified_isolation:
        degraded.add("config_isolation")
    assert set(step["context"]["draft"]["manifest"]["route"]["degraded"]) == degraded
    if not verified_isolation:
        assert step["route_snapshot"].get("verification_key") is None
        assert "verification_context" not in step["admission"]
        return

    assert step["route_snapshot"]["verification_key"] == key
    assert step["admission"]["verification_context"]["launch_config_digest"] == context.launch_config_digest
    fixture = exercise(tmp_path, monkeypatch, "executor", documents()["executor"])
    run(fixture.ctx, fixture.request)
    request, deps = fixture.requests[0]
    task = {
        **request.task,
        "host_id": str(exec_side.host1),
        "worker_id": str(exec_side.worker1),
        "attempt_id": claimed["attempt_id"],
        "run_id": claimed["run_id"],
        "task_id": claimed["task_id"],
        "task_key": "T1",
    }
    worker_request = build_runtime_request(
        replace(request, begin=admitted, task=task), deps, runtimes.SecretStr(secret), state_dir=tmp_path
    )
    assert worker_request.verification_context == context
    assert worker_request.verification_key == key

    runtime = CodexRuntime(binary=str(tmp_path / "unprobed-codex"))
    with pytest.raises(CapabilityUnavailable) as failure:
        runtime.start(worker_request)
    assert failure.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert failure.value.details["reason"] == "verified_runtime_not_probed"


@pytest.mark.parametrize(
    ("task", "subject", "kind"),
    [
        ({"display_key": "T1", "kind": "unit"}, "Task T1", "chore"),
        (
            {"entity_id": "01900000-0000-7000-8000-000000000001"},
            "01900000-0000-7000-8000-000000000001",
            "chore",
        ),
        ({"title": "", "display_key": "DOC-1", "kind": "docs"}, "DOC-1", "docs"),
    ],
)
def test_registrar_fallbacks_remain_schema_valid(
    tmp_path: Any,
    monkeypatch: Any,
    task: Any,
    subject: str,
    kind: str,
) -> None:
    fixture = exercise(tmp_path, monkeypatch, "registrar", documents()["registrar"], registrar_llm=False)
    fixture.client.response["task"] = task
    run(fixture.ctx, fixture.request)
    assert fixture.outcomes, fixture.failures
    assert fixture.outcomes[0].kind is StageOutcomeKind.SUCCESS
    assert fixture.outcomes[0].payload["role_result"]["commit"] == {
        "type": kind,
        "subject": subject,
        "body": "",
    }


def test_researcher_preserves_host_document_contract(tmp_path: Any, monkeypatch: Any) -> None:
    doc = {
        **documents()["researcher"],
        "claims": [{"text": "Evidence", "document_ids": ["01900000-0000-7000-8000-000000000001"]}],
        "unknowns": ["Missing replication"],
    }
    fixture = exercise(tmp_path, monkeypatch, "researcher", doc)
    run(fixture.ctx, fixture.request)
    assert fixture.outcomes[0].payload["role_result"] == doc


def test_default_registrar_needs_no_runtime_request(tmp_path: Any, monkeypatch: Any) -> None:
    fixture = exercise(tmp_path, monkeypatch, "registrar", documents()["registrar"], registrar_llm=False)
    run(fixture.ctx, fixture.request)
    original, deps = fixture.requests[0]
    root = tmp_path / "deterministic"
    root.mkdir()
    capture = StageCapture(root, fixture.services.storage, owner="registrar-test", max_bytes=16000, floor=0)
    request = replace(
        original,
        runtime_request=None,
        capture=capture,
        begin={**original.begin, "step": {"step_id": fixture.ids["step"], "role": "registrar"}},
    )
    try:
        handler = AgentStepStage(concurrency=worker_concurrency(), validate_result=worker_schema_issues)
        outcome = handler.run(request, deps)
        assert outcome.kind is StageOutcomeKind.SUCCESS
        document = outcome.payload["role_result"]
        assert isinstance(document, dict)
        commit = document["commit"]
        assert isinstance(commit, dict)
        assert commit["type"] == "fix"
        assert outcome.payload["step_id"] == fixture.ids["step"]
        assert outcome.usage is None
    finally:
        capture.close()


def test_triage_without_trusted_findings_never_clears_a_rejection(tmp_path: Any, monkeypatch: Any) -> None:
    doc = {
        **documents()["triager"],
        "confirmed": [],
        "rejected": [{"finding_id": "F1", "reason": "Unproved"}],
    }
    fixture = exercise(tmp_path, monkeypatch, "triager", doc)
    run(fixture.ctx, fixture.request)
    outcome = fixture.outcomes[0]
    assert outcome.payload["role_result"]["confirmed"] == [{"finding_id": "F1", "decision": "fix_now"}]
    assert outcome.payload["role_result"]["rejected"] == []
    assert json.loads(outcome.files[0].path.read_text()) == doc
    assert json.loads(outcome.payload["detail"])["triage"]["reverify"][0]["code"] == "TRIAGE_REPRO_UNVERIFIED"
