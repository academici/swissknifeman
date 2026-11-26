"""Host composition for a slot and an assignment; handlers receive only StageDeps."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from skm.kernel.gateways import host_gateway
from skm.kernel.json_types import JsonObject
from skm.modules.execution.host.stage_client import BoundStageClient
from skm.modules.execution.ports import CheckRunnerRegistry, IsolationRegistry, Vcs
from skm.modules.runtimes.public import RuntimeRegistry
from skm.platform.config import EffectiveConfig
from skm.platform.logging.logger import StructLogger

if TYPE_CHECKING:
    from contextlib import AbstractContextManager
    from uuid import UUID

    from skm.application_bus.client import SkmClient
    from skm.application_bus.host import HostContext
    from skm.kernel.clock import Clock, Monotonic
    from skm.kernel.entropy import EntropySource
    from skm.kernel.ids import WorkspaceId
    from skm.modules.execution.domain.lease import WorkerClaim
    from skm.modules.execution.host.context_inputs import ContextInputs
    from skm.modules.execution.host.environment import PreparedEnvironment
    from skm.modules.execution.host.heartbeat import HostConcurrency
    from skm.modules.execution.host.stages.base import StageCapture, StageRequest
    from skm.modules.execution.host.stages.registry import StageRegistry
    from skm.modules.execution.ports import StageDeps
    from skm.modules.runtimes.public import AgentRequest, McpServerSpec, SecretStr, SessionHandle
    from skm.platform.logging.redaction import Redactor


@dataclass(frozen=True, slots=True)
class StageToolBinding:
    claim: WorkerClaim
    workspace_id: WorkspaceId
    project_id: UUID
    run_id: UUID
    stage_record_id: UUID
    step_id: UUID
    tools: frozenset[str]


@dataclass(frozen=True, slots=True)
class StageToolChannel:
    path: str
    server: McpServerSpec
    process_started: Callable[[SessionHandle], None]


@host_gateway
@dataclass(frozen=True, slots=True)
class WorkerServices:
    """Explicit host dependencies built by bootstrap, shared ledger and immutable factories."""

    state_dir: Any
    storage: Any
    clock: Clock
    monotonic: Monotonic
    entropy: EntropySource
    commands: Mapping[str, Callable[[JsonObject], object]]
    stages: StageRegistry
    deps_factory: Callable[..., StageDeps]
    context_inputs: ContextInputs | None
    runtime_request: Callable[[StageRequest, StageDeps], AgentRequest]
    reap: Callable[[], tuple[JsonObject, ...]]
    reap_pending: Callable[[], bool]
    acknowledge_reap: Callable[[tuple[JsonObject, ...]], None]
    concurrency: HostConcurrency
    read_bytes: Callable[[Any], bytes]
    snapshot: Callable[[StageRequest, StageDeps, StageCapture], None] | None = None
    tick: Callable[[], None] = lambda: None
    process_started: Callable[[Any], None] = lambda _handle: None
    capture_max_bytes: int = 2_000_000
    refresh_config: Callable[[], bool] = lambda: True
    workspace_id: WorkspaceId | None = None
    verify_runtime: Callable[[AgentRequest, str | None], None] = lambda _request, _digest: None
    stage_tool_client: Callable[[StageToolBinding, SecretStr], AbstractContextManager[SkmClient]] | None = (
        None
    )
    stage_tools: (
        Callable[[StageToolBinding, SecretStr, SkmClient], AbstractContextManager[StageToolChannel]] | None
    ) = None
    refresh_offers: Callable[[], None] = lambda: None
    redact_runtime_probe: Callable[[str], str] = lambda value: value
    live: Callable[[WorkerClaim, Redactor], AbstractContextManager[Callable[[bytes], bool]]] | None = None


class AssignmentUploader:
    """A workspace-bound uploader exposes neither the host context nor its client."""

    def __init__(self, ctx: HostContext, workspace_id: WorkspaceId, claim: WorkerClaim) -> None:
        self.__upload = ctx.client.upload_blob
        self.__cancel = ctx.cancel
        self.__workspace = workspace_id
        self.__services = ctx.gateways.get(WorkerServices)
        self.__owner = str(claim.assignment_id)
        self.__floor = int(cast("int", cast("EffectiveConfig", ctx.config).get("worker.disk_min_bytes") or 0))

    def upload_blob(self, content: bytes) -> JsonObject:
        self.__cancel.raise_if_cancelled()
        services = self.__services
        with services.storage.reserve(
            services.state_dir,
            owner_id=self.__owner,
            max_bytes=len(content),
            min_free_bytes=self.__floor,
        ):
            self.__cancel.raise_if_cancelled()
            return self.__upload(self.__workspace, (content,), size=len(content)).to_json()


def build_stage_deps(
    ctx: HostContext,
    claim: WorkerClaim,
    env: PreparedEnvironment | None,
    *,
    workspace_id: WorkspaceId,
    worker: BoundStageClient | None = None,
) -> StageDeps:
    services = ctx.gateways.get(WorkerServices)
    return services.deps_factory(
        worker
        or BoundStageClient(
            ctx.client, claim, services.commands, ctx.cancel, concurrency=services.concurrency
        ),
        env,
        ctx.gateways.get(RuntimeRegistry),
        ctx.gateways.get(CheckRunnerRegistry),
        ctx.gateways.get(IsolationRegistry),
        ctx.gateways.get(Vcs),
        AssignmentUploader(ctx, workspace_id, claim),
        cast("EffectiveConfig", ctx.config),
        services.clock,
        services.monotonic,
        cast("StructLogger", ctx.log),
        ctx.cancel,
    )


class EnvironmentBindings:
    """Durable local locator for the server's opaque environment id; never infer another checkout."""

    def __init__(self, services: WorkerServices, *, floor: int) -> None:
        self.services, self.floor = services, floor
        self.root = services.state_dir / "environment-bindings"

    def remember(self, attempt_id: str, environment_id: str, locator: str) -> None:
        import json
        from uuid import UUID

        owner = str(UUID(attempt_id))
        environment_id = str(UUID(environment_id))
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = self.root / f"{environment_id}.json"
        data = {"attempt_id": owner, "environment_id": environment_id, "locator": locator}
        if target.exists():
            if json.loads(target.read_text()) != data:
                raise ValueError("environment binding changed")
            return
        content = json.dumps(data).encode()
        with self.services.storage.reserve(
            self.root, owner_id=owner, max_bytes=len(content), min_free_bytes=self.floor
        ) as reservation:
            writer = reservation.open_file(target)
            writer.write(content)
            writer.close()

    def locator(self, attempt_id: str, environment_id: str) -> str:
        import json
        from uuid import UUID

        target = self.root / f"{UUID(environment_id)}.json"
        with target.open("rb") as source:
            data = json.loads(source.read(8193))
        if data["attempt_id"] != str(UUID(attempt_id)) or data["environment_id"] != str(UUID(environment_id)):
            raise ValueError("environment belongs to another attempt")
        if not isinstance(data["locator"], str):
            raise ValueError("environment locator is missing")
        return data["locator"]
