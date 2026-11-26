"""Project and credential binding shared by embedded and HTTP MCP sessions."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast
from uuid import UUID

from skm.application_bus.client import SkmClient
from skm.bootstrap.local_memory import EpisodeScope, LocalEpisodicMemory
from skm.kernel.actor import Actor, PrincipalKind, TokenGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, InternalError, NotFound, PreconditionFailed, Unauthenticated
from skm.kernel.ids import PrincipalId, ProjectId, RunId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.access import public as access
from skm.modules.policy.public import tool_allowed
from skm.modules.settings import public as settings
from skm.modules.workspace import public as workspace
from skm.platform.logging.logger import get_logger

__all__ = ["DEFAULT_MAX_RESPONSE_TOKENS", "LocalMemorySession", "McpSession"]

_MAX_RESPONSE_TOKENS: Final = "api.mcp.max_response_tokens"
_CLI_CONTEXT_SCHEMA: Final = "urn:skm:cli:context:v1"
DEFAULT_MAX_RESPONSE_TOKENS: Final = 10_000
_LOG = get_logger("entrypoints.mcp")


def _unauthenticated() -> Unauthenticated:
    return Unauthenticated(ErrorCode.UNAUTHENTICATED, "An active SKM token is required")


def _project_from_context(path: Path | None, instance_id: UUID | None) -> UUID | None:
    if path is None:
        return None
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            return None
        document = cast("dict[str, object]", parsed)
        if document.get("schema") != _CLI_CONTEXT_SCHEMA:
            return None
        if instance_id is not None and document.get("instance_id") != str(instance_id):
            return None
        project_id: object = document.get("project_id")
        return UUID(project_id) if isinstance(project_id, str) else None
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        _LOG.warning("mcp.invalid_cli_context")
        return None


def _project_from_token(client: SkmClient, identity: access.WhoAmIView) -> workspace.ProjectView | None:
    token = identity.token
    if token is None or token.scope_id is None:
        return None
    candidates: tuple[UUID, ...] = (token.scope_id,)
    if token.kind.value == "assignment":
        candidates = tuple(
            UUID(scope_id)
            for scope_id, permissions in identity.permissions_by_scope.items()
            if scope_id != str(token.scope_id) and "project.read" in permissions
        )
    for candidate in candidates:
        try:
            return cast("workspace.ProjectView", client.ask(workspace.GetProject(project_id=candidate)))
        except NotFound:
            continue  # workspace and plan ancestors are valid scopes but have no project row
    return None


def _response_limit(client: SkmClient, project_id: UUID) -> int:
    request = settings.GetValue.from_json(
        {"scope": {"level": "project", "scope_id": str(project_id)}, "key": _MAX_RESPONSE_TOKENS}
    )
    try:
        configured = cast("settings.GetValueView", client.ask(request))
    except Forbidden:
        # A scoped credential, including a default assignment grant, may lack config.read.
        return DEFAULT_MAX_RESPONSE_TOKENS
    value = configured.value
    if not configured.present:
        return DEFAULT_MAX_RESPONSE_TOKENS
    if type(value) is not int or value <= 0:
        raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid MCP response limit")
    return value


def _actor(identity: access.WhoAmIView) -> Actor:
    token = identity.token
    if token is None or token.state != "active":
        raise _unauthenticated()
    principal = identity.principal
    return Actor(
        PrincipalId(principal.principal_id),
        PrincipalKind(principal.kind.value),
        principal.display_name,
        TokenGrant(
            token.token_id,
            token.kind.value,
            None if token.scope_id is None else ScopeId(token.scope_id),
            None if token.permissions is None else frozenset(token.permissions),
            token.assignment_id,
            token.step_id,
        ),
    )


@dataclass(frozen=True, slots=True)
class LocalMemorySession:
    store: LocalEpisodicMemory
    scope: EpisodeScope
    session_id: UUID


@dataclass(frozen=True, slots=True)
class McpSession:
    actor: Actor
    project_id: ProjectId
    client: SkmClient
    limits: JsonObject
    local_memory: LocalMemorySession | None = None
    stage_tools: frozenset[str] | None = None

    def allows_tool(self, name: str) -> bool:
        return self.stage_tools is None or tool_allowed((self.stage_tools,), f"mcp:skm/{name}")

    @classmethod
    def open(
        cls,
        client: SkmClient,
        *,
        project_id: UUID | None = None,
        cli_context_path: Path | None = None,
        instance_id: UUID | None = None,
        local_memory: tuple[LocalEpisodicMemory, UUID] | None = None,
    ) -> "McpSession":
        identity = cast("access.WhoAmIView", client.ask(access.WhoAmI()))
        actor = _actor(identity)
        if local_memory is not None and actor.kind is not PrincipalKind.HUMAN:
            raise Forbidden(ErrorCode.FORBIDDEN, "Local episodic memory requires a human credential")
        project = _project_from_token(client, identity) if project_id is None else None
        if project is None:
            selected = project_id or _project_from_context(cli_context_path, instance_id)
            if selected is None:
                raise PreconditionFailed(
                    ErrorCode.NO_PROJECT_SCOPE, "Select a project with --project or skm use"
                )
            project = cast("workspace.ProjectView", client.ask(workspace.GetProject(project_id=selected)))
        selected_project = ProjectId(project.project_id)
        binding = None
        if local_memory is not None:
            store, session_id = local_memory
            binding = LocalMemorySession(
                store, EpisodeScope(WorkspaceId(project.workspace_id), selected_project), session_id
            )
        return cls(actor, selected_project, client, {}, binding)

    @property
    def max_response_tokens(self) -> int:
        if _MAX_RESPONSE_TOKENS not in self.limits:
            grant = self.actor.grant
            if grant is not None and grant.permissions is not None and "config.read" not in grant.permissions:
                return DEFAULT_MAX_RESPONSE_TOKENS
            return _response_limit(self.client, self.project_id)
        value = self.limits[_MAX_RESPONSE_TOKENS]
        if type(value) is not int or value <= 0:
            raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid MCP response limit")
        return value

    @property
    def is_assignment(self) -> bool:
        return self.actor.grant is not None and self.actor.grant.kind == "assignment"

    @property
    def run_id(self) -> RunId | None:
        grant = self.actor.grant
        if grant is not None and grant.kind == "assignment" and grant.scope_id is not None:
            return RunId(grant.scope_id)
        return None

    @property
    def assignment_id(self) -> UUID | None:
        grant = self.actor.grant
        return None if grant is None else grant.assignment_id

    @property
    def step_id(self) -> UUID | None:
        grant = self.actor.grant
        return None if grant is None else grant.step_id

    def refresh(self) -> access.WhoAmIView:
        """Check the same live credential and project before discovery or dispatch."""
        identity = cast("access.WhoAmIView", self.client.ask(access.WhoAmI(scope_id=self.project_id)))
        live = _actor(identity)
        if (live.principal_id, live.kind, live.grant) != (
            self.actor.principal_id,
            self.actor.kind,
            self.actor.grant,
        ):
            raise _unauthenticated()
        if "project.read" not in identity.effective_permissions:
            raise Forbidden(ErrorCode.FORBIDDEN, "project.read is not granted for the session project")
        return identity
