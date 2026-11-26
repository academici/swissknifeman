"""Compose workspace checkout operations with the machine store and current project caller."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from uuid import UUID, uuid4, uuid5

from skm.adapters.git.identity_proof import IdentityProofCache
from skm.adapters.git.repo_inspect import GitRepositoryInspector
from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext
from skm.bootstrap.host_services import read_recorded_host_id
from skm.bootstrap.machine import open_machine_store
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, ProjectId, RepositoryId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.execution.ports import ReviewCheckoutPathResolver
from skm.modules.knowledge.ports import GraphCheckoutResolver
from skm.modules.workspace import public as workspace
from skm.modules.workspace.host.bind_checkout import bind_checkout
from skm.modules.workspace.host.verify_checkout import verify_checkout
from skm.modules.workspace.ports import RepositoryInspector
from skm.platform.config.bootstrap import BootstrapConfig
from skm.platform.logging.logger import get_logger
from skm.platform.machine import (
    MachineBinding,
    MachineCheckout,
    MachineCheckoutKey,
    MachinePrincipal,
    MachineRetry,
    MachineRetryKey,
    MachineStore,
)
from skm.platform.system_clock import SystemClock

__all__ = [
    "LocalCheckoutResolver",
    "bind_checkout_paths",
    "bind_checkout_runner",
    "checkout_host_id",
    "resolve_worker_checkout",
    "run_checkout_operation",
    "worker_checkout_root",
]

type CheckoutOperation = Literal["bind", "verify"]
type CheckoutRunner = Callable[[CheckoutOperation, dict[str, Any], UUID | None], JsonObject]


class _Record(Protocol):
    @classmethod
    def from_json(cls, data: JsonObject) -> Any: ...

    def to_json(self) -> JsonObject: ...


class _RetryClient(SkmClient, Protocol):
    def safe_retry_deadline(self) -> datetime: ...

    def dispatch_before(self, command: object, *, idempotency_key: str, safe_until: datetime) -> object: ...


_RESULTS: dict[type[object], type[_Record]] = {
    workspace.RegisterRepository: workspace.RegisterRepositoryResult,
    workspace.AttachRepository: workspace.AttachRepositoryResult,
    workspace.BindCheckout: workspace.BindCheckoutResult,
    workspace.RecordCheckoutVerification: workspace.RecordCheckoutVerificationResult,
}
_CHECKOUT_REQUEST_NAMESPACE = UUID("863a985b-9459-4e7f-90f2-dedd934c5499")


def checkout_host_id(config: BootstrapConfig) -> HostId:
    host = (
        HostId(config.host_id)
        if isinstance(config.host_id, UUID)
        else read_recorded_host_id(config.state_dir)
    )
    if host is None:
        raise error_for(ErrorCode.CONFIG_INVALID, "A registered local host is required")
    return host


def _checkout_key(installation: UUID, instance: UUID, host: HostId, locator: str) -> MachineCheckoutKey:
    identity = workspace.checkout_id_from_locator(locator)
    if identity is None:
        raise error_for(ErrorCode.CHECKOUT_UNBOUND, "Project did not provide a machine checkout ID")
    return MachineCheckoutKey(installation, instance, host, identity)


def _recorded_root(store: MachineStore, key: MachineCheckoutKey) -> Path:
    found = store.get_checkout(key)
    if found is None or found.key != key:
        raise error_for(ErrorCode.CHECKOUT_UNBOUND, "Checkout is not registered on this machine and host")
    return found.root


_PROOFS = IdentityProofCache(ttl_seconds=3.0)


def _check_identity(inspector: RepositoryInspector, root: Path, remote: str | None) -> Path:
    def prove() -> None:
        observed = inspector.observe(str(root))
        if observed.toplevel != str(root) or (
            remote is not None and remote not in {item.value for item in observed.remotes}
        ):
            raise error_for(ErrorCode.CHECKOUT_MISMATCH, "Local Git checkout no longer matches its binding")

    _PROOFS.proven(root, remote, prove, via=type(inspector))
    return root


def resolve_worker_checkout(
    store: MachineStore, installation: UUID, instance: UUID, host: HostId, mount: workspace.MountView
) -> Path:
    """Resolve a mount already read under the worker's lease and project authorization."""
    binding = mount.binding
    if binding is None or binding.local_locator is None or binding.state != "active":
        raise error_for(ErrorCode.CHECKOUT_UNBOUND, "Worker mount has no active local binding")
    key = _checkout_key(installation, instance, host, binding.local_locator)
    return _check_identity(
        GitRepositoryInspector(), _recorded_root(store, key), mount.repository.canonical_remote
    )


@dataclass(frozen=True, slots=True)
class LocalCheckoutResolver:
    scope: MachinePrincipal
    host: HostId
    store: MachineStore
    client: SkmClient
    inspector: RepositoryInspector

    def _key(self, locator: str) -> MachineCheckoutKey:
        return _checkout_key(self.scope.installation_id, self.scope.instance_id, self.host, locator)

    def bound_root(self, locator: str, workspace_id: UUID, project_id: UUID, repository_id: UUID) -> Path:
        key = self._key(locator)
        registered = self.store.get_binding(self.scope, key)
        if registered != MachineBinding(self.scope, key, workspace_id, project_id, repository_id):
            raise error_for(
                ErrorCode.CHECKOUT_UNBOUND, "Checkout is outside the current caller's local bindings"
            )
        return _recorded_root(self.store, key)

    def resolve(self, project_id: ProjectId, mount: str) -> tuple[UUID, Path]:
        location, root = self._resolve(project_id, mount)
        return location.binding_id, root

    def resolve_graph(self, project_id: ProjectId, mount: str) -> tuple[RepositoryId, str]:
        location, root = self._resolve(project_id, mount, require_fresh=True)
        return RepositoryId(location.repository_id), str(root)

    def _resolve(
        self, project_id: ProjectId, mount: str, *, require_fresh: bool = False
    ) -> tuple[workspace.CheckoutLocationView, Path]:
        location = self.client.ask(workspace.ResolveCheckout(project_id, mount, self.host))
        mounts = self.client.ask(workspace.ListProjectRepositories(project_id, host_id=self.host))
        if not isinstance(location, workspace.CheckoutLocationView) or not isinstance(
            mounts, workspace.ListProjectRepositoriesView
        ):
            raise error_for(ErrorCode.CONFIG_INVALID, "Project did not confirm the current checkout")
        chosen = next((item for item in mounts.items if item.mount_name == mount), None)
        if (
            chosen is None
            or chosen.binding is None
            or chosen.binding.binding_id != location.binding_id
            or chosen.binding.state != "active"
            or chosen.binding.local_locator != location.local_locator
            or chosen.repository.repository_id != location.repository_id
            or location.state != "active"
        ):
            raise error_for(ErrorCode.CHECKOUT_MISMATCH, "Project checkout changed during resolution")
        if require_fresh and (location.is_stale or chosen.binding.is_stale):
            raise error_for(ErrorCode.CHECKOUT_UNBOUND, "An active checkout binding is required")
        root = self.bound_root(
            location.local_locator, chosen.repository.workspace_id, project_id, location.repository_id
        )
        return location, _check_identity(self.inspector, root, chosen.repository.canonical_remote)


@dataclass(frozen=True, slots=True)
class _Transaction:
    resolver: LocalCheckoutResolver
    key: MachineRetryKey
    request: MachineRetry

    @classmethod
    def open(
        cls,
        resolver: LocalCheckoutResolver,
        checkout: MachineCheckoutKey,
        operation: CheckoutOperation,
        request_id: UUID,
        payload: JsonObject,
    ) -> "_Transaction":
        key = MachineRetryKey(resolver.scope, checkout, operation, request_id, "request")
        client = cast("_RetryClient", resolver.client)
        try:
            row = resolver.store.begin_retry(
                MachineRetry(key, client.new_idempotency_key(), payload, client.safe_retry_deadline())
            )
        except SkmError as error:
            if error.code is not ErrorCode.IDEMPOTENCY_KEY_REUSED:
                raise
            raise error_for(
                ErrorCode.IDEMPOTENCY_KEY_REUSED,
                "Checkout inputs changed for the existing request",
                details={
                    "request_id": str(request_id),
                    "hint": "Use a new explicit --request-id for changed inputs.",
                },
            ) from None
        return cls(resolver, key, row)

    @property
    def locator(self) -> str:
        return workspace.checkout_locator(self.key.checkout.checkout_id)

    def _get(self, step: str) -> MachineRetry | None:
        return self.resolver.store.get_retry(replace(self.key, step=step))

    def has_step(self, step: str) -> bool:
        return self._get(step) is not None

    def _begin(self, step: str, payload: JsonObject) -> MachineRetry:
        key = replace(self.key, step=step)
        return self.resolver.store.begin_retry(
            MachineRetry(key, self.resolver.client.new_idempotency_key(), payload, self.request.safe_until)
        )

    def match(self, query: workspace.MatchCheckout) -> workspace.AttachDecisionView:
        current = self.resolver.client.ask(query)
        if not isinstance(current, workspace.AttachDecisionView):
            raise error_for(ErrorCode.CONFIG_INVALID, "Project returned an invalid checkout decision")
        row = self._get("match")
        if row is not None and row.receipt is not None:
            return workspace.AttachDecisionView.from_json(row.receipt)
        if row is None:
            row = self._begin("match", self.request.payload)
        saved = self.resolver.store.confirm_retry(row.key, current.to_json())
        if saved.receipt is None:
            raise error_for(ErrorCode.INTERNAL_ERROR, "Checkout decision was not saved")
        return workspace.AttachDecisionView.from_json(saved.receipt)

    def dispatch(self, step: str, command: object) -> object:
        dto = cast("_Record", command)
        payload = dto.to_json()
        result_type = _RESULTS[type(command)]
        row = self._get(step)
        if row is None:
            row = self._begin(step, payload)
        else:
            # The original observed timestamp and CAS version belong to the persisted request.
            changing = {"observed_at", "expected_row_version"}
            if {k: v for k, v in row.payload.items() if k not in changing} != {
                k: v for k, v in payload.items() if k not in changing
            }:
                raise error_for(
                    ErrorCode.IDEMPOTENCY_KEY_REUSED, "Checkout request changed; use a new request ID"
                )
        if row.receipt is not None:
            return result_type.from_json(row.receipt)
        if row.state(SystemClock().now()) == "expired":
            raise error_for(
                ErrorCode.INVALID_TRANSITION,
                "Checkout write outcome is uncertain; the safe retry window closed",
                details={
                    "reason": "idempotency_window_closed",
                    "request_id": str(self.key.request_id),
                    "step": step,
                },
            )
        client = cast("_RetryClient", self.resolver.client)
        result = client.dispatch_before(
            type(dto).from_json(row.payload), idempotency_key=row.idempotency_key, safe_until=row.safe_until
        )
        if not isinstance(result, result_type):
            raise error_for(ErrorCode.CONFIG_INVALID, "Project returned an invalid checkout receipt")
        self.resolver.store.confirm_retry(row.key, result.to_json())
        return result

    def bound(
        self, workspace_id: UUID, project_id: UUID, repository_id: UUID, binding_id: UUID, mount: str
    ) -> None:
        # Recheck the live binding even when a restart has a confirmed write receipt.
        view = self.resolver.client.ask(
            workspace.ResolveCheckout(ProjectId(project_id), mount, self.resolver.host)
        )
        if (
            not isinstance(view, workspace.CheckoutLocationView)
            or view.repository_id != repository_id
            or view.binding_id != binding_id
            or view.local_locator != self.locator
            or view.state != "active"
        ):
            raise error_for(ErrorCode.CHECKOUT_MISMATCH, "Project no longer confirms this checkout binding")
        self.resolver.store.put_binding(
            MachineBinding(self.resolver.scope, self.key.checkout, workspace_id, project_id, repository_id)
        )


def _intent(payload: dict[str, Any]) -> JsonObject:
    comparable = {
        key: value for key, value in payload.items() if key not in {"path", "confirm", "instance_id"}
    }
    return {key: str(value) if isinstance(value, UUID) else value for key, value in comparable.items()}


def _ensure_repository(client: SkmClient, workspace_id: WorkspaceId, repository_id: RepositoryId) -> None:
    after = None
    while True:
        page = client.ask(workspace.ListRepositories(workspace_id=workspace_id, after=after, limit=100))
        if not isinstance(page, workspace.ListRepositoriesView):
            raise error_for(ErrorCode.CONFIG_INVALID, "Project returned invalid repository data")
        if any(item.repository_id == repository_id for item in page.items):
            return
        if page.next is None:
            raise error_for(ErrorCode.NOT_FOUND, "Requested repository is outside the selected workspace")
        after = page.next


def _bind(
    ctx: HostContext, resolver: LocalCheckoutResolver, payload: dict[str, Any], request_id: UUID | None
) -> JsonObject:
    ws = WorkspaceId(UUID(str(payload["workspace_id"])))
    if (repo := payload.get("repository_id")) is not None:
        _ensure_repository(ctx.client, ws, RepositoryId(UUID(str(repo))))

    def begin(observed: workspace.ObservedCheckout) -> _Transaction:
        assert observed.toplevel is not None  # noqa: S101 -- validated by the host operation
        if observed.marker is not None and observed.marker.instance_id != resolver.scope.instance_id:
            raise error_for(ErrorCode.CHECKOUT_MISMATCH, "Checkout marker belongs to a different instance")
        root = Path(observed.toplevel)
        key = MachineCheckoutKey(
            resolver.scope.installation_id, resolver.scope.instance_id, resolver.host, uuid4()
        )
        checkout = resolver.store.reserve_checkout(MachineCheckout(key, root))
        fields = _intent(payload)
        stable = request_id or uuid5(
            _CHECKOUT_REQUEST_NAMESPACE, json.dumps(fields, sort_keys=True, separators=(",", ":"))
        )
        fields.update(
            remotes=[remote.value for remote in observed.remotes],
            head=observed.head,
            dirty=observed.dirty,
            exists=observed.exists,
        )
        return _Transaction.open(resolver, checkout.key, "bind", stable, fields)

    return bind_checkout(ctx, {**payload, "instance_id": resolver.scope.instance_id}, begin=begin).to_json()


def _verify(
    ctx: HostContext, resolver: LocalCheckoutResolver, payload: dict[str, Any], request_id: UUID
) -> JsonObject:
    project_id = ProjectId(UUID(str(payload["project_id"])))
    project = ctx.client.ask(workspace.GetProject(project_id=project_id))
    if not isinstance(project, workspace.ProjectView) or project.project_id != project_id:
        raise error_for(ErrorCode.CONFIG_INVALID, "Project did not confirm the verification scope")
    workspace_id = WorkspaceId(project.workspace_id)

    def root_for(locator: str, repository_id: UUID) -> str:
        return str(resolver.bound_root(locator, workspace_id, project_id, repository_id))

    def begin(locator: str, observed: workspace.ObservedCheckout) -> _Transaction:
        # MatchCheckout supplies the live workspace checkout.bind check even on a confirmed local receipt.
        ctx.client.ask(
            workspace.MatchCheckout(
                workspace_id=workspace_id,
                host_id=resolver.host,
                project_id=project_id,
                observed_exists=observed.exists,
                observed_toplevel=locator if observed.toplevel else None,
                observed_remotes=tuple(remote.value for remote in observed.remotes),
                observed_head=observed.head,
                observed_marker=None,
                assume_yes=True,
            )
        )
        fields = _intent(payload)
        fields.update(
            remotes=[remote.value for remote in observed.remotes],
            head=observed.head,
            dirty=observed.dirty,
            exists=observed.exists,
        )
        return _Transaction.open(
            resolver,
            _checkout_key(resolver.scope.installation_id, resolver.scope.instance_id, resolver.host, locator),
            "verify",
            request_id,
            fields,
        )

    return verify_checkout(ctx, payload, resolve_root=root_for, begin=begin).to_json()


def run_checkout_operation(
    operation: CheckoutOperation,
    resolver: LocalCheckoutResolver,
    payload: dict[str, Any],
    request_id: UUID | None,
) -> JsonObject:
    ctx = HostContext(
        client=resolver.client,
        gateways=GatewayTable({RepositoryInspector: resolver.inspector}, "host_gateway"),
        host_id=resolver.host,
        config={},
        log=get_logger("workspace.local_checkout"),
        cancel=CancelSource().token,
    )
    if operation == "bind":
        return _bind(ctx, resolver, payload, request_id)
    current = request_id or uuid4()
    try:
        return _verify(ctx, resolver, payload, current)
    except SkmError as error:
        if error.code is not ErrorCode.BACKEND_UNAVAILABLE:
            raise
        raise error_for(
            error.code,
            error.message,
            details={
                **error.details,
                "request_id": str(current),
                "hint": f"Repeat the same verification with --request-id {current}.",
            },
            retryable=error.retryable,
        ) from None


def bind_checkout_runner(
    config: BootstrapConfig,
    client: SkmClient,
    store: MachineStore | None,
    scope: Callable[[], MachinePrincipal] | None,
) -> CheckoutRunner:
    def run(operation: CheckoutOperation, payload: dict[str, Any], request_id: UUID | None) -> JsonObject:
        if store is None or scope is None:
            raise error_for(
                ErrorCode.CONFIG_INVALID, "Checkout operations require a verified machine profile"
            )
        resolver = LocalCheckoutResolver(
            scope(), checkout_host_id(config), store, client, GitRepositoryInspector()
        )
        return run_checkout_operation(operation, resolver, payload, request_id)

    return run


def worker_checkout_root(
    config: BootstrapConfig,
    host: HostId,
    store: MachineStore | None,
    environ: Mapping[str, str],
    on_secret: Callable[[str], None],
) -> Callable[[workspace.MountView], Path] | None:
    installation, instance = config.installation_id, config.instance_id
    if installation is None and config.machine_database_url is None and store is None:
        return None
    if installation is None or instance is None:
        raise error_for(ErrorCode.CONFIG_INVALID, "Worker checkout requires a verified machine profile")
    machine = store if store is not None else open_machine_store(config, environ, on_secret=on_secret)
    return lambda mount: resolve_worker_checkout(machine, installation, instance, host, mount)


@dataclass(frozen=True, slots=True)
class _CheckoutPaths:
    scope: Callable[[], MachinePrincipal]
    host: HostId
    store: MachineStore
    client: SkmClient
    git: RepositoryInspector

    def _resolver(self) -> LocalCheckoutResolver:
        return LocalCheckoutResolver(self.scope(), self.host, self.store, self.client, self.git)

    def resolve(self, project_id: ProjectId, mount: str) -> str:
        _, path = self._resolver().resolve(project_id, mount)
        return str(path)

    def resolve_graph(self, project_id: ProjectId, mount: str) -> tuple[RepositoryId, str]:
        return self._resolver().resolve_graph(project_id, mount)


def bind_checkout_paths(
    factory: Callable[[], HostContext] | None,
    config: BootstrapConfig,
    store: MachineStore | None,
    scope: Callable[[], MachinePrincipal] | None,
) -> Callable[[], HostContext] | None:
    if factory is None or store is None or scope is None:
        return factory

    def context() -> HostContext:
        host = factory()
        entries = dict(cast("GatewayTable", host.gateways).entries)
        inspector = GitRepositoryInspector()
        entries.setdefault(RepositoryInspector, inspector)
        paths = _CheckoutPaths(scope, checkout_host_id(config), store, host.client, inspector)
        entries[ReviewCheckoutPathResolver] = paths
        entries[GraphCheckoutResolver] = paths
        return replace(host, gateways=GatewayTable(entries, "host_gateway"))

    return context
