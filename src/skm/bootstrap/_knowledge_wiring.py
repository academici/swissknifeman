"""Bind the context memory gateway for the selected modules."""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.adapters.git.repo_inspect import MARKER_FILENAME, GitRepositoryInspector
from skm.adapters.knowledge.context_source import KnowledgeMemoryRetriever
from skm.adapters.knowledge.manifest_readers.composer_json import ComposerJsonReader
from skm.adapters.knowledge.manifest_readers.package_json import PackageJsonReader
from skm.adapters.knowledge.manifest_readers.pyproject import PyprojectReader
from skm.adapters.knowledge.null_retriever import NullMemoryRetriever
from skm.adapters.knowledge.serena_reader import SerenaCodeGraphReader
from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostServices
from skm.bootstrap.host_services import read_recorded_host_id
from skm.kernel.actor import Actor
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.context.ports import MemoryRetriever
from skm.modules.knowledge.module import MODULE as KNOWLEDGE
from skm.modules.knowledge.ports import CodeGraphReader, ManifestReader
from skm.modules.settings.public import ExplainConfig, ExplainConfigResult
from skm.modules.workspace.public import GetProject, ProjectView
from skm.platform.config.bootstrap import BootstrapConfig
from skm.platform.config.loader import ConfigLoader
from skm.platform.system_clock import SystemClock

if TYPE_CHECKING:
    from skm.bootstrap.composition import App

__all__ = [
    "bind_cli_knowledge",
    "bind_http_cli_knowledge",
    "bind_memory_retriever",
    "current_checkout_revision",
]


def bind_memory_retriever(
    gateways: GatewayTable, disabled: frozenset[str], config: ConfigLoader, clock: Clock
) -> GatewayTable:
    if gateways.has(MemoryRetriever):
        return gateways
    retriever = NullMemoryRetriever() if "knowledge" in disabled else KnowledgeMemoryRetriever(clock, config)
    return GatewayTable({**gateways.entries, MemoryRetriever: retriever}, gateways.kind)


def bind_cli_knowledge(app: App, actor: Actor) -> tuple[App, Actor]:
    """Add the checkout-only graph gateways to a registered CLI host."""
    host = app.host
    if host is None or "knowledge" in app.bus._registry.disabled_modules():  # pyright: ignore[reportPrivateUsage]
        return app, actor
    bound = _bind_graph_gateways(host, app.client(actor=actor, surface=Surface.CLI))
    return replace(app, host=bound), actor


def bind_http_cli_knowledge(bootstrap: BootstrapConfig, client: SkmClient) -> HostServices | None:
    host_id = (
        HostId(bootstrap.host_id)
        if isinstance(bootstrap.host_id, UUID)
        else read_recorded_host_id(bootstrap.state_dir)
    )
    if host_id is None:
        return None
    host = HostServices(
        host_id,
        Surface.CLI,
        GatewayTable({}, "host_gateway"),
        lambda: _explain_graph(client, "host", str(host_id)),
        {},
    )
    return _bind_graph_gateways(host, client)


def current_checkout_revision(
    client: SkmClient,
    workspace_id: UUID,
    *,
    project: ProjectView | None = None,
    fallback: str | None = None,
) -> str | None:
    """Observe HEAD in a local checkout of a repository mounted by the project."""
    cwd = Path.cwd()
    root = next((path for path in (cwd, *cwd.parents) if (path / ".git").exists()), None)
    if root is None or (project is None and not (root / MARKER_FILENAME).exists()):
        return fallback
    inspector = GitRepositoryInspector()
    if inspector.toplevel(root) != root:
        return fallback
    marker = inspector.read_marker(root)
    if project is None:
        if marker is None or marker.workspace_id != workspace_id:
            return fallback
        try:
            project = cast("ProjectView", client.ask(GetProject(project_id=marker.project_id)))
        except (Forbidden, NotFound):
            return fallback
    if project.workspace_id != workspace_id:
        return fallback
    if marker is not None:
        if (
            marker.workspace_id != workspace_id
            or project.project_id != marker.project_id
            or not any(
                mount.repository_id == marker.repository_id and mount.mount_name == marker.mount_name.value
                for mount in project.mounts
            )
        ):
            return fallback
    else:
        remotes = {remote.value for remote in inspector.remotes(root)}
        repositories = {mount.repository_id for mount in project.mounts if mount.canonical_remote in remotes}
        if len(repositories) != 1:
            return fallback
    return inspector.head(root)


class _ManifestReaders:
    def __init__(self) -> None:
        self.readers: tuple[ManifestReader, ...] = (
            PyprojectReader(tomllib.loads),
            PackageJsonReader(),
            ComposerJsonReader(),
        )

    def dependencies(self, root: Path) -> tuple[JsonObject, ...]:
        return tuple(item for reader in self.readers for item in reader.dependencies(root))

    def read_snapshot(self, root: str) -> tuple[str, tuple[JsonObject, ...]]:
        return SystemClock().now().isoformat(), self.dependencies(Path(root))


@dataclass(frozen=True, slots=True)
class _GraphConfig:
    local: Callable[[], Any]
    client: SkmClient

    def get(self, key: str) -> JsonValue:
        return self.local().get(key)

    def for_project(self, project_id: str) -> JsonObject:
        return _explain_graph(self.client, "project", project_id)


def _explain_graph(client: SkmClient, level: str, scope_id: str) -> JsonObject:
    result = client.ask(
        ExplainConfig.from_json(
            {
                "scope": {"level": level, "scope_id": scope_id},
                "section": "knowledge",
                "detail": "value",
            }
        )
    )
    report = cast("ExplainConfigResult", result).to_json()
    return _graph_values(cast("list[JsonObject]", report["keys"]))


def _graph_values(keys: list[JsonObject]) -> JsonObject:
    values: JsonObject = {}
    for entry in keys:
        key = cast("str", entry["key"])
        if key.startswith(("knowledge.graph.", "knowledge.code_graph.")):
            if entry.get("valid") is False:
                raise ValidationFailed(
                    ErrorCode.CONFIG_INVALID, "Invalid graph configuration", details={"key": key}
                )
            values[key] = entry.get("value")
    return values


def _bind_graph_gateways(host: HostServices, client: SkmClient) -> HostServices:
    entries: dict[type[object], object] = {
        CodeGraphReader: SerenaCodeGraphReader(),
        ManifestReader: _ManifestReaders(),
        **host.gateways.entries,
    }
    return replace(
        host,
        gateways=GatewayTable(entries, "host_gateway"),
        operations={
            **host.operations,
            **{op.name: op for op in KNOWLEDGE.host_operations if host.surface in op.surfaces},
        },
        host_config=lambda: _GraphConfig(cache(host.host_config), client),
    )
