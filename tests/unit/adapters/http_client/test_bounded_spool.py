"""Unit & regression tests for BoundedLocalSpool (R3-8) and deploy/compose.hub.yaml."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest

from fakes.clock import FrozenClock
from security.api.harness import make_world
from skm.adapters.http_client.client import HttpSkmClient
from skm.adapters.http_client.spool import (
    DEFAULT_MAX_BYTES,
    DEFAULT_TTL,
    FORBIDDEN_REPLAY_OPERATIONS,
    BoundedLocalSpool,
    HistoricalObservation,
    SpoolEntry,
)
from skm.bootstrap.builtins import builtin_runtime_data
from skm.bootstrap.host_services import build_host_storage
from skm.bootstrap.plugins import capability_catalog
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, Conflict, ValidationFailed
from skm.kernel.ids import HostId, WorkerId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.execution import public as execution
from skm.modules.runtimes import public as runtimes
from skm.modules.runtimes.ports import CapabilityCatalog, HostRuntimeRepository
from skm.modules.settings import public as settings
from skm.modules.workspace import public as workspace
from skm.modules.workspace.ports import HostRepository, WorkerRepository
from skm.platform.config.secrets import SecretRef, SecretValue
from skm.platform.logging import setup as logging_setup
from skm.platform.logging.redaction import Redactor
from skm.platform.system_clock import SystemClock

ROOT = Path(__file__).resolve().parents[4]


def test_bounded_spool_defaults_fifo_size_cap_and_ttl(tmp_path: Path) -> None:
    assert DEFAULT_MAX_BYTES == 50 * 1024 * 1024
    assert timedelta(hours=24) == DEFAULT_TTL

    clock = FrozenClock(datetime(2026, 11, 20, 12, 0, tzinfo=UTC))
    spool = BoundedLocalSpool(tmp_path / "spool", clock=clock, max_bytes=420, ttl=timedelta(hours=24))

    # Oversized single item is rejected
    with pytest.raises(ValidationFailed) as oversize:
        spool.enqueue("execution.record_step_note", {"blob": "x" * 500}, fence_token=1)
    assert oversize.value.code is ErrorCode.PAYLOAD_TOO_LARGE

    # Enqueue 3 items; max_bytes=420 forces FIFO eviction of the oldest item
    e1 = spool.enqueue("execution.record_step_note", {"n": 1, "pad": "a" * 30}, fence_token=1)
    spool.enqueue("execution.record_step_note", {"n": 2, "pad": "b" * 30}, fence_token=1)
    e3 = spool.enqueue("execution.record_step_note", {"n": 3, "pad": "c" * 30}, fence_token=1)

    remaining = spool.entries()
    assert spool.total_bytes() <= 420
    assert [e.seq for e in remaining] == sorted(e.seq for e in remaining)
    assert e1.seq not in {e.seq for e in remaining}
    assert e3.seq in {e.seq for e in remaining}

    # Replay drains in strict FIFO order
    dispatched: list[int] = []
    report = spool.replay(
        active_fence=1,
        dispatch_command=lambda entry: dispatched.append(int(cast("int", entry.payload["n"]))),
        record_observation=lambda _obs: None,
    )
    assert dispatched == [int(cast("int", e.payload["n"])) for e in remaining]
    assert report.replayed_commands == len(remaining)
    assert report.evicted_fifo >= 1
    assert spool.entries() == ()

    # 24h TTL: expired items are dropped without replay
    spool.enqueue("execution.record_step_note", {"n": 10}, fence_token=1)
    clock.advance(timedelta(hours=24, seconds=1))
    spool.enqueue("execution.record_step_note", {"n": 11}, fence_token=1)
    dispatched.clear()
    report2 = spool.replay(
        active_fence=1,
        dispatch_command=lambda entry: dispatched.append(int(cast("int", entry.payload["n"]))),
        record_observation=lambda _obs: None,
    )
    assert dispatched == [11]
    assert report2.replayed_commands == 1


def test_r3_8_forbids_spooling_or_replaying_host_offer_or_lease_mutators(tmp_path: Path) -> None:
    clock = FrozenClock(datetime(2026, 11, 20, 12, 0, tzinfo=UTC))
    spool_dir = tmp_path / "spool"
    spool = BoundedLocalSpool(spool_dir, clock=clock)

    assert "execution.renew_lease" in FORBIDDEN_REPLAY_OPERATIONS
    assert "workspace.record_worker_heartbeat" in FORBIDDEN_REPLAY_OPERATIONS
    assert "runtimes.record_host_runtimes" in FORBIDDEN_REPLAY_OPERATIONS

    for forbidden in FORBIDDEN_REPLAY_OPERATIONS:
        with pytest.raises(ValidationFailed) as exc_info:
            spool.enqueue(forbidden, {"worker_id": "w1"}, fence_token=1)
        assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
        assert exc_info.value.details.get("rule") == "R3-8"

    # Defense in depth: even a tampered on-disk runtimes.record_host_runtimes entry is never dispatched
    tampered = {
        "seq": 99,
        "item_id": "tampered-offer",
        "kind": "command",
        "operation": "runtimes.record_host_runtimes",
        "fence_token": 1,
        "recorded_at": clock.now().isoformat(),
        "payload": {"host_id": "h1", "runtimes": []},
    }
    (spool_dir / "item-00000000000000000099-tampered-offer.json").write_text(
        json.dumps(tampered), encoding="utf-8"
    )
    dispatched: list[str] = []
    report = spool.replay(
        active_fence=1,
        dispatch_command=lambda entry: dispatched.append(entry.operation),
        record_observation=lambda _obs: None,
    )
    assert dispatched == []
    assert report.replayed_commands == 0
    assert report.rejected_stale_fence == 1


def test_spool_eviction_counts_only_a_successful_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FrozenClock(datetime(2026, 11, 20, 12, 0, tzinfo=UTC))
    root = tmp_path / "spool"
    spool = BoundedLocalSpool(root, clock=clock)
    first = spool.enqueue_heartbeat({"n": 1}, fence_token=1)
    second = spool.enqueue_heartbeat({"n": 2}, fence_token=1)
    spool = BoundedLocalSpool(root, clock=clock, max_bytes=first.size_bytes + second.size_bytes)
    unlink = Path.unlink

    def fail_first(path: Path, missing_ok: bool = False) -> None:
        if first.item_id in path.name:
            raise FileNotFoundError(path)
        unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_first)
    third = spool.enqueue_heartbeat({"n": 3}, fence_token=1)

    assert [entry.item_id for entry in spool.entries()] == [first.item_id, third.item_id]
    assert spool.total_bytes() == spool.max_bytes


@pytest.mark.parametrize("lease", [False, True], ids=["worker-disconnect", "lease-unavailable"])
def test_worker_http_drains_failed_heartbeat_as_a_historical_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lease: bool
) -> None:
    log_output = StringIO()
    # Restore the process-wide sink after observing this test's real log output.
    monkeypatch.setattr(logging_setup._state, "settings", logging_setup._state.settings)
    logging_setup.configure_logging(
        level="info", detail="normal", fmt="json", stream=log_output, redactor=Redactor(), host="localhost"
    )
    paths: list[str] = []
    worker_id = uuid4()
    assignment_id = uuid4()
    heartbeat: object = workspace.RecordWorkerHeartbeat(worker_id, None)
    heartbeat_path = "/api/v1/worker/heartbeat"
    if lease:
        heartbeat = execution.RenewLease.from_json(
            {
                "claim": {
                    "assignment_id": str(assignment_id),
                    "attempt_id": str(uuid4()),
                    "worker_id": str(worker_id),
                    "fencing_token": 7,
                }
            }
        )
        heartbeat_path = f"/api/v1/worker/assignments/{assignment_id}/heartbeat"

    def send(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.method == "POST":
            if lease:
                return httpx.Response(503)
            raise httpx.ConnectError("disconnected")
        return httpx.Response(200, json={"generation": 1})

    spool = BoundedLocalSpool(tmp_path / "worker-spool", clock=SystemClock())
    spool.advance_fence(3)
    with httpx.Client(transport=httpx.MockTransport(send)) as http:
        client = HttpSkmClient(
            "http://127.0.0.1",
            SecretValue(SecretRef.parse("secret://env/SKM_TEST_TOKEN"), "worker-test-secret"),
            build_route_table(MODULE_IDS),
            spool_root=tmp_path / "upload",
            storage_budget=build_host_storage(tmp_path / "budget"),
            min_free_bytes=0,
            max_attempts=1,
            http=http,
            local_spool=spool,
        )
        with pytest.raises(BackendUnavailable, match="HTTP backend unavailable"):
            client.dispatch(heartbeat)
        (queued,) = spool.entries()
        assert queued.fence_token == 3
        assert queued.payload["worker_id"] == str(worker_id)
        assert queued.operation == "observation.worker_heartbeat"

        client.ask(settings.GetGeneration.from_json({"scope": {"level": "instance"}}))

    assert paths == [heartbeat_path, "/api/v1/config/generation"]
    assert spool.entries() == ()
    records = (json.loads(line) for line in log_output.getvalue().splitlines())
    (record,) = (record for record in records if record["event"] == "worker.heartbeat.observed")
    assert record["worker_id"] == str(worker_id)
    observed_at = queued.recorded_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    assert record["observed_at"] == observed_at


def test_r3_8_heartbeat_replay_is_historical_only_and_never_mutates_host_or_offers(tmp_path: Path) -> None:
    world = make_world(tmp_path, gateways={CapabilityCatalog: capability_catalog((), builtin_runtime_data())})
    try:
        actor = world.core.authenticate(world.secret)
        client = world.core.client(actor=actor, surface=Surface.CLI)
        ws = cast(
            "workspace.CreateWorkspaceResult",
            client.dispatch(
                workspace.CreateWorkspace(slug="spool-ws", title="Spool WS"),
                idempotency_key=client.new_idempotency_key(),
            ),
        )
        ws_id = WorkspaceId(ws.workspace_id)
        host = cast(
            "workspace.RegisterHostResult",
            client.dispatch(
                workspace.RegisterHost.from_json(
                    {"name": "worker-host", "platform": {"os": "linux", "arch": "x86_64"}}
                ),
                idempotency_key=client.new_idempotency_key(),
            ),
        )
        host_id = HostId(host.host_id)
        worker = cast(
            "workspace.RegisterWorkerResult",
            client.dispatch(
                workspace.RegisterWorker.from_json(
                    {
                        "workspace_id": str(ws_id),
                        "host_id": str(host_id),
                        "display_name": "spool-worker",
                        "capabilities": {
                            "max_concurrency": 1,
                            "runtimes": ["codex"],
                            "isolation_profiles": ["worktree"],
                            "labels": [],
                            "platform": {"os": "linux", "arch": "x86_64"},
                            "skm_version": "2.0.0",
                        },
                    }
                ),
            ),
        )
        worker_id = WorkerId(worker.worker_id)
        client.dispatch(
            runtimes.RecordHostRuntimes.from_json(
                {
                    "host_id": str(host_id),
                    "installations": [
                        {
                            "runtime_id": "codex",
                            "version": "1.0.0",
                            "binary_locator": None,
                            "auth_state": "ok",
                            "detected_at": "2026-11-18T00:00:00+00:00",
                            "details": {},
                        }
                    ],
                }
            ),
            idempotency_key=client.new_idempotency_key(),
        )

        # Snapshot host, worker, and host runtime offers before spool replay
        meta = RequestMeta("snap-before", Surface.TEST, None, world.core.clock.now())
        with world.core.uow_factory(meta, readonly=True) as uow:
            host_before = uow.repo(HostRepository).get(host_id)
            worker_before = uow.repo(WorkerRepository).get(worker_id)
            offers_before = uow.repo(HostRuntimeRepository).list_for_host(host_id)

        original_ts = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
        clock = FrozenClock(original_ts)
        spool = BoundedLocalSpool(tmp_path / "spool", clock=clock)
        spool.enqueue_heartbeat(
            {"worker_id": str(worker_id), "host_id": str(host_id), "status": "online"},
            fence_token=3,
            observed_at=original_ts,
        )

        # Advance time 2 hours before replaying
        replay_ts = original_ts + timedelta(hours=2)
        clock.advance(timedelta(hours=2))

        dispatched_ops: list[str] = []
        observations: list[HistoricalObservation] = []

        def dispatch_cmd(entry: SpoolEntry) -> None:
            dispatched_ops.append(entry.operation)

        report = spool.replay(
            active_fence=3,
            dispatch_command=dispatch_cmd,
            record_observation=observations.append,
        )

        # Replay recorded historical observation with ORIGINAL timestamp, never dispatched any command
        assert dispatched_ops == []
        assert report.replayed_commands == 0
        assert len(report.recorded_observations) == 1
        obs = report.recorded_observations[0]
        assert obs.observed_at == original_ts
        assert obs.replayed_at == replay_ts
        assert obs.observed_at != obs.replayed_at
        assert obs.payload["worker_id"] == str(worker_id)

        # Verify host, worker, and offers were NEVER mutated
        meta_after = RequestMeta("snap-after", Surface.TEST, None, world.core.clock.now())
        with world.core.uow_factory(meta_after, readonly=True) as uow:
            host_after = uow.repo(HostRepository).get(host_id)
            worker_after = uow.repo(WorkerRepository).get(worker_id)
            offers_after = uow.repo(HostRuntimeRepository).list_for_host(host_id)

        assert host_after == host_before
        assert worker_after == worker_before
        assert offers_after == offers_before
    finally:
        world.core.close()


def test_new_fence_supersedes_and_rejects_stale_spooled_items(tmp_path: Path) -> None:
    clock = FrozenClock(datetime(2026, 11, 20, 12, 0, tzinfo=UTC))
    spool = BoundedLocalSpool(tmp_path / "spool", clock=clock)

    # Enqueue stale command and stale heartbeat under fence 1
    spool.enqueue("execution.record_step_note", {"seq": "old-cmd"}, fence_token=1)
    spool.enqueue_heartbeat({"seq": "old-hb"}, fence_token=1)

    # New fence 2 arrives; enqueue fresh command and heartbeat under fence 2
    spool.advance_fence(2)
    spool.enqueue("execution.record_step_note", {"seq": "new-cmd"}, fence_token=2)
    spool.enqueue_heartbeat({"seq": "new-hb"}, fence_token=2)

    # Attempting to enqueue a stale fence 1 item is immediately rejected
    with pytest.raises(Conflict) as exc_info:
        spool.enqueue("execution.record_step_note", {"seq": "late-stale"}, fence_token=1)
    assert exc_info.value.code is ErrorCode.VERSION_CONFLICT

    dispatched: list[Any] = []
    observations: list[HistoricalObservation] = []
    report = spool.replay(
        active_fence=2,
        dispatch_command=lambda entry: dispatched.append(entry.payload["seq"]),
        record_observation=observations.append,
    )

    assert report.rejected_stale_fence == 2
    assert report.replayed_commands == 1
    assert dispatched == ["new-cmd"]
    assert len(observations) == 1
    assert observations[0].payload["seq"] == "new-hb"
    assert spool.entries() == ()


def test_hub_compose_file_is_valid_and_hardened() -> None:
    compose_path = ROOT / "deploy" / "compose.hub.yaml"
    assert compose_path.exists()
    text = compose_path.read_text(encoding="utf-8")
    assert "name: skm-hub" in text
    for required in (
        "postgres:",
        "migrate:",
        "init:",
        "hub:",
        "SKM_FIRST_ADMIN_PASSWORD:",
        "healthcheck:",
        "read_only: true",
        "cap_drop: [ALL]",
        "no-new-privileges:true",
        "internal: true",
    ):
        assert required in text
