"""Access events (access §9): event types, their stream and the payload field inventory.

Payload classes are generated from ``schemas/access/events``; this module pins what the domain promises: every
event belongs to the ``principal`` stream and no payload carries a secret, a hash or a pepper.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

__all__ = [
    "EVENT_PAYLOAD_FIELDS",
    "EVENT_STREAM_KIND",
    "EVENT_TYPES",
    "MEMBERSHIP_GRANTED",
    "MEMBERSHIP_REVOKED",
    "PRINCIPAL_CREATED",
    "PRINCIPAL_DISABLED",
    "SECRET_FIELD_NAMES",
    "TOKEN_CREATED",
    "TOKEN_REVOKED",
    "TOKEN_ROTATED",
]

MEMBERSHIP_GRANTED: Final = "urn:skm:access:event:membership-granted:v1"
MEMBERSHIP_REVOKED: Final = "urn:skm:access:event:membership-revoked:v1"
PRINCIPAL_CREATED: Final = "urn:skm:access:event:principal-created:v1"
PRINCIPAL_DISABLED: Final = "urn:skm:access:event:principal-disabled:v1"
TOKEN_CREATED: Final = "urn:skm:access:event:token-created:v1"
TOKEN_REVOKED: Final = "urn:skm:access:event:token-revoked:v1"
TOKEN_ROTATED: Final = "urn:skm:access:event:token-rotated:v1"

EVENT_TYPES = (
    MEMBERSHIP_GRANTED,
    MEMBERSHIP_REVOKED,
    PRINCIPAL_CREATED,
    PRINCIPAL_DISABLED,
    TOKEN_CREATED,
    TOKEN_REVOKED,
    TOKEN_ROTATED,
)

# All access events, token and membership events included, go to the stream of the affected principal.
EVENT_STREAM_KIND: Final = "principal"

EVENT_PAYLOAD_FIELDS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        PRINCIPAL_CREATED: ("principal_id", "kind", "display_name"),
        PRINCIPAL_DISABLED: ("principal_id", "reason"),
        TOKEN_CREATED: ("token_id", "principal_id", "kind", "name", "prefix", "scope_id", "expires_at"),
        TOKEN_ROTATED: (
            "token_id",
            "previous_token_id",
            "principal_id",
            "kind",
            "expires_at",
            "previous_expires_at",
        ),
        TOKEN_REVOKED: ("token_id", "principal_id", "revoked_by"),
        MEMBERSHIP_GRANTED: ("scope_id", "principal_id", "role", "previous_role"),
        MEMBERSHIP_REVOKED: ("scope_id", "principal_id", "role"),
    }
)

SECRET_FIELD_NAMES: Final = frozenset({"secret", "secret_hash", "random", "pepper", "token_secret"})
