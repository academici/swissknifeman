"""Memory scope shapes, explicit sharing, and stable lock identity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from enum import StrEnum

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, ValidationFailed
from skm.kernel.ids import ScopeId, WorkspaceId

_NAMESPACE = re.compile(r"[a-z][a-z0-9-]{1,40}")


class MemoryScopeKind(StrEnum):
    PROJECT = "project"
    NAMESPACE = "namespace"
    GLOBAL = "global"


@dataclass(frozen=True, slots=True)
class MemoryScope:
    kind: MemoryScopeKind
    scope_id: ScopeId | None
    namespace: str | None
    workspace_id: WorkspaceId | None

    def __post_init__(self) -> None:
        match self.kind:
            case MemoryScopeKind.PROJECT:
                valid = self.scope_id is not None and self.workspace_id is not None and self.namespace is None
            case MemoryScopeKind.NAMESPACE:
                valid = (
                    self.scope_id is None
                    and self.workspace_id is not None
                    and self.namespace is not None
                    and _NAMESPACE.fullmatch(self.namespace) is not None
                )
            case MemoryScopeKind.GLOBAL:
                valid = self.scope_id is None and self.namespace is None and self.workspace_id is None
            case _:
                valid = False
        if not valid:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid memory scope shape")


def require_project_scope(project_scope: MemoryScope | None) -> MemoryScope:
    if project_scope is None or project_scope.kind is not MemoryScopeKind.PROJECT:
        raise PreconditionFailed(ErrorCode.MEMORY_SCOPE_REQUIRED, "Memory requires a project scope")
    return project_scope


def allowed_scopes(
    project_scope: MemoryScope | None, shared_namespaces: Iterable[str]
) -> tuple[MemoryScope, ...]:
    project = require_project_scope(project_scope)
    # Settings v1 admits names that cannot describe a persisted memory scope.
    shared = tuple(
        MemoryScope(MemoryScopeKind.GLOBAL, None, None, None)
        if namespace == "*"
        else MemoryScope(MemoryScopeKind.NAMESPACE, None, namespace, project.workspace_id)
        for namespace in sorted(set(shared_namespaces))
        if namespace == "*" or _NAMESPACE.fullmatch(namespace) is not None
    )
    return (project, *shared)


def recall_scopes(
    project_scope: MemoryScope | None, shared_namespaces: Iterable[str], *, include_shared: bool = False
) -> tuple[MemoryScope, ...]:
    if include_shared:
        return allowed_scopes(project_scope, shared_namespaces)
    return (require_project_scope(project_scope),)


def ensure_scope_allowed(scope: MemoryScope, scopes: Collection[MemoryScope]) -> None:
    if scope not in scopes:
        raise Forbidden(ErrorCode.FORBIDDEN, "Memory scope is outside the allowed scopes")


def scope_lock_key(scope: MemoryScope) -> int:
    """Return the signed advisory lock key for the complete scope tuple (KNOWLEDGE-05)."""
    encoded = json.dumps(
        [
            "skm-memory-scope-v1",
            scope.kind.value,
            str(scope.scope_id) if scope.scope_id is not None else None,
            scope.namespace,
            str(scope.workspace_id) if scope.workspace_id is not None else None,
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big", signed=True)
