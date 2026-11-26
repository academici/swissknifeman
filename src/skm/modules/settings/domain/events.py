"""Events of the settings module (settings §A.9).

The stream is ``config`` with ``stream_id = scope_id``; ``scope_workspace_id`` is the workspace the scope
belongs to (``None`` for instance and host). Payloads carry key names only, never values, so any subscriber
or SSE client may read them. The JSON form comes from the generated event DTOs.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Literal, override
from uuid import UUID

from skm.kernel.events import DomainEvent
from skm.kernel.ids import WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.scopes import ScopeRef
from skm.modules.settings.generated import events as generated

__all__ = ["EVENT_TYPES", "ConfigChanged", "ConfigLocked", "ConfigUnlocked", "EntryChangeKind"]

type EntryChangeKind = Literal["created", "updated", "removed", "lock_changed"]


@dataclass(frozen=True, slots=True)
class ConfigChanged(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:settings:event:config-changed:v1"
    stream_kind: ClassVar[str] = "config"

    scope: ScopeRef
    workspace_id: WorkspaceId | None
    changes: Mapping[str, EntryChangeKind]  # key → change; ``keys`` is its sorted key list
    generation: int

    def __post_init__(self) -> None:
        if not self.changes:
            raise ValueError("a config change names at least one key")
        object.__setattr__(self, "changes", MappingProxyType(dict(sorted(self.changes.items()))))

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(self.changes)

    @override
    def stream_id(self) -> UUID:
        return self.scope.id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.ConfigChanged(
            scope=generated.ConfigChangedDefsScopeRef(level=self.scope.kind.value, scope_id=self.scope.id),
            keys=self.keys,
            changes=self.changes,
            generation=self.generation,
        ).to_json()


@dataclass(frozen=True, slots=True)
class ConfigLocked(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:settings:event:config-locked:v1"
    stream_kind: ClassVar[str] = "config"

    scope: ScopeRef
    workspace_id: WorkspaceId | None
    key: str
    generation: int

    @override
    def stream_id(self) -> UUID:
        return self.scope.id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.ConfigLocked(
            scope=generated.ConfigLockedDefsScopeRef(level=self.scope.kind.value, scope_id=self.scope.id),
            key=self.key,
            generation=self.generation,
        ).to_json()


@dataclass(frozen=True, slots=True)
class ConfigUnlocked(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:settings:event:config-unlocked:v1"
    stream_kind: ClassVar[str] = "config"

    scope: ScopeRef
    workspace_id: WorkspaceId | None
    key: str
    generation: int

    @override
    def stream_id(self) -> UUID:
        return self.scope.id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.ConfigUnlocked(
            scope=generated.ConfigUnlockedDefsScopeRef(level=self.scope.kind.value, scope_id=self.scope.id),
            key=self.key,
            generation=self.generation,
        ).to_json()


EVENT_TYPES: tuple[str, ...] = (ConfigChanged.event_type, ConfigLocked.event_type, ConfigUnlocked.event_type)
