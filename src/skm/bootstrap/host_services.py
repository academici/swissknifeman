"""Host composition boundary (kernel-platform §5.3a).

``build_host_services`` assembles the ``GatewayTable(kind="host_gateway")``, the surface-filtered operation
table and ``HostServices``. Config, gateway adapters and owned resources arrive through explicit factories.
Control-plane ports (``ContextOwnerGuard``, ``BlobCoordination`` ...) are rejected by the host table.
"""

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from functools import cache, cached_property
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.adapters.research.retry import ResearchSources
from skm.application_bus.host import HostServices, check_host_operation_name
from skm.bootstrap.builtins import BUILTIN_COMPONENTS, build_native_codegraph
from skm.bootstrap.plugins import LoadedPlugin
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.generated.error_codes import ErrorCode
from skm.kernel.ids import HostId
from skm.kernel.json_types import JsonObject
from skm.kernel.module_manifest import HostOperationSpec
from skm.kernel.ports_uow import Surface
from skm.modules.context.module import CODEGRAPH_SPEC, RESEARCH_SPEC
from skm.modules.context.ports import CodeGraphIndex, ResearchSourceRegistry
from skm.platform.logging.logger import get_logger
from skm.platform.system_clock import SystemClock
from skm.plugin_api.manifest import ComponentKind, PluginContext, Side

if TYPE_CHECKING:
    from skm.adapters.runtimes._cli_session.identity import OwnedContainment
    from skm.application_bus.client import SkmClient
    from skm.application_bus.host import HostContext
    from skm.modules.context.ports import CheckoutReader, ResearchSource
    from skm.modules.context.public import ContextDraft, ResearchBatch
    from skm.modules.execution.host.context import WorkerServices
    from skm.modules.execution.host.context_inputs import ContextInputs
    from skm.modules.execution.host.environment import PreparedEnvironment
    from skm.modules.execution.host.heartbeat import HostConcurrency
    from skm.modules.execution.host.stages.base import StageRequest
    from skm.modules.execution.host.stages.registry import StageRegistry
    from skm.modules.execution.ports import StageDeps
    from skm.modules.runtimes.public import AgentRequest, ProcessOwnership, SecretStr, SessionHandle
    from skm.platform.fs.storage_budget import StorageBudget
    from skm.platform.schema.registry import SchemaRegistry

__all__ = ["bind_cli_research", "build_host_services", "read_recorded_host_id", "resolve_host_id"]

_HOST_SURFACES = frozenset({Surface.CLI, Surface.WORKER, Surface.HOOK})


def read_recorded_host_id(state_dir: Path) -> HostId | None:
    """``paths.state_dir/host.json`` -> ``host_id``; ``None`` when the host was never registered."""
    try:
        data = json.loads((state_dir / "host.json").read_text(encoding="utf-8"))
        return HostId(UUID(str(data["host_id"])))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "state_dir/host.json is unreadable or has no valid host_id",
            details={"field": "paths.state_dir", "reason": "host_json_invalid"},
        ) from None


def resolve_host_id(
    bootstrap: JsonObject, surface: Surface, access_mode: str | None, recorded_host_id: HostId | None
) -> HostId:
    host = bootstrap.get("host")
    raw = host.get("id") if isinstance(host, dict) else None
    if raw is None or raw == "auto":
        http_auto = raw == "auto" and surface is Surface.WORKER and access_mode == "http"
        if recorded_host_id is None:
            paths = bootstrap.get("paths")
            state_dir = paths.get("state_dir") if isinstance(paths, dict) else None
            if isinstance(state_dir, str) and state_dir:
                try:
                    recorded_host_id = read_recorded_host_id(Path(state_dir).expanduser())
                except ValidationFailed:
                    if not http_auto:
                        raise
        if recorded_host_id is not None:
            return recorded_host_id
        if http_auto:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                "host.id 'auto' is forbidden for an http worker",
                details={"field": "host.id", "reason": "auto_forbidden_in_http"},
            )
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "host is not registered; run `skm host register`",
            details={"reason": "host_not_registered"},
        )
    try:
        return HostId(UUID(str(raw)))
    except ValueError:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "host.id is not a UUID", details={"field": "host.id"}
        ) from None


def _research_sources(plugins: Sequence[object], host_config: Callable[[], object]) -> ResearchSources:
    clock = SystemClock()
    context = PluginContext("skm", host_config, None, get_logger("host.research"), None, None, clock)
    sources = {
        spec.key: cast("ResearchSource", spec.factory(context))
        for spec in BUILTIN_COMPONENTS
        if spec.kind is ComponentKind.RESEARCH_SOURCE and spec.side is Side.HOST
    }
    for plugin in plugins:
        if isinstance(plugin, LoadedPlugin):
            sources.update(
                (key, cast("ResearchSource", source))
                for (kind, key), source in plugin.instances.items()
                if kind is ComponentKind.RESEARCH_SOURCE
            )
    return ResearchSources(sources, clock=clock)


class _CliResearchConfig:
    def __init__(
        self, local: object, client: "SkmClient", host_id: HostId, *, remote: bool, project: str | None = None
    ) -> None:
        self._local, self._client, self._host_id = local, client, host_id
        self._remote, self._project = remote, project

    def __getattr__(self, name: str) -> object:
        return getattr(self._local, name)

    def get(self, key: str) -> object:
        if not key.startswith("context.research."):
            return cast("Mapping[str, object]", self._local).get(key)
        if key in {"context.research.sources", "context.research.fs_roots_allow"}:
            return self._host.get(key) if self._remote else cast("Mapping[str, object]", self._local).get(key)
        return self._work.get(key)

    def for_research_project(self, project: str) -> "_CliResearchConfig":
        return _CliResearchConfig(
            self._local, self._client, self._host_id, remote=self._remote, project=project
        )

    @cached_property
    def _host(self) -> JsonObject:
        return self._explain({"level": "host", "scope_id": str(self._host_id)})

    @cached_property
    def _work(self) -> JsonObject:
        scope: JsonObject = (
            {"level": "project", "scope_id": self._project} if self._project else {"level": "instance"}
        )
        return self._explain(scope)

    def _explain(self, scope: JsonObject) -> JsonObject:
        from skm.modules.settings.public import ExplainConfig, ExplainConfigResult

        result = cast(
            "ExplainConfigResult",
            self._client.ask(
                ExplainConfig.from_json({"scope": scope, "section": "context", "detail": "value"})
            ),
        )
        values: JsonObject = {}
        for entry in cast("list[JsonObject]", result.to_json()["keys"]):
            key = str(entry["key"])
            if key.startswith("context.research."):
                if entry.get("valid") is False:
                    raise ValidationFailed(
                        ErrorCode.CONFIG_INVALID, "Invalid research setting", details={"key": key}
                    )
                values[key] = entry.get("value")
        return values


def bind_cli_research(
    host: HostServices | None, client: "SkmClient", plugins: Sequence[object] = (), *, remote: bool = False
) -> HostServices | None:
    """Attach the context host gateways to an existing registered CLI host."""
    if host is None:
        return None
    local_config = host.host_config
    host_id = host.host_id

    def config() -> object:
        return _CliResearchConfig(local_config(), client, host_id, remote=remote)

    entries = dict(host.gateways.entries)
    if ResearchSourceRegistry not in entries:
        entries[ResearchSourceRegistry] = _research_sources(plugins, config)
    if CodeGraphIndex not in entries:
        entries[CodeGraphIndex] = build_native_codegraph()
    operations = {RESEARCH_SPEC.name: RESEARCH_SPEC, CODEGRAPH_SPEC.name: CODEGRAPH_SPEC, **host.operations}
    return replace(
        host, gateways=GatewayTable(entries, "host_gateway"), operations=operations, host_config=config
    )


def _write_external_file(destination: str, data: bytes) -> None:
    from skm.platform.fs.atomic_write import UnsafePathError, atomic_write_nofollow

    try:
        atomic_write_nofollow(destination, data)
    except UnsafePathError as error:
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "unsafe external write destination",
            details={"reason": error.reason},
        ) from error


def build_host_services(  # noqa: PLR0913 - spec signature plus explicit factories
    bootstrap: JsonObject,
    *,
    client: "SkmClient",
    plugins: Sequence[object],
    environ: Mapping[str, str],
    surface: Surface,
    host_config: Callable[[], object],
    gateways: Mapping[type[object], object] = {},
    operations: Iterable[HostOperationSpec] | None = None,
    owned_resources: Sequence[Callable[[], None]] = (),
    recorded_host_id: HostId | None = None,
    access_mode: str | None = None,
    worker_services: "WorkerServices | None" = None,
) -> HostServices:
    """Assemble ``HostServices``; ``host_config`` re-reads the host chain and is called per context."""
    del client, environ
    if surface not in _HOST_SURFACES:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            f"surface {surface.value!r} has no host services",
            details={"field": "surface"},
        )
    host_id = resolve_host_id(bootstrap, surface, access_mode, recorded_host_id)
    from skm.adapters.git.repo_inspect import GitRepositoryInspector
    from skm.modules.workspace.ports import RepositoryInspector

    entries = dict(gateways)
    if RepositoryInspector not in entries:
        entries[RepositoryInspector] = GitRepositoryInspector(clock=SystemClock())
    if surface is Surface.CLI:
        from skm.modules.policy.ports import ExternalFileWriter

        entries.setdefault(ExternalFileWriter, _write_external_file)
        if CodeGraphIndex not in entries:
            entries[CodeGraphIndex] = build_native_codegraph()
    if surface in RESEARCH_SPEC.surfaces and ResearchSourceRegistry not in entries:
        entries[ResearchSourceRegistry] = _research_sources(plugins, host_config)
    if worker_services is not None:
        from skm.modules.execution.host.context import WorkerServices

        entries[WorkerServices] = worker_services
    table = GatewayTable(entries=entries, kind="host_gateway")
    for port in table.entries:
        table.has(port)  # TypeError for control-plane / unmarked ports
    ops: dict[str, HostOperationSpec] = {}
    for spec in (RESEARCH_SPEC, CODEGRAPH_SPEC) if operations is None else operations:
        check_host_operation_name(spec.name, spec)  # ValueError before any registration
        if surface not in spec.surfaces:
            continue
        if spec.name in ops:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"duplicate host operation {spec.name!r}",
                details={"operation": spec.name},
            )
        ops[spec.name] = spec
    return HostServices(
        host_id=host_id,
        surface=surface,
        gateways=table,
        host_config=host_config,
        operations=ops,
        owned_resources=tuple(owned_resources),
    )


def build_host_storage(state_dir: Path) -> "StorageBudget":
    """One host/instance ledger, shared by every root, slot, transcript and client spool."""
    import shutil

    from skm.platform.fs.storage_budget import StorageBudget, StorageOwnerIdentity
    from skm.platform.process.identity import ProcessIdentity, identity_of, is_same_process

    def identity() -> StorageOwnerIdentity:
        import os

        current = identity_of(os.getpid())
        if current is None or current.boot_id is None or current.start_ticks is None:
            raise RuntimeError("host storage requires boot/pid/start ownership")
        return StorageOwnerIdentity(current.boot_id, current.pid, str(current.start_ticks))

    def alive(owner: StorageOwnerIdentity) -> bool | None:
        try:
            current = identity_of(owner.pid)
            return current is not None and is_same_process(
                ProcessIdentity(owner.pid, int(owner.start_identity), owner.boot_id)
            )
        except (OSError, ValueError):
            return None

    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    budget = StorageBudget(
        state_dir / "locks",
        free_bytes=lambda root: shutil.disk_usage(root).free,
        identity=identity,
        owner_alive=alive,
    )
    budget.reconcile(state_dir)
    return budget


def worker_command_factories() -> "Mapping[str, Callable[[JsonObject], object]]":
    """Bridge generated host wire values to the exact registered bus DTO identities."""
    from skm.modules.execution import public as execution

    return {
        "claim_assignment": execution.ClaimAssignment.from_json,
        "begin_stage": execution.BeginStage.from_json,
        "renew_lease": execution.RenewLease.from_json,
        "record_stage_result": execution.RecordStageResult.from_json,
        "release_assignment": execution.ReleaseAssignment.from_json,
        "report_attempt_failure": execution.ReportAttemptFailure.from_json,
        "seal_output": execution.SealOutput.from_json,
        "record_external_effect": execution.RecordExternalEffect.from_json,
        "acquire_integration_slot": execution.AcquireIntegrationSlot.from_json,
        "release_integration_slot": execution.ReleaseIntegrationSlot.from_json,
    }


def decode_context_draft(raw: JsonObject) -> "ContextDraft":
    """Decode the full pinned draft; preserve conditional blocks and its server digest."""
    from dataclasses import replace
    from typing import Any, cast

    from skm.modules.context.domain.blocks import BlockType, BudgetClass, TrustLevel
    from skm.modules.context.domain.draft import ConditionalBlock, build_draft
    from skm.modules.context.domain.manifest import ManifestBlock

    data = cast("dict[str, Any]", raw)
    draft = build_draft(raw)
    conditional = tuple(
        ConditionalBlock(
            build_draft({**data, "blocks": [item["block"]]}).blocks[0],
            item["condition"],
            frozenset(item["deps"]),
        )
        for item in data.get("conditional", ())
    )
    excluded = tuple(
        ManifestBlock(
            **cast(
                "dict[str, Any]",
                {
                    **item,
                    "block_type": BlockType(item["block_type"]),
                    "budget_class": BudgetClass(item["budget_class"]),
                    "trust": TrustLevel(item["trust"]),
                    "research_query_ids": tuple(item.get("research_query_ids", ())),
                },
            )
        )
        for item in data.get("excluded", ())
    )
    return replace(
        draft,
        conditional=conditional,
        excluded=excluded,
        draft_digest=data["draft_digest"],
        budget=replace(draft.budget, estimator_id=data["budget"]["estimator_id"]),
    )


def read_runtime_transcript(path: str, limit: int) -> bytes:
    """Bounded local transcript reader supplied to host stages by the composition root."""
    with Path(path).open("rb") as stream:
        return stream.read(limit)


def build_runtime_request(
    request: "StageRequest", deps: "StageDeps", _secret: "SecretStr | None" = None, *, state_dir: Path
) -> "AgentRequest":
    """Translate server-admitted permission data; no policy dispatch or route selection on the host."""
    import secrets
    from typing import Any, cast

    from skm.kernel.ids import HostId
    from skm.kernel.isolation import parse_isolation_profile
    from skm.modules.runtimes.domain.request import (
        AgentRequest,
        ProcessOwner,
        ResultFormat,
        RuntimeLimits,
    )
    from skm.modules.runtimes.public import Effort, RoleId, VerificationContext

    step = cast("dict[str, Any]", request.begin["step"])
    if request.context is None or deps.environment is None or request.capture is None:
        raise ValueError("runtime requires final context and owned environment")
    environment = deps.environment
    workdir = next(iter(environment.mounts.values()))
    task = cast("dict[str, Any]", request.task)
    owner = ProcessOwner(
        UUID(task["host_id"]),
        UUID(task["worker_id"]),
        UUID(task["attempt_id"]),
        UUID(str(request.begin["stage_record_id"])),
        "step",
        UUID(step["step_id"]),
        secrets.token_hex(24),
        str(state_dir / "identities"),
    )
    from skm.bootstrap.worker_permissions import runtime_permissions

    home = state_dir / "client-homes" / str(owner.attempt_id) / step["route"]["runtime_id"]
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    grant = runtime_permissions(step["permissions"], environment.mounts)
    limits = step["limits"]
    verification = step.get("admission", {}).get("verification_context")
    snapshot = step.get("route_snapshot", {})
    return AgentRequest(
        step["step_id"],
        step["route"]["runtime_id"],
        step["route"]["model"],
        None if step["route"]["effort"] is None else Effort(step["route"]["effort"]),
        RoleId(step["role"]),
        request.context.rendered_prompt,
        request.context.prompt_digest,
        ResultFormat.JSON,
        step["result_schema_urn"],
        str(workdir),
        grant,
        parse_isolation_profile(step["isolation_profile"]),
        owner,
        "isolated",
        str(home),
        step["session"]["resume_ref"],
        step["session_policy"],
        (),
        {},
        {},
        (),
        RuntimeLimits(**limits, max_output_bytes=request.capture.max_bytes),
        {key: str(task[key]) for key in ("run_id", "task_id", "attempt_id", "task_key")},
        verification_context=None
        if verification is None
        else VerificationContext(
            host_id=HostId(UUID(verification["host_id"])),
            binary_sha256=verification["binary_sha256"],
            os=verification["os"],
            kernel=verification["kernel"],
            adapter_version=verification["adapter_version"],
            isolation_profile=parse_isolation_profile(verification["isolation_profile"]),
            launch_config_digest=verification["launch_config_digest"],
        ),
        verification_key=snapshot.get("verification_key"),
        expected_runtime_version=snapshot.get("runtime_version"),
    )


def _publish_complete(
    storage: "StorageBudget", root: Path, owner_id: str, target: Path, content: bytes
) -> None:
    """Publish ``target`` only once ``content`` is complete.

    Reserving through ``open_file`` creates the final name as an empty file before the
    write. Readers that glob that name then parse it as JSON.
    """
    from skm.platform.fs.atomic_write import atomic_write

    with storage.reserve(root, owner_id=owner_id, max_bytes=len(content), min_free_bytes=0):
        atomic_write(target, content, mode=0o600)


class WorkerReaper:
    """Keep durable proofs until the server acknowledges claim; uncertain markers block all slots."""

    def __init__(
        self,
        state_dir: Path,
        storage: "StorageBudget",
        *,
        resolve: "Callable[[ProcessOwnership], OwnedContainment | None]",
    ) -> None:
        from threading import RLock

        self.state_dir, self.storage, self.resolve = state_dir, storage, resolve
        self._lock = RLock()
        self._proofs = state_dir / "recovery" / "reaped"
        self._identities = state_dir / "identities"
        self._identities.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._proofs.mkdir(mode=0o700, parents=True, exist_ok=True)

    def record(self, handle: "SessionHandle") -> None:
        from skm.modules.runtimes.public import process_ownership_to_json

        if handle.ownership is None:
            raise ValueError("a spawned runtime must retain durable process ownership")
        root = self.state_dir / "ownership-facts"
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = root / f"{handle.ownership.owner.unit_id}.json"
        content = json.dumps(
            {
                "pid": handle.pid,
                "pgid": handle.pid,
                "started_at": handle.started_at.isoformat(),
                "start_ticks": handle.process_start_ticks,
                "ownership": process_ownership_to_json(handle.ownership),
            },
            default=str,
        ).encode()
        _publish_complete(self.storage, root, handle.request_id, target, content)

    def reap(self) -> tuple[JsonObject, ...]:
        from typing import cast

        from skm.adapters.runtimes._cli_session.identity import reap_orphans
        from skm.modules.runtimes.public import process_ownership_to_json

        outer = self

        class RecordingContainment:
            def __init__(self, backend: "OwnedContainment", ownership: "ProcessOwnership") -> None:
                self.backend, self.ownership = backend, ownership

            def confirmed(self, ownership: "ProcessOwnership") -> bool:
                return self.backend.confirmed(ownership)

            def signal(self, sig: int) -> None:
                self.backend.signal(sig)

            def identity_facts(self) -> object:
                from datetime import UTC, datetime

                owner = self.ownership.owner
                facts = outer.state_dir / "ownership-facts" / f"{owner.unit_id}.json"
                if facts.exists():
                    return json.loads(facts.read_text())
                # No child facts exist for a pre-exec marker. Its timestamp identifies the launch intent.
                marker = outer._identities / f"{owner.unit_id}.json"
                return {
                    "pid": None,
                    "pgid": None,
                    "started_at": datetime.fromtimestamp(marker.stat().st_mtime, UTC).isoformat(),
                    "ownership": process_ownership_to_json(self.ownership),
                }

            def empty(self) -> bool | None:
                empty = self.backend.empty()
                if empty is True:
                    owner = self.ownership.owner
                    target = outer._proofs / f"{owner.unit_id}.json"
                    if not target.exists():
                        proof = {
                            "stage_record_id": str(owner.stage_record_id),
                            "unit_kind": owner.unit_kind,
                            "unit_id": str(owner.unit_id),
                            "dead": True,
                            "identity": self.identity_facts(),
                        }
                        content = json.dumps(proof, default=str).encode()
                        _publish_complete(outer.storage, outer._proofs, str(owner.unit_id), target, content)
                return empty

        def resolve(ownership: "ProcessOwnership") -> "OwnedContainment | None":
            backend = self.resolve(ownership)
            return None if backend is None else RecordingContainment(backend, ownership)

        with self._lock:
            reap_orphans(self._identities, resolve=resolve)
            return tuple(
                cast("JsonObject", json.loads(path.read_text()))
                for path in sorted(self._proofs.glob("*.json"))
            )

    def pending(self) -> bool:
        with self._lock:
            return any(self._identities.glob("*.json"))

    def acknowledge(self, proofs: "tuple[JsonObject, ...]") -> None:
        from skm.platform.fs.atomic_write import fsync_dir

        with self._lock:
            for proof in proofs:
                unit = str(UUID(str(proof["unit_id"])))
                (self._proofs / f"{unit}.json").unlink(missing_ok=True)
            fsync_dir(self._proofs)


def build_worker_services(
    state_dir: Path,
    *,
    stages: "StageRegistry",
    context_inputs: "ContextInputs | None",
    resolve: "Callable[[ProcessOwnership], OwnedContainment | None]",
    storage: "StorageBudget | None" = None,
    tick: Callable[[], None] = lambda: None,
) -> "WorkerServices":
    from functools import partial

    from skm.modules.execution.host.context import WorkerServices
    from skm.modules.execution.ports import StageDeps
    from skm.platform.system_clock import SystemClock, SystemMonotonic
    from skm.platform.system_entropy import SystemEntropy

    budget = storage if storage is not None else build_host_storage(state_dir)
    reaper = WorkerReaper(state_dir, budget, resolve=resolve)
    return WorkerServices(
        state_dir,
        budget,
        SystemClock(),
        SystemMonotonic(),
        SystemEntropy(),
        worker_command_factories(),
        stages,
        StageDeps,
        context_inputs,
        partial(build_runtime_request, state_dir=state_dir),
        reaper.reap,
        reaper.pending,
        reaper.acknowledge,
        concurrency=worker_concurrency(),
        read_bytes=Path.read_bytes,
        tick=tick,
        process_started=reaper.record,
    )


def build_context_inputs(
    *,
    checkout: "Callable[[PreparedEnvironment], CheckoutReader] | None" = None,
    publish_prompt: "Callable[[HostContext, bytes, str], JsonObject] | None" = None,
) -> "ContextInputs":
    """Use the owning context codec and a lawful prompt publisher, without public worker file mutations."""
    from skm.adapters.git.host_inputs import GitCheckoutReader
    from skm.modules.context.application.commands.finalize_manifest import FinalizeManifest
    from skm.modules.context.domain.research import ResearchBatch, result_from_json
    from skm.modules.context.host.research_query import run
    from skm.modules.execution.host.context_inputs import ContextInputs
    from skm.platform.tokens.heuristic import HeuristicTokenEstimator

    def query(ctx: "HostContext", request: JsonObject) -> "ResearchBatch":
        result = run(ctx, request)
        return ResearchBatch(
            cast("str", result["query_text"]),
            cast("str", result["query_digest"]),
            tuple(result_from_json(row) for row in cast("list[JsonObject]", result["results"])),
        )

    return ContextInputs(
        HeuristicTokenEstimator(),
        decode_context_draft,
        checkout
        or (
            lambda env: GitCheckoutReader(env.mounts, baseline={b.mount: b.commit_sha for b in env.baseline})
        ),
        publish_prompt,
        FinalizeManifest.from_json,
        research_query=query,
    )


def with_worker_tick(
    host: HostServices, extra_tick: Callable[[], None], *, refresh_offers: bool = False
) -> HostServices:
    """Attach a shared credential tick or a runtime probe outside the renewal loop."""
    from dataclasses import replace

    from skm.modules.execution.host.context import WorkerServices

    services = host.gateways.get(WorkerServices)

    def tick() -> None:
        services.tick()
        extra_tick()

    updated = replace(services, refresh_offers=extra_tick) if refresh_offers else replace(services, tick=tick)
    table = GatewayTable({**host.gateways.entries, WorkerServices: updated}, "host_gateway")
    return replace(host, gateways=table)


def run_worker_contexts(contexts: "Sequence[HostContext]", request: JsonObject) -> JsonObject:
    """Entrypoints reach the host loop through the composition boundary."""
    from skm.modules.execution.host.worker_loop import run

    return run(contexts, request)


def worker_concurrency() -> "HostConcurrency":
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, RLock, Thread

    from skm.modules.execution.host.heartbeat import HostConcurrency

    return HostConcurrency(
        Event,
        lambda target, name: Thread(target=target, name=name, daemon=True),
        RLock,
        lambda size: ThreadPoolExecutor(max_workers=size),
    )


@cache
def _worker_schemas() -> "SchemaRegistry":
    from skm.platform.schema.registry import SchemaRegistry

    return SchemaRegistry.load_default()


def worker_schema_issues(urn: str, document: object) -> tuple[JsonObject, ...]:
    return tuple(
        {"path": issue.pointer, "message": issue.message}
        for issue in _worker_schemas().validate(urn, document)
    )
