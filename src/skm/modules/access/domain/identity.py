"""External identities of principals (access §4.2): ``(issuer, subject)`` is unique in an instance."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from skm.kernel.ids import PrincipalId

__all__ = ["LOCAL_ISSUER", "LOCAL_OWNER_SUBJECT", "SERVICE_ISSUER", "PrincipalIdentity"]


LOCAL_ISSUER: Final = "local"
SERVICE_ISSUER: Final = "service"
LOCAL_OWNER_SUBJECT: Final = "owner"
_OIDC_PREFIX: Final = "oidc:"
_ISSUER_MAX: Final = 200
_SUBJECT_MAX: Final = 300


@dataclass(frozen=True, slots=True)
class PrincipalIdentity:
    principal_id: PrincipalId
    issuer: str
    subject: str
    created_at: datetime

    def __post_init__(self) -> None:
        issuer_ok = self.issuer in (LOCAL_ISSUER, SERVICE_ISSUER) or (
            self.issuer.startswith(_OIDC_PREFIX) and len(self.issuer) > len(_OIDC_PREFIX)
        )
        if not issuer_ok or len(self.issuer) > _ISSUER_MAX:
            raise ValueError("issuer must be 'local', 'service' or 'oidc:<issuer-url>' of 1..200 characters")
        if not 1 <= len(self.subject) <= _SUBJECT_MAX:
            raise ValueError("subject must be 1..300 characters")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
