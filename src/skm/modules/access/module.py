"""Manifest of the access module (access §3)."""

from skm.kernel.module_manifest import ModuleManifest

from .application.events import (
    MembershipGranted,
    MembershipRevoked,
    PrincipalCreated,
    PrincipalDisabled,
    TokenCreated,
    TokenRevoked,
    TokenRotated,
)
from .application.registry import COMMANDS, QUERIES
from .application.subscribers import SUBSCRIBERS
from .permissions import PERMISSIONS
from .ports import (
    IdentityRepository,
    MembershipRepository,
    PairingRepository,
    PrincipalRepository,
    TokenPepperSource,
    TokenRepository,
    WebSessionRepository,
    WorkerHostLookup,
)

__all__ = ["MODULE"]

MODULE = ModuleManifest(
    id="access",
    depends_on=(),
    optional=False,
    db_schema="skm_access",
    settings_sections=("access",),
    permissions=PERMISSIONS,
    repository_ports=(
        PrincipalRepository,
        IdentityRepository,
        TokenRepository,
        MembershipRepository,
        PairingRepository,
        WebSessionRepository,
        WorkerHostLookup,
    ),
    gateway_ports=(TokenPepperSource,),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=SUBSCRIBERS,
    host_operations=(),
    events=(
        PrincipalCreated,
        PrincipalDisabled,
        TokenCreated,
        TokenRotated,
        TokenRevoked,
        MembershipGranted,
        MembershipRevoked,
    ),
)
