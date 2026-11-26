"""Database-free process configuration for the schema-incompatible API status surface.

Only schema defaults and explicit invocation layers are available here. The provisional nil instance
identity when bootstrap has none is local metadata, never an authenticated actor or a stored scope.
No plugins or database configuration are consulted; normal startup after migration reads stored identity.
"""

from collections.abc import Mapping, Sequence
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ports_uow import Surface
from skm.platform.config.bootstrap import BootstrapConfig, apply_process_config
from skm.platform.config.keys import Chain, Level
from skm.platform.config.layers import Layer
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.config.store import EmptyPackConfigSource, StoredContribution

__all__ = ["restricted_api_process"]


class _UnavailableConfig:
    """Explicitly no stored configuration until a compatible schema is available."""

    def generation(self) -> int:
        return 0

    def pending_writes(self) -> bool:
        return False

    def entries_for(self, scope_ids: Sequence[UUID]) -> Mapping[UUID, Mapping[str, StoredContribution]]:
        del scope_ids
        return {}


class _BootstrapScopes:
    def __init__(self, instance: ScopeRef, host: ScopeRef) -> None:
        self.instance, self.host = instance, host

    def instance_scope(self) -> ScopeRef:
        return self.instance

    def chain_for(self, scope: ScopeRef, kind: Chain) -> ScopeChain:
        if scope == self.instance:
            return ScopeChain(kind, (self.instance,))
        if scope == self.host and kind is Chain.HOST:
            return ScopeChain(kind, (self.instance, self.host))
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Unknown bootstrap config scope")

    def label(self, scope: ScopeRef) -> str:
        return scope.label


def restricted_api_process(
    bootstrap: BootstrapConfig, registry: SettingsRegistry, layers: Sequence[Layer]
) -> tuple[BootstrapConfig, ConfigLoader]:
    """Capture validated process values without accessing any database table."""
    instance = ScopeRef(Level.INSTANCE, bootstrap.instance_id or UUID(int=0))
    host = ScopeRef(Level.HOST, bootstrap.host_id) if isinstance(bootstrap.host_id, UUID) else instance
    config = ConfigLoader(registry, EmptyPackConfigSource(), layers)
    process = config.start_process(_UnavailableConfig(), _BootstrapScopes(instance, host), host)
    return apply_process_config(bootstrap, process, surface=Surface.API), config
