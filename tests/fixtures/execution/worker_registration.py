"""A separately authenticated worker on a different registered host."""

from contracts.execution._client_execution import ClientWorker, model_snapshot
from contracts.execution.harness import PEPPER
from integration.artifacts.test_upload_flow import dispatch_new
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import authenticate_token
from skm.modules.workspace.generated.documents import WorkerCapabilities
from skm.modules.workspace.public import RecordWorkerHeartbeat, RegisterWorker


def other_worker(side):
    registered = side.client.dispatch(
        RegisterWorker(
            side.ws,
            side.host2,
            "recovery-other-host",
            WorkerCapabilities.from_json(
                {
                    "runtimes": ["fake", "codex_cli"],
                    "isolation_profiles": ["worktree", "landlock"],
                    "max_concurrency": 4,
                    "labels": ["linux"],
                    "platform": {"os": "linux", "arch": "x86_64"},
                    "skm_version": "2.0.0",
                }
            ),
        )
    )
    with side.uow() as uow:
        actor = authenticate_token(uow, registered.token_secret, pepper=PEPPER, now=side.clock.now())
        uow.commit()
    client = side.app.client(actor=actor, surface=Surface.WORKER)
    worker = ClientWorker(client, registered.worker_id, side.host2, side.ws, registered.token_secret)
    dispatch_new(client, model_snapshot(worker, side.clock.now(), ("fake-a", "fake-b")))
    client.dispatch(RecordWorkerHeartbeat(registered.worker_id, None))
    return registered.worker_id, client
