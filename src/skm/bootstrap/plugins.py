"""Plugin loader (kernel-platform §5.4; steps 1-11 of mechanisms/02-plugins §4; security S16).

The contract (``ComponentKind``, ``ComponentSpec``, ``PluginManifest``) belongs to ``skm.plugin_api``. Steps
1, 2 and 2a never execute plugin code: discovery reads entry point metadata, the allowlist is
``plugins.allowed``, and the runtime data files are found through the distribution's RECORD and read as text
(no ``importlib.resources``). ``ep.load()`` (step 3) runs import-time code of an *allowed* plugin and is no
sandbox; the compatibility check of step 4 happens after it, but no factory of an incompatible plugin is ever
called. Every key and schema conflict is found before the first factory runs and stops the bootstrap
regardless of the order of ``plugins.allowed``.

One ``LoadedPlugin`` is returned per discovered entry point, allowed ones first in allowlist order: a
not-allowed one has no manifest and no data; on the control plane a plugin outside
``plugins.control_plane_allowed`` contributes its runtime data only (``data_only``), which is what lets the
control plane see a host runtime without its code."""

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.metadata import Distribution, EntryPoint, PackagePath
from types import MappingProxyType
from typing import Any, ClassVar, Final, Literal, cast

from skm import __version__
from skm.application_bus.client import new_request_id
from skm.bootstrap.builtins import BUILTIN_COMPONENTS, builtin_keys, component_problem
from skm.bootstrap.plugin_distribution import (
    LOAD_FAILED,
    UNKNOWN,
    UNKNOWN_PROVENANCE,
    PluginProvenance,
    RuntimeDataFiles,
    default_entry_points,
    distribution_files,
    provenance,
    read_runtime_data,
    record_digest,
)
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, InternalError, ValidationFailed
from skm.kernel.id_generator import IdGenerator
from skm.kernel.isolation import is_plugin_isolation_profile
from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import Diagnostic, Severity
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWorkFactory
from skm.modules.runtimes.domain.capability import (
    StaticCapabilityCatalog,
)
from skm.modules.runtimes.domain.ids import is_runtime_id
from skm.platform.config.effective import ProcessConfig
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.registry import SettingsRegistry, schema_closure_digest
from skm.platform.config.scopes import ScopeRef as ConfigScopeRef
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.logging.logger import get_logger
from skm.platform.schema.registry import DRAFT_2020_12, URN_PATTERN, SchemaRegistry
from skm.platform.system_clock import SystemClock
from skm.plugin_api import API_VERSION
from skm.plugin_api.manifest import (
    PLUGIN_ID_PATTERN,
    ComponentKind,
    ComponentSpec,
    PluginContext,
    PluginManifest,
    Side,
    requires_skm_matches,
)

__all__ = [
    "LoadedPlugin",
    "PluginAllowlist",
    "PluginSchema",
    "PluginSchemas",
    "PluginSettingsView",
    "PluginStatus",
    "PluginViews",
    "ProcessPlugins",
    "SettingsPhase2",
    "capability_catalog",
    "default_context",
    "load_plugins",
    "merged_schemas",
    "plugin_settings_view",
]


_PLUGIN_ID: Final = re.compile(PLUGIN_ID_PATTERN.removeprefix("^").removesuffix("$"))
_SCHEMA_FILE: Final = re.compile(r"[a-z0-9][a-z0-9_.-]*\.v[1-9][0-9]*\.json")
# Registries with a closed built-in set: a plugin key is "<plugin_id>:<name>" (02-plugins §1).
_PREFIXED: Final = frozenset(
    map(ComponentKind, ("isolation", "check_runner", "stage_handler", "research_source"))
)
_LOCAL_NAME: Final = re.compile(r"[a-z0-9_-]+")


class PluginStatus(StrEnum):
    NOT_ALLOWED = "not_allowed"
    DATA_ONLY = "data_only"  # control plane: runtime data without importing the code
    LOADED = "loaded"
    DEGRADED = "degraded"  # loaded, a health check failed (step 9)
    INCOMPATIBLE = "incompatible"
    FAILED = "failed"


_EMPTY: Final[Mapping[Any, Any]] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class LoadedPlugin:
    manifest: PluginManifest | None  # None until imported (not allowed, data only, failed import)
    dist_name: str
    dist_version: str
    record_digest: str  # "sha256:<hex>" of RECORD, or unknown
    components: tuple[ComponentSpec, ...]  # passed steps 4-8 for the side of the process
    runtime_data: Mapping[str, RuntimeDataFiles]  # runtime_id -> data (step 2a, without import)
    diagnostics: tuple[Diagnostic, ...]
    plugin_id: str = field(kw_only=True)  # = entry point name = manifest id
    status: PluginStatus = field(kw_only=True)
    provenance: PluginProvenance = field(default=UNKNOWN_PROVENANCE, kw_only=True)
    instances: Mapping[tuple[ComponentKind, str], object] = field(default=_EMPTY, kw_only=True)
    schemas: Mapping[str, Mapping[str, JsonValue]] = field(default=_EMPTY, kw_only=True)
    settings_urn: str | None = field(default=None, kw_only=True)


@dataclass(frozen=True, slots=True)
class PluginAllowlist:
    """``plugins.*`` of the trusted instance layer (embedded: ProcessConfig; http: the control plane)."""

    allowed: tuple[str, ...] = ()
    required: frozenset[str] = frozenset()
    control_plane_allowed: frozenset[str] = frozenset()
    override_builtin: frozenset[str] = frozenset()

    @classmethod
    def from_values(cls, values: Mapping[str, JsonValue]) -> "PluginAllowlist":
        def names(key: str) -> tuple[str, ...]:
            value = values.get(key) or []
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                message = f"{key} must be a list of strings"
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, message, details={"key": key})
            return tuple(cast("list[str]", value))

        return cls(
            allowed=names("plugins.allowed"),
            required=frozenset(names("plugins.required")),
            control_plane_allowed=frozenset(names("plugins.control_plane_allowed")),
            override_builtin=frozenset(names("plugins.override_builtin")),
        )


@dataclass(frozen=True, slots=True)
class PluginSchema:
    plugin_id: str
    urn: str
    file_name: str  # "<name>.v<N>.json"
    document: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class PluginSchemas:
    """Result of settings phase 2 (step 6): the merged schema registry and the plugin section views by URN."""

    schemas: SchemaRegistry
    views: Mapping[str, type] = field(default_factory=lambda: MappingProxyType({}))


type ContextFactory = Callable[[str, type | None, SchemaRegistry], PluginContext]
type SettingsPhase2 = Callable[[Sequence[PluginSchema], Sequence[str]], PluginSchemas]


@dataclass(frozen=True, slots=True)
class _Entry:
    name: str
    value: str
    entry: EntryPoint
    dist: Distribution | None
    dist_name: str
    dist_version: str


class _Refused(Exception):
    """One plugin fails a step; it is skipped with this diagnostic."""

    def __init__(self, step: str, reason: str, message: str, code: str = LOAD_FAILED, **details: JsonValue):
        super().__init__(message)
        context: dict[str, JsonValue] = {"step": step, "reason": reason, **details}
        self.diagnostic = Diagnostic(code, message, Severity.WARNING, None, context)


def _unbound_config() -> object:
    raise CapabilityUnavailable(
        ErrorCode.CAPABILITY_UNAVAILABLE,
        "plugin configuration is not bound in this composition",
        details={"reason_code": "plugin_config_unbound"},
    )


def default_context(
    plugin_id: str, view: type | None, schemas: SchemaRegistry, config: Callable[[], object] = _unbound_config
) -> PluginContext:
    """Factory context; ``secrets`` stays unbound until a resolver limited to the section's refs exists."""
    log = get_logger("plugin." + re.sub(r"[^a-z0-9_.]", "_", plugin_id))
    return PluginContext(plugin_id, config, view, log, schemas, None, SystemClock())


def _imports_on(side: Side, plugin_id: str, allow: PluginAllowlist) -> bool:
    return side is not Side.CONTROL_PLANE or plugin_id in allow.control_plane_allowed


def _side_fits(process: Side, component: Side) -> bool:
    return process is Side.BOTH or component is Side.BOTH or component is process


def _validate_manifest(entry: _Entry, loaded: object, skm_version: str) -> PluginManifest:
    """Steps 3-4 after ``ep.load()``: the object, the compatibility, then the declaration rules."""
    if not isinstance(loaded, PluginManifest):
        raise _Refused("import", "not_a_manifest", f"{entry.value} is not a PluginManifest")
    incompatible = "PLUGIN_INCOMPATIBLE"
    if loaded.plugin_api != API_VERSION:
        message = f"plugin_api {loaded.plugin_api} != {API_VERSION}"
        raise _Refused("compat", "plugin_api", message, incompatible, plugin_api=loaded.plugin_api)
    try:
        fits = requires_skm_matches(skm_version, loaded.requires_skm)
    except ValueError:
        fits = False
    if not fits:
        message = f"skm {skm_version} is not in {loaded.requires_skm!r}"
        raise _Refused("compat", "requires_skm", message, incompatible, requires_skm=loaded.requires_skm)
    if loaded.id != entry.name or _PLUGIN_ID.fullmatch(loaded.id) is None:
        raise _Refused("import", "id", f"manifest id {loaded.id!r} must equal entry point {entry.name!r}")
    seen: set[tuple[ComponentKind, str]] = set()
    for spec in loaded.components:
        if not isinstance(spec, ComponentSpec):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise _Refused("import", "component", "components must be ComponentSpec")
        _check_key(loaded.id, spec)
        if (spec.kind, spec.key) in seen:
            raise _Refused("import", "duplicate_key", f"{spec.kind}:{spec.key} is declared twice")
        seen.add((spec.kind, spec.key))
    return loaded


def _check_key(plugin_id: str, spec: ComponentSpec) -> None:
    key, kind = spec.key, spec.kind
    if kind is ComponentKind.RUNTIME:
        if not is_runtime_id(key):
            raise _Refused("import", "key", f"{key!r} is not a runtime id")
        expected = f"skm_runtimes/{key}/capabilities.toml"
        if spec.capabilities != expected:
            raise _Refused("import", "capabilities_path", f"runtime {key}: capabilities must be {expected}")
    elif kind in _PREFIXED:
        prefix, _, name = key.partition(":")
        valid = prefix == plugin_id and _LOCAL_NAME.fullmatch(name) is not None
        if not valid or (kind is ComponentKind.ISOLATION and not is_plugin_isolation_profile(key)):
            raise _Refused("import", "key", f"{kind} key must be '{plugin_id}:<name>', got {key!r}")


def _package_file(entry: _Entry, relative: str) -> PackagePath:
    top = entry.value.split(":")[0].split(".")[0].strip()
    if relative.startswith("/") or ".." in relative.split("/"):
        raise _Refused("schemas", "schema_path", f"{relative!r} is not a package path")
    found = distribution_files(entry.dist).get(f"{top}/{relative}")
    if found is None:
        raise _Refused("schemas", "schema_missing", f"{top}/{relative} is not in RECORD")
    if _SCHEMA_FILE.fullmatch(found.name) is None:
        raise _Refused("schemas", "schema_name", f"{relative}: a schema file is named <name>.v<N>.json")
    return found


def _plugin_schemas(
    entry: _Entry, manifest: PluginManifest, schemas: SchemaRegistry
) -> tuple[dict[str, PluginSchema], str | None]:
    """Step 5: the plugin's schema documents by ``$id`` (each sound Draft 2020-12) and its section URN."""
    paths = [path for spec in manifest.components for path in spec.schemas]
    documents: dict[str, PluginSchema] = {}
    settings_urn: str | None = None
    for relative in [*paths, *([manifest.settings_schema] if manifest.settings_schema else [])]:
        path = _package_file(entry, relative)
        try:
            document: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise _Refused("schemas", "schema_json", f"{relative} is not JSON") from None
        if not isinstance(document, dict):
            raise _Refused("schemas", "schema_json", f"{relative} is not a JSON object")
        body = cast("dict[str, JsonValue]", document)
        urn = body.get("$id")
        if not isinstance(urn, str) or URN_PATTERN.fullmatch(urn) is None or urn in documents:
            raise _Refused("schemas", "schema_id", f"{relative} has no unique urn:skm:<module>:...:v<N> $id")
        if body.get("$schema") != DRAFT_2020_12 or not schemas.is_valid_schema(body):
            raise _Refused("schemas", "schema_invalid", f"{relative} is not a Draft 2020-12 schema")
        documents[urn] = PluginSchema(manifest.id, urn, path.name, MappingProxyType(body))
        if relative == manifest.settings_schema:
            settings_urn = urn
            section = body.get("x-skm-section")
            if not isinstance(section, dict) or section.get("id") != f"plugins.{manifest.id}":
                raise _Refused("settings", "section_id", f"settings section must be 'plugins.{manifest.id}'")
    return documents, settings_urn


def _check_protocol(spec: ComponentSpec, built: object) -> None:
    problem = component_problem(spec, built)
    if problem is not None:
        raise _Refused("construct", problem[0], problem[1])


def _conflict(conflicts: list[JsonValue], message: str) -> InternalError:
    details: dict[str, JsonValue] = {"reason_code": "PLUGIN_CONFLICT", "conflicts": conflicts}
    return InternalError(ErrorCode.CONFIG_REGISTRY_INVALID, message, details=details)


@dataclass(slots=True)
class _State:
    entry: _Entry
    status: PluginStatus
    diagnostics: list[Diagnostic] = field(default_factory=list[Diagnostic])
    data: dict[str, RuntimeDataFiles] = field(default_factory=dict[str, RuntimeDataFiles])
    manifest: PluginManifest | None = None
    schemas: dict[str, PluginSchema] = field(default_factory=dict[str, PluginSchema])
    settings_urn: str | None = None
    components: tuple[ComponentSpec, ...] = ()
    instances: dict[tuple[ComponentKind, str], object] = field(
        default_factory=dict[tuple[ComponentKind, str], object]
    )

    def refuse(self, refused: _Refused) -> None:
        self.diagnostics.append(refused.diagnostic)
        incompatible = refused.diagnostic.code == "PLUGIN_INCOMPATIBLE"
        self.status = PluginStatus.INCOMPATIBLE if incompatible else PluginStatus.FAILED
        self.schemas, self.settings_urn, self.components, self.instances = {}, None, (), {}

    @property
    def active(self) -> bool:
        return self.manifest is not None and self.status in (PluginStatus.LOADED, PluginStatus.DEGRADED)


def _entries(discover: Callable[[], Iterable[EntryPoint]]) -> list[_Entry]:
    found: list[_Entry] = []
    for entry in discover():
        dist = cast("Distribution | None", getattr(entry, "dist", None))
        name = UNKNOWN if dist is None else str(dist.metadata["Name"] or UNKNOWN)
        version = UNKNOWN if dist is None else str(dist.version)
        found.append(_Entry(entry.name, entry.value, entry, dist, name, version))
    return found


def _key_preflight(
    states: Sequence[_State], allow: PluginAllowlist, builtins: frozenset[tuple[ComponentKind, str]]
) -> None:
    """Step 7 (with the runtime ids of step 2a): a collision stops the bootstrap before any factory."""
    providers: dict[tuple[str, str], list[str]] = {}
    for state in states:
        keys = {("runtime", runtime_id) for runtime_id in state.data}
        if state.active and state.manifest is not None:
            keys |= {(spec.kind.value, spec.key) for spec in state.manifest.components}
        for key in sorted(keys):
            providers.setdefault(key, []).append(state.entry.name)
    builtin = {(kind.value, key) for kind, key in builtins}
    conflicts: list[JsonValue] = []
    for (kind, key), owners in sorted(providers.items()):
        name, plugins = f"{kind}:{key}", cast("list[JsonValue]", sorted(owners))
        if len(owners) > 1:
            conflicts.append({"key": name, "plugins": plugins, "with": "plugin"})
        elif (kind, key) in builtin and name not in allow.override_builtin:
            conflicts.append({"key": name, "plugins": plugins, "with": "builtin"})
    if conflicts:
        raise _conflict(conflicts, f"plugin component keys collide: {len(conflicts)} conflict(s)")


def _schema_preflight(states: Sequence[_State], schemas: SchemaRegistry) -> None:
    """Step 5: a schema ``$id`` taken by the core or by two plugins stops the bootstrap."""
    owners: dict[str, list[str]] = {}
    for state in states:
        for urn in state.schemas:
            owners.setdefault(urn, []).append(state.entry.name)
    core = schemas.urns()
    conflicts: list[JsonValue] = [
        {
            "schema": urn,
            "plugins": cast("list[JsonValue]", sorted(names)),
            "with": "core" if urn in core else "plugin",
        }
        for urn, names in sorted(owners.items())
        if urn in core or len(names) > 1
    ]
    if conflicts:
        raise _conflict(conflicts, f"plugin schema ids collide: {len(conflicts)} conflict(s)")


def _snapshot(state: _State) -> LoadedPlugin:
    return LoadedPlugin(
        manifest=state.manifest,
        dist_name=state.entry.dist_name,
        dist_version=state.entry.dist_version,
        record_digest=record_digest(state.entry.dist),
        components=state.components,
        runtime_data=MappingProxyType(dict(state.data)),
        diagnostics=tuple(state.diagnostics),
        plugin_id=state.entry.name,
        status=state.status,
        provenance=provenance(state.entry.dist),
        instances=MappingProxyType(dict(state.instances)),
        schemas=MappingProxyType({urn: item.document for urn, item in state.schemas.items()}),
        settings_urn=state.settings_urn,
    )


def _import(state: _State, skm_version: str, schemas: SchemaRegistry) -> None:
    """Steps 3-5 for one allowed plugin of a side that imports it."""
    try:
        loaded = state.entry.entry.load()
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - any import failure skips this plugin
        get_logger("bootstrap.plugins").error("plugin.import_failed", exc=exc, plugin=state.entry.name)
        state.refuse(_Refused("import", "import_error", f"importing {state.entry.value} failed"))
        return
    try:
        state.manifest = _validate_manifest(state.entry, loaded, skm_version)
        state.schemas, state.settings_urn = _plugin_schemas(state.entry, state.manifest, schemas)
    except _Refused as refused:
        state.manifest = loaded if isinstance(loaded, PluginManifest) else None
        state.refuse(refused)


def _phase2(states: Sequence[_State], phase2: SettingsPhase2) -> PluginSchemas:
    """Step 6: a plugin whose section the settings registry refuses (``plugins.<id>``) is skipped."""
    while True:
        active = [state for state in states if state.active]
        documents = [item for state in active for item in state.schemas.values()]
        try:
            return phase2(documents, [state.settings_urn for state in active if state.settings_urn])
        except InternalError as exc:
            if exc.code is not ErrorCode.CONFIG_REGISTRY_INVALID:
                raise
            problems = cast("list[dict[str, JsonValue]]", exc.details.get("problems") or [])
            sections = {str(problem.get("section") or "") for problem in problems}
            failing = [state for state in active if f"plugins.{state.entry.name}" in sections]
            if not failing:
                raise
            for state in failing:
                state.refuse(
                    _Refused("settings", "section_invalid", "the settings registry refuses the section")
                )


def _construct(state: _State, side: Side, context: ContextFactory, built: PluginSchemas) -> None:
    """Step 8 for one plugin: factories of the process side, owner Protocol and runtime identity checks."""
    manifest = cast("PluginManifest", state.manifest)
    view = None if state.settings_urn is None else built.views.get(state.settings_urn)
    chosen = tuple(spec for spec in manifest.components if _side_fits(side, spec.side))
    try:
        for spec in chosen:
            if spec.kind is ComponentKind.RUNTIME and spec.key not in state.data:
                raise _Refused("construct", "runtime_data", f"runtime {spec.key} has no valid data (step 2a)")
            try:
                instance = spec.factory(context(manifest.id, view, built.schemas))
            except Exception:  # noqa: BLE001 - a failing factory skips the plugin
                message = f"factory of {spec.kind}:{spec.key} failed"
                raise _Refused("construct", "factory_error", message) from None
            _check_protocol(spec, instance)
            state.instances[(spec.kind, spec.key)] = instance
    except _Refused as refused:
        state.refuse(refused)
        return
    state.components = chosen


def _health(state: _State) -> None:
    """Step 9: a failing ``health()`` marks the plugin degraded; its components stay registered."""
    for (kind, key), instance in state.instances.items():
        check = getattr(instance, "health", None)
        if not callable(check):
            continue
        try:
            healthy = check() is not False
        except Exception:  # noqa: BLE001 - a health failure is a finding, not a stop
            healthy = False
        if not healthy:
            state.status = PluginStatus.DEGRADED
            details: dict[str, JsonValue] = {"step": "health", "reason": "degraded"}
            message = f"{kind}:{key} reports unhealthy"
            state.diagnostics.append(
                Diagnostic(LOAD_FAILED, message, Severity.WARNING, f"{kind}:{key}", details)
            )


def _required(states: Sequence[_State], allow: PluginAllowlist, side: Side) -> None:
    """Step 10: every required plugin passed its steps for this side, else the start fails."""
    by_id = {state.entry.name: state for state in states}
    missing: list[str] = []
    statuses: list[JsonValue] = []
    for plugin_id in sorted(allow.required):
        state = by_id.get(plugin_id)
        data_side = state is not None and state.status is PluginStatus.DATA_ONLY
        if state is None or not (state.active or (data_side and not _imports_on(side, plugin_id, allow))):
            missing.append(plugin_id)
            statuses.append(
                {"plugin": plugin_id, "status": "not_installed" if state is None else state.status.value}
            )
    if missing:
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            f"required plugins did not load: {', '.join(missing)}",
            details={"reason_code": "plugin_required", "plugins": statuses},
        )


def _audit(plugins: Sequence[LoadedPlugin]) -> None:
    """Step 11: one record per plugin: version, components, RECORD digest, provenance (unknown explicit)."""
    log = get_logger("bootstrap.plugins")
    for plugin in plugins:
        event = (
            "plugin.loaded"
            if plugin.status in (PluginStatus.LOADED, PluginStatus.DEGRADED)
            else "plugin.skipped"
        )
        components = ",".join(f"{spec.kind}:{spec.key}" for spec in plugin.components)
        facts = {"plugin": plugin.plugin_id, "status": plugin.status.value, "version": plugin.dist_version}
        provenance_facts = {
            name: getattr(plugin.provenance, name) for name in ("source", "install", "dependency_lock")
        }
        log.info(
            event, **facts, components=components, record_digest=plugin.record_digest, **provenance_facts
        )


def load_plugins(  # noqa: PLR0913 - the kernel-platform §5.4 call site plus the allowlist and seams
    *,
    allowed: Sequence[str],
    required: frozenset[str],
    side: Side | Literal["control_plane", "host", "both"],
    skm_version: str,
    schemas: SchemaRegistry,
    settings_phase2: SettingsPhase2,
    discover: Callable[[], Iterable[EntryPoint]] = default_entry_points,
    control_plane_allowed: frozenset[str] = frozenset(),
    override_builtin: frozenset[str] = frozenset(),
    builtins: tuple[ComponentSpec, ...] = BUILTIN_COMPONENTS,
    context: ContextFactory = default_context,
) -> tuple[LoadedPlugin, ...]:
    """Steps 1-11 of 02-plugins §4. ``discover`` is replaced only by tests.

    ``settings_phase2(documents, section_urns)`` builds the merged schema registry and the settings registry
    phase 2 (step 6) before any factory and returns the registry with the generated section views. A key or
    schema conflict raises ``CONFIG_REGISTRY_INVALID`` (``details.reason_code = PLUGIN_CONFLICT``); a required
    plugin that did not load raises ``CAPABILITY_UNAVAILABLE`` (``details.reason_code = plugin_required``).
    """
    process = Side(side)
    allow = PluginAllowlist(tuple(allowed), required, control_plane_allowed, override_builtin)
    states = [_State(entry, PluginStatus.LOADED) for entry in _entries(discover)]  # step 1
    refused = [state for state in states if state.entry.name not in allow.allowed]
    chosen = [state for state in states if state.entry.name in allow.allowed]
    chosen.sort(key=lambda state: allow.allowed.index(state.entry.name))
    for state in refused:  # step 2: not imported, no data read
        state.status = PluginStatus.NOT_ALLOWED
        message = f"plugin {state.entry.name!r} is not in plugins.allowed"
        details: dict[str, JsonValue] = {"step": "allowlist", "reason": "not_allowed"}
        state.diagnostics.append(
            Diagnostic("PLUGIN_NOT_ALLOWED", message, Severity.INFO, state.entry.name, details)
        )
    for state in chosen:  # step 2a, both sides, without import
        state.data, problems = read_runtime_data(state.entry.dist, schemas)
        state.diagnostics.extend(problems)
    for state in chosen:  # steps 3-5
        if _imports_on(process, state.entry.name, allow):
            _import(state, skm_version, schemas)
        else:
            state.status = PluginStatus.DATA_ONLY
    _schema_preflight(chosen, schemas)
    built = _phase2(chosen, settings_phase2)  # steps 5-6
    _key_preflight(chosen, allow, builtin_keys(builtins))  # step 7
    for state in chosen:  # steps 8-9
        if state.active:
            _construct(state, process, context, built)
        if state.active:
            _health(state)
    _required(chosen, allow, process)  # step 10
    result = tuple(_snapshot(state) for state in [*chosen, *refused])
    _audit(result)  # step 11
    return result


def capability_catalog(
    plugins: Sequence[LoadedPlugin], builtin: Sequence[RuntimeDataFiles] = ()
) -> StaticCapabilityCatalog:
    """``CapabilityCatalog`` of both sides: built-in data plus step 2a data of allowed plugins (no code)."""
    items = [*builtin, *(data for plugin in plugins for data in plugin.runtime_data.values())]
    return StaticCapabilityCatalog(
        declarations={item.runtime_id: item.capabilities for item in items},
        rules={item.runtime_id: item.error_rules for item in items},
    )


def merged_schemas(base: SchemaRegistry, documents: Sequence[PluginSchema]) -> SchemaRegistry:
    """The packaged schemas plus the plugin documents step 5 admitted (their ``$id`` is new to ``base``)."""
    if not documents:
        return base
    contents = {
        **{urn: base.get(urn) for urn in base.urns()},
        **{item.urn: item.document for item in documents},
    }
    return SchemaRegistry(contents, base.registry.with_contents((d.urn, dict(d.document)) for d in documents))


class PluginSettingsView:
    """Typed view of a plugin section ``plugins.<id>`` (generated at load): resolved values by full key."""

    SCHEMA_URN: ClassVar[str]
    SECTION: ClassVar[str]
    SCHEMA_DIGEST: ClassVar[str]
    __slots__ = ("values",)

    def __init__(self, values: Mapping[str, JsonValue]) -> None:
        self.values: Mapping[str, JsonValue] = MappingProxyType(dict(values))

    @classmethod
    def from_settings(cls, values: Mapping[str, JsonValue]) -> "PluginSettingsView":
        return cls(values)


def plugin_settings_view(schemas: SchemaRegistry, urn: str) -> type[PluginSettingsView]:
    """The view of the section schema ``urn``; its own module keeps the digest the settings registry checks.

    The digest is the registry's own closure digest, so the two cannot drift.
    """
    section = cast("Mapping[str, JsonValue]", schemas.get(urn).get("x-skm-section") or {})
    members: dict[str, object] = {
        "__slots__": (),
        "__module__": "skm.bootstrap.plugins.sections." + re.sub(r"[^a-z0-9_]", "_", urn),
        "SCHEMA_URN": urn,
        "SECTION": str(section.get("id")),
        "SCHEMA_DIGEST": schema_closure_digest(schemas, (urn,)),
    }
    return cast("type[PluginSettingsView]", type("PluginSettings", (PluginSettingsView,), members))


type PluginViews = Mapping[str, type[PluginSettingsView]]  # section URN -> generated view
type SettingsBuilder = Callable[[SchemaRegistry, PluginViews], SettingsRegistry]


class ProcessPlugins:
    """Step 9a of ``build_app``: the process's plugins, phase 2 of the settings registry (mechanisms/01 §6).

    ``load`` takes the restart values of the instance layer (phase 1, core keys only); afterwards ``schemas``
    and ``settings`` are the final registries. ``bind_config`` connects ``PluginContext.config`` once a
    unit of work can be opened.
    """

    def __init__(
        self,
        *,
        schemas: SchemaRegistry,
        settings: SettingsRegistry,
        host_surface: bool,
        build_settings: SettingsBuilder,
        loader: Callable[[SettingsRegistry], ConfigLoader],
        skm_version: str = __version__,
        discover: Callable[[], Iterable[EntryPoint]] = default_entry_points,
        use_project_settings: bool = True,
    ) -> None:
        # kernel-platform §5.4: embedded CLI/worker/hook are both sides, ``skm serve`` is the control plane
        self._side = Side.BOTH if host_surface else Side.CONTROL_PLANE
        self._base, self._build, self._loader = (schemas, settings), build_settings, loader
        self._version, self._discover = skm_version, discover
        self._use_project_settings = use_project_settings
        self.schemas, self.settings = schemas, settings
        self.plugins: tuple[LoadedPlugin, ...] = ()
        self._config: Callable[[], object] = _unbound_config

    def _settings_phase2(self, documents: Sequence[PluginSchema], urns: Sequence[str]) -> PluginSchemas:
        schemas = merged_schemas(self._base[0], documents)
        views = {urn: plugin_settings_view(schemas, urn) for urn in urns}
        self.schemas = schemas
        self.settings = self._build(schemas, views) if urns else self._base[1]
        return PluginSchemas(schemas, MappingProxyType(views))

    def _read_config(self) -> object:
        return self._config()

    def _context(self, plugin_id: str, view: type | None, schemas: SchemaRegistry) -> PluginContext:
        return default_context(plugin_id, view, schemas, self._read_config)

    def load(self, values: Mapping[str, JsonValue]) -> bool:
        """Load per ``plugins.*`` of ``values``; ``True`` when plugin sections changed the settings."""
        allow = PluginAllowlist.from_values(values)
        self.plugins = load_plugins(
            allowed=allow.allowed,
            required=allow.required,
            side=self._side,
            skm_version=self._version,
            schemas=self._base[0],
            settings_phase2=self._settings_phase2,
            discover=self._discover,
            control_plane_allowed=allow.control_plane_allowed,
            override_builtin=allow.override_builtin,
            context=self._context,
        )
        return self.settings is not self._base[1]

    def start(
        self, config: ConfigLoader, store: ConfigStore, scopes: ScopeTree, host: ConfigScopeRef | None
    ) -> tuple[ProcessConfig, ConfigLoader]:
        """Capture phase 1, load the plugins, and capture again with the phase-2 loader when it changed."""
        process = config.start_process(store, scopes, host)
        if not self._use_project_settings or not self.load(process.work):
            return process, config
        config = self._loader(self.settings)
        return config.start_process(store, scopes, host), config

    def bind_config(
        self,
        units: UnitOfWorkFactory,
        config: ConfigLoader,
        *,
        surface: Surface,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        """``PluginContext.config``: the instance chain, read in a short read-only unit of work."""

        def read() -> object:
            with units(RequestMeta(new_request_id(ids), surface, None, clock.now()), readonly=True) as uow:
                return config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), None)

        self._config = read
