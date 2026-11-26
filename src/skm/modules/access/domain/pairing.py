"""Stored single-use pairing credentials and their secret-free exchange outcomes."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from skm.kernel.ids import PrincipalId, WorkspaceId
from skm.kernel.json_types import JsonObject

from .token import TokenId


@dataclass(frozen=True, slots=True)
class PairingResult:
    principal_id: PrincipalId
    token_id: TokenId
    worker_id: UUID | None


@dataclass(frozen=True, slots=True)
class PairingToken:
    id: UUID
    issuer_id: PrincipalId
    issuer_token_id: TokenId | None
    workspace_id: WorkspaceId
    secret_hash: bytes = field(repr=False)
    binding: JsonObject
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    result: PairingResult | None = None
