"""Host protocol against real fake subprocesses: context, handoff, stop mode and staged evidence."""

from __future__ import annotations

import json
from dataclasses import replace
from threading import Barrier
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, Forbidden, error_for
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import AttemptId, WorkerId, WorkspaceId
from skm.modules.execution.domain.ids import AssignmentId
from skm.modules.execution.host.context import WorkerServices
from skm.modules.execution.host.heartbeat import Heartbeat
from skm.modules.execution.host.stage_client import BoundStageClient
from skm.modules.execution.host.worker_loop import run

from ._support import make_host, result_scenario


def documents():
    result = {
        "scout": {"status": "complete", "summary": "Read", "relevant_paths": []},
        "executor": {
            "status": "done",
            "summary": "Fixed",
            "changed_paths": [],
            "checks_run": [],
            "open_issues": [],
            "self_check": {"performed": False},
        },
        "reviewer": {"verdict": "green", "summary": "Checked", "findings": [], "residual_risk": "None"},
        "triager": {
            "confirmed": [{"finding_id": "F1", "decision": "fix_now"}],
            "rejected": [],
            "summary": "Confirmed original finding without reproduction",
        },
        "advisor": {
            "mode": "advice",
            "problem_ref": "checks:1",
            "confidence": "high",
            "needs_owner": False,
            "rationale": "Evidence",
            "sources": [],
            "category": "local_reversible",
            "recommendation": {"text": "Continue"},
        },
        "researcher": {
            "status": "complete",
            "query": "fixture",
            "claims": [],
            "contradictions": [],
            "unknowns": [],
            "sources_used": [],
            "follow_up_queries": [],
        },
        "registrar": {"commit": {"type": "fix", "subject": "Fix answer", "body": ""}},
    }
    return {
        role: {"schema": f"urn:skm:execution:role-result:{role}:v1", **doc} for role, doc in result.items()
    }


@pytest.mark.parametrize("role", list(documents()))
def test_real_fake_runtime_all_roles_use_context_handoff_and_staged_evidence(tmp_path, monkeypatch, role):
    document = documents()[role]
    fixture = make_host(tmp_path, monkeypatch, role=role, scenario=result_scenario(tmp_path, role, document))
    if role == "registrar":
        monkeypatch.setattr(fixture.services.stages.for_stage("agent_step"), "registrar_llm", True)
    result = run(fixture.ctx, fixture.request)
    assert result == {"outcome": "stopped", "assignments": 1}
    calls = [call for call, _ in fixture.client.calls]
    ops = [c["operation"] for c in calls]
    assert ops.index("begin_stage") < ops.index("finalize_manifest") < ops.index("renew_lease")
    assert len(fixture.published) == 1
    recorded = next(c for c in calls if c["operation"] == "record_stage_result")
    assert recorded["outcome"]["role_result"] == document
    assert recorded["usage"]["input_tokens"] == 10
    assert recorded["evidence"][0]["role"] == "raw_result"
    assert "staged_blob" in recorded["evidence"][0]
    assert "file_version_id" not in json.dumps(recorded)
    assert all(not op.startswith("policy.") for op in ops)
    secret = next(c["runtime_token_secret"] for c in calls if c["operation"] == "begin_stage")
    assert secret not in repr(fixture.services)
    assert all(
        secret.encode() not in path.read_bytes()
        for path in fixture.services.state_dir.rglob("*")
        if path.is_file()
    )
    assert fixture.services.storage.snapshot(fixture.services.state_dir, min_free_bytes=0).reserved_bytes == 0


@pytest.mark.parametrize("refusal", [{"refusal": {"code": "BUDGET_EXHAUSTED"}}, {"cancel_requested": True}])
def test_refused_handoff_never_spawns(tmp_path, monkeypatch, refusal):
    fixture = make_host(tmp_path, monkeypatch)
    fixture.client.renew = lambda _: {**refusal, "next": {"kind": "release", "release_reason": "paused"}}
    monkeypatch.setattr(fixture.runtime, "start", lambda _: pytest.fail("spawn after refused handoff"))
    run(fixture.ctx, fixture.request)
    assert not any(c["operation"] == "record_stage_result" for c, _ in fixture.client.calls)
    assert any(c["operation"] == "release_assignment" for c, _ in fixture.client.calls)


def test_begin_response_loss_reuses_exact_secret_and_idempotency_key(tmp_path, monkeypatch):
    fixture = make_host(tmp_path, monkeypatch)
    fixture.client.fail_begin_once = True
    run(fixture.ctx, fixture.request)
    begins = [(c, key) for c, key in fixture.client.calls if c["operation"] == "begin_stage"]
    assert len(begins) == 2
    assert begins[0] == begins[1]


@pytest.mark.parametrize("reason", ["lease_lost", "user_cancel", "shutdown"])
def test_late_completed_runtime_is_retained_locally_without_admission(tmp_path, monkeypatch, reason):
    fixture = make_host(
        tmp_path,
        monkeypatch,
        role="executor",
        scenario=result_scenario(tmp_path, "executor", documents()["executor"]),
    )
    original = fixture.runtime.result

    def result(handle):
        value = original(handle)
        assert value.outcome == "completed"
        fixture.shutdown.cancel(reason)
        return value

    monkeypatch.setattr(fixture.runtime, "result", result)
    summary = run(fixture.ctx, fixture.request)
    assert summary["reason"] == reason
    assert len(fixture.client.uploads) == 1  # prompt was staged before the cancellation
    assert not any(c["operation"] == "record_stage_result" for c, _ in fixture.client.calls)
    journal = next(fixture.services.state_dir.rglob("journal.json"))
    assert json.loads(journal.read_text())["stage_record_id"] == fixture.ids["stage"]
    assert journal.with_name("raw.json").exists()
    assert journal.with_name("environment.patch").exists()
    if reason == "shutdown":
        failed = next(c for c, _ in fixture.client.calls if c["operation"] == "report_attempt_failure")
        assert failed["error_class"] == "worker_shutdown"
        assert failed["usage"]["input_tokens"] == 10
    else:
        assert not any(c["operation"] == "report_attempt_failure" for c, _ in fixture.client.calls)


def test_loss_after_output_sealed_preserves_seal_without_stale_result(tmp_path, monkeypatch):
    fixture = make_host(
        tmp_path,
        monkeypatch,
        role="executor",
        scenario=result_scenario(tmp_path, "executor", documents()["executor"]),
    )
    fixture.client.on_seal = lambda: fixture.shutdown.cancel("lease_lost")
    assert run(fixture.ctx, fixture.request)["reason"] == "lease_lost"
    assert fixture.client.sealed["tree_digest"] == "sha256:" + "f" * 64
    assert len(fixture.client.uploads) == 1  # prompt was staged before the cancellation
    assert not any(c["operation"] == "record_stage_result" for c, _ in fixture.client.calls)
    assert next(fixture.services.state_dir.rglob("raw.json")).exists()


def test_two_renewal_errors_or_one_lease_lost_latches_stop_and_snapshot(tmp_path, monkeypatch):
    from skm.kernel.cancel import CancelSource
    from skm.modules.execution.domain.lease import WorkerClaim

    fixture = make_host(tmp_path, monkeypatch)
    source = CancelSource()
    claim = WorkerClaim(
        AssignmentId(UUID(fixture.ids["assignment"])),
        AttemptId(UUID(fixture.ids["attempt"])),
        WorkerId(UUID(fixture.ids["worker"])),
        1,
    )
    worker = BoundStageClient(
        fixture.client,
        claim,
        fixture.services.commands,
        source.token,
        source.cancel,
        concurrency=fixture.services.concurrency,
    )
    heartbeat = Heartbeat(worker, source, every_seconds=0.01, concurrency=fixture.services.concurrency)
    fixture.client.renew = lambda _: {"snapshot_requested": True}
    heartbeat.tick()
    assert heartbeat.snapshot_requested.is_set()

    def fail(_):
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "transport failed")

    fixture.client.renew = fail
    heartbeat.tick()
    assert not source.token.cancelled
    heartbeat.tick()
    assert source.token.reason == "lease_lost"
    count = len(fixture.client.calls)
    heartbeat.tick()
    assert len(fixture.client.calls) == count
    source = CancelSource()
    worker = BoundStageClient(
        fixture.client,
        claim,
        fixture.services.commands,
        source.token,
        source.cancel,
        concurrency=fixture.services.concurrency,
    )
    heartbeat = Heartbeat(worker, source, every_seconds=0.01, concurrency=fixture.services.concurrency)
    fixture.client.renew = lambda _: (_ for _ in ()).throw(error_for(ErrorCode.LEASE_LOST, "fence lost"))
    heartbeat.tick()
    assert source.token.reason == "lease_lost"


def test_capacity_slots_have_independent_cancellation_context_and_worktrees(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    fixtures = [
        make_host(
            path,
            monkeypatch,
            role="registrar",
            scenario=result_scenario(path, "registrar", documents()["registrar"]),
        )
        for path in (left, right)
    ]
    barrier = Barrier(2)
    for f in fixtures:
        f.entries[type(f.services)] = replace(f.services, tick=lambda: barrier.wait(timeout=10))
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(run, tuple(f.ctx for f in fixtures), fixtures[0].request).result(timeout=20)
    slots = result["slots"]
    assert isinstance(slots, list)
    assert len(slots) == 2
    assert fixtures[0].environment.mounts != fixtures[1].environment.mounts
    assert fixtures[0].ctx.cancel is not fixtures[1].ctx.cancel


def test_unconfirmed_cleanup_retains_late_bytes_and_blocks_next_claim(tmp_path, monkeypatch):
    from skm.modules.runtimes.domain.detection import CancellationResult

    fixture = make_host(
        tmp_path,
        monkeypatch,
        role="registrar",
        scenario=result_scenario(tmp_path, "registrar", documents()["registrar"]),
    )
    monkeypatch.setattr(fixture.services.stages.for_stage("agent_step"), "registrar_llm", True)
    original = fixture.runtime.cancel

    def uncertain(handle, *, grace_seconds):
        original(handle, grace_seconds=grace_seconds)
        return CancellationResult(False, "SIGKILL", True)

    monkeypatch.setattr(fixture.runtime, "cancel", uncertain)
    fixture.request["max_assignments"] = 2
    assert run(fixture.ctx, fixture.request)["reason"] == "cleanup_unconfirmed"
    assert next(fixture.services.state_dir.rglob("raw.json")).exists()
    assert len([c for c, _ in fixture.client.calls if c["operation"] == "claim_assignment"]) == 1
    assert not any(c["operation"] == "record_stage_result" for c, _ in fixture.client.calls)


def test_stage_context_keeps_frozen_instructions_and_soft_warnings_out_of_emergency_limits(
    tmp_path, monkeypatch
):
    import hashlib

    from skm.modules.context.domain.draft import build_draft

    fixture = make_host(
        tmp_path,
        monkeypatch,
        role="registrar",
        scenario=result_scenario(tmp_path, "registrar", documents()["registrar"]),
    )
    monkeypatch.setattr(fixture.services.stages.for_stage("agent_step"), "registrar_llm", True)
    frozen = (
        "Frozen instructions: preserve API. Warning: expected time/tokens exceeded; continue useful work."
    )
    draft = build_draft(
        {
            "manifest_id": str(UUID(fixture.ids["step"])),
            "blocks": [
                {
                    "ordinal": 0,
                    "block_type": "task_contract",
                    "budget_class": "core",
                    "mandatory": True,
                    "source_kind": "derived",
                    "source_ref": "task:contract",
                    "trust": "system",
                    "atomic_group": None,
                    "source_version": None,
                    "content": frozen,
                    "content_digest": "sha256:" + hashlib.sha256(frozen.encode()).hexdigest(),
                    "tokens_estimate": 40,
                    "reason": "mandatory",
                }
            ],
        }
    )
    services = replace(
        fixture.services, context_inputs=replace(fixture.services.context_inputs, decode=lambda _: draft)
    )
    fixture.entries[type(services)] = services
    original = fixture.runtime.start
    seen = []

    def start(request):
        seen.append(request)
        assert frozen in request.rendered_prompt
        assert request.limits.timeout_seconds == 30
        assert not request.extra_env
        return original(request)

    monkeypatch.setattr(fixture.runtime, "start", start)
    assert run(fixture.ctx, fixture.request).get("reason") is None
    assert len(seen) == 1
    assert not seen[0].secret_env  # host drops its per-step secret binding after terminal processing


def test_unreaped_check_from_existing_runner_blocks_result_and_next_claim(tmp_path, monkeypatch):
    from skm.modules.execution.domain.stage_record import StageOutcomeKind
    from skm.modules.execution.host.stages.base import StageOutcome

    class UnreapedChecks:
        stage_type = "run_checks"
        side = "host"
        params_schema_urn = "urn:skm:execution:workflow:v1#/$defs/params"

        def run(self, request, deps):
            return StageOutcome(StageOutcomeKind.CHECKS_UNKNOWN, {"error_code": "CHECK_CLEANUP_UNCONFIRMED"})

    fixture = make_host(tmp_path, monkeypatch, handler=UnreapedChecks())
    fixture.client.response["instruction"]["stage_type"] = "run_checks"
    fixture.client.begin.pop("step")
    fixture.request["max_assignments"] = 2
    assert run(fixture.ctx, fixture.request)["reason"] == "cleanup_unconfirmed"
    assert len([c for c, _ in fixture.client.calls if c["operation"] == "claim_assignment"]) == 1
    assert not any(c["operation"] == "record_stage_result" for c, _ in fixture.client.calls)


def test_completed_stage_replay_observes_lease_loss_while_acquiring_guard(tmp_path, monkeypatch):
    fixture = make_host(tmp_path, monkeypatch)
    fixture.client.begin.update(already_completed=True, prior_outcome={})
    fixture.client.renew = lambda _: (_ for _ in ()).throw(error_for(ErrorCode.LEASE_LOST, "stale fence"))

    def start(heartbeat):
        # Schedule a real renewal at the next acquisition after BeginStage returned.
        original = heartbeat.worker.guard

        class Interleaving:
            def __enter__(self):
                if fixture.client.calls[-1][0]["operation"] == "begin_stage":
                    heartbeat.worker.guard = original
                    heartbeat.tick()
                return original.__enter__()

            def __exit__(self, *args):
                return original.__exit__(*args)

        heartbeat.worker.guard = Interleaving()

    monkeypatch.setattr(Heartbeat, "start", start)
    assert run(fixture.ctx, fixture.request)["reason"] == "lease_lost"
    assert [c["operation"] for c, _ in fixture.client.calls] == [
        "claim_assignment",
        "begin_stage",
        "renew_lease",
    ]


def test_disconnected_worker_with_cached_policy_does_not_claim(tmp_path, monkeypatch):
    fixture = make_host(tmp_path, monkeypatch)
    services = replace(fixture.services, refresh_config=lambda: False)
    ctx = replace(
        fixture.ctx, gateways=GatewayTable({**fixture.entries, WorkerServices: services}, "host_gateway")
    )
    result = run(ctx, {**fixture.request, "once": True})
    assert result == {"outcome": "stopped", "reason": "backend_unavailable", "assignments": 0}
    assert fixture.client.calls == []


def test_worker_rejects_other_workspace_before_claim(tmp_path, monkeypatch):
    fixture = make_host(tmp_path, monkeypatch)
    services = replace(fixture.services, workspace_id=WorkspaceId(UUID(fixture.ids["workspace"])))
    ctx = replace(
        fixture.ctx, gateways=GatewayTable({**fixture.entries, WorkerServices: services}, "host_gateway")
    )
    with pytest.raises(Forbidden) as denied:
        run(ctx, {**fixture.request, "workspace_id": fixture.ids["worker"]})
    assert denied.value.code is ErrorCode.FORBIDDEN
    assert fixture.client.calls == []


def test_machine_model_is_rechecked_after_finalize_before_handoff(tmp_path, monkeypatch):
    fixture = make_host(tmp_path, monkeypatch)
    model_checks: list[str] = []

    def withdraw(request, _digest):
        assert fixture.published
        assert not request.secret_env
        model_checks.append(request.model)
        raise error_for(ErrorCode.CAPABILITY_UNAVAILABLE, "Machine operator withdrew the model")

    services = replace(fixture.services, verify_runtime=withdraw)
    ctx = replace(
        fixture.ctx, gateways=GatewayTable({**fixture.entries, WorkerServices: services}, "host_gateway")
    )
    monkeypatch.setattr(fixture.runtime, "start", lambda _: pytest.fail("spawn after model withdrawal"))
    result = run(ctx, fixture.request)
    assert model_checks
    assert result["reason"] == "host_failure"
    assert all(
        command.get("progress", {}).get("phase") != "runtime_started" for command, _ in fixture.client.calls
    )
