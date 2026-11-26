"""Host settings snapshot carried by a registered HTTP worker."""

from collections.abc import Callable
from dataclasses import replace
from threading import RLock
from typing import cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, Forbidden, ValidationFailed
from skm.kernel.ids import HostId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.access.public import WhoAmI, WhoAmIView
from skm.modules.settings.public import (
    PROJECT_WORKER_KEYS,
    ExplainConfig,
    ExplainConfigResult,
    GetHostConfig,
    GetHostConfigResult,
    GetHostConfigResultPlugins,
    worker_identifiers,
    worker_values,
)

__all__ = ["RemoteWorkerConfig", "worker_credential_workspace"]


def worker_credential_workspace(identity: WhoAmIView) -> WorkspaceId:
    """Use the unique claim grant of the authenticated worker credential."""
    token = identity.token
    if token is None or token.kind != "worker" or token.state != "active":
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "An active worker credential is required")
    grants = token.scope_grants
    scopes: set[UUID]
    if grants is None:
        scopes = {token.scope_id} if token.scope_id is not None else set()
    else:
        scopes = {
            grant.scope_id for grant in grants if {"worker.claim", "token.own"} <= set(grant.permissions)
        }
    if len(scopes) != 1:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Worker credential needs exactly one workspace grant"
        )
    return WorkspaceId(scopes.pop())


class RemoteWorkerConfig:
    """Shared host settings for the lifetime of the worker's capacity slots."""

    def __init__(self, ask: Callable[[object], object], host_id: HostId, identity: WhoAmIView) -> None:
        self._ask, self._query = ask, GetHostConfig(host_id=host_id)
        self._lock = RLock()
        self.workspace_id = worker_credential_workspace(identity)
        self._principal_id = identity.principal.principal_id
        self._policy_query = ExplainConfig.from_json(
            {
                "scope": {"level": "workspace", "scope_id": str(self.workspace_id)},
                "detail": "value",
                "keys": ["access.tokens.worker_rotate_before_hours", "access.tokens.worker_ttl_hours"],
            }
        )
        self._verify_workspace()
        self._current = self._fetch()
        self._policy = self._rotation_policy()
        self.fresh = True

    def _verify_workspace(self) -> None:
        identity = cast("WhoAmIView", self._ask(WhoAmI(scope_id=self.workspace_id)))
        if (
            identity.principal.principal_id != self._principal_id
            or worker_credential_workspace(identity) != self.workspace_id
            or "worker.claim" not in identity.effective_permissions
        ):
            raise Forbidden(ErrorCode.FORBIDDEN, "Worker has no live grant in its registered workspace")

    def _rotation_policy(self) -> dict[str, int]:
        result = cast("ExplainConfigResult", self._ask(self._policy_query)).to_json()
        scope = cast("JsonObject", result["scope"])
        if (scope.get("level"), scope.get("scope_id")) != ("workspace", str(self.workspace_id)):
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Worker rotation policy has a different scope")
        settings = {
            str(item["key"]): value
            for item in cast("list[JsonObject]", result["keys"])
            if type(value := item.get("value")) is int
        }
        if settings.keys() != set(self._policy_query.keys or ()):
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Missing worker rotation policy")
        return settings

    def rotation_setting(self, key: str) -> int:
        return self._policy[key]

    def _fetch(self) -> GetHostConfigResult:
        result = cast("GetHostConfigResult", self._ask(self._query))
        if result.host_id != self._query.host_id:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "HTTP host configuration has a different host ID"
            )
        projected = worker_values(result.values)
        return replace(
            result,
            values=projected,
            invalid=tuple(key for key in result.invalid if key in PROJECT_WORKER_KEYS),
            plugins=GetHostConfigResultPlugins(
                worker_identifiers(result.plugins.allowed, key="plugins.allowed"),
                worker_identifiers(result.plugins.required, key="plugins.required"),
            ),
        )

    def snapshot(self) -> GetHostConfigResult:
        return self._current

    def refresh(self) -> bool:
        with self._lock:
            self.fresh = False
            try:
                self._verify_workspace()
                current = self._fetch()
                policy = self._rotation_policy()
            except BackendUnavailable:
                return False
            self._current, self._policy = current, policy
            self.fresh = True
            return True

    def get(self, key: str) -> JsonValue:
        current = self._current
        if key in current.invalid:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Invalid HTTP host setting", details={"key": key}
            )
        return current.values.get(key)
