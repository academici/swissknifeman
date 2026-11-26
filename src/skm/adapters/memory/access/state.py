"""Tables of ``skm_access`` in the memory backend state (access §11).

The tables live in ``MemoryBackendState.modules["access"]``; a unit of work works on a deep copy, so
a rollback drops them. Plaintext secrets are never stored: ``ApiToken`` holds the peppered hash only.
"""

from dataclasses import dataclass, field
from typing import Final
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.ids import PrincipalId, ScopeId
from skm.modules.access.domain.identity import PrincipalIdentity
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.pairing import PairingToken
from skm.modules.access.domain.principal import Principal
from skm.modules.access.domain.session import WebSession
from skm.modules.access.domain.token import ApiToken, TokenId

__all__ = ["STATE_KEY", "MemoryAccessState", "access_state"]

STATE_KEY: Final = "access"


@dataclass
class MemoryAccessState:
    principals: dict[PrincipalId, Principal] = field(default_factory=dict[PrincipalId, Principal])
    identities: dict[tuple[str, str], PrincipalIdentity] = field(
        default_factory=dict[tuple[str, str], PrincipalIdentity]
    )
    pairings: dict[UUID, PairingToken] = field(default_factory=dict[UUID, PairingToken])
    passwords: dict[PrincipalId, bytes] = field(default_factory=dict[PrincipalId, bytes], repr=False)
    tokens: dict[TokenId, ApiToken] = field(default_factory=dict[TokenId, ApiToken])
    memberships: dict[tuple[ScopeId, PrincipalId], Membership] = field(
        default_factory=dict[tuple[ScopeId, PrincipalId], Membership]
    )
    web_sessions: dict[UUID, WebSession] = field(default_factory=dict[UUID, WebSession])


def access_state(state: MemoryBackendState) -> MemoryAccessState:
    found = state.modules.get(STATE_KEY)
    if found is None:
        found = MemoryAccessState()
        state.modules[STATE_KEY] = found
    if not isinstance(found, MemoryAccessState):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "access memory state is malformed", details={"module": STATE_KEY}
        )
    return found
