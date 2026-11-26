"""Principals acting through the bus (kernel-platform §2.4, access §4.2 and §18).

``Actor.grant`` carries the one ``TokenGrant`` contract; no parallel flattened token fields exist. The module
depends on neither ``access`` nor ``execution``: assignment and step ids are plain UUIDs.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal
from uuid import UUID

from skm.kernel.ids import PrincipalId, ScopeId

__all__ = [
    "SYSTEM_PRINCIPAL_ID",
    "Actor",
    "PrincipalKind",
    "ScopeGrant",
    "TokenGrant",
    "ordered_scope_grants",
]


class PrincipalKind(StrEnum):
    HUMAN = "human"
    SERVICE = "service"
    WORKER = "worker"


_GRANT_KINDS: Final = frozenset({"personal", "worker", "assignment"})
_WORKER_GRANT_KINDS: Final = frozenset({"worker", "assignment"})


@dataclass(frozen=True, slots=True)
class ScopeGrant:
    """A permission ceiling rooted at one scope and inherited by its descendants."""

    scope_id: ScopeId
    permissions: frozenset[str]


def ordered_scope_grants(grants: tuple[ScopeGrant, ...]) -> tuple[ScopeGrant, ...]:
    """The canonical order shared by credentials and their persistence adapters."""
    if len({pair.scope_id for pair in grants}) != len(grants):
        raise ValueError("scope grants repeat a scope")
    return tuple(sorted(grants, key=lambda pair: pair.scope_id))


@dataclass(frozen=True, slots=True)
class TokenGrant:
    """Narrowing carried by the authenticating token; ``None`` fields do not narrow.

    ``kind == "assignment"`` holds exactly when ``assignment_id`` is set; such a grant is bound to one step
    (``step_id``) and one run scope (``scope_id``). ``scope_ancestors`` lists the ancestors of ``scope_id``
    from the instance down, filled by token authentication.
    """

    token_id: UUID
    kind: Literal["personal", "worker", "assignment"]
    scope_id: ScopeId | None
    permissions: frozenset[str] | None
    assignment_id: UUID | None = None
    step_id: UUID | None = None
    scope_ancestors: tuple[ScopeId, ...] = ()
    scope_grants: tuple[ScopeGrant, ...] | None = None
    assignment_scope_id: ScopeId | None = None
    worker_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.kind not in _GRANT_KINDS:
            raise ValueError(f"unknown token grant kind: {self.kind!r}")
        if self.permissions is not None and not isinstance(self.permissions, frozenset):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("TokenGrant.permissions must be a frozenset or None")
        if not isinstance(self.scope_ancestors, tuple):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("TokenGrant.scope_ancestors must be a tuple")
        if self.scope_grants is not None:
            if self.scope_id is not None or self.permissions is not None or self.kind == "assignment":
                raise ValueError("paired grants require their own scope and permission fields")
            object.__setattr__(self, "scope_grants", ordered_scope_grants(self.scope_grants))
        if self.worker_id is not None and self.kind != "worker":
            raise ValueError("only worker grants have a worker binding")
        if self.kind == "assignment":
            if self.assignment_id is None or self.step_id is None or self.scope_id is None:
                raise ValueError("an assignment grant needs assignment_id, step_id and scope_id")
            if self.assignment_scope_id not in (None, self.scope_id):
                raise ValueError("assignment scope must match the run scope")
            object.__setattr__(self, "assignment_scope_id", self.scope_id)
        elif (
            self.assignment_id is not None or self.step_id is not None or self.assignment_scope_id is not None
        ):
            raise ValueError("assignment_id and step_id are allowed only for an assignment grant")


@dataclass(frozen=True, slots=True)
class Actor:
    principal_id: PrincipalId
    kind: PrincipalKind
    display_name: str
    grant: TokenGrant | None = None

    def __post_init__(self) -> None:
        if self.grant is None:
            return
        # Workers own worker/assignment tokens; humans and services own personal tokens.
        if (self.kind is PrincipalKind.WORKER) != (self.grant.kind in _WORKER_GRANT_KINDS):
            raise ValueError(f"a {self.kind.value} principal cannot hold a {self.grant.kind!r} token grant")


# Principal of kind ``service`` (display name "system") created by ``skm init``; background services and
# in-process subscribers act on its behalf. The only hard-coded id in the system.
SYSTEM_PRINCIPAL_ID: Final = PrincipalId(UUID("00000000-0000-7000-8000-000000000001"))
