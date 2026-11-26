"""Scope of a settings operation (settings §A.7): DTO ``scope_ref`` → bus scope → target of the write.

``scope_of`` is the bus ``scope_of`` of every settings operation: the instance level may omit ``scope_id``
(the bus then takes the instance scope); every other level needs it (``INVALID_REFERENCE``). The bus resolves
the chain (``NotFound`` for an unknown scope); ``resolve_target_scope`` checks that the scope found has the
requested kind and adds the label and the workspace the scope belongs to.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRef
from skm.platform.config.keys import Level
from skm.platform.config.scopes import ScopeRef as ConfigScopeRef
from skm.platform.config.store import ScopeTree

__all__ = ["ScopeRefDto", "Target", "bus_scope_of", "resolve_target_scope", "scope_of"]


class ScopeRefDto(Protocol):
    """``urn:skm:config:entry:v1#/$defs/scope_ref`` as every generated settings DTO spells it."""

    @property
    def level(self) -> str: ...
    @property
    def scope_id(self) -> UUID | None: ...


@dataclass(frozen=True, slots=True)
class Target:
    scope: ScopeRef  # the scope whose entries are written or read
    ref: ConfigScopeRef  # the same scope for the config engine, with its label
    workspace_id: WorkspaceId | None  # workspace the scope belongs to; None for instance and host

    @property
    def label(self) -> str:
        return self.ref.label


def scope_of(ref: ScopeRefDto | None) -> ScopeRef | None:
    """Bus scope of a DTO scope; ``None`` is the instance scope."""
    if ref is None:
        return None
    kind = ScopeKind(ref.level)
    if ref.scope_id is None:
        if kind is ScopeKind.INSTANCE:
            return None
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            f"a {kind.value} scope needs scope_id",
            details={"kind": "scope", "level": kind.value, "reason": "scope_id_required"},
        )
    return ScopeRef(kind, ScopeId(ref.scope_id))


def bus_scope_of[D](select: Callable[[D], ScopeRefDto | None]) -> Callable[[D], ScopeRef]:
    """``scope_of`` of a settings spec. It may answer ``None`` (the instance scope without ``scope_id``): the
    bus passes that to ``ScopeChainResolver.chain(uow, None)`` exactly as for a spec without ``scope_of``;
    only the ``CommandSpec``/``QuerySpec`` annotation is narrower."""

    def selected(dto: D) -> ScopeRef | None:
        return scope_of(select(dto))

    return cast("Callable[[D], ScopeRef]", selected)


def resolve_target_scope(uow: UnitOfWork, ref: ScopeRefDto | None, chain: tuple[ScopeRecord, ...]) -> Target:
    """The target of the bus-resolved ``chain``; its kind must be the requested level and its id the
    requested ``scope_id``. A level other than instance needs its explicit ``scope_id`` here too (a handler
    called around the bus): the scope is never inferred from ``chain``."""
    scope_of(ref)  # INVALID_REFERENCE scope_id_required
    record = chain[-1]
    level = ScopeKind.INSTANCE if ref is None else ScopeKind(ref.level)
    if record.kind is not level:
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            f"scope {record.id} is a {record.kind.value} scope, not {level.value}",
            details={"kind": "scope", "level": level.value, "actual": record.kind.value},
        )
    if ref is not None and ref.scope_id is not None and ref.scope_id != record.id:
        # rights are confirmed on ``chain``: it must end at the scope the DTO names
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            f"the resolved scope {record.id} is not the requested scope {ref.scope_id}",
            details={"kind": "scope", "level": level.value, "reason": "scope_mismatch"},
        )
    plain = ConfigScopeRef(Level(record.kind.value), record.id)
    labelled = ConfigScopeRef(plain.level, plain.scope_id, uow.repo(ScopeTree).label(plain))
    workspace_id = next(
        (item.workspace_id for item in reversed(chain) if item.workspace_id is not None), None
    )
    return Target(scope=ScopeRef(record.kind, record.id), ref=labelled, workspace_id=workspace_id)
