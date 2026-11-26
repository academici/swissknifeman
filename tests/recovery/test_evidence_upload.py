"""Blob faults in the App upload path cannot commit stage results or partial evidence."""

import pytest

from contracts.execution._worker_protocol_support import worker_claim
from fixtures.execution.blob_faults import application_with_blob_fault
from fixtures.execution.harness import clean_test_database, pg_session, recovery, test_database
from fixtures.execution.protocol import agent, finalize
from skm.application_bus.host import HostContext
from skm.kernel.cancel import CancelSource
from skm.kernel.gateways import GatewayTable
from skm.kernel.ports_uow import Surface
from skm.modules.execution import public as execution
from skm.modules.execution.generated.commands import RecordStageResult
from skm.modules.execution.host.evidence import ClientBlobUploader, EvidenceFile, record_with_evidence
from skm.modules.execution.ports import AcceptanceRepository, EvidenceBindingRepository, StageRepository
from skm.platform.logging.logger import get_logger
from support.fault_injection import FaultPlan, FaultPoint, InjectedFault

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = pytest.mark.pg


@pytest.mark.parametrize("point", [FaultPoint.BLOB_AFTER_STAGE, FaultPoint.BLOB_AFTER_PROMOTE])
def test_partial_upload_is_not_evidence_and_cannot_pass_a_check(recovery, point):
    side = recovery
    case = agent(side)
    finalize(side, case)
    plan = FaultPlan({point: 1})
    data = b"actual evidence bytes\n"
    path = side.root / "check.log"
    path.write_bytes(data)
    files = (EvidenceFile(path, f"attempt:{case.attempt.id}", "evidence", "check.log", "text/plain"),)
    command = RecordStageResult(
        claim=worker_claim(side, case.claimed),
        stage_record_id=case.ready["stage_record_id"],
        outcome_kind="runtime_error",
        outcome={"error_code": "RUNTIME_TRANSPORT"},
    )
    with application_with_blob_fault(side, plan) as app:
        client = app.client(actor=side.worker1_client._actor, surface=Surface.WORKER)
        ctx = HostContext(
            client,
            GatewayTable({}, "host_gateway"),
            side.host1,
            app.config,
            get_logger("recovery.evidence"),
            CancelSource().token,
        )
        uploader = ClientBlobUploader(ctx, side.ws)

        def record():
            return record_with_evidence(
                ctx,
                command,
                files=files,
                uploader=uploader,
                read=type(path).read_bytes,
                idempotency_key=f"evidence-result:{case.attempt.id}",
                command_factory=lambda raw: execution.RecordStageResult(**raw),
            )

        with pytest.raises(InjectedFault) as caught:
            record()
        assert caught.value.point is point
        assert plan.hits[point] == 1
        with side.uow(readonly=True) as uow:
            assert uow.repo(StageRepository).get(case.ready["stage_record_id"]).finished_at is None
            assert not uow.repo(EvidenceBindingRepository).for_owner("attempt", case.attempt.id)
            assert not uow.repo(AcceptanceRepository).decisions_for_task(case.task.id)
            assert (
                uow.connection.execute(
                    "SELECT count(*) FROM skm_artifacts.staged_blobs WHERE workspace_id=%s AND size_bytes=%s",
                    (side.ws, len(data)),
                ).fetchone()[0]
                == 0
            )
        record()
        with side.uow(readonly=True) as uow:
            assert uow.repo(StageRepository).get(case.ready["stage_record_id"]).finished_at is not None
            assert len(uow.repo(EvidenceBindingRepository).for_owner("attempt", case.attempt.id)) == 1
            assert (
                uow.connection.execute(
                    "SELECT count(*) FROM skm_execution.check_executions "
                    "WHERE attempt_id=%s AND state='passed'",
                    (case.attempt.id,),
                ).fetchone()[0]
                == 0
            )
