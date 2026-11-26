"""PostgreSQL adapters of the access repository ports (access §3, §6, §11).

``REPOSITORIES`` maps each access port to its factory over the unit-of-work connection; it is merged with the
core table by ``bootstrap.adapters.postgres_repository_table``. ``WorkerHostLookup`` is not here: the
workspace adapters implement it (access §6), and ``RbacAuthorizer`` reads an empty set until then.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

import psycopg

from skm.adapters.postgres.access.pairing import PostgresPairingRepository
from skm.adapters.postgres.access.repositories import (
    PostgresIdentityRepository,
    PostgresMembershipRepository,
    PostgresPrincipalRepository,
    PostgresTokenRepository,
)
from skm.adapters.postgres.access.sessions import PostgresWebSessionRepository
from skm.modules.access.ports import (
    IdentityRepository,
    MembershipRepository,
    PairingRepository,
    PrincipalRepository,
    TokenRepository,
    WebSessionRepository,
)

__all__ = ["REPOSITORIES"]

REPOSITORIES: Mapping[type, Callable[[psycopg.Connection], object]] = MappingProxyType(
    {
        PrincipalRepository: PostgresPrincipalRepository,
        IdentityRepository: PostgresIdentityRepository,
        TokenRepository: PostgresTokenRepository,
        PairingRepository: PostgresPairingRepository,
        MembershipRepository: PostgresMembershipRepository,
        WebSessionRepository: PostgresWebSessionRepository,
    }
)
