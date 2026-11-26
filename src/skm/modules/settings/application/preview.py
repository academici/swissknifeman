"""Resolution previews on the connection of the command's unit of work (settings §A.7.0).

Settings commands do not read ``ctx.config``: they resolve on their own transaction, so they see their own
uncommitted writes, and they never include the invocation layer of the serving process. ``Preview`` loads
the layers of one target scope once (defaults, pack fragments, the stored entries of the chain) and answers

* ``farther(key)`` — the key folded over the farther levels without the target scope (R5 b, R7, R8);
* ``candidate(overrides)`` — the target scope with its entries replaced by ``overrides`` (``None`` = the entry
  is removed), resolved for every key of the affected sections, so the section validators see their whole
  candidate slice (R14, import ``effective_diff``).

The chain kind follows the target level: a host scope has the host chain, project/plan/run (and workspace)
the work chain; the instance scope belongs to both, so the kind of the key decides there.
``RegistryChecks`` is the ``ValueChecks`` of the write rules over the registry schemas and the engine merge.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from functools import cache
from typing import cast
from uuid import UUID

from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import Diagnostic
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.domain.entry import ConfigEntry
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.keys import LOCK_LEVELS, Chain, KeySpec, Level, copy_json
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.merge import KeyResolution, deep_merge, fold, narrow_value
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.resolver import resolve
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.config.sources.defaults import defaults_layer
from skm.platform.config.sources.packs import pack_layers
from skm.platform.config.store import ConfigStore, PackConfigSource, ScopeTree, StoredContribution
from skm.platform.schema.findings import SchemaIssue
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import SchemaValidator

from .project_keys import project_keys
from .rights import packaged_schemas

__all__ = ["Preview", "RegistryChecks", "chain_kind", "contribution_of"]


def chain_kind(level: Level, spec: KeySpec | None = None) -> Chain:
    """The chain a write at ``level`` resolves in: host for a host scope, the key's own chain at instance."""
    if level is Level.HOST:
        return Chain.HOST
    if level is Level.INSTANCE and spec is not None:
        return spec.chain
    return Chain.WORK


def _ref(scope: ScopeRef, *, entry_id: UUID | None = None, row_version: int | None = None) -> LayerRef:
    return LayerRef(
        scope.level, scope.scope_id, label=scope.label, entry_id=entry_id, row_version=row_version
    )


def contribution_of(scope: ScopeRef, entry: ConfigEntry | StoredContribution) -> Contribution:
    """The contribution an entry makes at ``scope``; a lock outside instance/workspace is never trusted."""
    entry_id = entry.id if isinstance(entry, ConfigEntry) else entry.entry_id
    op = entry.op.value if isinstance(entry, ConfigEntry) else entry.op
    locked = entry.locked and scope.level in LOCK_LEVELS
    return Contribution(
        _ref(scope, entry_id=entry_id, row_version=entry.row_version), op, entry.value, locked=locked
    )


class Preview:
    """Layers of one target scope in one unit of work; built lazily per chain kind."""

    def __init__(
        self, uow: UnitOfWork, registry: SettingsRegistry, packs: PackConfigSource, target: ScopeRef
    ) -> None:
        self._uow = uow
        self._registry = registry
        self._packs = packs
        self._target = target
        self._chains: dict[Chain, tuple[ScopeChain, tuple[Layer, ...], Layer]] = {}

    @property
    def registry(self) -> SettingsRegistry:
        return self._registry

    def _load(self, kind: Chain) -> tuple[ScopeChain, tuple[Layer, ...], Layer]:
        """``(chain, layers before the target, target layer)`` of ``kind``."""
        loaded = self._chains.get(kind)
        if loaded is not None:
            return loaded
        chain = self._uow.repo(ScopeTree).chain_for(self._target, kind)
        warnings: list[Diagnostic] = []
        layers: list[Layer] = [defaults_layer(self._registry, kind)]
        layers.extend(
            Layer(layer.ref, project_keys(layer.contributions))
            for layer in pack_layers(self._packs.fragments(chain), self._registry, kind, warn=warnings.append)
        )
        stored = self._uow.repo(ConfigStore).entries_for(chain.ids())
        for scope in chain.scopes:
            rows = project_keys(stored.get(scope.scope_id, {}))
            contributions = {key: contribution_of(scope, row) for key, row in sorted(rows.items())}
            layers.append(Layer(_ref(scope), contributions))
        loaded = (chain, tuple(layers[:-1]), layers[-1])
        self._chains[kind] = loaded
        return loaded

    def chain(self, kind: Chain) -> ScopeChain:
        return self._load(kind)[0]

    def farther(self, spec: KeySpec) -> KeyResolution:
        """``spec`` folded over default, packs and the stored levels above the target (no invocation)."""
        _, farther, _ = self._load(chain_kind(self._target.level, spec))
        contributions = [
            layer.contributions[spec.key] for layer in farther if spec.key in layer.contributions
        ]
        return fold(spec, contributions)

    def candidate(
        self, kind: Chain, overrides: Mapping[str, Contribution | None], *, keys: Iterable[str] = ()
    ) -> EffectiveConfig:
        """The target with ``overrides`` applied, resolved for every key of the sections of ``overrides``
        and ``keys`` that belongs to ``kind``."""
        chain, farther, target = self._load(kind)
        contributions = dict(target.contributions)
        for key, contribution in overrides.items():
            if contribution is None:
                contributions.pop(key, None)
            else:
                contributions[key] = contribution
        sections = dict.fromkeys(
            self._registry.spec(key).section for key in (*overrides, *keys) if self._registry.find(key)
        )
        selected = [
            spec.key for section in sections for spec in self._registry.keys(chain=kind, section=section)
        ]
        return self._resolve(chain, (*farther, Layer(target.ref, contributions)), selected)

    def current(self, kind: Chain, keys: Iterable[str] | None = None) -> EffectiveConfig:
        """The stored state of the target chain for ``keys`` (``None``: every key of ``kind``); a key of the
        other chain is ``CONFIG_SCOPE_NOT_ALLOWED``."""
        chain, farther, target = self._load(kind)
        return self._resolve(chain, (*farther, target), keys)

    def _resolve(
        self, chain: ScopeChain, layers: Sequence[Layer], keys: Iterable[str] | None
    ) -> EffectiveConfig:
        return resolve(
            self._registry,
            chain,
            layers,
            keys=keys,
            generation=self._uow.repo(ConfigStore).generation(),
            pack_generation=self._packs.generation(),
        )


def _shift(issues: Sequence[SchemaIssue]) -> list[SchemaIssue]:
    """Findings of ``[item]`` that belong to the item, with the ``/0`` prefix removed."""
    return [
        SchemaIssue(issue.pointer[2:], issue.schema_pointer, issue.code, issue.message)
        for issue in issues
        if issue.pointer == "/0" or issue.pointer.startswith("/0/")
    ]


_REQUIRED_KEYWORDS = ("required", "dependentRequired")
_SCHEMA_MAPS = frozenset({"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"})
_REF_KEYWORDS = ("$ref", "$dynamicRef")


def _presence_keyword(name: str, child: object) -> bool:
    return (name == "required" and isinstance(child, list)) or (
        name == "dependentRequired" and isinstance(child, dict)
    )


def _data_keyword(name: str) -> bool:
    """Keywords whose value is instance data or metadata, never a subschema."""
    return name in ("const", "enum", "default", "examples") or name.startswith("x-")


def _schema_children(name: str, child: object) -> Iterable[object]:
    """Subschemas under keyword ``name``: the values of a name→schema map, else ``child`` itself."""
    if _data_keyword(name):
        return ()
    if name in _SCHEMA_MAPS and isinstance(child, dict):
        return cast("Mapping[str, object]", child).values()
    return (child,)


def _mentions_required(node: object) -> bool:
    if isinstance(node, list):
        return any(_mentions_required(child) for child in cast("list[object]", node))
    if not isinstance(node, dict):
        return False
    return any(
        _presence_keyword(name, child)
        or any(_mentions_required(sub) for sub in _schema_children(name, child))
        for name, child in cast("Mapping[str, object]", node).items()
    )


def _without_required(node: object) -> object:
    """Schema ``node`` with presence constraints removed recursively: ``required``/``dependentRequired``
    dropped, ``oneOf`` as ``anyOf`` (branches told apart only by required members would all match), a
    ``not`` or an ``if`` that tests presence dropped (``if`` with its ``then``/``else``). Every other
    constraint stays; the merged value is still checked against the full schema (R5 b)."""
    if isinstance(node, list):
        return [_without_required(child) for child in cast("list[object]", node)]
    if not isinstance(node, dict):
        return node
    mapping = cast("Mapping[str, object]", node)
    out: dict[str, object] = {}
    drop_if = "if" in mapping and _mentions_required(mapping["if"])
    for name, child in mapping.items():
        if _data_keyword(name):
            out[name] = child
            continue
        if _presence_keyword(name, child):
            continue
        if (name == "not" and _mentions_required(child)) or (drop_if and name in ("if", "then", "else")):
            continue
        if name in _SCHEMA_MAPS and isinstance(child, dict):
            items = cast("Mapping[str, object]", child).items()
            out[name] = {member: _without_required(schema) for member, schema in items}
        else:
            out["anyOf" if name == "oneOf" and "anyOf" not in mapping else name] = _without_required(child)
    return out


def _references(node: object) -> Iterable[str]:
    """Absolute schema URNs ``node`` refers to (fragments and local pointers excluded)."""
    if isinstance(node, dict):
        for name, child in cast("Mapping[str, object]", node).items():
            if _data_keyword(name):
                continue
            if name in _REF_KEYWORDS and isinstance(child, str):
                urn = child.partition("#")[0]
                if urn:
                    yield urn
            else:
                yield from _references(child)
    elif isinstance(node, list):
        for child in cast("list[object]", node):
            yield from _references(child)


@cache
def _partial_validator(key: str, schema_text: str) -> SchemaValidator | None:
    """The key schema and every schema it refers to with ``required`` removed recursively (settings §A.5
    R5 a); ``None`` when a referenced schema is not packaged (the caller falls back to filtering findings)."""
    schemas = packaged_schemas()
    known = schemas.urns()
    documents: dict[str, Mapping[str, JsonValue]] = {}
    root = cast("Mapping[str, JsonValue]", json.loads(schema_text))
    pending = list(_references(root))
    while pending:
        urn = pending.pop()
        if urn in documents:
            continue
        if urn not in known:
            return None
        document = dict(schemas.get(urn))  # a read-only view: walk a plain copy
        documents[urn] = cast("Mapping[str, JsonValue]", _without_required(document))
        pending.extend(_references(document))
    urn = f"urn:skm:settings:partial:{key}:v1"
    documents[urn] = {
        **cast("Mapping[str, JsonValue]", _without_required(dict(root))),
        "$id": urn,
    }
    return SchemaRegistry(documents, schemas.registry).validator(urn)


class RegistryChecks:
    """``ValueChecks`` of one key: schema findings from the registry, ``deep_merge``/``narrow_value`` of the
    engine. The partial schema of a ``deep_merge`` contribution is the key schema with ``required`` removed
    recursively, through its ``$ref`` targets and combinator branches."""

    def __init__(self, registry: SettingsRegistry, spec: KeySpec) -> None:
        self._registry = registry
        self._spec = spec

    def schema_issues(self, value: JsonValue, *, partial: bool = False) -> Sequence[SchemaIssue]:
        if not partial:
            return list(self._registry.value_issues(self._spec.key, value))
        schema = copy_json(self._spec.value_schema, "value_schema")
        validator = _partial_validator(self._spec.key, json.dumps(schema, sort_keys=True))
        if validator is None:
            issues = self._registry.value_issues(self._spec.key, value)
            return [issue for issue in issues if issue.code not in _REQUIRED_KEYWORDS]
        return list(validator.issues(value))

    def item_issues(self, item: JsonValue) -> Sequence[SchemaIssue]:
        return _shift(self._registry.value_issues(self._spec.key, [item]))

    def deep_merge(self, base: JsonValue, overlay: JsonValue) -> JsonValue:
        return deep_merge(cast("Mapping[str, JsonValue]", base), cast("Mapping[str, JsonValue]", overlay))

    def narrow_value(self, current: JsonValue, candidate: JsonValue) -> JsonValue:
        return narrow_value(self._spec, current, candidate)
