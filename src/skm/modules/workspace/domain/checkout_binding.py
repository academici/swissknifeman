"""Checkout binding: where a repository lies on a host, and what the host last observed (workspace §4.2,
§4.3, §5.3).

Everything here is a function of facts handed in by the caller: this module never touches a file system, a
process or a working directory. The binding *identity* ``(binding_id, host_id, repository_id,
local_locator)`` is fixed when the binding is created; observed remotes, HEAD, state and the verification
time are replaceable observations. A checkout that moved is reported as ``mismatched`` and is never rebound:
a new binding (a new ID) is created after the old one is removed."""

import hashlib
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Final, NewType
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import HostId, RepositoryId, WorkspaceId
from skm.kernel.json_types import JsonObject

from .checkout_marker import CheckoutMarker
from .remote_url import NormalizedRemote

__all__ = [
    "BINDING_TRANSITIONS",
    "LOCATOR_MAX",
    "BindingIdentity",
    "BindingState",
    "CheckoutBinding",
    "CheckoutBindingId",
    "ObservedCheckout",
    "VerifyReason",
    "VerifyResult",
    "binding_identity",
    "checkout_id_from_locator",
    "checkout_locator",
    "ensure_transition",
    "is_stale",
    "locator_digest",
    "new_binding",
    "normalize_locator",
    "remove",
    "require_remotes_match",
    "verify",
]

LOCATOR_MAX: Final = 4096
_OBSERVED_REMOTES_MAX: Final = 32
_CHECKOUT_PREFIX: Final = "/.skm-checkout/"
_HEX: Final = frozenset("0123456789abcdef")


class BindingState(StrEnum):
    ACTIVE = "active"
    MISSING = "missing"
    MISMATCHED = "mismatched"
    REMOVED = "removed"


class VerifyReason(StrEnum):
    OK = "ok"
    MISSING = "missing"  # not a git checkout, or gone
    MOVED = "moved"  # the toplevel the host sees is not the bound locator
    REMOTES = "remotes"  # no observed remote belongs to the repository


CheckoutBindingId = NewType("CheckoutBindingId", UUID)

BINDING_TRANSITIONS: Final[Mapping[BindingState, frozenset[BindingState]]] = MappingProxyType(
    {
        BindingState.ACTIVE: frozenset({BindingState.MISSING, BindingState.MISMATCHED, BindingState.REMOVED}),
        BindingState.MISSING: frozenset({BindingState.ACTIVE, BindingState.MISMATCHED, BindingState.REMOVED}),
        BindingState.MISMATCHED: frozenset({BindingState.ACTIVE, BindingState.MISSING, BindingState.REMOVED}),
        BindingState.REMOVED: frozenset[BindingState](),
    }
)


@dataclass(frozen=True, slots=True)
class ObservedCheckout:
    """Facts the host client saw in the checkout directory; the server records them as data of the actor."""

    exists: bool
    toplevel: str | None  # absolute realpath of the git toplevel; None when not a git checkout
    remotes: tuple[NormalizedRemote, ...]  # fetch remotes in git order
    head: str | None  # 40 or 64 hex; None for an empty repository
    marker: CheckoutMarker | None
    observed_at: datetime
    dirty: bool | None

    def __post_init__(self) -> None:
        if self.head is not None and (len(self.head) not in (40, 64) or not _HEX.issuperset(self.head)):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID, "head must be 40 or 64 lower-case hex", details={"field": "head"}
            )
        if len(self.remotes) > _OBSERVED_REMOTES_MAX:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                f"at most {_OBSERVED_REMOTES_MAX} observed remotes",
                details={"field": "remotes"},
            )

    @property
    def is_git_checkout(self) -> bool:
        return self.exists and self.toplevel is not None


@dataclass(frozen=True, slots=True)
class CheckoutBinding:
    id: CheckoutBindingId
    workspace_id: WorkspaceId
    host_id: HostId
    repository_id: RepositoryId
    local_locator: str  # normalized absolute path on the host
    state: BindingState
    observed_remotes: tuple[NormalizedRemote, ...]
    observed_head: str | None
    last_verified_at: datetime
    row_version: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BindingIdentity:
    """What an approval of a host effect is tied to; the raw locator is replaced by its digest."""

    binding_id: CheckoutBindingId
    host_id: HostId
    repository_id: RepositoryId
    locator_digest: str

    def to_json(self) -> JsonObject:
        return {
            "binding_id": str(self.binding_id),
            "host_id": str(self.host_id),
            "repository_id": str(self.repository_id),
            "locator_digest": self.locator_digest,
        }


@dataclass(frozen=True, slots=True)
class VerifyResult:
    binding: CheckoutBinding
    reason: VerifyReason


def _bad_locator(reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "invalid checkout locator",
        details={"field": "local_locator", "reason": reason},
    )


def normalize_locator(text: str) -> str:
    """An absolute POSIX or Windows (``X:\\…``) path, trailing separators removed; the root stays whole."""
    if not 1 <= len(text) <= LOCATOR_MAX:
        raise _bad_locator("length")
    if "\0" in text or "\n" in text or "\r" in text:
        raise _bad_locator("control_character")
    if text.startswith("/"):
        return text.rstrip("/") or "/"
    if len(text) >= 3 and text[0].isascii() and text[0].isalpha() and text[1:3] == ":\\":
        stripped = text.rstrip("\\/")
        return stripped if len(stripped) > 2 else text[:3]
    raise _bad_locator("not_absolute")


def checkout_locator(checkout_id: UUID) -> str:
    """Encode a machine checkout ID in the existing project locator field."""
    return f"{_CHECKOUT_PREFIX}{checkout_id}"


def checkout_id_from_locator(locator: str) -> UUID | None:
    """Return an ID only for the canonical wire format."""
    if not locator.startswith(_CHECKOUT_PREFIX):
        return None
    try:
        checkout_id = UUID(locator.removeprefix(_CHECKOUT_PREFIX))
    except ValueError:
        return None
    return checkout_id if checkout_locator(checkout_id) == locator else None


def locator_digest(locator: str) -> str:
    """SHA-256 hex of the normalized locator; policy and effect views carry this, never the path."""
    return hashlib.sha256(normalize_locator(locator).encode("utf-8")).hexdigest()


def binding_identity(binding: CheckoutBinding) -> BindingIdentity:
    return BindingIdentity(
        binding_id=binding.id,
        host_id=binding.host_id,
        repository_id=binding.repository_id,
        locator_digest=locator_digest(binding.local_locator),
    )


def ensure_transition(source: BindingState, target: BindingState) -> None:
    if target not in BINDING_TRANSITIONS[source]:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            f"binding cannot go from {source.value} to {target.value}",
            details={"from": source.value, "to": target.value},
        )


def require_remotes_match(
    observed_remotes: Collection[NormalizedRemote], repository_remotes: Collection[NormalizedRemote]
) -> None:
    """The server does not trust the host op: a repository with remotes needs one of them observed."""
    if repository_remotes and not set(observed_remotes) & set(repository_remotes):
        raise PreconditionFailed(
            ErrorCode.CHECKOUT_MISMATCH,
            "the observed remotes do not belong to the repository",
            details={"reason": VerifyReason.REMOTES.value},
        )


def _moved(locator: str, toplevel: str) -> bool:
    try:
        return normalize_locator(toplevel) != locator
    except ValidationFailed:
        return True  # a toplevel that is no valid locator cannot be the bound one


def _judge(
    binding: CheckoutBinding, observed: ObservedCheckout, repository_remotes: Collection[NormalizedRemote]
) -> tuple[BindingState, VerifyReason]:
    if not observed.is_git_checkout or observed.toplevel is None:
        return BindingState.MISSING, VerifyReason.MISSING
    if _moved(binding.local_locator, observed.toplevel):
        return BindingState.MISMATCHED, VerifyReason.MOVED
    if repository_remotes and not set(observed.remotes) & set(repository_remotes):
        return BindingState.MISMATCHED, VerifyReason.REMOTES
    return BindingState.ACTIVE, VerifyReason.OK


def verify(
    binding: CheckoutBinding,
    observed: ObservedCheckout,
    repository_remotes: Collection[NormalizedRemote],
    now: datetime,
) -> VerifyResult:
    """Replace observed facts and state; identity fields, the locator included, never change here."""
    if binding.state is BindingState.REMOVED:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "a removed binding cannot be verified",
            details={"from": binding.state.value, "to": "verified"},
        )
    state, reason = _judge(binding, observed, repository_remotes)
    updated = replace(
        binding,
        state=state,
        observed_remotes=observed.remotes,
        observed_head=observed.head,
        last_verified_at=now,
        row_version=binding.row_version + 1,
    )
    return VerifyResult(updated, reason)


def new_binding(
    *,
    binding_id: CheckoutBindingId,
    workspace_id: WorkspaceId,
    host_id: HostId,
    repository_id: RepositoryId,
    local_locator: str,
    observed: ObservedCheckout,
    repository_remotes: Collection[NormalizedRemote],
    now: datetime,
) -> VerifyResult:
    """A new binding for an observed checkout of the repository; its state is the result of ``verify``."""
    require_remotes_match(observed.remotes, repository_remotes)
    initial = CheckoutBinding(
        id=binding_id,
        workspace_id=workspace_id,
        host_id=host_id,
        repository_id=repository_id,
        local_locator=normalize_locator(local_locator),
        state=BindingState.ACTIVE,
        observed_remotes=(),
        observed_head=None,
        last_verified_at=now,
        row_version=0,
        created_at=now,
    )
    result = verify(initial, observed, repository_remotes, now)
    return VerifyResult(replace(result.binding, row_version=1), result.reason)


def remove(binding: CheckoutBinding) -> CheckoutBinding:
    """``* -> removed``; a removed binding stays as it is. For a moved checkout: remove, then bind anew."""
    if binding.state is BindingState.REMOVED:
        return binding
    ensure_transition(binding.state, BindingState.REMOVED)
    return replace(binding, state=BindingState.REMOVED, row_version=binding.row_version + 1)


def is_stale(binding: CheckoutBinding, now: datetime, stale_after: timedelta) -> bool:
    """Computed, never stored: the last verification is older than ``stale_after``."""
    return now - binding.last_verified_at > stale_after
