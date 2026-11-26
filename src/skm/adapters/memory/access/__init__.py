"""Memory adapters of the access repository ports (access §3, §6, §11).

``REPOSITORIES`` maps each access port to its factory over the backend state. ``WorkerHostLookup`` is not
here: the workspace adapters implement it (access §6), and ``RbacAuthorizer`` reads an empty set until then.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from skm.adapters.memory.access.pairing import MemoryPairingRepository
from skm.adapters.memory.access.repositories import (
    MemoryIdentityRepository,
    MemoryMembershipRepository,
    MemoryPrincipalRepository,
    MemoryTokenRepository,
)
from skm.adapters.memory.access.sessions import MemoryWebSessionRepository
from skm.adapters.memory.core.state import MemoryBackendState
from skm.modules.access.ports import (
    IdentityRepository,
    MembershipRepository,
    PairingRepository,
    PrincipalRepository,
    TokenRepository,
    WebSessionRepository,
)

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[MemoryBackendState], object]] = MappingProxyType(
    {
        PrincipalRepository: MemoryPrincipalRepository,
        IdentityRepository: MemoryIdentityRepository,
        TokenRepository: MemoryTokenRepository,
        PairingRepository: MemoryPairingRepository,
        MembershipRepository: MemoryMembershipRepository,
        WebSessionRepository: MemoryWebSessionRepository,
    }
)
