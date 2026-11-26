"""Admission deadlines, stale epochs and crash reconciliation against real local Git."""

from uuid import uuid4

import pytest

from integration.git.test_integration import NOW, make_case, ownership, prepare, publish
from skm.adapters.git.integration import GitIntegrator
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.ids import ExternalEffectId


def successor(case):
    case.effect = ExternalEffectId(uuid4())
    case.slot = {**case.slot, "fencing_token": case.slot["fencing_token"] + 1}
    case.client.admission["slot_fencing_token"] = case.slot["fencing_token"]
    case.inputs = {
        **case.inputs,
        "process_ownership": ownership(case.effect, case.inputs["attempt_id"], case.tmp),
    }


@pytest.mark.parametrize(
    "admission",
    [
        None,
        {},
        {"slot_fencing_token": 99},
        {"request_digest": "sha256:" + "0" * 64},
        {"effect_id": str(uuid4())},
    ],
)
def test_missing_cached_or_changed_admission_never_moves_target(tmp_path, admission):
    case = make_case(tmp_path)
    request = prepare(case)
    original = case.client.record_effect

    def guard(report):
        response = original(report)
        if report["phase"] == "executing":
            if admission is None:
                response["admission"] = None
            elif not admission:
                response["cached"] = True
            else:
                response["admission"].update(admission)
        return response

    case.client.record_effect = guard
    with pytest.raises(SkmError) as caught:
        publish(case, request)
    assert caught.value.code.value == "LEASE_LOST"
    assert case.git.run(case.repo, ["rev-parse", "integration"]).stdout.strip() == case.before


def test_delayed_admission_uses_request_start_not_response_time(tmp_path):
    case = make_case(tmp_path)
    request = prepare(case)
    case.client.delay = 5.001
    with pytest.raises(SkmError) as caught:
        publish(case, request)
    assert caught.value.code.value == "LEASE_LOST"
    assert case.git.run(case.repo, ["rev-parse", "integration"]).stdout.strip() == case.before


def test_successor_epoch_rejects_paused_old_candidate_before_admission(tmp_path):
    case = make_case(tmp_path)
    old_request, old_effect, old_slot = prepare(case), case.effect, case.slot
    successor(case)
    new_request = prepare(case)
    with pytest.raises(SkmError) as caught:
        case.writer.publish_integration(case.repo, old_effect, old_request, slot=old_slot, client=case.client)
    assert caught.value.code.value == "LEASE_LOST"
    assert not case.client.calls
    publish(case, new_request)


@pytest.mark.parametrize("crash_after_refs", [False, True])
def test_supervisor_restart_blocks_until_helper_quiescent_then_reconciles(
    tmp_path, monkeypatch, crash_after_refs
):
    case = make_case(tmp_path)
    request, effect = prepare(case), case.effect
    from skm.adapters.git import integration

    run = integration.run_ref_transaction

    def crash(*args, **kwargs):
        if crash_after_refs:
            run(*args, **kwargs)
        raise ConnectionError("supervisor vanished with unresolved helper")

    monkeypatch.setattr(integration, "run_ref_transaction", crash)
    with pytest.raises(ConnectionError):
        publish(case, request)
    monkeypatch.setattr(integration, "run_ref_transaction", run)
    case.writer = GitIntegrator(
        case.git, worktrees_root=tmp_path / "owned", now=lambda: NOW, monotonic=lambda: 0
    )
    successor(case)
    with pytest.raises(SkmError) as caught:
        prepare(case)
    assert caught.value.code.value == "OUTCOME_UNKNOWN"
    result = case.writer.reconcile_integration(case.repo, effect, request)
    assert result["state"] == "outcome_unknown"
    recovered = GitIntegrator(
        case.git,
        worktrees_root=tmp_path / "owned",
        now=lambda: NOW,
        monotonic=lambda: 0,
        quiescent=lambda _: True,
    )
    reconciled = recovered.reconcile_integration(case.repo, effect, request)
    assert reconciled["state"] == ("succeeded" if crash_after_refs else "failed")
    case.writer = recovered
    prepare(case)


def test_db_receipt_loss_reconciles_without_second_ref_io(tmp_path):
    case = make_case(tmp_path)
    request = prepare(case)
    case.client.fail_result = True
    with pytest.raises(ConnectionError):
        publish(case, request)
    case.writer = GitIntegrator(
        case.git, worktrees_root=tmp_path / "owned", now=lambda: NOW, monotonic=lambda: 0
    )
    assert case.writer.reconcile_integration(case.repo, case.effect, request)["state"] == "succeeded"
    phases = len(case.client.calls)
    receipt = publish(case, request)
    assert receipt.after_sha == request.after_sha
    assert len(case.client.calls) == phases


def test_git_helper_identity_and_actual_group_are_durable_before_ref_stdin(tmp_path, monkeypatch):
    import json
    import os

    from skm.adapters.git import integration_process
    from skm.platform.process.identity import identity_of

    case = make_case(tmp_path)
    request = prepare(case)
    journals = list((case.repo / ".git/skm-integration").glob(f"*/{case.effect}.json"))
    assert len(journals) == 1
    spawn = integration_process.processes.spawn
    observed = []

    def gated(argv, **kwargs):
        journal = json.loads(journals[0].read_bytes())
        assert journal["state"] == "consumed"
        assert journal["reaped"] is False
        assert journal["ownership"] == case.inputs["process_ownership"]
        process = spawn(argv, **kwargs)
        write = process.write_stdin

        def release(data):
            saved = json.loads(journals[0].read_bytes())
            identity = saved["process"]
            assert identity["pid"] == process.pid == identity["pgid"] == os.getpgid(process.pid)
            assert identity["boot_id"] == process.identity.boot_id
            assert identity["start_ticks"] == process.identity.start_ticks
            assert identity_of(process.pid) == process.identity
            assert case.git.run(case.repo, ["rev-parse", "integration"]).stdout.strip() == case.before
            observed.append(identity)
            write(data)

        process.write_stdin = release
        return process

    monkeypatch.setattr(integration_process.processes, "spawn", gated)
    receipt = publish(case, request)
    assert len(observed) == 1
    saved = json.loads(journals[0].read_bytes())
    assert saved["reaped"] is True
    assert saved["state"] == "published"
    assert saved["process"] == observed[0]
    assert receipt.after_sha == request.after_sha


def test_identity_persistence_failure_cannot_release_git_transaction(tmp_path, monkeypatch):
    from skm.adapters.git import integration

    case = make_case(tmp_path)
    request = prepare(case)
    save = case.writer._save

    def failed(path, journal):
        if "process" in journal:
            raise OSError("identity fsync failed")
        save(path, journal)

    monkeypatch.setattr(case.writer, "_save", failed)
    with pytest.raises(OSError, match="identity fsync failed"):
        publish(case, request)
    assert case.git.run(case.repo, ["rev-parse", "integration"]).stdout.strip() == case.before
    monkeypatch.setattr(case.writer, "_save", save)
    case.writer = integration.GitIntegrator(
        case.git, worktrees_root=case.tmp / "owned", now=lambda: NOW, monotonic=lambda: 0
    )
    successor(case)
    with pytest.raises(SkmError) as blocked:
        prepare(case)
    assert blocked.value.code.value == "OUTCOME_UNKNOWN"


@pytest.mark.parametrize("kind", ["cgroup", "container"])
def test_unavailable_git_containment_never_claims_a_different_backend(tmp_path, kind):
    case = make_case(tmp_path)
    case.inputs["process_ownership"].update(kind=kind, ref="foreign-containment")
    if kind == "container":
        case.inputs["process_ownership"]["daemon_identity"] = "test-daemon"
    request = prepare(case)
    with pytest.raises(SkmError) as rejected:
        publish(case, request)
    assert rejected.value.code.value == "CAPABILITY_UNAVAILABLE"
    assert case.git.run(case.repo, ["rev-parse", "integration"]).stdout.strip() == case.before
    assert not case.client.calls


def test_partial_refs_remain_unknown_and_block_next_generation(tmp_path):
    case = make_case(tmp_path)
    request = prepare(case)
    receipt = publish(case, request)
    case.git.run(case.repo, ["update-ref", "-d", receipt.receipt_ref, receipt.receipt_commit_sha])
    assert case.writer.reconcile_integration(case.repo, case.effect, request)["state"] == "outcome_unknown"
    successor(case)
    with pytest.raises(SkmError):
        prepare(case)


def test_consumed_admission_cannot_be_reused_by_another_effect(tmp_path):
    case = make_case(tmp_path)
    case.client.admission["admission_id"] = str(uuid4())
    publish(case, prepare(case))
    successor(case)
    request = prepare(case)
    with pytest.raises(SkmError) as caught:
        publish(case, request)
    assert caught.value.code.value == "LEASE_LOST"


def test_slot_change_between_intended_and_executing_refuses_io(tmp_path):
    case = make_case(tmp_path)
    request = prepare(case)
    original = case.client.record_effect

    def changed(report):
        if report["phase"] == "executing":
            from skm.kernel.error_codes import ErrorCode
            from skm.kernel.errors import error_for

            raise error_for(ErrorCode.LEASE_LOST, "slot changed after intended")
        return original(report)

    case.client.record_effect = changed
    with pytest.raises(SkmError):
        publish(case, request)
    assert case.git.run(case.repo, ["rev-parse", "integration"]).stdout.strip() == case.before


def test_task_trailer_without_protected_receipt_never_proves_a_green_range(tmp_path):
    case = make_case(tmp_path)
    request = prepare(case)
    # A raw output or a forged task trailer is insufficient evidence of publication.
    case.git.run(case.repo, ["update-ref", "refs/heads/integration", case.head, case.before])
    result = case.writer.reconcile_integration(case.repo, case.effect, request)
    assert result["state"] == "outcome_unknown"
    assert "receipt" not in result


def test_target_file_lock_serializes_parallel_writers_while_admission_is_in_flight(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from skm.platform.fs.file_lock import LockTimeout

    case = make_case(tmp_path)
    request = prepare(case)
    entered, release = Event(), Event()
    original = case.client.record_effect

    def blocked(report):
        response = original(report)
        if report["phase"] == "executing":
            entered.set()
            assert release.wait(10)
        return response

    case.client.record_effect = blocked
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(publish, case, request)
        try:
            assert entered.wait(10)
            successor(case)
            with pytest.raises(LockTimeout):
                prepare(case)
        finally:
            release.set()
        receipt = running.result(timeout=10)
    assert receipt.after_sha == request.after_sha


def test_lost_publish_receipt_survives_successor_slot_fence(tmp_path):
    case = make_case(tmp_path)
    old_request, old_effect, old_slot = prepare(case), case.effect, case.slot
    case.client.fail_result = True
    with pytest.raises(ConnectionError):
        publish(case, old_request)
    after = case.git.run(case.repo, ["rev-parse", "integration"]).stdout.strip()
    assert after != case.before
    receipt_ref = f"refs/skm/effects/{old_effect}"
    receipt = case.git.run(case.repo, ["rev-parse", receipt_ref]).stdout.strip()

    successor(case)
    phases = len(case.client.calls)
    replay = case.writer.publish_integration(
        case.repo, old_effect, old_request, slot=old_slot, client=case.client
    )
    assert replay.after_sha == after
    assert len(case.client.calls) == phases
    assert case.git.run(case.repo, ["rev-parse", "integration"]).stdout.strip() == after
    assert case.git.run(case.repo, ["rev-parse", receipt_ref]).stdout.strip() == receipt
