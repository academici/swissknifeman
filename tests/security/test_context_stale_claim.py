"""Current claim fencing, immutable admission and deterministic PostgreSQL lock contention."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from threading import Event, current_thread
from typing import Any

import pytest

from contracts.context.test_owner_guard import dispatch, owned_draft, upload_prompt
from contracts.execution._worker_protocol_support import claim
from contracts.execution.harness import exec_side as exec_side
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.context.domain.finalize import sha256_text
from skm.modules.context.domain.manifest import ManifestState
from skm.modules.context.ports import ContextRepository, TextStore
from skm.modules.execution.domain.assignment import AssignmentState, reissue, transition_assignment
from skm.modules.execution.domain.attempt import ContinuationCause, SelectedStage, select_stage
from skm.modules.execution.domain.stage_record import interrupt_stage
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    RunRepository,
    StageRepository,
)
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "pg_session", "test_database"]


def expire(case: Any, *, reissue_lease: bool = False) -> Any:
    side = case.side
    with side.uow() as uow:
        repo = uow.repo(AssignmentRepository)
        saved = repo.get(case.assignment.id)
        expired = transition_assignment(saved, AssignmentState.EXPIRED)
        repo.save(expired, expected_version=saved.row_version)
        if side.kind == "postgres":
            now = uow.connection.execute("SELECT clock_timestamp()").fetchone()[0]
            uow.connection.execute(
                "UPDATE skm_execution.assignment_leases SET last_heartbeat_at=%s, expires_at=%s "
                "WHERE assignment_id=%s",
                (now - timedelta(seconds=2), now - timedelta(seconds=1), saved.id),
            )
        else:
            now = side.clock.now()
        successor = None
        if reissue_lease:
            stage = uow.repo(StageRepository).get(case.stage.id)
            uow.repo(StageRepository).save(interrupt_stage(stage, now=now))
            attempt = uow.repo(AttemptRepository).get(case.attempt.id)
            selected = SelectedStage(
                "execute", "agent_step", StageMode.NORMAL, 1, {}, None, None, FeedbackRefs(), None, None
            )
            updated = select_stage(
                attempt,
                cause=ContinuationCause("lease_recovery", "L1"),
                stage=selected,
                continuation_id=side.new_id(),
            )
            uow.repo(AttemptRepository).save(
                updated, expected_version=uow.repo(AttemptRepository).version(attempt.id)
            )
            successor = reissue(expired, new_id=side.new_id(), now=now, available_at=side.clock.now())
            repo.add(successor)
        uow.commit()
    return successor


@pytest.mark.parametrize("finalized", [False, True])
def test_expired_claim_cannot_finalize_or_replay(exec_side: Any, finalized: bool) -> None:
    case = owned_draft(exec_side)
    if finalized:
        dispatch(case)
    expire(case)
    with pytest.raises(SkmError) as caught:
        dispatch(case)
    assert caught.value.code is ErrorCode.LEASE_LOST
    with exec_side.uow(readonly=True) as uow:
        saved = uow.repo(ContextRepository).get(case.draft.manifest_id)
        assert saved.state is (ManifestState.FINAL if finalized else ManifestState.DRAFT)


def test_foreign_claim_and_stale_token_cannot_finalize(exec_side: Any) -> None:
    case = owned_draft(exec_side)
    for field in ("worker_id", "attempt_id", "assignment_id", "fencing_token"):
        cmd = deepcopy(case.command)
        cmd["claim"][field] = cmd["claim"][field] + 1 if field == "fencing_token" else str(exec_side.new_id())
        with pytest.raises(SkmError) as caught:
            dispatch(case, cmd)
        assert caught.value.code in {ErrorCode.FORBIDDEN, ErrorCode.NOT_FOUND, ErrorCode.LEASE_LOST}
        with exec_side.uow(readonly=True) as uow:
            assert uow.repo(ContextRepository).get(case.draft.manifest_id).state is ManifestState.DRAFT


def test_foreign_manifest_and_prompt_workspace_are_rejected(exec_side: Any) -> None:
    first, foreign = owned_draft(exec_side), owned_draft(exec_side)
    cmd = deepcopy(first.command)
    cmd["manifest_id"] = str(foreign.draft.manifest_id)
    with pytest.raises(SkmError) as caught:
        dispatch(first, cmd)
    assert caught.value.code in {ErrorCode.FORBIDDEN, ErrorCode.NOT_FOUND, ErrorCode.LEASE_LOST}
    cmd = deepcopy(first.command)
    cmd["prompt_file_version_id"] = upload_prompt(
        exec_side, first.final.rendered_prompt, workspace=exec_side.ws2, project=exec_side.proj2
    )
    with pytest.raises(SkmError) as caught:
        dispatch(first, cmd)
    assert caught.value.code is ErrorCode.NOT_FOUND


def test_lease_reissue_revokes_old_assignment_even_for_intrinsic_retry(exec_side: Any) -> None:
    case = owned_draft(exec_side)
    dispatch(case)
    successor = expire(case, reissue_lease=True)
    new = claim(exec_side)
    assert new["assignment_id"] == str(successor.id)
    assert new["fencing_token"] > case.claimed["fencing_token"]
    with pytest.raises(SkmError) as caught:
        dispatch(case)
    assert caught.value.code is ErrorCode.LEASE_LOST


@pytest.mark.parametrize("mutation", ["crlf", "newline", "unicode"])
def test_changed_exact_prompt_bytes_cannot_finalize(exec_side: Any, mutation: str) -> None:
    case = owned_draft(exec_side)
    prompt = case.final.rendered_prompt
    changed = {
        "crlf": prompt.replace("\n", "\r\n"),
        "newline": prompt + "\n",
        "unicode": prompt.replace("Привет", "Приве\u0301т"),
    }[mutation]
    assert changed.encode() != prompt.encode()
    cmd = deepcopy(case.command)
    cmd["prompt_file_version_id"] = upload_prompt(exec_side, changed)
    cmd["rendered_prompt_digest"] = sha256_text(changed)
    with pytest.raises(SkmError) as caught:
        dispatch(case, cmd)
    assert caught.value.code is ErrorCode.BLOB_DIGEST_MISMATCH
    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(ContextRepository).get(case.draft.manifest_id).state is ManifestState.DRAFT
        assert uow.repo(StageRepository).get(case.stage.id).state.value == "context_draft"


def test_absent_host_texts_are_trusted_worker_attestation(exec_side: Any) -> None:
    """Metadata/digests cannot prove an honest host read; the trust boundary is intentional."""
    case = owned_draft(exec_side, store_content=False)
    assert all("text" not in item for item in case.command["host_blocks"])
    assert dispatch(case)["state"] == "final"


def test_postfinalization_prompt_mutations_are_refused_before_runtime_start(exec_side: Any) -> None:
    case = owned_draft(exec_side)
    dispatch(case)
    prompt = case.final.rendered_prompt
    for changed in (prompt.replace("\n", "\r\n"), prompt + "\n", prompt.replace("Привет", "Приве\u0301т")):
        cmd = deepcopy(case.command)
        cmd["prompt_file_version_id"] = upload_prompt(exec_side, changed)
        cmd["rendered_prompt_digest"] = sha256_text(changed)
        with pytest.raises(SkmError) as caught:
            dispatch(case, cmd)
        assert caught.value.code is ErrorCode.INVALID_TRANSITION
    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(case.stage.id).state.value == "context_draft"


def test_server_text_mutation_is_rejected(exec_side: Any, monkeypatch: Any) -> None:
    case = owned_draft(exec_side)
    with exec_side.uow(readonly=True) as uow:
        cls = type(uow.repo(TextStore))
    original = cls.get_many

    def corrupted(self: Any, digests: Any) -> Any:
        return {key: text + "!" for key, text in original(self, digests).items()}

    monkeypatch.setattr(cls, "get_many", corrupted)
    with pytest.raises(SkmError) as caught:
        dispatch(case)
    assert caught.value.code is ErrorCode.CONTEXT_MANIFEST_TAMPERED


@pytest.mark.pg
@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_concurrent_reissue_and_finalize_have_one_lock_order_without_40p01(
    exec_side: Any,
    monkeypatch: Any,
) -> None:
    """Real claim/reissue and finalize wait on the same run lock on independent PG connections."""
    from skm.adapters.postgres.context.repositories import PostgresContextRepository
    from skm.adapters.postgres.execution.assignments import PostgresAssignmentRepository
    from skm.adapters.postgres.execution.runs_tasks import PostgresRunRepository

    case = owned_draft(exec_side)
    successor = expire(case, reissue_lease=True)
    entered_claim, entered_finalize, manifest_locked = Event(), Event(), Event()
    original_claim = PostgresAssignmentRepository._try_claim_candidate
    original_run, original_manifest = PostgresRunRepository.get, PostgresContextRepository.get

    def observed_claim(self: Any, *args: Any, **kwargs: Any) -> Any:
        entered_claim.set()
        return original_claim(self, *args, **kwargs)

    def observed_run(self: Any, identity: Any, *, for_update: bool = False) -> Any:
        if for_update and current_thread().name.startswith("finalizer"):
            entered_finalize.set()
        return original_run(self, identity, for_update=for_update)

    def observed_manifest(self: Any, identity: Any, *, for_update: bool = False) -> Any:
        if for_update:
            manifest_locked.set()
        return original_manifest(self, identity, for_update=for_update)

    monkeypatch.setattr(PostgresAssignmentRepository, "_try_claim_candidate", observed_claim)
    monkeypatch.setattr(PostgresRunRepository, "get", observed_run)
    monkeypatch.setattr(PostgresContextRepository, "get", observed_manifest)

    def finalizer() -> str:
        try:
            dispatch(case)
        except SkmError as exc:
            return exc.code.value
        return "unexpected success"

    with (
        exec_side.uow() as holder,
        ThreadPoolExecutor(max_workers=1) as claims,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="finalizer") as finalizers,
    ):
        holder.repo(RunRepository).get(case.run.id, for_update=True)
        pending_claim = claims.submit(claim, exec_side)
        pending_finalize = finalizers.submit(finalizer)
        try:
            assert entered_claim.wait(10)
            assert entered_finalize.wait(10)
            assert not manifest_locked.is_set()
        finally:
            holder.commit()
        new = pending_claim.result(timeout=20)
        assert pending_finalize.result(timeout=20) == "LEASE_LOST"
    assert new["assignment_id"] == str(successor.id)
    assert new["fencing_token"] > case.claimed["fencing_token"]
    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(ContextRepository).get(case.draft.manifest_id).state is ManifestState.DRAFT


@pytest.mark.pg
@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_waiting_finalizer_uses_database_expiry_after_execution_lock(
    exec_side: Any, monkeypatch: Any
) -> None:
    import psycopg

    from skm.adapters.postgres.execution.runs_tasks import PostgresRunRepository

    case = owned_draft(exec_side)
    entered = Event()
    original = PostgresRunRepository.get

    def observed(self: Any, identity: Any, *, for_update: bool = False) -> Any:
        if for_update and current_thread().name.startswith("expiry-finalizer"):
            entered.set()
        return original(self, identity, for_update=for_update)

    monkeypatch.setattr(PostgresRunRepository, "get", observed)

    def waiting() -> str:
        try:
            dispatch(case)
        except SkmError as exc:
            return exc.code.value
        return "unexpected success"

    with (
        exec_side.uow() as holder,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="expiry-finalizer") as pool,
    ):
        holder.repo(RunRepository).get(case.run.id, for_update=True)
        pending = pool.submit(waiting)
        try:
            assert entered.wait(10)
            with psycopg.connect(exec_side.dsn) as conn:
                conn.execute(
                    "UPDATE skm_execution.assignment_leases SET expires_at=clock_timestamp() "
                    "WHERE assignment_id=%s",
                    (case.assignment.id,),
                )
        finally:
            holder.commit()
        assert pending.result(timeout=20) == "LEASE_LOST"
