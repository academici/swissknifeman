"""Scope tree primitives (kernel-platform §2.10).

``ScopeRegistry`` is a core repository port reached through ``uow.repo(ScopeRegistry)``; its
implementations are ``adapters/{memory,postgres}/core/scopes.py``.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Protocol

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.ports_uow import repository_port

__all__ = [
    "ALLOWED_PARENTS",
    "ScopeKind",
    "ScopeRecord",
    "ScopeRef",
    "ScopeRegistry",
    "check_scope_parent",
    "check_scope_workspace",
    "scope_not_found",
]


class ScopeKind(StrEnum):
    INSTANCE = "instance"
    WORKSPACE = "workspace"
    PROJECT = "project"
    PLAN = "plan"
    RUN = "run"
    HOST = "host"


ALLOWED_PARENTS: Final[Mapping[ScopeKind, tuple[ScopeKind | None, ...]]] = MappingProxyType(
    {
        ScopeKind.INSTANCE: (None,),
        ScopeKind.WORKSPACE: (ScopeKind.INSTANCE,),
        ScopeKind.PROJECT: (ScopeKind.WORKSPACE,),
        ScopeKind.PLAN: (ScopeKind.PROJECT,),
        ScopeKind.RUN: (ScopeKind.PLAN, ScopeKind.PROJECT),
        ScopeKind.HOST: (ScopeKind.INSTANCE,),
    }
)


@dataclass(frozen=True, slots=True)
class ScopeRef:
    kind: ScopeKind
    id: ScopeId


@dataclass(frozen=True, slots=True)
class ScopeRecord:
    id: ScopeId
    kind: ScopeKind
    parent_id: ScopeId | None
    workspace_id: WorkspaceId | None
    created_at: datetime


def scope_not_found() -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, "scope not found", details={"kind": "scope"})


def check_scope_parent(kind: ScopeKind, parent: ScopeRecord | None) -> None:
    """``ValidationFailed(SCHEMA_INVALID)`` unless ``parent`` has the kind ``ALLOWED_PARENTS`` requires."""
    parent_kind = None if parent is None else parent.kind
    if parent_kind not in ALLOWED_PARENTS[kind]:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "scope parent has the wrong kind",
            details={
                "kind": kind.value,
                "parent_kind": None if parent_kind is None else parent_kind.value,
            },
        )


def check_scope_workspace(
    scope_id: ScopeId, kind: ScopeKind, parent: ScopeRecord | None, workspace_id: WorkspaceId | None
) -> None:
    """A workspace scope is its own workspace, project/plan/run inherit the parent's, the rest have none."""
    expected: WorkspaceId | None
    if kind is ScopeKind.WORKSPACE:
        expected = WorkspaceId(scope_id)
    elif parent is not None and kind in {ScopeKind.PROJECT, ScopeKind.PLAN, ScopeKind.RUN}:
        expected = parent.workspace_id
    else:
        expected = None
    if workspace_id != expected:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "scope workspace does not match its kind",
            details={"kind": kind.value, "field": "workspace_id"},
        )


@repository_port
class ScopeRegistry(Protocol):
    def create(
        self,
        scope_id: ScopeId,
        kind: ScopeKind,
        *,
        parent: ScopeId | None,
        workspace_id: WorkspaceId | None,
    ) -> None:
        """Enforces ``ALLOWED_PARENTS`` and the workspace rule (``ValidationFailed(SCHEMA_INVALID)``)."""
        ...

    def get(self, scope_id: ScopeId) -> ScopeRecord:
        """``NotFound(NOT_FOUND, details={"kind": "scope"})``."""
        ...

    def list_scopes(self, *, after: ScopeId | None = None, limit: int = 100) -> tuple[ScopeRecord, ...]:
        """Read all kinds from the current UoW snapshot in ascending UUID order.

        Includes scopes without configuration and retained scope rows, regardless of entity lifecycle.
        ``after`` is an exclusive UUID boundary; it need not identify an existing scope. An empty or
        exhausted inventory returns ``()``. ``limit`` is an integer in the kernel page bounds (1..500);
        invalid types raise ``TypeError`` and out-of-range limits raise ``ValueError``.

        Internal repository inventory: consumers must authorize access before reading it. This port
        does not expose a client or bus endpoint.
        """
        ...

    def ancestors(self, scope_id: ScopeId) -> tuple[ScopeRecord, ...]:
        """``[instance, ..., scope]``, farthest first."""
        ...

    def instance(self) -> ScopeRecord:
        """``NotFound`` until ``skm init`` ran."""
        ...
