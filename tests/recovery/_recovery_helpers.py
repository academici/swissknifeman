"""Worker boundary fixtures for effect recovery."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from threading import Event
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from contracts.execution._worker_protocol_support import worker_claim
from skm.application_bus.host import HostContext
from skm.bootstrap.host_services import worker_concurrency
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.cancel import CancelSource
from skm.modules.execution import public as execution
from skm.modules.execution.application._worker_protocol import parse_worker_claim
from skm.modules.execution.application.commands.expire_leases import ExpireLeases
from skm.modules.execution.domain.assignment import StageInstruction
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.host import worker_loop
from skm.modules.execution.host.context import WorkerServices
from skm.modules.execution.host.stage_client import BoundStageClient
from skm.modules.execution.host.stages.base import StageRequest
from skm.modules.execution.host.stages.integrate import IntegrateStage
from skm.modules.execution.ports import StageDeps


def stage_request(claimed, ready):
    raw = claimed["instruction"]
    inst = StageInstruction(
        kind="run_stage",
        stage_id=raw["stage_id"],
        stage_type="integrate",
        mode=StageMode.RECONCILE,
        round_no=raw["round_no"],
        params=raw["params"],
        input_digest=raw["input_digest"],
    )
    return StageRequest(inst, ready, None, {})


def inspect_push(side, git, case, claimed, ready, root):
    from integration.git.test_integration import ownership
    from unit.execution.application.test_external_effects import dispatch

    own = ownership(case.effect.id, str(case.attempt_id), root)
    own["owner"].update(
        host_id=str(side.host1), worker_id=str(side.worker1), stage_record_id=ready["stage_record_id"]
    )
    progress = []

    def heartbeat(value):
        progress.append(value)
        return dispatch(side, execution.RenewLease(claim=worker_claim(side, claimed), progress=value))

    deps = SimpleNamespace(
        vcs=git.writer,
        cancel=CancelSource().token,
        environment=None,
        worker=SimpleNamespace(report_progress=heartbeat),
    )
    outcome = IntegrateStage(ownership=lambda *a: own).run(
        stage_request(claimed, ready), cast("StageDeps", deps)
    )
    assert outcome.kind.value == "success"
    observed = outcome.payload["reconciled_effect"]
    assert isinstance(observed, dict)
    return observed, progress


def assert_emergency_push_reconciled(side, git, case, journal, recorded, root, monkeypatch):
    from skm.modules.execution.domain.external_effect import EffectState
    from skm.modules.execution.ports import AssignmentRepository
    from unit.execution.application.test_external_effects import admin_case, admin_result, saved_effect

    uncertain = saved_effect(side, case.effect.id)
    assert uncertain.state is EffectState.OUTCOME_UNKNOWN
    assert uncertain.request_digest == case.effect.request_digest
    assert uncertain.receipt is None
    claimed, ready = admin_case(side, case)
    with side.uow(readonly=True) as uow:
        assignment = uow.repo(AssignmentRepository).get(UUID(claimed["assignment_id"]))
        assert assignment.reconcile_effect_id == case.effect.id
    monkeypatch.setattr(git.writer, "push_external", lambda *a, **k: pytest.fail("second push"))
    observed, _ = inspect_push(side, git, case, claimed, ready, root)
    assert observed["state"] == "succeeded"
    admin_result(side, claimed, ready, observed)
    assert saved_effect(side, case.effect.id).state is EffectState.SUCCEEDED
    assert journal.read_bytes() == recorded
    assert git.tip() == git.after


def stage_tokens(side, assignment_id):
    with side.uow(readonly=True) as uow:
        return dict(
            uow.connection.execute(
                "SELECT id, revoked_at FROM skm_access.api_tokens "
                "WHERE assignment_id=%s AND step_id IS NOT NULL",
                (assignment_id,),
            ).fetchall()
        )


def assert_emergency_admission_closed(side, effect):
    from contracts.execution._worker_protocol_support import make_case
    from fixtures.execution.harness import recovery_claim
    from skm.kernel.error_codes import ErrorCode
    from skm.kernel.errors import SkmError
    from skm.modules.execution.domain.assignment import AssignmentState
    from unit.execution.application.test_autopilot_commands import command
    from unit.execution.application.test_external_effects import effect_record

    with pytest.raises(SkmError) as restart:
        command(side, execution.StartAutopilot)
    assert restart.value.code is ErrorCode.EMERGENCY_STOPPED

    # A runnable candidate in the stopped project must still be refused by the claim path.
    _, _, _, candidate = make_case(side, stage_id="execute", stage_type="agent_step")
    assert candidate.state is AssignmentState.AVAILABLE
    assert recovery_claim(side) == {"outcome": "nothing_to_claim"}
    with pytest.raises(SkmError) as write:
        effect_record(side, effect)
    assert write.value.code is ErrorCode.LEASE_LOST


def worker_result_path(side, claimed, ready, monkeypatch):
    source = CancelSource()
    ctx = SimpleNamespace(client=side.worker1_client, cancel=source.token)
    services = SimpleNamespace(
        commands={
            "record_stage_result": execution.RecordStageResult,
            "renew_lease": execution.RenewLease,
        },
        read_bytes=lambda path: pytest.fail("lookup has no evidence to upload"),
    )
    owned = parse_worker_claim(worker_claim(side, claimed))
    worker = BoundStageClient(
        ctx.client, owned, services.commands, source.token, concurrency=worker_concurrency()
    )
    worker.set_stage(ready["stage_record_id"])
    deps = SimpleNamespace(cancel=source.token, vcs=None, worker=worker, uploader=None, environment=None)
    monkeypatch.setattr(worker_loop, "build_stage_deps", lambda *args, **kwargs: deps)
    request = replace(stage_request(claimed, ready), task={"workspace_id": str(side.ws)})
    return cast("HostContext", ctx), cast("WorkerServices", services), owned, worker, request, deps


def expire(side, claimed):
    from skm.modules.execution.application.commands.expire_leases import handle
    from unit.execution.application._support import context

    if side.kind == "postgres":
        import psycopg

        from support.pg import require_session_database

        with psycopg.connect(side.dsn) as conn:
            require_session_database(conn, conn.info.dbname)
            conn.execute(
                "UPDATE skm_execution.assignment_leases "
                "SET expires_at=clock_timestamp()-interval '1 second', "
                "last_heartbeat_at=clock_timestamp()-interval '121 seconds' WHERE assignment_id=%s",
                (UUID(claimed["assignment_id"]),),
            )
    with side.uow() as uow:
        result = handle(
            ExpireLeases(limit=100),
            context(side, uow, actor=Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")),
            uow,
        )
        uow.commit()
        return result


@contextmanager
def executing_push(side, root):
    from integration.git.test_integration import ownership
    from integration.git.test_push_receipts import push_case
    from unit.execution.application.test_external_effects import effect_case, effect_record

    git = push_case(root)
    case = effect_case(
        side,
        kind="git_push",
        locator=str(git.repo),
        after=git.after,
        before=git.before,
        endpoint=git.request["endpoint"],
    )
    git.writer.repositories = {str(side.repo_id): git.repo}
    ready, release = Event(), Event()

    def report(raw):
        if raw["phase"] == "result":
            ready.set()
            assert release.wait(45)
            raise ConnectionError("interrupted before publishing the effect receipt")
        return effect_record(side, case, raw["phase"])

    with ThreadPoolExecutor(1) as pool:
        result = pool.submit(
            git.writer.push_external,
            git.repo,
            str(case.effect.id),
            case.request,
            case.effect.request_digest,
            SimpleNamespace(record_effect=report),
            ownership(case.effect.id, str(case.attempt_id), root),
        )
        try:
            if not ready.wait(15) and result.done():
                result.result()
            assert ready.is_set()
            (journal,) = git.repo.glob(f".git/skm-integration/*/{case.effect.id}.json")
            yield case, git, journal
        finally:
            release.set()
        with pytest.raises(ConnectionError, match="interrupted before publishing"):
            result.result(timeout=5)
