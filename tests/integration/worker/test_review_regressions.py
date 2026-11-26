"""Regressions for three reproduced major findings of an independent worker review."""

from dataclasses import replace
from uuid import UUID

import pytest

from skm.adapters.git.host_inputs import GitCheckoutReader
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, error_for
from skm.kernel.ids import AttemptId, WorkerId, WorkspaceId
from skm.modules.context.domain.blocks import BlockType, TrustLevel
from skm.modules.context.domain.draft import build_draft, host_input_to_json
from skm.modules.context.domain.host_inputs import (
    HostInputKind,
    HostInputRequest,
    HostReadStatus,
    HostSelector,
)
from skm.modules.context.public import collect_host_blocks
from skm.modules.execution.domain.ids import AssignmentId
from skm.modules.execution.domain.lease import WorkerClaim
from skm.modules.execution.host.context_inputs import finalize_stage_context
from skm.modules.execution.host.stage_client import BoundStageClient
from skm.modules.execution.host.worker_loop import run
from skm.platform.tokens.heuristic import HeuristicTokenEstimator

from ._support import make_host, result_scenario
from .test_worker_loop import documents


def host_request(path, *, kind=HostInputKind.REPOSITORY_PATH):
    return HostInputRequest(
        f"input:{path}",
        kind,
        "repo",
        path,
        (),
        HostSelector("whole"),
        65536,
        False,
        BlockType.RESEARCH if kind is HostInputKind.RESEARCH_QUERY else BlockType.MATERIALS,
        TrustLevel.EXTERNAL if kind is HostInputKind.RESEARCH_QUERY else TrustLevel.REPOSITORY,
        f"repo:{path}",
        False,
        (),
        None,
    )


@pytest.mark.parametrize("kind", [HostInputKind.REPOSITORY_PATH, HostInputKind.RESEARCH_QUERY])
def test_zero_budget_and_missing_research_produce_statuses_without_name_error(tmp_path, kind):
    (tmp_path / "input.txt").write_text("data")
    request = host_request("input.txt", kind=kind)
    (block,), _ = collect_host_blocks(
        (request,),
        GitCheckoutReader({"repo": tmp_path}),
        HeuristicTokenEstimator(),
        total_max_bytes=0,
        max_work_paths=10,
        repo_max_files=8,
        path_patterns=(),
        research={},
    )
    expected = (
        HostReadStatus.MISSING if kind is HostInputKind.RESEARCH_QUERY else HostReadStatus.BUDGET_EXCEEDED
    )
    assert block.status is expected
    assert block.text is None


def finalize_fixture(fixture, *, requests=(), patterns=(), checkout=None):
    draft = build_draft(
        {
            "manifest_id": fixture.ids["step"],
            "blocks": [],
            "host_inputs": [host_input_to_json(r) for r in requests],
        }
    )
    inputs = replace(fixture.services.context_inputs, decode=lambda _: draft)
    if checkout is not None:
        inputs = replace(inputs, checkout=lambda _: checkout)
    claim = WorkerClaim(
        AssignmentId(UUID(fixture.ids["assignment"])),
        AttemptId(UUID(fixture.ids["attempt"])),
        WorkerId(UUID(fixture.ids["worker"])),
        1,
    )
    finalize_stage_context(
        fixture.ctx,
        claim,
        fixture.client.begin,
        fixture.environment,
        inputs,
        workspace_id=WorkspaceId(UUID(fixture.ids["workspace"])),
        path_patterns=patterns,
    )
    return next(c for c, _ in fixture.client.calls if c["operation"] == "finalize_manifest")


def test_worker_refuses_missing_frozen_limits_before_read_or_publication(tmp_path, monkeypatch):
    fixture = make_host(tmp_path, monkeypatch)
    fixture.client.begin["step"]["context"].pop("host_limits")
    with pytest.raises(ValueError, match="frozen context host limits"):
        finalize_fixture(fixture)
    assert not fixture.published
    assert not any(c["operation"] == "finalize_manifest" for c, _ in fixture.client.calls)


@pytest.mark.parametrize("limit", [0, 4, 8])
def test_worker_respects_aggregate_configured_byte_budget_including_zero(tmp_path, monkeypatch, limit):
    fixture = make_host(tmp_path, monkeypatch)
    fixture.client.begin["step"]["context"]["host_limits"]["max_bytes"] = limit
    requests = tuple(host_request(f"{n}.txt") for n in range(3))
    for request in requests:
        (fixture.environment.mounts["repo"] / request.path).write_text("data")
    reader = GitCheckoutReader(fixture.environment.mounts)
    read = reader.read
    measured = []

    def counted(*args, **kwargs):
        value = read(*args, **kwargs)
        consumed = getattr(value, "bytes_read", None)
        assert isinstance(consumed, int)
        measured.append(consumed)
        return value

    monkeypatch.setattr(reader, "read", counted)
    command = finalize_fixture(fixture, requests=requests, checkout=reader)
    assert sum(measured) == limit
    assert len(measured) == limit // 4
    statuses = [block["status"] for block in command["host_blocks"]]
    assert statuses == ["ok"] * (limit // 4) + ["budget_exceeded"] * (3 - limit // 4)


def test_worker_uses_configured_work_path_limit(tmp_path, monkeypatch):
    fixture = make_host(tmp_path, monkeypatch)
    fixture.client.begin["step"]["context"]["host_limits"]["max_work_paths"] = 10
    for n in range(25):
        (fixture.environment.mounts["repo"] / f"{n:02}.txt").write_text("data")
    command = finalize_fixture(fixture, patterns=(("repo", "*.txt"),))
    facts = command["host_facts"]
    assert facts["work_paths_count"] == 10
    assert len(facts["work_paths"]) == 10
    assert facts["work_paths_truncated"] is True
    assert facts["work_paths"][0] == ["repo", "*.txt"]


@pytest.mark.parametrize("progress_kind", ["process", "last_runtime_event_at"])
@pytest.mark.parametrize("recover", [False, True])
def test_single_progress_error_does_not_discard_completed_fake_result(
    tmp_path, monkeypatch, progress_kind, recover
):
    fixture = make_host(
        tmp_path,
        monkeypatch,
        role="triager",
        scenario=result_scenario(tmp_path, "triager", documents()["triager"]),
    )
    original = BoundStageClient.report_progress
    injected, successes = [], []
    pending = False

    def renew(_):
        nonlocal pending
        if pending:
            pending = False
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "transient delivery failure")
        if injected:
            successes.append(True)
        return {"cancel_requested": False}

    fixture.client.renew = renew

    def report(worker, progress):
        nonlocal pending
        # Serialize the injected transport failure with the actual bound-client renewal state.
        with worker.guard:
            if progress_kind in progress and not injected:
                injected.append(progress_kind)
                pending = True
                try:
                    return original(worker, progress)
                except BackendUnavailable:
                    if recover:
                        worker.heartbeat()  # successful renewal before the stage observes the old error
                    raise
            return original(worker, progress)

    monkeypatch.setattr(BoundStageClient, "report_progress", report)
    summary = run(fixture.ctx, fixture.request)
    assert injected == [progress_kind]
    if recover:
        assert successes
    assert summary == {"outcome": "stopped", "assignments": 1}
    results = [c for c, _ in fixture.client.calls if c["operation"] == "record_stage_result"]
    assert len(results) == 1
    assert results[0]["outcome"]["role_result"] == documents()["triager"]
    assert results[0]["outcome_kind"] == "success"
    assert not any(c["operation"] == "report_attempt_failure" for c, _ in fixture.client.calls)


@pytest.mark.parametrize("failure", ["two_errors", "lease_lost"])
def test_progress_failure_threshold_still_prevents_stale_admission(tmp_path, monkeypatch, failure):
    fixture = make_host(
        tmp_path,
        monkeypatch,
        role="triager",
        scenario=result_scenario(tmp_path, "triager", documents()["triager"]),
    )
    original = BoundStageClient.report_progress
    count = 0

    def fail(_):
        nonlocal count
        count += 1
        if failure == "lease_lost":
            raise error_for(ErrorCode.LEASE_LOST, "fence lost")
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "transport unavailable")

    def report(worker, progress):
        with worker.guard:
            if "process" in progress or "last_runtime_event_at" in progress:
                fixture.client.renew = fail
            return original(worker, progress)

    monkeypatch.setattr(BoundStageClient, "report_progress", report)
    assert run(fixture.ctx, fixture.request)["reason"] == "lease_lost"
    assert count == (1 if failure == "lease_lost" else 2)
    assert not any(c["operation"] == "record_stage_result" for c, _ in fixture.client.calls)
    assert next(fixture.services.state_dir.rglob("raw.json")).exists()
