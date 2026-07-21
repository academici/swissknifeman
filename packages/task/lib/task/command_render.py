"""Deterministic Codex projection for the immutable task command catalog."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Mapping

from core.provider import CapabilityId, CapabilityRequirement, ProviderId, SupportLevel
from core.provider_artifact import (ArtifactAdapterIdentity, ArtifactRenderRequest,
                                    ArtifactRenderResult, ArtifactSource, ArtifactTarget,
                                    plan_artifact_render)
from core.provider_lock import (ArtifactPlan, apply_plan, plan_artifact_lock)
from task.command_catalog import (CommandCatalog, CommandRecord, EFFORTS, MODEL_CLASSES,
                                  metadata_value)


ADAPTER_VERSION = "1.0.0"
PROVIDER_LOCK_PATH = "packages/task/adapters/codex/provider-artifacts.lock.json"
_MAPPING_KEYS = frozenset({
    "provider_id", "mapping_version", "class_selectors", "effort_selectors",
    "capability_bindings", "invocation_binding", "evidence",
})


@dataclass(frozen=True)
class CommandDiagnostic:
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


@dataclass(frozen=True)
class ProviderCommandMapping:
    provider_id: str
    mapping_version: str
    class_selectors: tuple[tuple[str, tuple[str, ...]], ...]
    effort_selectors: tuple[tuple[str, tuple[str, ...]], ...]
    capability_bindings: tuple[tuple[str, str], ...]
    invocation_template: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class RenderedCommandArtifact:
    path: str
    managed_bytes: bytes
    source_hash: str
    rendered_hash: str
    artifact_id: str


@dataclass(frozen=True)
class CodexCommandRenderPlan:
    results: tuple[ArtifactRenderResult, ...]
    diagnostics: tuple[CommandDiagnostic, ...]

    @property
    def artifacts(self) -> tuple[RenderedCommandArtifact, ...]:
        return tuple(RenderedCommandArtifact(
            result.target.path, result.managed_bytes, result.provenance.source_hash,
            result.provenance.rendered_hash, result.provenance.artifact_id,
        ) for result in self.results)

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)


def mapping_from_catalog(catalog: CommandCatalog, provider_id: str) -> ProviderCommandMapping:
    """Resolve one explicit provider mapping captured by the catalog."""
    metadata = metadata_value(catalog)
    raw = metadata.get("mappings", {}).get(provider_id)
    if not isinstance(raw, dict) or set(raw) != _MAPPING_KEYS or raw.get("provider_id") != provider_id:
        raise ValueError(f"CMD_MAPPING_MISSING: {provider_id}")
    invocation = raw["invocation_binding"]
    if not isinstance(invocation, dict) or set(invocation) != {"template"}:
        raise ValueError(f"CMD_INVOCATION_INVALID: {provider_id}")
    return ProviderCommandMapping(
        provider_id, _required_string(raw["mapping_version"], "mapping_version"),
        _selector_pairs(raw["class_selectors"], MODEL_CLASSES, "class_selectors"),
        _selector_pairs(raw["effort_selectors"], EFFORTS, "effort_selectors"),
        _capability_pairs(raw["capability_bindings"]),
        _required_string(invocation["template"], "invocation template"),
        tuple(_evidence_label(item) for item in _required_list(raw["evidence"], "evidence")),
    )


def render_invocation(record: CommandRecord, arguments: str,
                      mapping: ProviderCommandMapping) -> str:
    """Render native invocation only from explicit validated values."""
    if mapping.provider_id != "codex" or not isinstance(arguments, str):
        raise ValueError("CMD_INVOCATION_INVALID")
    if "{command_id}" not in mapping.invocation_template or "{arguments}" not in mapping.invocation_template:
        raise ValueError("CMD_INVOCATION_INVALID")
    invocation = mapping.invocation_template.format(command_id=record.command_id, arguments=arguments).rstrip()
    if not invocation.startswith("$ ") or invocation.startswith("$task:"):
        raise ValueError("CMD_INVOCATION_INVALID")
    return invocation


def validate_route(record: CommandRecord, observed_class: str, observed_effort: str,
                   mapping: ProviderCommandMapping) -> tuple[CommandDiagnostic, ...]:
    """Validate both neutral axes before an invocation or write."""
    diagnostics = list(_mapping_diagnostics(record, mapping))
    if record.routing.mode == "inherited-plan":
        return tuple(diagnostics)
    if observed_class not in MODEL_CLASSES or observed_effort not in EFFORTS:
        diagnostics.append(_diag("CMD_MAPPING_MISSING", record, "/routing/observed",
                                 {"known_classes": MODEL_CLASSES, "known_efforts": EFFORTS},
                                 {"model_class": observed_class, "effort": observed_effort},
                                 mapping, "observed route is not mapped"))
        return tuple(diagnostics)
    required_class = MODEL_CLASSES.index(record.routing.model_class)
    required_effort = EFFORTS.index(record.routing.effort)
    observed = (MODEL_CLASSES.index(observed_class), EFFORTS.index(observed_effort))
    if observed[0] < required_class or observed[1] < required_effort:
        diagnostics.append(_diag("CMD_ROUTE_UNDERSHOOT", record, "/routing",
                                 {"model_class": record.routing.model_class,
                                  "effort": record.routing.effort},
                                 {"model_class": observed_class, "effort": observed_effort},
                                 mapping, "observed route is below the command minimum"))
    elif observed[0] > required_class or observed[1] > required_effort:
        diagnostics.append(_diag("CMD_ROUTE_OVERSHOOT", record, "/routing",
                                 {"model_class": record.routing.model_class,
                                  "effort": record.routing.effort},
                                 {"model_class": observed_class, "effort": observed_effort},
                                 mapping, "observed route exceeds the command minimum",
                                 severity="info"))
    return tuple(diagnostics)


def plan_codex_command_render(
        catalog: CommandCatalog, mapping: ProviderCommandMapping,
        capability_support: Mapping[str, str], *,
        observed_routes: Mapping[str, tuple[str, str]] | None = None) -> CodexCommandRenderPlan:
    """Return a complete no-write Codex render plan or only pre-write diagnostics."""
    diagnostics: list[CommandDiagnostic] = []
    if mapping.provider_id != "codex":
        return CodexCommandRenderPlan((), (_diag_raw(
            "CMD_PROVIDER_DISABLED", "task:catalog", "/provider_id", {"provider_id": "codex"},
            {"provider_id": mapping.provider_id}, mapping, "Codex projection is not selected"),))
    if not isinstance(capability_support, Mapping):
        raise TypeError("capability_support must be a mapping")
    observed_routes = observed_routes or {}
    for record in catalog.records:
        diagnostics.extend(_mapping_diagnostics(record, mapping))
        for requirement in record.capability_requirements:
            level = capability_support.get(requirement.capability_id)
            if level not in requirement.accepted_levels:
                diagnostics.append(_diag(
                    "CMD_CAPABILITY_UNSUPPORTED", record,
                    f"/capabilities/{requirement.capability_id}",
                    {"accepted_levels": requirement.accepted_levels}, {"support_level": level},
                    mapping, "required command capability is missing or unsupported"))
        if record.command_id in observed_routes:
            observed = observed_routes[record.command_id]
            if not isinstance(observed, tuple) or len(observed) != 2:
                diagnostics.append(_diag("CMD_MAPPING_MISSING", record, "/routing/observed",
                                         {}, {"route": observed}, mapping,
                                         "observed route must be a model-class/effort pair"))
            else:
                diagnostics.extend(validate_route(record, observed[0], observed[1], mapping))
    diagnostics = _dedupe_diagnostics(diagnostics)
    if any(item.severity == "error" for item in diagnostics):
        return CodexCommandRenderPlan((), tuple(diagnostics))

    results: list[ArtifactRenderResult] = []
    plugin = {
        "name": "task", "version": catalog.plugin_version,
        "description": "Provider-neutral task commands and executable plan protocol for Codex",
        "skills": ["./adapters/codex/skills"],
    }
    all_sources = tuple(_source(record) for record in catalog.records)
    results.append(_artifact("task.codex.plugin", "packages/task/.codex-plugin/plugin.json",
                             _json_bytes(plugin), all_sources, ("skills.repository",),
                             catalog, {"publication_unit": "task", "kind": "plugin"}))

    for record in catalog.records:
        name = record.command_id.removeprefix("task:")
        base = f"packages/task/adapters/codex/skills/task-{name}"
        content = catalog.content_for(record.command_id)
        description = _frontmatter_description(content)
        wrapper = _wrapper_bytes(record, description, mapping)
        capabilities = tuple(item.capability_id for item in record.capability_requirements)
        results.append(_artifact(f"task.codex.{name.replace('-', '.')}.skill", f"{base}/SKILL.md",
                                 wrapper, (_source(record),), capabilities, catalog,
                                 {"command_id": record.command_id, "kind": "skill-wrapper"}))
        results.append(_artifact(f"task.codex.{name.replace('-', '.')}.runtime", f"{base}/command.md",
                                 content, (_source(record),), capabilities, catalog,
                                 {"command_id": record.command_id, "kind": "runtime-copy"}))

    records = [{
        "path": result.target.path,
        "source_hash": result.provenance.source_hash,
        "rendered_hash": result.provenance.rendered_hash,
        "artifact_id": result.provenance.artifact_id,
    } for result in sorted(results, key=lambda item: item.target.path)]
    publication_lock = {
        "contract_version": "1.0.0", "publication_unit": "task",
        "version": catalog.plugin_version, "artifacts": records,
    }
    results.append(_artifact("task.codex.publication-lock",
                             "packages/task/adapters/codex/publication-lock.json",
                             _json_bytes(publication_lock), all_sources, ("skills.repository",),
                             catalog, {"publication_unit": "task", "kind": "publication-lock"}))
    return CodexCommandRenderPlan(tuple(sorted(results, key=lambda item: item.target.path)),
                                  tuple(diagnostics))


def plan_codex_command_apply(root: Path, render_plan: CodexCommandRenderPlan, *,
                             lock_bytes: bytes | None,
                             repair_artifact_ids: tuple[str, ...] = ()) -> ArtifactPlan:
    """Classify one complete render plan through the frozen P2 lock engine."""
    if not render_plan.ok or not render_plan.results:
        raise ValueError("render diagnostics must be resolved before write planning")
    planned = plan_artifact_lock(Path(root), render_plan.results, lock_bytes=lock_bytes,
                                 repair_artifact_ids=repair_artifact_ids)
    return ArtifactPlan(planned.actions, planned.next_lock, PROVIDER_LOCK_PATH)


def apply_codex_command_plan(root: Path, artifact_plan: ArtifactPlan) -> ArtifactPlan:
    """Apply an already-classified P2 plan under one explicit root."""
    return apply_plan(Path(root), artifact_plan)


def _mapping_diagnostics(record: CommandRecord,
                         mapping: ProviderCommandMapping) -> tuple[CommandDiagnostic, ...]:
    diagnostics = []
    classes, efforts = dict(mapping.class_selectors), dict(mapping.effort_selectors)
    if record.routing.mode == "fixed":
        for path, required, values in (("/routing/model_class", record.routing.model_class,
                                        classes.get(record.routing.model_class, ())),
                                       ("/routing/effort", record.routing.effort,
                                        efforts.get(record.routing.effort, ()))):
            if not values:
                diagnostics.append(_diag("CMD_MAPPING_MISSING", record, path,
                                         {"semantic_value": required}, {"selectors": values}, mapping,
                                         "provider selector mapping is missing"))
            elif len(values) != 1:
                diagnostics.append(_diag("CMD_MAPPING_AMBIGUOUS", record, path,
                                         {"selector_count": 1}, {"selectors": values}, mapping,
                                         "provider selector mapping is ambiguous"))
    return tuple(diagnostics)


def _artifact(artifact_id: str, target: str, rendered: bytes,
              sources: tuple[ArtifactSource, ...], capabilities: tuple[str, ...],
              catalog: CommandCatalog, semantic_parameters: Mapping[str, object]) -> ArtifactRenderResult:
    requirements = tuple(CapabilityRequirement(CapabilityId(item),
                                                (SupportLevel.ADAPTED, SupportLevel.NATIVE))
                         for item in sorted(set(capabilities)))
    request = ArtifactRenderRequest(
        artifact_id, sources, ArtifactTarget(target, ("whole-file", ())),
        ArtifactAdapterIdentity("task.codex-command", ADAPTER_VERSION, ProviderId.CODEX,
                                catalog.catalog_version, requirements),
        (), semantic_parameters, lambda _request: rendered,
    )
    return plan_artifact_render(request)


def _source(record: CommandRecord) -> ArtifactSource:
    return ArtifactSource(record.source.source_id, record.source.path, record.source.content_hash)


def _wrapper_bytes(record: CommandRecord, description: str,
                   mapping: ProviderCommandMapping) -> bytes:
    name = record.command_id.removeprefix("task:")
    source_hash = record.source.content_hash
    invocation = render_invocation(record, "<arguments>", mapping)
    if record.routing.mode == "fixed":
        selector = dict(mapping.class_selectors)[record.routing.model_class][0]
        effort = dict(mapping.effort_selectors)[record.routing.effort][0]
        route = f"{record.routing.model_class}/{record.routing.effort} -> {selector}/{effort}"
    else:
        route = "inherited-plan -> validate the current session against the selected plan item"
    text = f'''---
name: task-{name}
description: {json.dumps(description, ensure_ascii=False)}
---

# Task {name}

Generated Codex adapter for semantic command `{record.command_id}`.

- Invocation: `{invocation}`
- Routing: `{route}`
- Canonical source: `{record.source.path}`
- Canonical SHA-256: `{source_hash}`
- Runtime snapshot: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
'''
    return text.encode("utf-8")


def _frontmatter_description(content: bytes) -> str:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("CMD_SOURCE_DRIFT: command source is not UTF-8") from error
    match = re.search(r"^description:\s*(.+?)\s*$", text, re.MULTILINE)
    if not match:
        raise ValueError("CMD_SOURCE_DRIFT: command description is missing")
    value = match.group(1)
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("CMD_SOURCE_DRIFT: command description is malformed") from error
        return _required_string(parsed, "description")
    return _required_string(value, "description")


def _diag(code: str, record: CommandRecord, path: str, required: Mapping[str, object],
          observed: Mapping[str, object], mapping: ProviderCommandMapping, message: str,
          *, severity: str = "error") -> CommandDiagnostic:
    return _diag_raw(code, record.command_id, path, required, observed, mapping, message,
                     severity=severity)


def _diag_raw(code: str, command_id: str, path: str, required: Mapping[str, object],
              observed: Mapping[str, object], mapping: ProviderCommandMapping, message: str,
              *, severity: str = "error") -> CommandDiagnostic:
    return CommandDiagnostic(severity, code, mapping.provider_id, command_id, path,
                             tuple(sorted(required.items())), tuple(sorted(observed.items())),
                             mapping.evidence, message,
                             "repair the explicit mapping/capability/route input before writing")


def _dedupe_diagnostics(values: list[CommandDiagnostic]) -> list[CommandDiagnostic]:
    seen, result = set(), []
    for value in values:
        key = (value.severity, value.code, value.command_id, value.path,
               repr(value.required), repr(value.observed))
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _selector_pairs(raw: object, expected: tuple[str, ...], label: str
                    ) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not isinstance(raw, dict) or set(raw) != set(expected):
        raise ValueError(f"CMD_MAPPING_MISSING: {label}")
    result = []
    for key in expected:
        values = raw[key]
        if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
            raise ValueError(f"CMD_MAPPING_MISSING: {label}/{key}")
        result.append((key, tuple(values)))
    return tuple(result)


def _capability_pairs(raw: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw, dict) or not all(isinstance(key, str) and value in {"native", "adapted", "unsupported"}
                                            for key, value in raw.items()):
        raise ValueError("CMD_CAPABILITY_UNSUPPORTED: capability_bindings")
    return tuple(sorted(raw.items()))


def _evidence_label(raw: object) -> str:
    if not isinstance(raw, dict) or set(raw) != {"source", "verified_at", "scope", "claim"}:
        raise ValueError("CMD_MAPPING_MISSING: evidence")
    return " | ".join(_required_string(raw[key], key)
                      for key in ("source", "verified_at", "scope", "claim"))


def _required_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    return value


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
