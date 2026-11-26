"""Configuration loader with a generation cache (settings §B.13).

``effective`` resolves one chain from the ports of the caller's unit of work: defaults, pack fragments,
stored entries of the chain and the invocation layers of this process, then selects run-frozen values of a
run snapshot and restart values of this process (``EffectiveConfig.with_overrides``).

The shared LRU cache is keyed by chain kind, chain scope ids and labels, store generation, pack generation,
the invocation layers, the frozen digest and whether process values apply. It only holds committed
configuration: when the store reports uncommitted writes of the current transaction (``pending_writes``) the
loader neither reads nor fills the cache, so a settings command sees its own writes and a rollback leaves
nothing behind. A result is also not cached when a generation moved while it was being read.

``start_process`` captures the restart values of the instance chain (and of one host chain) once, from
committed configuration; the captured ``ProcessConfig`` carries the instance and host identity it was
captured for and is applied only to chains of that identity.
"""

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Mapping, Sequence
from typing import Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.outcomes import Diagnostic, Severity
from skm.kernel.scopes import ScopeKind
from skm.kernel.scopes import ScopeRef as KernelScopeRef

from .effective import EffectiveConfig, FrozenConfig, ProcessConfig
from .keys import LOCK_LEVELS, Chain, Level
from .layers import Contribution, Layer, LayerRef
from .registry import SettingsRegistry
from .resolver import resolve
from .scopes import ScopeChain, ScopeRef
from .sources.defaults import defaults_layer
from .sources.packs import pack_layers
from .store import ConfigStore, PackConfigSource, ScopeTree, StoredContribution

__all__ = ["ConfigLoader", "ProcessConfig"]

DEFAULT_CACHE_SIZE: Final = 256

type _CacheKey = tuple[Hashable, ...]


class ConfigLoader:
    """Effective configuration of scope chains for one process (registry, packs and invocation are fixed)."""

    def __init__(
        self,
        registry: SettingsRegistry,
        packs: PackConfigSource,
        invocation: Sequence[Layer] = (),
        *,
        expand_path: Callable[[str], str] | None = None,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ) -> None:
        if isinstance(cache_size, bool) or cache_size < 0:
            raise ValueError("cache_size must be a non-negative integer")
        layers = tuple(invocation)
        for layer in layers:
            if layer.ref.level is not Level.INVOCATION:
                raise ValueError(f"invocation layers only, not {layer.ref.display}")
        self._registry = registry
        self._packs = packs
        self._invocation = layers
        self._expand = expand_path
        self._cache_size = cache_size
        self._cache: OrderedDict[_CacheKey, EffectiveConfig] = OrderedDict()
        self._lock = threading.Lock()
        self._process: ProcessConfig | None = None

    @property
    def registry(self) -> SettingsRegistry:
        return self._registry

    @property
    def process(self) -> ProcessConfig | None:
        """The restart values captured by ``start_process``; ``None`` before it."""
        return self._process

    # ------------------------------------------------------------------ public calls
    def start_process(
        self, store: ConfigStore, scopes: ScopeTree, host: ScopeRef | KernelScopeRef | None
    ) -> ProcessConfig:
        """Capture restart values once, from committed configuration (a short read-only unit of work)."""
        if self._process is not None:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "process configuration is already captured",
                details={"reason": "process_already_started"},
            )
        if store.pending_writes():
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "process configuration must be captured from committed configuration",
                details={"reason": "process_capture_uncommitted"},
            )
        work = self._effective(store, scopes, None, Chain.WORK, frozen=None, process=False)
        host_config = (
            None
            if host is None
            else self._effective(store, scopes, host, Chain.HOST, frozen=None, process=False)
        )
        captured = ProcessConfig.capture(work, host_config)
        with self._lock:
            if self._process is not None:
                raise InternalError(
                    ErrorCode.INTERNAL_ERROR,
                    "process configuration is already captured",
                    details={"reason": "process_already_started"},
                )
            self._process = captured
        return captured

    def effective(
        self,
        store: ConfigStore,
        scopes: ScopeTree,
        scope: ScopeRef | KernelScopeRef | None,
        kind: Chain = Chain.WORK,
        *,
        frozen: FrozenConfig | None = None,
    ) -> EffectiveConfig:
        """The chain of ``scope`` (``None`` → instance) as the caller's transaction sees it.

        A kernel ``ScopeRef`` (the bus spelling, ``scope_of(cmd)``) names its chain itself: a host scope gets
        the host chain, every other scope the chain ``kind``. A config ``ScopeRef`` always uses ``kind``, so a
        host level asked for in the work chain is still refused by the scope tree.
        """
        return self._effective(store, scopes, scope, _chain_kind(scope, kind), frozen=frozen, process=True)

    def effective_host(
        self, store: ConfigStore, scopes: ScopeTree, host: ScopeRef | KernelScopeRef
    ) -> EffectiveConfig:
        return self._effective(store, scopes, host, Chain.HOST, frozen=None, process=True)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    # ------------------------------------------------------------------ algorithm (§B.13.2)
    def _effective(
        self,
        store: ConfigStore,
        scopes: ScopeTree,
        scope: ScopeRef | KernelScopeRef | None,
        kind: Chain,
        *,
        frozen: FrozenConfig | None,
        process: bool,
    ) -> EffectiveConfig:
        target = scopes.instance_scope() if scope is None else _config_ref(scope)
        chain = scopes.chain_for(target, kind)
        _check_chain(chain, target, kind)
        selected = self._process_for(chain) if process else None
        pending = store.pending_writes()
        generation = store.generation()
        pack_generation = self._packs.generation()
        key: _CacheKey = (
            kind,
            chain.ids(),
            tuple(item.label for item in chain.scopes),
            generation,
            pack_generation,
            id(self._invocation),
            # The digest does not cover the run id: a cache hit must not skip the run identity check.
            None if frozen is None else (frozen.run_scope_id, frozen.digest),
            selected is not None,
        )
        if not pending:
            with self._lock:
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    return cached
        result = self._resolve(store, chain, generation, pack_generation)
        if frozen is not None or selected is not None:
            result = result.with_overrides(frozen, selected)
        if (
            not pending
            and self._cache_size
            and not store.pending_writes()
            and store.generation() == generation
            and self._packs.generation() == pack_generation
        ):
            with self._lock:
                self._cache[key] = result
                self._cache.move_to_end(key)
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
        return result

    def _process_for(self, chain: ScopeChain) -> ProcessConfig | None:
        """Process values apply to every work chain of the captured instance and to the captured host chain.

        A work chain of another instance is refused by ``with_overrides`` (fail closed); a host chain of
        another host is not this process and gets no restart values.
        """
        process = self._process
        if process is None:
            return None
        if chain.kind is Chain.HOST and process.host_target != chain.target:
            return None
        return process

    def _resolve(
        self, store: ConfigStore, chain: ScopeChain, generation: int, pack_generation: int
    ) -> EffectiveConfig:
        warnings: list[Diagnostic] = []
        layers: list[Layer] = [defaults_layer(self._registry, chain.kind)]
        layers.extend(
            pack_layers(self._packs.fragments(chain), self._registry, chain.kind, warn=warnings.append)
        )
        entries = store.entries_for(chain.ids())
        for scope in chain.scopes:
            layer, bad_locks = _stored_layer(scope, entries.get(scope.scope_id, {}))
            layers.append(layer)
            warnings.extend(bad_locks)
        layers.extend(self._invocation)
        result = resolve(
            self._registry,
            chain,
            layers,
            generation=generation,
            pack_generation=pack_generation,
            expand=self._expand,
        )
        return _with_diagnostics(result, warnings) if warnings else result


def _chain_kind(scope: ScopeRef | KernelScopeRef | None, kind: Chain) -> Chain:
    if isinstance(scope, KernelScopeRef) and scope.kind is ScopeKind.HOST:
        return Chain.HOST
    return Chain(kind)


def _config_ref(scope: ScopeRef | KernelScopeRef) -> ScopeRef:
    if isinstance(scope, ScopeRef):
        return scope
    return ScopeRef(Level(scope.kind.value), scope.id)


def _check_chain(chain: ScopeChain, target: ScopeRef, kind: Chain) -> None:
    if chain.kind is not kind or chain.target != target:
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            "scope tree returned a chain of another scope",
            details={"chain": kind.value, "level": target.level.value},
        )


def _stored_layer(scope: ScopeRef, rows: Mapping[str, StoredContribution]) -> tuple[Layer, list[Diagnostic]]:
    ref = LayerRef(scope.level, scope.scope_id, label=scope.label)
    contributions: dict[str, Contribution] = {}
    bad_locks: list[Diagnostic] = []
    for key, row in sorted(rows.items()):
        if row.key != key:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "config entry is filed under another key",
                details={"scope_id": str(scope.scope_id), "key": key},
            )
        at = LayerRef(
            scope.level, scope.scope_id, label=scope.label, entry_id=row.entry_id, row_version=row.row_version
        )
        locked = row.locked and scope.level in LOCK_LEVELS
        if row.locked and not locked:
            # Data changed outside the commands: the lock is ignored, never trusted (§B.5.6).
            bad_locks.append(
                Diagnostic(
                    code="CONFIG_SCOPE_NOT_ALLOWED",
                    message=f"lock at {at.display} is ignored: only instance and workspace may lock a key",
                    severity=Severity.WARNING,
                    target=key,
                    details={"reason": "lock_level", "layers": [at.to_json()]},
                )
            )
        contributions[key] = Contribution(at, row.op, row.value, locked=locked)
    return Layer(ref, contributions), bad_locks


def _with_diagnostics(result: EffectiveConfig, extra: Sequence[Diagnostic]) -> EffectiveConfig:
    return EffectiveConfig(
        registry=result.registry,
        chain=result.chain,
        resolutions={key: result.resolution(key) for key in result.resolved_keys()},
        invalid=result.invalid_keys(),
        diagnostics=(*extra, *result.diagnostics),
        generation=result.generation,
        pack_generation=result.pack_generation,
        digest=result.digest,
    )
