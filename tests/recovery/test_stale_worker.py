"""Late results cannot revive cancelled ownership or erase a durable output."""

import pytest

from contracts.execution._worker_protocol_support import begin, make_case
from fixtures.execution.harness import (
    clean_test_database,
    expire,
    pg_session,
    recovery,
    recovery_claim,
    test_database,
)
from fixtures.execution.protocol import agent, dispatch_result, finalize, handoff, seal_command
from skm.kernel.errors import SkmError
from skm.modules.execution.generated.commands import CancelRun
from skm.modules.execution.ports import AcceptanceRepository, OutputRepository, StageRepository

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = pytest.mark.pg


def test_expired_worker_result_is_refused_and_new_fence_records_result(recovery):
    side = recovery
    _, _, attempt, _ = make_case(side)
    old = recovery_claim(side)
    ready = begin(side, old)
    expire(side)
    fresh = recovery_claim(side)
    fresh_ready = begin(side, fresh)
    with pytest.raises(SkmError) as caught:
        dispatch_result(side, old, ready)
    assert caught.value.code.value == "LEASE_LOST"
    result = dispatch_result(side, fresh, fresh_ready)
    assert result["next"]
    with side.uow(readonly=True) as uow:
        assert len(uow.repo(StageRepository).history(attempt.id).entries) == 2


@pytest.mark.parametrize("sealed", [False, True])
def test_cancel_at_seal_and_result_boundaries_preserves_only_committed_evidence(recovery, sealed):
    side = recovery
    case = agent(side)
    finalize(side, case)
    handoff(side, case)
    command = seal_command(side, case)
    if sealed:
        side.worker1_client.dispatch(command, idempotency_key=f"seal:{side.new_id()}")
    side.client.dispatch(CancelRun(case.run.id, "cancel at result boundary"))
    for late in (command,):
        with pytest.raises(SkmError) as caught:
            side.worker1_client.dispatch(late, idempotency_key=f"late:{side.new_id()}")
        assert caught.value.code.value == "LEASE_LOST"
    with pytest.raises(SkmError):
        dispatch_result(
            side,
            case.claimed,
            case.ready,
            kind="success",
            outcome={"accepted": True, "status": "succeeded", "step_id": case.ready["step"]["step_id"]},
        )
    with side.uow(readonly=True) as uow:
        assert (uow.repo(OutputRepository).latest(case.attempt.id) is not None) is sealed
        assert not uow.repo(AcceptanceRepository).decisions_for_task(case.task.id)


@pytest.mark.parametrize("lost_visibility", [False, True], ids=["forged-stdout", "missing-transcript"])
def test_provider_claims_and_missing_transcript_never_create_acceptance(recovery, lost_visibility):
    import json

    from fixtures.execution.processes import scenario, script, worker
    from fixtures.execution.recovery_process import process_case, restore_subreaper

    side = recovery
    case = process_case(side)
    side.missing_visibility = lost_visibility
    path = scenario(
        side.root / "untrusted.toml",
        "executor",
        document=None
        if lost_visibility
        else {"accepted": True, "status": "succeeded", "checks": "all passed"},
    )
    plan = script(side.root / "visibility.toml", [("executor", case.task.display_key, 1, path)])
    try:
        with worker(side, side.root / f"repository-{case.attempt.id}", plan) as process:
            process.wait(timeout=120)
        with side.uow(readonly=True) as uow:
            entries = uow.repo(StageRepository).history(case.attempt.id).entries
            assert any(
                e.record.outcome_kind.value == "result_invalid" for e in entries if e.record.outcome_kind
            )
            steps = [s for entry in entries for s in entry.steps]
            assert any(s.usage is not None and s.usage.input_tokens == 10 for s in steps)
            assert all(s.state.value != "succeeded" for s in steps)
            assert uow.repo(OutputRepository).latest(case.attempt.id) is None
            assert not any(
                d.decision == "accepted"
                for d in uow.repo(AcceptanceRepository).decisions_for_task(case.task.id)
            )
            if lost_visibility:
                assert all(
                    s.transcript_file_version_id is None and s.runtime_observation is None for s in steps
                )
        calls = json.loads((side.root / "state/fake" / f"{case.run.id}.json").read_text())
        assert calls[json.dumps(["executor", case.task.display_key])] >= 1
    finally:
        restore_subreaper(case)
