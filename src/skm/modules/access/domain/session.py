"""Web session record backed by ``skm_access.web_sessions`` (0006)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from skm.kernel.ids import PrincipalId

__all__ = ["WebSession"]


@dataclass(frozen=True, slots=True)
class WebSession:
    """Immutable session binding except for one-way ``revoked_at`` revocation."""

    id: UUID
    principal_id: PrincipalId
    secret_hash: bytes
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if len(self.secret_hash) != 32:
            raise ValueError("web session secret_hash must be 32 bytes")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("web session timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("web session expires_at must be after created_at")
        if self.revoked_at is not None and self.revoked_at.tzinfo is None:
            raise ValueError("web session revoked_at must be timezone-aware")

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now
