"""Permission sets of settings commands (settings §A.5 ``required_permissions``, §A.7, §18 p.4).

The bus authorizes ``CommandSpec.permission`` plus ``permissions_of(dto)`` before the handler runs, and it
sees only the DTO. The extra right of a key (``x-skm.write_permission``, e.g. ``hook.manage``) is therefore
read from the packaged section schemas, once per process.

``permissions_of`` only says what the bus must check; it is never taken as proof that the actor holds a right.
``Rights`` asks the ``Authorizer`` bound in the command's unit of work (the one the bus uses), for the actor
and the resolved target chain, about exactly the rights the change needs once the stored entry and the import
plan are known: clearing or setting a lock the stored entry carries, removing a locked entry, the key right of
an entry a replace import removes. Only confirmed rights reach ``WriteContext.granted``, so R13/R16 refuse
the rest, also for a handler called around the bus; a unit of work without an ``Authorizer`` confirms nothing
(``INTERNAL_ERROR`` from ``uow.repo``, nothing written). The ``reason_code`` of a refusing decision reaches
``WriteContext.refused``, so the ``FORBIDDEN`` of R13/R16 and the bus's denied audit name the reason of the
decision that refused, not of a later one.
"""

from collections.abc import Iterable, Mapping
from functools import cache
from types import MappingProxyType
from typing import cast

from skm.application_bus.context import CommandContext
from skm.application_bus.ports import Authorizer, AuthzDecision
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.domain.write_rules import required_permissions
from skm.platform.schema.registry import SchemaRegistry

from .project_keys import require_project_key

__all__ = [
    "BASE_PERMISSION",
    "Rights",
    "base_permission",
    "key_write_permission",
    "packaged_schemas",
    "write_permissions",
]

BASE_PERMISSION = "config.write"  # CommandSpec.permission of every settings command


def _walk(node: Mapping[str, JsonValue], prefix: str, found: dict[str, str]) -> None:
    properties = node.get("properties")
    if not isinstance(properties, dict):
        return
    for name, child in properties.items():
        if not isinstance(child, dict):
            continue
        key = f"{prefix}.{name}"
        meta = child.get("x-skm")
        if isinstance(meta, dict):
            permission = meta.get("write_permission")
            if isinstance(permission, str) and permission:
                found[key] = permission
        else:
            _walk(child, key, found)


@cache
def packaged_schemas() -> SchemaRegistry:
    """The schemas shipped with the package, loaded once per process."""
    return SchemaRegistry.load_default()


@cache
def _packaged() -> Mapping[str, str]:
    schemas = packaged_schemas()
    found: dict[str, str] = {}
    for urn in sorted(schemas.urns()):
        document = schemas.get(urn)
        section = document.get("x-skm-section")
        if isinstance(section, dict) and isinstance(section.get("id"), str):
            _walk(document, cast("str", section["id"]), found)
    return MappingProxyType(found)


def key_write_permission(key: str) -> str | None:
    """``x-skm.write_permission`` of a packaged key; ``None`` for other keys."""
    return _packaged().get(key)


def write_permissions(level: str, keys: Iterable[str], *, lock_change: bool) -> tuple[str, ...]:
    """``required_permissions`` of a write at ``level`` touching ``keys`` (all of them are required)."""
    needed: set[str] = set(required_permissions(level, None, lock_change=lock_change))
    for key in keys:
        # Run before the bus can return an idempotency receipt for this command.
        require_project_key(key)
        if (permission := key_write_permission(key)) is not None:
            needed.add(permission)
    return tuple(sorted(needed))


def base_permission(level: str) -> str:
    """``config.write_shared`` at instance/workspace/host, else ``config.write``."""
    return min(required_permissions(level, None, lock_change=False))


class Rights:
    """Rights of the command's actor in the resolved target chain, confirmed in the command's unit of work.

    Each permission is asked once per command and its ``AuthzDecision`` is kept: ``confirmed`` returns the
    granted subset, ``refusals`` the ``reason_code`` of each refused one, ``require`` refuses a permission the
    actor lacks with ``FORBIDDEN``. A refusal reports the reason of that one decision, for this actor, this
    permission and this chain; it is never asked again to explain a refusal, and a decision without a reason
    is reported without one.
    """

    def __init__(self, ctx: CommandContext, uow: UnitOfWork) -> None:
        self._ctx = ctx
        self._uow = uow
        self._decided: dict[str, AuthzDecision] = {}

    def _decision(self, permission: str) -> AuthzDecision:
        decision = self._decided.get(permission)
        if decision is None:
            authorizer = self._uow.repo(Authorizer)
            decision = authorizer.authorize(self._uow, self._ctx.actor, permission, self._ctx.scope_chain)
            self._decided[permission] = decision
        return decision

    def has(self, permission: str) -> bool:
        return self._decision(permission).allowed is True

    def confirmed(self, permissions: Iterable[str]) -> frozenset[str]:
        return frozenset(permission for permission in permissions if self.has(permission))

    def refusals(self, permissions: Iterable[str]) -> Mapping[str, str]:
        """``reason_code`` of each of ``permissions`` already refused with a reason; asks nothing."""
        found: dict[str, str] = {}
        for permission in permissions:
            reason = _reason(self._decided.get(permission))
            if reason is not None:
                found[permission] = reason
        return MappingProxyType(found)

    def require(self, permission: str) -> None:
        if not self.has(permission):
            details: dict[str, JsonValue] = {"permission": permission}
            reason = _reason(self._decided[permission])
            if reason is not None:
                details["reason_code"] = reason
            raise Forbidden(ErrorCode.FORBIDDEN, f"this change requires {permission}", details=details)


def _reason(decision: AuthzDecision | None) -> str | None:
    """The reason of a refusing decision as the ``Authorizer`` gave it; ``None`` for an allowed or unknown
    decision and for a refusal without one."""
    if decision is None or decision.allowed is True:
        return None
    reason = decision.reason_code
    return reason if isinstance(reason, str) and reason else None
