"""``ScopeTree`` over any ``ScopeRegistry``: the config chain of a stored scope, instance first."""

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRegistry

from .keys import Chain, Level
from .scopes import ScopeChain, ScopeRef

__all__ = ["RegistryScopeTree"]

_WORK_CHAIN = frozenset(
    {ScopeKind.INSTANCE, ScopeKind.WORKSPACE, ScopeKind.PROJECT, ScopeKind.PLAN, ScopeKind.RUN}
)
_HOST_CHAIN = frozenset({ScopeKind.INSTANCE, ScopeKind.HOST})


class RegistryScopeTree:
    """Read side for the config resolver (settings §B.10): the chain of a scope, instance first.

    work: the ancestors by ``parent_id``; a host scope has no work chain. host: ``(instance, host)`` for a
    host scope and ``(instance)`` for the instance scope. The requested level must be the stored kind of the
    scope. Labels are ``instance`` and ``<level>:<id>``: slugs and names live in tables of the owning modules.
    """

    def __init__(self, registry: ScopeRegistry) -> None:
        self._registry = registry

    def instance_scope(self) -> ScopeRef:
        return self._ref(self._registry.instance())

    def chain_for(self, scope: ScopeRef, kind: Chain) -> ScopeChain:
        chain = Chain(kind)
        records = self._registry.ancestors(ScopeId(scope.scope_id))
        if records[-1].kind.value != scope.level.value:
            raise ValidationFailed(
                ErrorCode.INVALID_REFERENCE,
                "scope has another kind",
                details={"kind": "scope", "level": scope.level.value, "actual": records[-1].kind.value},
            )
        allowed = _HOST_CHAIN if chain is Chain.HOST else _WORK_CHAIN
        if records[-1].kind not in allowed:
            raise ValidationFailed(
                ErrorCode.CONFIG_SCOPE_NOT_ALLOWED,
                f"a {records[-1].kind.value} scope has no {chain.value} configuration chain",
                details={"level": records[-1].kind.value, "chain": chain.value},
            )
        return ScopeChain(chain, tuple(self._ref(record) for record in records))

    def label(self, scope: ScopeRef) -> str:
        return "instance" if scope.level is Level.INSTANCE else f"{scope.level.value}:{scope.scope_id}"

    def _ref(self, record: ScopeRecord) -> ScopeRef:
        level = Level(record.kind.value)
        return ScopeRef(level, record.id, self.label(ScopeRef(level, record.id)))
