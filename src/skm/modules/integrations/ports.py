"""Repository and host-gateway ports of the ``integrations`` module (integrations §6)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol

from skm.kernel.gateways import host_gateway
from skm.kernel.pagination import Cursor, Page
from skm.kernel.ports_uow import repository_port

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence
    from pathlib import Path
    from uuid import UUID

    from skm.kernel.ids import ProjectId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.kernel.scopes import ScopeRef
    from skm.modules.workspace.public import CheckoutBindingId

    from .domain.contracts import ClientLayer, HookOutput
    from .domain.desired import DesiredFile, ProjectionInputs
    from .domain.filesystem import FileStat
    from .domain.hook_events import NormalizedHookEvent
    from .domain.hook_rules import HookDecision
    from .domain.observed import AppliedFileRecord
    from .domain.projection import LocalPreImage, LocalPreImageKey, Projection, ProjectionId
    from .domain.reports import CommandResult
    from .domain.target import TargetCapabilities, TargetId
    from .generated.host import SyncProjectionsResult

__all__ = [
    "CheckoutFs",
    "CheckoutGitExcludes",
    "Cursor",
    "HostCommandRunner",
    "IntegrationTarget",
    "IntegrationTargetRegistry",
    "LocalCheckoutProjections",
    "Page",
    "ProjectionConfig",
    "ProjectionRepository",
    "UserHomeReader",
]


@repository_port
class ProjectionRepository(Protocol):
    def get(self, projection_id: ProjectionId) -> Projection: ...

    def find(
        self, project_id: ProjectId, checkout_binding_id: CheckoutBindingId, target: TargetId
    ) -> Projection | None: ...

    def list_for_project(
        self, project_id: ProjectId, *, after: Cursor | None, limit: int
    ) -> Page[Projection]: ...

    def add(self, projection: Projection) -> None: ...

    def save(self, projection: Projection, *, expected_version: int) -> None: ...

    def files(self, projection_id: ProjectionId) -> tuple[AppliedFileRecord, ...]: ...

    def replace_files(self, projection_id: ProjectionId, records: tuple[AppliedFileRecord, ...]) -> None: ...

    def managed_file_paths(self, project_id: ProjectId, target: TargetId) -> frozenset[str]: ...

    def mark_pending(self, scope: ScopeRef) -> int: ...


@host_gateway
class IntegrationTarget(Protocol):
    target_id: TargetId
    renderer_version: str

    def capabilities(self) -> TargetCapabilities: ...

    def render(self, inputs: ProjectionInputs) -> tuple[DesiredFile, ...]: ...

    def normalize_hook_payload(
        self, event_name: str, payload: Mapping[str, JsonValue]
    ) -> NormalizedHookEvent: ...

    def render_hook_decision(self, event: NormalizedHookEvent, decision: HookDecision) -> HookOutput: ...

    def client_layers(self, fs: CheckoutFs, home: UserHomeReader) -> tuple[ClientLayer, ...]: ...

    def instruction_paths(self) -> tuple[str, ...]: ...

    def summarize_session(self, payload: Mapping[str, JsonValue], fs: CheckoutFs) -> JsonObject | None: ...


@host_gateway
class IntegrationTargetRegistry(Protocol):
    def get(self, target: TargetId) -> IntegrationTarget: ...

    def all(self) -> tuple[IntegrationTarget, ...]: ...


@host_gateway
class CheckoutFs(Protocol):
    root: Path

    def read(self, relative_path: str) -> bytes | None: ...

    def stat(self, relative_path: str) -> FileStat: ...

    def write_atomic(self, relative_path: str, data: bytes, *, expected_whole_digest: str | None) -> str: ...

    def remove(self, relative_path: str, *, expected_whole_digest: str) -> None: ...

    def is_gitignored(self, relative_path: str) -> bool | None: ...


@host_gateway
class CheckoutGitExcludes(Protocol):
    def require_untracked(self, checkout: str) -> None: ...

    def untrack_service_files(self, checkout: str) -> tuple[str, ...]: ...

    def sync(
        self,
        checkout: str,
        *,
        conflict_sources: Collection[str] = (),
        conflict_suffix: str = ".skm-new",
    ) -> bool:
        """Add service paths and sidecars derived from trusted projection plans."""
        ...


@host_gateway
class ProjectionConfig(Protocol):
    def __call__(self, project_id: ProjectId) -> Mapping[str, JsonValue]: ...


@host_gateway
class LocalCheckoutProjections(Protocol):
    """Resolve and synchronize verified checkouts for the current local caller."""

    def resolve(self, project_id: ProjectId, mount: str) -> tuple[UUID, Path]: ...

    def require_apply(self, project_id: ProjectId) -> None: ...

    def save_pre_image(self, key: LocalPreImageKey, contents: bytes | None, *, replace: bool) -> UUID: ...

    def read_pre_image(self, key: LocalPreImageKey) -> LocalPreImage | None: ...

    def sync(self, project_id: ProjectId) -> SyncProjectionsResult: ...


@host_gateway
class UserHomeReader(Protocol):
    def read(
        self,
        logical: Literal[
            "claude.user_settings", "claude.managed_settings", "codex.user_config", "vscode.user_settings"
        ],
    ) -> bytes | None: ...


@host_gateway
class HostCommandRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        stdin: bytes,
        timeout_ms: int,
        max_stdout: int = 65536,
        max_stderr: int = 8192,
    ) -> CommandResult: ...
