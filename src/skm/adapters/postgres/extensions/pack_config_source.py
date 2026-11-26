"""``PackConfigSource`` over ``skm_extensions`` and ``skm_config`` without a cycle (extensions §11.3, S26).

``PostgresPackConfigSource`` computes active pack configuration fragments for a ``ScopeChain``:
1. ``extensions.packs.enabled``, ``extensions.packs.versions`` and ``extensions.packs.priority`` carry flag
   ``K`` (``spec.pack == False``) and are resolved on the work chain using only ``defaults_layer``, stored
   ``skm_config.entries`` and ``invocation`` layers — never a ``pack`` layer — avoiding any config cycle.
2. Active versions of ``core`` plus enabled slugs are chosen via ``choose_pack_versions``.
3. Only ``builtin`` and ``operator`` packs supply ``[config]`` (security S26); ``third_party`` rows are
   ignored even if present in storage.
4. Unknown keys, keys missing ``Level.PACK`` (flag ``K``) and ``SECRET`` keys are dropped.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from contextlib import AbstractContextManager, contextmanager, suppress
from typing import TYPE_CHECKING, Final, cast

import psycopg

from skm.adapters.postgres.config_store import PostgresConfigStore, damaged_row, loads_value
from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.extensions.mapping import pack_summary_from_row
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.modules.extensions.domain.keys import PackVersionId, VersionConstraint
from skm.modules.extensions.domain.pack import CORE_PACK, PackTrust, PackVersionSummary
from skm.modules.extensions.domain.resolution import choose_pack_versions, config_choices
from skm.platform.config.keys import LOCK_LEVELS, Chain, Level, Sensitivity
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.resolver import resolve
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.config.sources.defaults import defaults_layer
from skm.platform.config.sources.packs import PackFragment

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence

    from skm.adapters.postgres.pool import PoolHandle
    from skm.kernel.json_types import JsonValue
    from skm.platform.config.registry import SettingsRegistry
    from skm.platform.config.store import StoredContribution

__all__ = ["PackConnectionSlot", "PostgresPackConfigSource"]

_LOG = logging.getLogger(__name__)

_PACK_ENABLED_KEY: Final = "extensions.packs.enabled"
_PACK_VERSIONS_KEY: Final = "extensions.packs.versions"
_PACK_PRIORITY_KEY: Final = "extensions.packs.priority"
_PACK_SELECTION_KEYS: Final = (_PACK_ENABLED_KEY, _PACK_VERSIONS_KEY, _PACK_PRIORITY_KEY)

_GENERATION_ROWS: Final = """
SELECT v.id::text, p.trust, v.state, v.priority, v.digest, (v.manifest -> 'config')::text
  FROM skm_extensions.pack_versions v
  JOIN skm_extensions.packs p ON p.id = v.pack_id
 ORDER BY v.id
"""

_ACTIVE_PACK_CONFIGS: Final = """
SELECT v.id, v.pack_id, p.slug, p.title, p.trust, v.version, v.digest, v.priority, v.state,
       v.installed_at, (v.manifest -> 'config')::text
  FROM skm_extensions.pack_versions v
  JOIN skm_extensions.packs p ON p.id = v.pack_id
 WHERE v.state = 'active'
 ORDER BY p.slug, v.version_major DESC, v.version_minor DESC, v.version_patch DESC,
          (v.prerelease IS NULL) DESC, v.prerelease DESC
"""

type ConnectionSource = psycopg.Connection | Callable[[], AbstractContextManager[psycopg.Connection]]


class PackConnectionSlot:
    """Thread-local active PostgreSQL connection (start-up or open UoW) with pool fallback."""

    def __init__(self) -> None:
        self._local = threading.local()
        self._pool: PoolHandle | None = None

    def push(self, supplier: Callable[[], psycopg.Connection | None]) -> None:
        stack = cast("list[Callable[[], psycopg.Connection | None]]", getattr(self._local, "stack", []))
        stack.append(supplier)
        self._local.stack = stack

    def pop(self) -> None:
        stack = cast("list[Callable[[], psycopg.Connection | None]]", getattr(self._local, "stack", []))
        if stack:
            stack.pop()

    def holds(self) -> bool:
        return bool(getattr(self._local, "stack", ()))

    def bind_pool(self, pool: PoolHandle) -> None:
        self._pool = pool

    @contextmanager
    def connection(self) -> Generator[psycopg.Connection]:
        stack = cast("list[Callable[[], psycopg.Connection | None]]", getattr(self._local, "stack", []))
        for supplier in reversed(stack):
            active = supplier()
            if active is not None and not active.closed:
                yield active
                return
        if self._pool is None:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "pack config source has no active connection or pool",
                details={"reason": "pack_config_connection_unavailable"},
            )
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            if not conn.closed:
                with suppress(psycopg.Error):
                    conn.rollback()
            self._pool.putconn(conn)


def _stored_layer(scope: ScopeRef, rows: Mapping[str, StoredContribution]) -> Layer:
    ref = LayerRef(scope.level, scope.scope_id, label=scope.label)
    contributions: dict[str, Contribution] = {}
    for key, row in sorted(rows.items()):
        at = LayerRef(
            scope.level,
            scope.scope_id,
            label=scope.label,
            entry_id=row.entry_id,
            row_version=row.row_version,
        )
        locked = row.locked and scope.level in LOCK_LEVELS
        contributions[key] = Contribution(at, row.op, row.value, locked=locked)
    return Layer(ref, contributions)


def _work_chain(scope_chain: ScopeChain) -> ScopeChain:
    if scope_chain.kind is Chain.WORK:
        return scope_chain
    return ScopeChain(Chain.WORK, (scope_chain.scopes[0],))


def _decode_config(version_id: PackVersionId, raw_text: str | None) -> Mapping[str, JsonValue]:
    if raw_text is None:
        return {}
    try:
        parsed = loads_value(raw_text)
    except (TypeError, ValueError) as exc:
        raise damaged_row("pack_versions", version_id, exc) from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise damaged_row("pack_versions", version_id, ValueError("manifest.config is not a JSON object"))
    return parsed


class PostgresPackConfigSource:
    """``PackConfigSource`` reading ``skm_extensions.pack_versions`` without a ``pack`` layer cycle."""

    def __init__(
        self,
        conn: ConnectionSource,
        settings: SettingsRegistry,
        invocation: Sequence[Layer] = (),
    ) -> None:
        for layer in invocation:
            if layer.ref.level is not Level.INVOCATION:
                raise ValueError(f"invocation layers only, not {layer.ref.display}")
        self._conn = conn
        self._settings = settings
        self._invocation = tuple(invocation)

    @contextmanager
    def _open(self) -> Generator[psycopg.Connection]:
        if callable(self._conn):
            with self._conn() as conn:
                yield conn
            return
        yield self._conn

    def generation(self) -> int:
        with self._open() as conn:
            try:
                rows = conn.execute(_GENERATION_ROWS).fetchall()
            except psycopg.Error as exc:
                raise translate_pg_error(exc) from exc
        if not rows:
            return 0
        hasher = hashlib.sha256()
        for row in rows:
            version_id, trust, state, priority, digest, config_text = row
            record = f"{version_id}\0{trust}\0{state}\0{priority}\0{digest}\0{config_text or ''}\n"
            hasher.update(record.encode("utf-8"))
        value = int.from_bytes(hasher.digest()[:8], "big") & 0x3FFF_FFFF_FFFF_FFFF
        return value or 1

    def fragments(self, scope_chain: ScopeChain) -> tuple[PackFragment, ...]:
        work_chain = _work_chain(scope_chain)
        with self._open() as conn:
            entries = PostgresConfigStore(conn).entries_for(work_chain.ids())
            try:
                active_rows = conn.execute(_ACTIVE_PACK_CONFIGS).fetchall()
            except psycopg.Error as exc:
                raise translate_pg_error(exc) from exc
        if not active_rows:
            return ()

        layers: list[Layer] = [
            defaults_layer(self._settings, Chain.WORK),
            *(_stored_layer(scope, entries.get(scope.scope_id, {})) for scope in work_chain.scopes),
            *self._invocation,
        ]
        selection = resolve(
            self._settings, work_chain, layers, generation=0, pack_generation=0, keys=_PACK_SELECTION_KEYS
        )
        invalid = selection.invalid_keys()

        enabled: Sequence[str] = (
            cast("Sequence[str]", selection.get(_PACK_ENABLED_KEY))
            if _PACK_ENABLED_KEY not in invalid
            else (CORE_PACK,)
        )
        raw_versions: Mapping[str, str] = (
            cast("Mapping[str, str]", selection.get(_PACK_VERSIONS_KEY))
            if _PACK_VERSIONS_KEY not in invalid
            else {}
        )
        priorities: Mapping[str, int] = (
            cast("Mapping[str, int]", selection.get(_PACK_PRIORITY_KEY))
            if _PACK_PRIORITY_KEY not in invalid
            else {}
        )
        constraints: dict[str, VersionConstraint] = {}
        for slug, expr in raw_versions.items():
            try:
                constraints[slug] = VersionConstraint.parse(expr)
            except ValueError:
                continue

        summaries: list[PackVersionSummary] = []
        configs_by_version: dict[PackVersionId, Mapping[str, JsonValue]] = {}
        for row in active_rows:
            summary = pack_summary_from_row(row[:10])
            summaries.append(summary)
            configs_by_version[summary.version_id] = _decode_config(
                summary.version_id, cast("str | None", row[10])
            )

        choices, _diagnostics = choose_pack_versions(
            [CORE_PACK, *enabled],
            constraints,
            summaries,
            priorities=priorities,
        )
        for choice in choices:
            if choice.trust is PackTrust.THIRD_PARTY and configs_by_version.get(choice.version_id):
                _LOG.warning(
                    "PACK_CONFIG_IGNORED: %s@%s (third_party config fragment ignored)",
                    choice.slug,
                    choice.version,
                )

        fragments: list[PackFragment] = []
        for choice in config_choices(choices):
            raw_config = configs_by_version.get(choice.version_id, {})
            if not raw_config:
                continue
            filtered: dict[str, JsonValue] = {}
            for key, value in raw_config.items():
                spec = self._settings.find(key)
                if spec is None or not spec.pack or spec.sensitivity is Sensitivity.SECRET:
                    _LOG.warning("PACK_CONFIG_IGNORED: %s (%s)", key, choice.slug)
                    continue
                filtered[key] = value
            if filtered:
                fragments.append(PackFragment(pack_id=choice.slug, priority=choice.priority, values=filtered))
        return tuple(fragments)
