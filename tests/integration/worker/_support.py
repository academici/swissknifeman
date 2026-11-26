"""Isolated worker host fixtures; control-plane persistence cases use the dual-backend harness."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

from fakes.clock import FrozenClock
from skm.adapters.git.host_inputs import GitCheckoutReader
from skm.adapters.runtimes.fake.runtime import FakeRuntime
from skm.application_bus.client import SkmClient, StagedBlobRef
from skm.application_bus.host import HostContext
from skm.bootstrap.host_services import build_host_storage, worker_concurrency, worker_schema_issues
from skm.kernel.cancel import CancelSource
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId
from skm.kernel.isolation import IsolationProfile
from skm.modules.context.domain.draft import build_draft
from skm.modules.execution.domain.ids import EnvironmentId
from skm.modules.execution.host.context import WorkerServices
from skm.modules.execution.host.context_inputs import ContextInputs
from skm.modules.execution.host.environment import PreparedEnvironment
from skm.modules.execution.host.stages.agent_step import AgentStepStage
from skm.modules.execution.host.stages.registry import HostStage, StageRegistry
from skm.modules.execution.ports import (
    CheckRunnerRegistry,
    ExecutionEnvironmentManager,
    IsolationRegistry,
    StageDeps,
    Vcs,
)
from skm.modules.runtimes.domain.request import (
    AgentRequest,
    CommandRules,
    NetworkRules,
    PathRule,
    PathRules,
    PermissionGrant,
    ProcessOwner,
    ResultFormat,
    RuntimeLimits,
)
from skm.modules.runtimes.public import RoleId, RuntimeRegistry
from skm.platform.logging.logger import get_logger
from skm.platform.system_clock import SystemMonotonic
from skm.platform.system_entropy import SystemEntropy
from skm.platform.tokens.heuristic import HeuristicTokenEstimator


class Config:
    def __init__(self, state: Path, **values):
        self.values = {
            "worker.state_dir": str(state),
            "worker.disk_min_bytes": 0,
            "worker.capacity": 1,
            **values,
        }

    def get(self, key):
        return self.values.get(key)


class Client:
    def __init__(self, response, begin):
        self.response, self.begin = response, begin
        self.calls, self.uploads = [], []
        self.renew = lambda _: {"cancel_requested": False, "snapshot_requested": False}
        self.on_seal = lambda: None
        self.sealed = None
        self.fail_begin_once = False

    def new_idempotency_key(self):
        return "idem_" + uuid4().hex

    def dispatch(self, command, *, idempotency_key=None):
        self.calls.append((command, idempotency_key))
        op = command["operation"]
        if op == "claim_assignment":
            return self.response
        if op == "begin_stage":
            if self.fail_begin_once:
                from skm.kernel.error_codes import ErrorCode
                from skm.kernel.errors import BackendUnavailable

                self.fail_begin_once = False
                raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "response lost after commit")
            return self.begin
        if op == "renew_lease":
            return self.renew(command)
        if op in {"record_stage_result", "report_attempt_failure"}:
            return {"next": {"kind": "release", "release_reason": "done"}}
        if op == "seal_output":
            self.sealed = dict(command["manifest"])
            self.on_seal()
            return {"output_id": str(uuid4())}
        return {}

    def upload_blob(self, workspace, chunks, *, size, **kwargs):
        data = b"".join(chunks)
        assert len(data) == size
        self.uploads.append(data)
        return StagedBlobRef(
            uuid4(), workspace, "sha256:" + hashlib.sha256(data).hexdigest(), size, "application/octet-stream"
        )


class RuntimeRegistryFixture:
    def __init__(self, runtime):
        self.runtime = runtime

    def get(self, runtime_id):
        assert runtime_id == "fake"
        return self.runtime

    def ids(self):
        return frozenset({"fake"})


def make_host(tmp_path, monkeypatch, *, role="triager", handler=None, scenario=None, checkout_root=None):
    state = tmp_path / "state"
    state.mkdir(mode=0o700, parents=True)
    checkout = checkout_root or tmp_path / "checkout"
    checkout.mkdir(exist_ok=True)
    ids = {
        name: str(uuid4())
        for name in ("attempt", "assignment", "stage", "step", "worker", "workspace", "host", "run", "task")
    }
    clock = FrozenClock()
    shutdown = CancelSource()
    environment = PreparedEnvironment(
        EnvironmentId(uuid4()), str(checkout), {"repo": checkout}, (), "attempt-branch"
    )
    budget = build_host_storage(state)
    operations = (
        "claim_assignment",
        "begin_stage",
        "renew_lease",
        "record_stage_result",
        "release_assignment",
        "report_attempt_failure",
        "seal_output",
        "record_external_effect",
        "acquire_integration_slot",
        "release_integration_slot",
    )
    commands = {op: lambda raw, op=op: {"operation": op, **raw} for op in operations}
    draft = build_draft({"manifest_id": str(uuid4()), "blocks": [], "templates": {}, "prompt_plan": {}})
    begin = {
        "outcome": "ready",
        "stage_record_id": ids["stage"],
        "already_completed": False,
        "step": {
            "step_id": ids["step"],
            "context": {
                "draft": {},
                "estimator_id": "heuristic-v1",
                "host_limits": {"max_bytes": 2097152, "max_work_paths": 300},
            },
        },
    }
    instruction = {
        "kind": "run_stage",
        "stage_id": role,
        "stage_type": "agent_step",
        "round_no": 1,
        "input_digest": "sha256:" + "a" * 64,
        "params": {},
        "mode": "normal",
        "environment": {"environment_id": str(environment.environment_id), "locator": str(checkout)},
    }
    response = {
        "assignment_id": ids["assignment"],
        "attempt_id": ids["attempt"],
        "fencing_token": 1,
        "run_id": ids["run"],
        "task_id": ids["task"],
        "instruction": instruction,
        "task": {"display_key": "T1"},
        "renew_every_seconds": 30,
    }
    client = Client(response, begin)
    published, finals = [], []

    def publish(ctx, content, owner):
        published.append((content, owner))
        return client.upload_blob(UUID(ids["workspace"]), (content,), size=len(content)).to_json()

    inputs = ContextInputs(
        HeuristicTokenEstimator(),
        lambda _: draft,
        lambda env: GitCheckoutReader(env.mounts),
        publish,
        lambda raw: {"operation": "finalize_manifest", **raw},
    )
    scenario = scenario or Path(__file__).resolve().parents[2] / "fixtures/runtimes/fake/review-green.toml"
    runtime = FakeRuntime(state_dir=state, scenario=scenario, allow_pgroup_best_effort=True)

    def runtime_request(request, deps):
        root = str(checkout)
        paths = PathRules((PathRule(root, "**"),), ())
        perms = PermissionGrant(
            paths, paths, CommandRules("none", (), (), ()), NetworkRules("none", ()), frozenset(), frozenset()
        )
        owner = ProcessOwner(
            uuid4(), uuid4(), uuid4(), uuid4(), "step", uuid4(), "n" * 32, str(state / "identities")
        )
        owner = replace(owner, host_id=UUID(ids["host"]), unit_id=UUID(ids["step"]))
        return AgentRequest(
            ids["step"],
            "fake",
            "fake-model",
            None,
            RoleId(role),
            request.context.rendered_prompt,
            request.context.prompt_digest,
            ResultFormat.JSON,
            f"urn:skm:execution:role-result:{role}:v1",
            root,
            perms,
            IsolationProfile.WORKTREE,
            owner,
            "isolated",
            str(state / "client-home"),
            None,
            "ephemeral",
            (),
            {},
            {},
            (),
            RuntimeLimits(30, 10, None, None, 16000),
            {"run_id": ids["run"], "task_key": "T1"},
        )

    concurrency = worker_concurrency()
    if handler is None:
        handler = AgentStepStage(
            concurrency=concurrency,
            validate_result=worker_schema_issues,
            output_manifest=lambda *_: {"tree_digest": "sha256:" + "f" * 64},
        )
    services = WorkerServices(
        state,
        budget,
        clock,
        SystemMonotonic(),
        SystemEntropy(),
        commands,
        StageRegistry((cast("HostStage", handler),)),
        StageDeps,
        inputs,
        runtime_request,
        lambda: (),
        lambda: False,
        lambda _proofs: None,
        concurrency=concurrency,
        read_bytes=Path.read_bytes,
        capture_max_bytes=16000,
    )
    entries = {
        WorkerServices: services,
        RuntimeRegistry: RuntimeRegistryFixture(runtime),
        CheckRunnerRegistry: object(),
        IsolationRegistry: object(),
        Vcs: SimpleNamespace(dirty_patch=lambda _: b"diff --git a/x b/x\n"),
        ExecutionEnvironmentManager: SimpleNamespace(reopen=lambda *_: environment),
    }
    context = HostContext(
        cast("SkmClient", client),
        GatewayTable(entries, "host_gateway"),
        HostId(UUID(ids["host"])),
        Config(state),
        get_logger("worker.test"),
        shutdown.token,
    )
    request = {
        "worker_id": ids["worker"],
        "workspace_id": ids["workspace"],
        "host_id": ids["host"],
        "offer": {
            "capabilities": ["fake"],
            "labels": [],
            "environment_kinds": ["git_worktree"],
            "isolation_profiles": ["worktree"],
        },
        "max_assignments": 1,
        "once": True,
    }
    return SimpleNamespace(
        ctx=context,
        services=services,
        client=client,
        request=request,
        runtime=runtime,
        ids=ids,
        shutdown=shutdown,
        environment=environment,
        published=published,
        finals=finals,
        entries=entries,
    )


def result_scenario(tmp_path, role, document):
    path = tmp_path / f"{role}.toml"
    path.write_text(
        'scenario = "success"\n[[step]]\naction = "read_stdin"\n[result]\ntext = '
        + json.dumps(json.dumps(document))
        + "\n[usage]\ninput_tokens = 10\noutput_tokens = 4\n"
    )
    return path
