"""Transactional web sessions in the memory access state."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from skm.adapters.memory.access.state import access_state
from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import PrincipalId
from skm.modules.access.domain.session import WebSession

__all__ = ["MemoryWebSessionRepository"]


class MemoryWebSessionRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._sessions = access_state(state).web_sessions

    def add(self, session: WebSession) -> None:
        self._state.core.require_writable()
        if session.id in self._sessions or any(
            existing.secret_hash == session.secret_hash for existing in self._sessions.values()
        ):
            raise Conflict(ErrorCode.ALREADY_EXISTS, "web session already exists")
        self._sessions[session.id] = deepcopy(session)

    def get(self, session_id: UUID) -> WebSession | None:
        session = self._sessions.get(session_id)
        return None if session is None else deepcopy(session)

    def find_by_hash(self, secret_hash: bytes) -> WebSession | None:
        for session in self._sessions.values():
            if session.secret_hash == secret_hash:
                return deepcopy(session)
        return None

    def revoke(self, session_id: UUID, now: datetime) -> bool:
        self._state.core.require_writable()
        session = self._sessions.get(session_id)
        if session is None or session.revoked_at is not None:
            return False
        self._sessions[session_id] = replace(session, revoked_at=now)
        return True

    def revoke_for_principal(self, principal_id: PrincipalId, now: datetime) -> int:
        self._state.core.require_writable()
        count = 0
        for sid, session in list(self._sessions.items()):
            if session.principal_id == principal_id and session.revoked_at is None:
                self._sessions[sid] = replace(session, revoked_at=now)
                count += 1
        return count

    def revoke_all(self, now: datetime) -> int:
        self._state.core.require_writable()
        count = 0
        for sid, session in list(self._sessions.items()):
            if session.revoked_at is None:
                self._sessions[sid] = replace(session, revoked_at=now)
                count += 1
        return count
