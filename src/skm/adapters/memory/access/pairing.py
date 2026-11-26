"""Transactional pairing credentials in the memory access state."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from skm.adapters.memory.access.state import access_state
from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed
from skm.modules.access.domain.pairing import PairingResult, PairingToken

__all__ = ["MemoryPairingRepository"]


class MemoryPairingRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._pairings = access_state(state).pairings

    def add(self, pairing: PairingToken) -> None:
        self._state.core.require_writable()
        if pairing.id in self._pairings or any(
            p.secret_hash == pairing.secret_hash for p in self._pairings.values()
        ):
            raise Conflict(ErrorCode.ALREADY_EXISTS, "pairing credential already exists")
        self._pairings[pairing.id] = deepcopy(pairing)

    def get_for_update(self, pairing_id: UUID) -> PairingToken | None:
        return deepcopy(self._pairings.get(pairing_id))

    def consume(self, pairing_id: UUID, result: PairingResult, now: datetime) -> None:
        self._state.core.require_writable()
        pairing = self._pairings[pairing_id]
        if pairing.result is not None or pairing.revoked_at is not None or pairing.expires_at <= now:
            raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "pairing credential is unavailable")
        self._pairings[pairing_id] = replace(pairing, result=result)

    def revoke(self, pairing_id: UUID, now: datetime) -> None:
        self._state.core.require_writable()
        pairing = self._pairings.get(pairing_id)
        if pairing is not None and pairing.revoked_at is None:
            self._pairings[pairing_id] = replace(pairing, revoked_at=now)

    def revoke_all(self, now: datetime) -> int:
        self._state.core.require_writable()
        count = 0
        for pid, pairing in list(self._pairings.items()):
            if pairing.revoked_at is None:
                self._pairings[pid] = replace(pairing, revoked_at=now)
                count += 1
        return count
