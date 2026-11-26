"""Worker admission and token rotation serialize at the credential row."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Event
from time import monotonic, sleep
from typing import Any, Literal, cast
from uuid import UUID

import psycopg
import pytest

from contracts.execution._client_execution import (
    ClientWorker,
    begin_command,
    configure_execution,
    model_snapshot,
    prepare_agent_request,
    register_worker,
    schedule,
    start_run_command,
)
from contracts.execution.test_client_worker_protocol import worker_plan
from integration.artifacts.test_upload_flow import dispatch_new
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.access.public import RotateToken, RotateTokenResult, WhoAmI, WhoAmIView
from skm.modules.execution import public as execution
from skm.modules.execution.application.commands import claim_assignment, renew_lease
from skm.modules.execution.domain.ids import StageRecordId
from skm.modules.execution.ports import StageRepository
from support.backend import ClientBackend, client_backend
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "client_backend", "pg_session", "test_database"]


def _rotate(side: ClientBackend, worker: ClientWorker) -> ClientWorker:
    credential = cast("WhoAmIView", worker.client.ask(WhoAmI())).token
    assert credential is not None
    result = cast(
        "RotateTokenResult", worker.client.dispatch(RotateToken(credential.token_id, grace_minutes=1))
    )
    return replace(worker, client=side.client(token=result.secret), token=result.secret)


def _case(side: ClientBackend, transition: Literal["claim", "handoff"]):
    owner = side.client()
    repo = configure_execution(side, owner)
    worker = register_worker(side, owner, "rotation-race")
    plan, revision = worker_plan(side)
    run = dispatch_new(owner, start_run_command(plan, revision, "P1.1"))
    schedule(side)
    if transition == "claim":
        return worker, run.run_id, worker.claim(), None
    claim = dispatch_new(worker.client, worker.claim())
    prepared = dispatch_new(worker.client, begin_command(worker, claim))
    agent = prepare_agent_request(side, worker, claim, prepared, repo)
    stage = StageRecordId(UUID(str(agent.stage.begin["stage_record_id"])))
    command = execution.RenewLease(
        claim=worker.fence(claim),
        progress={
            "phase": "runtime_started",
            "stage_record_id": str(stage),
            "step_id": agent.request.request_id,
        },
    )
    return worker, run.run_id, command, stage


def _await_pg_lock(dsn: str, *, relation: str, blocking_pid: int | None = None) -> None:
    with psycopg.connect(dsn, autocommit=True) as observer:
        deadline = monotonic() + 10
        while monotonic() < deadline:
            row = observer.execute(
                """
                SELECT EXISTS (
                  SELECT 1 FROM pg_stat_activity
                  WHERE datname = current_database() AND wait_event_type = 'Lock'
                    AND query LIKE %s AND (%s::integer IS NULL OR %s = ANY(pg_blocking_pids(pid)))
                )
                """,
                (f"%{relation}%FOR UPDATE%", blocking_pid, blocking_pid),
            ).fetchone()
            if row is not None and row[0]:
                return
            sleep(0.01)
    pytest.fail(f"Expected a transaction waiting for the {relation} row")


@pytest.mark.parametrize("transition", ["claim", "handoff"])
def test_rotation_commits_before_worker_admission_waiting_for_ownership(
    client_backend: ClientBackend, transition: Literal["claim", "handoff"]
) -> None:
    side = client_backend
    if side.dsn is None:
        pytest.skip("Only PostgreSQL can rotate while another write transaction waits on an ownership row")
    worker, run_id, command, stage = _case(side, transition)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with psycopg.connect(side.dsn) as ownership:
            ownership.execute("SELECT id FROM skm_execution.runs WHERE id=%s FOR UPDATE", (run_id,))
            pending = pool.submit(dispatch_new, worker.client, command)
            _await_pg_lock(side.dsn, relation="skm_execution.runs", blocking_pid=ownership.info.backend_pid)
            successor = _rotate(side, worker)
            side.clock.advance(timedelta(seconds=1))
            dispatch_new(successor.client, model_snapshot(successor, side.clock.now(), ("fake-b",)))
            ownership.commit()
        with pytest.raises(SkmError) as obsolete:
            pending.result(timeout=15)
        assert obsolete.value.code is ErrorCode.FORBIDDEN

    if stage is not None:
        with side.uow() as uow:
            assert uow.repo(StageRepository).get(stage).runtime_started_at is None
        reply = dispatch_new(successor.client, command)
        assert reply.get("refusal") is None
    else:
        assert dispatch_new(successor.client, command)["fencing_token"] == 1


@pytest.mark.parametrize("transition", ["claim", "handoff"])
def test_worker_admission_keeps_credential_stable_until_commit(
    client_backend: ClientBackend,
    transition: Literal["claim", "handoff"],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    side = client_backend
    worker, _, command, stage = _case(side, transition)
    admitted, release, rotating = Event(), Event(), Event()
    token = cast("WhoAmIView", worker.client.ask(WhoAmI())).token
    assert token is not None
    if stage is None:
        module, name = claim_assignment, "stage_route_available"
    else:
        module, name = renew_lease, "_require_runtime_offer"
    original = getattr(module, name)

    def pause(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        admitted.set()
        assert release.wait(15)
        return result

    def rotate() -> RotateTokenResult:
        rotating.set()
        return cast("RotateTokenResult", worker.client.dispatch(RotateToken(token.token_id, grace_minutes=1)))

    monkeypatch.setattr(module, name, pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(dispatch_new, worker.client, command)
        try:
            assert admitted.wait(10)
            rotation = pool.submit(rotate)
            assert rotating.wait(10)
            if side.dsn is not None:
                _await_pg_lock(side.dsn, relation="skm_access.api_tokens")
            else:
                # Memory holds its writer lock for the entire claim or handoff transaction.
                assert not rotation.done()
        finally:
            release.set()
        reply = pending.result(timeout=15)
        assert rotation.result(timeout=15).previous_token_id == token.token_id

    if stage is None:
        assert reply["fencing_token"] == 1
    else:
        assert reply.get("refusal") is None
        with side.uow() as uow:
            assert uow.repo(StageRepository).get(stage).runtime_started_at is not None
