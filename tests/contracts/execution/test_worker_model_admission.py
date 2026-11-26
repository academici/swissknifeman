"""A particular claim keeps its offered routes and the run's chosen resource versions."""

from dataclasses import replace
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

import pytest

from contracts.context.harness import MutableBuiltinPacks
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
from contracts.extensions.harness import pack_payload
from integration.artifacts.test_upload_flow import dispatch_new
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import ResourceVersionId
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import RotateToken, RotateTokenResult, WhoAmI, WhoAmIView
from skm.modules.execution import public as execution
from skm.modules.execution.domain.ids import AssignmentId, StageRecordId
from skm.modules.execution.ports import AssignmentRepository, StageRepository
from skm.modules.extensions import public as extensions
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.runtimes import public as runtimes
from skm.modules.settings import public as settings
from skm.platform.config import ConfigStore, ScopeTree
from support.backend import ClientBackend, client_backend
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "client_backend", "pg_session", "test_database"]


def _publish_test_pack(side: ClientBackend, version: str) -> None:
    packs = cast("MutableBuiltinPacks", side.app.bus._gateways.get(BuiltinPacks))
    files = {item.path: item.content.decode() for item in packs.current[0].files}
    catalog = files["runtimes/models.toml"]
    alternate = catalog[catalog.index("[runtimes.fake]") :].replace("runtimes.fake", "runtimes.fake_alt")
    files["runtimes/models.toml"] = (catalog + alternate).replace(
        'catalog_version = "1.3.0"', f'catalog_version = "{version}"'
    )
    files["agent-profiles/executor.toml"] = files["agent-profiles/executor.toml"].replace(
        'version = "1.3.0"', f'version = "{version}"'
    )
    packs.current = (*packs.current, pack_payload("core", version, files=files))
    actor = side.app.authenticate(side.seed.tokens["owner"].secret)
    side.app.client(actor=actor, surface=Surface.API).dispatch(extensions.SyncBuiltinPacks())


def _publish_both(side: ClientBackend, worker: ClientWorker) -> None:
    side.clock.advance(timedelta(seconds=1))
    observed = side.clock.now()
    snapshot = model_snapshot(worker, observed, ("fake-b",)).to_json()
    snapshot["installations"] += [{**item, "runtime_id": "fake_alt"} for item in snapshot["installations"]]
    snapshot["model_offers"] += [{**item, "runtime_id": "fake_alt"} for item in snapshot["model_offers"]]
    dispatch_new(worker.client, runtimes.RecordHostRuntimes.from_json(snapshot))


@pytest.mark.parametrize("last_change", ["disable", "rotate", "withdraw"])
def test_first_runtime_handoff_uses_the_exact_claim_routes_and_pinned_resources(
    client_backend: ClientBackend, last_change: str
) -> None:
    side = client_backend
    owner = side.client()
    repo_id = configure_execution(side, owner)
    _publish_test_pack(side, "1.4.0")
    worker = register_worker(side, owner, "two-runtime-worker", runtime_ids=("fake", "fake_alt"))
    dispatch_new(
        owner,
        settings.SetValue.from_json(
            {
                "scope": {"level": "instance"},
                "key": "runtimes.allowed",
                "value": ["fake", "fake_alt"],
                "expected_row_version": 1,
            }
        ),
    )
    dispatch_new(
        owner,
        settings.SetValue.from_json(
            {
                "scope": {"level": "host", "scope_id": str(worker.host_id)},
                "key": "runtimes.host.route_substitutions",
                "value": [
                    {
                        "requested": {"runtime_id": "fake", "model_id": "fake-b", "effort": "high"},
                        "selected": {"runtime_id": "fake_alt", "model_id": "fake-b", "effort": "high"},
                    }
                ],
                "expected_row_version": 0,
            }
        ),
    )
    _publish_both(side, worker)
    with side.uow() as uow:
        config = side.app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), None)
        pinned_catalog = runtimes.catalog(uow, config=config)
        profile = extensions.select_agent_profile(uow, "executor", stage_profile=None, config=config)
    plan, revision = worker_plan(side)
    dispatch_new(owner, start_run_command(plan, revision, "P1.1"))
    schedule(side)
    narrow = worker.claim().to_json()
    narrow["offer"]["capabilities"] = ["runtime:fake_alt"]
    claimed = dispatch_new(worker.client, execution.ClaimAssignment.from_json(narrow))
    assert claimed.get("outcome") is None, claimed
    prepared = dispatch_new(worker.client, begin_command(worker, claimed))
    with side.uow() as uow:
        lease = uow.repo(AssignmentRepository).lease(AssignmentId(UUID(claimed["assignment_id"])))
        assert lease is not None
        assert lease.offered_runtimes == {"fake_alt"}

    _publish_test_pack(side, "1.5.0")
    with side.uow() as uow:
        config = side.app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), None)
        assert runtimes.catalog(uow, config=config).digest != pinned_catalog.digest
        current_profile = extensions.select_agent_profile(uow, "executor", stage_profile=None, config=config)
        assert current_profile.resource_version_id != profile.resource_version_id
    agent = prepare_agent_request(side, worker, claimed, prepared, repo_id)
    assert agent.request.runtime_id == "fake_alt"
    step = agent.stage.begin["step"]
    assert isinstance(step, dict)
    snapshot = step["route_snapshot"]
    assert isinstance(snapshot, dict)
    assert snapshot["catalog_digest"] == pinned_catalog.digest
    assert ResourceVersionId(UUID(str(snapshot["profile_version_id"]))) == profile.resource_version_id
    stage_id = agent.stage.begin["stage_record_id"]
    handoff = execution.RenewLease(
        claim=worker.fence(claimed),
        progress={
            "stage_record_id": stage_id,
            "step_id": agent.request.request_id,
            "phase": "runtime_started",
        },
    )

    if last_change == "rotate":
        before = cast("WhoAmIView", worker.client.ask(WhoAmI())).token
        assert before is not None
        rotated = cast(
            "RotateTokenResult", worker.client.dispatch(RotateToken(before.token_id, grace_minutes=1))
        )
        successor = replace(worker, client=side.client(token=rotated.secret), token=rotated.secret)
        _publish_both(side, successor)
        assert cast("WhoAmIView", worker.client.ask(WhoAmI())).token is not None
        with pytest.raises(SkmError) as stale:
            dispatch_new(worker.client, handoff)
        assert stale.value.code is ErrorCode.FORBIDDEN
        assert dispatch_new(successor.client, handoff).get("refusal") is None
        return
    if last_change == "disable":
        dispatch_new(
            owner,
            settings.SetValue.from_json(
                {
                    "scope": {"level": "instance"},
                    "key": "runtimes.models.overrides",
                    "value": {"fake_alt:fake-b": {"disabled": True}},
                    "expected_row_version": 0,
                }
            ),
        )
    else:
        side.clock.advance(timedelta(seconds=1))
        dispatch_new(worker.client, model_snapshot(worker, side.clock.now(), ("fake-b",)))
    reply: Any = dispatch_new(worker.client, handoff)
    assert reply["refusal"]["code"] == ErrorCode.CAPABILITY_UNAVAILABLE
    with side.uow() as uow:
        assert uow.repo(StageRepository).get(StageRecordId(UUID(str(stage_id)))).runtime_started_at is None
