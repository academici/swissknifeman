"""Plugin distribution metadata (mechanisms/02-plugins §4 steps 1, 2a and 11; security S16).

Everything here reads a distribution without executing plugin code: entry point discovery is metadata only,
runtime data files are found through RECORD and read as text, and provenance comes from ``direct_url.json``
and ``INSTALLER``. The loader in ``plugins`` and the ``skm plugins`` CLI both build on it."""

import hashlib
import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from importlib.metadata import Distribution, EntryPoint, PackagePath, entry_points
from typing import Any, Final, cast

from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import Diagnostic, Severity
from skm.modules.runtimes.domain.capability import (
    RuntimeCapabilities,
    parse_capabilities,
)
from skm.modules.runtimes.domain.error_rules import ErrorRule, parse_error_rules
from skm.modules.runtimes.domain.ids import is_runtime_id
from skm.platform.schema.registry import SchemaRegistry

__all__ = [
    "CAPABILITIES_URN",
    "ENTRY_POINT_GROUP",
    "ERROR_RULES_URN",
    "LOAD_FAILED",
    "UNKNOWN",
    "UNKNOWN_PROVENANCE",
    "PluginProvenance",
    "RuntimeDataFiles",
    "default_entry_points",
    "distribution_files",
    "provenance",
    "read_runtime_data",
    "record_digest",
]

ENTRY_POINT_GROUP: Final = "skm.plugins"
UNKNOWN: Final = "unknown"
CAPABILITIES_URN: Final = "urn:skm:runtimes:capabilities:v1"
ERROR_RULES_URN: Final = "urn:skm:runtimes:error-rules:v1"
LOAD_FAILED: Final = "PLUGIN_LOAD_FAILED"
_DATA_FILE: Final = re.compile(
    r"(?P<top>[A-Za-z_][A-Za-z0-9_]*)/skm_runtimes/(?P<runtime>[^/]+)/(?P<name>capabilities|error_rules)\.toml"
)


@dataclass(frozen=True, slots=True)
class RuntimeDataFiles:
    """Step 2a: ``<top>/skm_runtimes/<runtime_id>/{capabilities,error_rules}.toml`` of a dist, parsed."""

    runtime_id: str
    capabilities: RuntimeCapabilities
    error_rules: tuple[ErrorRule, ...]
    capabilities_path: str  # RECORD path
    error_rules_path: str


@dataclass(frozen=True, slots=True)
class PluginProvenance:
    """Step 11: where the distribution came from; what cannot be known is ``unknown``, never guessed."""

    source: str  # PEP 610 direct_url.json url (with the VCS commit), else unknown
    install: str  # INSTALLER of the distribution, else unknown
    dependency_lock: str  # fingerprint of the operator-managed dependency lock, else unknown

    def unknown_fields(self) -> tuple[str, ...]:
        names = ("source", "install", "dependency_lock")
        return tuple(name for name in names if getattr(self, name) == UNKNOWN)


UNKNOWN_PROVENANCE: Final = PluginProvenance(UNKNOWN, UNKNOWN, UNKNOWN)


def default_entry_points() -> tuple[EntryPoint, ...]:
    """Step 1: entry points of group ``skm.plugins``; metadata only, nothing is imported."""
    return tuple(entry_points(group=ENTRY_POINT_GROUP))


def record_digest(dist: Distribution | None) -> str:
    text = None if dist is None else dist.read_text("RECORD")
    return UNKNOWN if text is None else "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def provenance(dist: Distribution | None) -> PluginProvenance:
    if dist is None:
        return UNKNOWN_PROVENANCE
    source = UNKNOWN
    try:
        document: object = json.loads(dist.read_text("direct_url.json") or "null")
    except ValueError:
        document = None
    if isinstance(document, dict) and isinstance(cast("dict[str, Any]", document).get("url"), str):
        info = cast("dict[str, Any]", document)
        vcs = info.get("vcs_info")
        commit = cast("dict[str, Any]", vcs).get("commit_id") if isinstance(vcs, dict) else None
        source = cast("str", info["url"]) + (f"@{commit}" if isinstance(commit, str) else "")
    installer = (dist.read_text("INSTALLER") or "").strip() or UNKNOWN
    # 02-plugins §4 step 11: no operator lock source is defined for the process yet, so it stays unknown.
    return PluginProvenance(source=source, install=installer, dependency_lock=UNKNOWN)


def distribution_files(dist: Distribution | None) -> dict[str, PackagePath]:
    return {} if dist is None else {path.as_posix(): path for path in dist.files or ()}


def _plain(value: object) -> JsonValue:
    """TOML -> JSON document: dates become ISO strings; TOML has no null, and none is invented."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in cast("dict[object, object]", value).items()}
    if isinstance(value, list):
        return [_plain(item) for item in cast("list[object]", value)]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return cast("JsonValue", value)


class _DataInvalid(ValueError):
    """A runtime data file of step 2a is unusable; only this runtime is skipped."""


def _toml(path: PackagePath, urn: str, schemas: SchemaRegistry) -> Mapping[str, JsonValue]:
    try:
        document = _plain(tomllib.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise _DataInvalid(f"{path.as_posix()}: cannot read TOML ({type(exc).__name__})") from None
    issues = schemas.validate(urn, document)
    if issues:
        raise _DataInvalid(f"{path.as_posix()}{issues[0].pointer}: {issues[0].message}")
    return cast("Mapping[str, JsonValue]", document)


def _runtime_files(
    runtime_id: str, files: Mapping[str, PackagePath], schemas: SchemaRegistry
) -> RuntimeDataFiles:
    if not is_runtime_id(runtime_id):
        raise _DataInvalid(f"{runtime_id!r} is not a runtime id")
    if set(files) != {"capabilities", "error_rules"}:
        raise _DataInvalid("capabilities.toml and error_rules.toml are both required")
    capabilities = _toml(files["capabilities"], CAPABILITIES_URN, schemas)
    error_rules = _toml(files["error_rules"], ERROR_RULES_URN, schemas)
    try:
        caps = parse_capabilities(capabilities)
        rules = parse_error_rules(error_rules)
    except (KeyError, TypeError, ValueError, SkmError) as exc:
        raise _DataInvalid(f"invalid runtime data ({type(exc).__name__})") from None
    if caps.runtime_id != runtime_id:
        raise _DataInvalid(f"capabilities.toml declares {caps.runtime_id!r} in directory {runtime_id!r}")
    if any(rule.runtime_id != runtime_id for rule in rules):
        raise _DataInvalid(f"error_rules.toml names another runtime than {runtime_id!r}")
    paths = files["capabilities"].as_posix(), files["error_rules"].as_posix()
    return RuntimeDataFiles(runtime_id, caps, rules, *paths)


def read_runtime_data(
    dist: Distribution | None, schemas: SchemaRegistry
) -> tuple[dict[str, RuntimeDataFiles], list[Diagnostic]]:
    """Step 2a without import: data files listed by RECORD, read as text and checked against their schemas."""
    groups: dict[tuple[str, str], dict[str, PackagePath]] = {}
    for name, path in sorted(distribution_files(dist).items()):
        found = _DATA_FILE.fullmatch(name)
        if found is not None:
            groups.setdefault((found["top"], found["runtime"]), {})[found["name"]] = path
    data: dict[str, RuntimeDataFiles] = {}
    problems: list[Diagnostic] = []
    for (top, runtime_id), files in sorted(groups.items()):
        try:
            if runtime_id in data:
                raise _DataInvalid(f"runtime {runtime_id!r} has data in two packages")
            data[runtime_id] = _runtime_files(runtime_id, files, schemas)
        except _DataInvalid as exc:
            message = f"runtime data of {runtime_id!r} is invalid: {exc}"
            details: dict[str, JsonValue] = {"step": "data", "reason": "runtime_data_invalid", "package": top}
            problems.append(Diagnostic(LOAD_FAILED, message, Severity.WARNING, runtime_id, details))
    return data, problems
