"""Principals: the subjects of actions (access §4.2, §5).

The kind of a principal never changes (ACCESS-01): a different kind is a new principal with new credentials
and explicit memberships. ``Actor.kind`` is taken from this record, never from a request field.
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import PrincipalId

__all__ = ["Principal", "PrincipalState", "disable", "ensure_principal_update", "new_principal"]

_NAME_MAX: Final = 200


class PrincipalState(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class Principal:
    id: PrincipalId
    kind: PrincipalKind
    display_name: str
    state: PrincipalState
    row_version: int
    created_at: datetime
    created_by: PrincipalId | None

    def __post_init__(self) -> None:
        if self.row_version < 1:
            raise ValueError("row_version starts at 1")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")


def _is_control(char: str) -> bool:
    """A Unicode control character (category Cc): C0, DEL and C1."""
    code = ord(char)
    return code < 0x20 or 0x7F <= code <= 0x9F


def _invalid_name(reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "invalid principal display_name",
        details={"field": "display_name", "reason": reason},
    )


def new_principal(
    *,
    principal_id: PrincipalId,
    kind: PrincipalKind,
    display_name: str,
    created_by: PrincipalId | None,
    now: datetime,
) -> Principal:
    name = display_name.strip()
    if not 1 <= len(name) <= _NAME_MAX:
        raise _invalid_name("length")
    if any(_is_control(char) for char in name):
        raise _invalid_name("control_character")
    return Principal(
        id=principal_id,
        kind=PrincipalKind(kind),
        display_name=name,
        state=PrincipalState.ACTIVE,
        row_version=1,
        created_at=now,
        created_by=created_by,
    )


def disable(principal: Principal) -> Principal:
    """``active -> disabled``; an already disabled principal is returned as is (no event is written)."""
    if principal.state is PrincipalState.DISABLED:
        return principal
    return dataclasses.replace(
        principal, state=PrincipalState.DISABLED, row_version=principal.row_version + 1
    )


def ensure_principal_update(before: Principal, after: Principal) -> None:
    """Repository ``save`` guard: kind, id and origin are immutable, the version moves forward by one."""
    if (
        before.id != after.id
        or before.kind is not after.kind
        or before.created_at != after.created_at
        or before.created_by != after.created_by
    ):
        raise ValueError("a principal keeps its id, kind and origin; create a new principal instead")
    if after.row_version != before.row_version + 1:
        raise ValueError("principal row_version advances by exactly one")
