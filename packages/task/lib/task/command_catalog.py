"""Immutable semantic task-command catalog for provider renderers.

The caller supplies the canonical command directory and routing carrier explicitly.
This module performs no cwd, home, environment, import-registry, or output discovery.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Mapping


CONTRACT_VERSION = "1.0.0"
MODEL_CLASSES = ("economy", "implementation", "frontier")
EFFORTS = ("low", "medium", "high", "xhigh")
COMMAND_KINDS = ("intent", "workflow-authoring", "plan-protocol")
ROUTING_MODES = ("fixed", "inherited-plan")
_MAPPING_KEYS = frozenset({
    "provider_id", "mapping_version", "class_selectors", "effort_selectors",
    "capability_bindings", "invocation_binding", "model_inventory", "evidence",
})
_INVENTORY_ENTRY_KEYS = frozenset({"id", "roles"})
_COMMAND_ID_RE = re.compile(r"^task:[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMAND_KEYS = frozenset({
    "command_id", "kind", "source", "argument_contract", "output_contract",
    "routing", "capability_requirements", "plan_semantics", "aliases",
})
_ROOT_KEYS = frozenset({
    "contract_version", "catalog_version", "plugin_version", "commands", "mappings",
})


def package_root() -> Path:
    """Task package root in both source checkout and installed plugin layouts."""
    return Path(__file__).resolve().parents[2]


def package_command_path(command_id: str) -> Path:
    """Resolve a canonical command without assuming the monorepo directory shape."""
    if not isinstance(command_id, str) or not _COMMAND_ID_RE.fullmatch(command_id):
        raise ValueError("CMD_ID_UNKNOWN")
    path = package_root() / "commands" / f"{command_id.removeprefix('task:')}.md"
    if not path.is_file():
        raise ValueError(f"CMD_SOURCE_MISSING: {path}")
    return path


@dataclass(frozen=True, order=True)
class CommandSource:
    source_id: str
    path: str
    content_hash: str


@dataclass(frozen=True, order=True)
class CommandCapability:
    capability_id: str
    accepted_levels: tuple[str, ...] = ("adapted", "native")


@dataclass(frozen=True)
class CommandRouting:
    mode: str
    model_class: str
    effort: str


@dataclass(frozen=True)
class CommandRecord:
    contract_version: str
    command_id: str
    kind: str
    source: CommandSource
    aliases: tuple[str, ...]
    argument_contract: str
    output_contract: str
    routing: CommandRouting
    capability_requirements: tuple[CommandCapability, ...]
    plan_semantics: tuple[str, ...]
    projections: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CommandCatalog:
    contract_version: str
    catalog_version: str
    plugin_version: str
    records: tuple[CommandRecord, ...]
    source_contents: tuple[tuple[str, bytes], ...]
    routing_metadata: tuple[tuple[str, object], ...]

    def by_id(self) -> Mapping[str, CommandRecord]:
        return {record.command_id: record for record in self.records}

    def content_for(self, command_id: str) -> bytes:
        try:
            return dict(self.source_contents)[command_id]
        except KeyError as error:
            raise KeyError(f"unknown command content: {command_id}") from error


@dataclass(frozen=True, order=True)
class CatalogDiagnostic:
    severity: str
    code: str
    provider_id: str
    command_id: str
    path: str
    required: tuple[tuple[str, object], ...]
    observed: tuple[tuple[str, object], ...]
    provenance: tuple[str, ...]
    message: str
    next_action: str


class CommandCatalogError(ValueError):
    def __init__(self, diagnostic: CatalogDiagnostic):
        super().__init__(f"{diagnostic.code}: {diagnostic.message}")
        self.diagnostic = diagnostic


def load_routing_metadata(path: Path) -> dict[str, object]:
    """Load the exact task routing carrier from an explicit path."""
    path = Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _catalog_error("CMD_VERSION_UNSUPPORTED", "/", {}, {"path": str(path)},
                             f"routing carrier is unreadable: {error}") from error
    if not isinstance(value, dict) or set(value) != _ROOT_KEYS:
        raise _catalog_error("CMD_VERSION_UNSUPPORTED", "/", {"keys": sorted(_ROOT_KEYS)},
                             {"keys": sorted(value) if isinstance(value, dict) else type(value).__name__},
                             "routing carrier has an unsupported shape")
    if value.get("contract_version") != CONTRACT_VERSION:
        raise _catalog_error("CMD_VERSION_UNSUPPORTED", "/contract_version",
                             {"version": CONTRACT_VERSION}, {"version": value.get("contract_version")},
                             "unsupported command-routing contract version")
    for key in ("catalog_version", "plugin_version"):
        if not isinstance(value.get(key), str) or not re.fullmatch(r"\d+\.\d+\.\d+", value[key]):
            raise _catalog_error("CMD_VERSION_UNSUPPORTED", f"/{key}", {"semver": True},
                                 {key: value.get(key)}, f"{key} must be SemVer")
    if not isinstance(value.get("commands"), list) or not isinstance(value.get("mappings"), dict):
        raise _catalog_error("CMD_CATALOG_MISMATCH", "/", {}, {},
                             "commands must be a list and mappings must be an object")
    return value


def build_command_catalog(command_root: Path, routing_path: Path) -> CommandCatalog:
    """Build and exact-set validate the immutable catalog from explicit inputs."""
    command_root = Path(command_root)
    metadata = load_routing_metadata(routing_path)
    try:
        files = tuple(sorted(path for path in command_root.iterdir()
                             if path.is_file() and path.suffix == ".md"))
    except OSError as error:
        raise _catalog_error("CMD_CATALOG_MISMATCH", "/commands", {},
                             {"path": str(command_root)}, f"command root is unreadable: {error}") from error

    entries = metadata["commands"]
    configured_ids = []
    configured_names = []
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict) or set(raw) != _COMMAND_KEYS:
            raise _catalog_error("CMD_CATALOG_MISMATCH", f"/commands/{index}",
                                 {"keys": sorted(_COMMAND_KEYS)},
                                 {"keys": sorted(raw) if isinstance(raw, dict) else type(raw).__name__},
                                 "command record has an unsupported shape")
        command_id = raw.get("command_id")
        source = raw.get("source")
        if not isinstance(command_id, str) or not _COMMAND_ID_RE.fullmatch(command_id):
            raise _catalog_error("CMD_ID_UNKNOWN", f"/commands/{index}/command_id", {},
                                 {"command_id": command_id}, "invalid semantic command ID")
        if not isinstance(source, str):
            raise _catalog_error("CMD_CATALOG_MISMATCH", f"/commands/{index}/source", {},
                                 {"source": source}, "source must be a project-relative path")
        pure = PurePosixPath(source)
        expected_name = command_id.removeprefix("task:") + ".md"
        if pure.is_absolute() or ".." in pure.parts or pure.name != expected_name:
            raise _catalog_error("CMD_CATALOG_MISMATCH", f"/commands/{index}/source",
                                 {"basename": expected_name}, {"source": source},
                                 "command source and stable ID disagree")
        configured_ids.append(command_id)
        configured_names.append(pure.name)

    duplicates = sorted(item for item in set(configured_ids) if configured_ids.count(item) > 1)
    source_duplicates = sorted(item for item in set(configured_names) if configured_names.count(item) > 1)
    actual_names = {path.name for path in files}
    expected_names = set(configured_names)
    missing, extra = sorted(expected_names - actual_names), sorted(actual_names - expected_names)
    if duplicates or source_duplicates or missing or extra:
        raise _catalog_error("CMD_CATALOG_MISMATCH", "/commands",
                             {"missing": [], "extra": [], "duplicates": []},
                             {"missing": missing, "extra": extra,
                              "duplicates": sorted(set(duplicates + source_duplicates))},
                             "canonical command inventory and routing metadata differ")

    mapping_versions = []
    for provider_id, raw in sorted(metadata["mappings"].items()):
        if not isinstance(raw, dict) or raw.get("provider_id") != provider_id:
            raise _catalog_error("CMD_MAPPING_MISSING", f"/mappings/{provider_id}", {},
                                 {"mapping": raw}, "provider mapping identity is missing or inconsistent")
        if set(raw) != _MAPPING_KEYS:
            raise _catalog_error("CMD_MAPPING_MISSING", f"/mappings/{provider_id}",
                                 {"keys": sorted(_MAPPING_KEYS)},
                                 {"keys": sorted(raw)}, "provider mapping has an unsupported shape")
        version = raw.get("mapping_version")
        if not isinstance(version, str):
            raise _catalog_error("CMD_MAPPING_MISSING", f"/mappings/{provider_id}/mapping_version",
                                 {}, {"mapping_version": version}, "mapping version is missing")
        _validate_model_inventory(raw.get("model_inventory"), provider_id)
        mapping_versions.append((provider_id, version))

    records, contents = [], []
    by_name = {path.name: path for path in files}
    for index, raw in enumerate(entries):
        command_id = raw["command_id"]
        source_path = raw["source"]
        content = by_name[PurePosixPath(source_path).name].read_bytes()
        routing = _routing(raw["routing"], command_id, index)
        capabilities = _capabilities(raw["capability_requirements"], command_id, index)
        aliases = _string_tuple(raw["aliases"], f"/commands/{index}/aliases")
        if aliases:
            raise _catalog_error("CMD_ID_AMBIGUOUS", f"/commands/{index}/aliases", {"aliases": []},
                                 {"aliases": aliases}, "v1 aliases must be empty")
        kind = raw["kind"]
        if kind not in COMMAND_KINDS:
            raise _catalog_error("CMD_CATALOG_MISMATCH", f"/commands/{index}/kind",
                                 {"kinds": COMMAND_KINDS}, {"kind": kind}, "unknown command kind")
        records.append(CommandRecord(
            CONTRACT_VERSION, command_id, kind,
            CommandSource(f"task.command.{command_id.removeprefix('task:').replace('-', '.')}",
                          source_path, "sha256:" + sha256(content).hexdigest()),
            aliases, _required_string(raw["argument_contract"], "argument_contract"),
            _required_string(raw["output_contract"], "output_contract"), routing,
            capabilities, _string_tuple(raw["plan_semantics"], f"/commands/{index}/plan_semantics"),
            tuple(mapping_versions),
        ))
        contents.append((command_id, content))

    frozen_metadata = tuple((key, _freeze(value)) for key, value in sorted(metadata.items()))
    return CommandCatalog(CONTRACT_VERSION, metadata["catalog_version"], metadata["plugin_version"],
                          tuple(records), tuple(contents), frozen_metadata)


def metadata_value(catalog: CommandCatalog) -> dict[str, object]:
    """Return a detached JSON-compatible copy of the captured routing carrier."""
    return _thaw(dict(catalog.routing_metadata))


def _validate_model_inventory(raw: object, provider_id: str) -> None:
    if not isinstance(raw, dict):
        raise _catalog_error("CMD_MAPPING_MISSING", f"/mappings/{provider_id}/model_inventory",
                             {}, {"model_inventory": raw}, "model inventory is missing")
    required = {"verified_at", "source", "entries"}
    if not required <= set(raw):
        raise _catalog_error("CMD_MAPPING_MISSING", f"/mappings/{provider_id}/model_inventory",
                             {"keys": sorted(required)}, {"keys": sorted(raw)},
                             "model inventory has an unsupported shape")
    if not isinstance(raw["verified_at"], str) or not isinstance(raw["source"], str):
        raise _catalog_error("CMD_MAPPING_MISSING", f"/mappings/{provider_id}/model_inventory",
                             {}, {}, "model inventory provenance is invalid")
    entries = raw["entries"]
    if not isinstance(entries, list) or not entries:
        raise _catalog_error("CMD_MAPPING_MISSING", f"/mappings/{provider_id}/model_inventory/entries",
                             {}, {"entries": entries}, "model inventory entries are missing")
    seen = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not _INVENTORY_ENTRY_KEYS <= set(entry):
            raise _catalog_error("CMD_MAPPING_MISSING",
                                 f"/mappings/{provider_id}/model_inventory/entries/{index}",
                                 {}, {"entry": entry}, "model inventory entry is invalid")
        model_id = entry["id"]
        roles = entry["roles"]
        if not isinstance(model_id, str) or not model_id or model_id in seen:
            raise _catalog_error("CMD_MAPPING_MISSING",
                                 f"/mappings/{provider_id}/model_inventory/entries/{index}/id",
                                 {}, {"id": model_id}, "model inventory id is invalid or duplicated")
        seen.add(model_id)
        if not isinstance(roles, list) or not roles or not all(isinstance(item, str) and item for item in roles):
            raise _catalog_error("CMD_MAPPING_MISSING",
                                 f"/mappings/{provider_id}/model_inventory/entries/{index}/roles",
                                 {}, {"roles": roles}, "model inventory roles are invalid")
    auto_mode = raw.get("auto_mode")
    if auto_mode is not None:
        if not isinstance(auto_mode, dict) or set(auto_mode) != {"allowed_for", "forbidden_for"}:
            raise _catalog_error("CMD_MAPPING_MISSING",
                                 f"/mappings/{provider_id}/model_inventory/auto_mode",
                                 {}, {"auto_mode": auto_mode}, "auto_mode shape is invalid")
        for key in ("allowed_for", "forbidden_for"):
            values = auto_mode[key]
            if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
                raise _catalog_error("CMD_MAPPING_MISSING",
                                     f"/mappings/{provider_id}/model_inventory/auto_mode/{key}",
                                     {}, {key: values}, "auto_mode list is invalid")

def _routing(raw: object, command_id: str, index: int) -> CommandRouting:
    if not isinstance(raw, dict) or set(raw) != {"mode", "model_class", "effort"}:
        raise _catalog_error("CMD_CATALOG_MISMATCH", f"/commands/{index}/routing", {},
                             {"routing": raw}, "routing has an unsupported shape", command_id)
    mode, model_class, effort = raw["mode"], raw["model_class"], raw["effort"]
    if mode not in ROUTING_MODES:
        raise _catalog_error("CMD_CATALOG_MISMATCH", f"/commands/{index}/routing/mode",
                             {"modes": ROUTING_MODES}, {"mode": mode}, "unknown routing mode", command_id)
    if mode == "inherited-plan":
        if (model_class, effort) != ("routing-required", "routing-required"):
            raise _catalog_error("CMD_CATALOG_MISMATCH", f"/commands/{index}/routing", {}, raw,
                                 "inherited-plan route must use routing-required axes", command_id)
    elif model_class not in MODEL_CLASSES or effort not in EFFORTS:
        raise _catalog_error("CMD_CATALOG_MISMATCH", f"/commands/{index}/routing", {}, raw,
                             "fixed route uses an unknown model class or effort", command_id)
    return CommandRouting(mode, model_class, effort)


def _capabilities(raw: object, command_id: str, index: int) -> tuple[CommandCapability, ...]:
    values = _string_tuple(raw, f"/commands/{index}/capability_requirements")
    if len(set(values)) != len(values) or any(not _CAPABILITY_RE.fullmatch(value) for value in values):
        raise _catalog_error("CMD_CAPABILITY_UNSUPPORTED",
                             f"/commands/{index}/capability_requirements", {}, {"values": values},
                             "capability requirements are invalid or duplicated", command_id)
    return tuple(CommandCapability(value) for value in values)


def _string_tuple(raw: object, path: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise _catalog_error("CMD_CATALOG_MISMATCH", path, {"type": "array<string>"},
                             {"value": raw}, "expected an array of strings")
    return tuple(raw)


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _catalog_error(code: str, path: str, required: Mapping[str, object],
                   observed: Mapping[str, object], message: str,
                   command_id: str = "task:catalog") -> CommandCatalogError:
    diagnostic = CatalogDiagnostic("error", code, "catalog", command_id, path,
                                   tuple(sorted(required.items())), tuple(sorted(observed.items())), (),
                                   message, "repair the canonical catalog inputs before rendering")
    return CommandCatalogError(diagnostic)


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return tuple((key, _freeze(item)) for key, item in sorted(value.items()))
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, dict):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        if value and all(isinstance(item, tuple) and len(item) == 2 and
                         isinstance(item[0], str) for item in value):
            return {key: _thaw(item) for key, item in value}
        return [_thaw(item) for item in value]
    return value
