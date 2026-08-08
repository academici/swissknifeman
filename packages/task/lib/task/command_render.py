"""Deterministic provider projections for the immutable task command catalog."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
import shlex
from typing import Mapping

from core.provider.values import CapabilityId, CapabilityRequirement, ProviderId, SupportLevel
from core.provider.manifest import (ProviderCapabilityManifest, load_provider_manifest,
                                    provider_support_projection)
from core.provider.artifact import (ArtifactAdapterIdentity, ArtifactRenderRequest,
                                    ArtifactRenderResult, ArtifactSource, ArtifactTarget,
                                    plan_artifact_render)
from core.provider.lock import (ArtifactPlan, apply_plan, plan_artifact_lock)
from core.provider.runtime import codex_task_plugin_root_expression
from task.command_catalog import (CommandCatalog, CommandRecord, EFFORTS, MODEL_CLASSES,
                                  metadata_value)


ADAPTER_VERSION = "1.0.4"
PROVIDER_LOCK_PATH = "packages/task/adapters/codex/provider-artifacts.lock.json"
_MAPPING_KEYS = frozenset({
    "provider_id", "mapping_version", "class_selectors", "effort_selectors",
    "capability_bindings", "invocation_binding", "evidence",
})
_PLAN_NEXT_COMMANDS = {
    "exec-items": "task:plan-exec",
    "run-items": "task:plan-run",
    "audit-design": "task:plan-audit",
    "design-phase": "task:plan-design",
    "design-item": "task:plan-design",
    "audit-phase": "task:plan-audit",
    "close": "task:plan-close",
    "archive": "task:plan-close",
}
_PLAN_NEXT_TERMINALS = ("terminal", "manual", "waiting")
_CODEX_MODEL_CLASS_PROJECTIONS = {
    "haiku": "economy",
    "sonnet": "implementation",
    "opus": "frontier",
    "fable": "frontier",
}
_CODEX_WORKFLOW_CARRIER = (
    "native orchestration carrier for the referenced plan-owned workflow script")
_CODEX_RUNTIME_TOKEN = re.compile(
    r'(?P<workflow_path>Workflow\(\{scriptPath: "plans/<ID>/workflows/wf-…\.js"\}\))'
    r'|(?P<workflow>Workflow\(\{scriptPath\}\))'
    r'|(?P<model_class>\b(?:opus|sonnet|haiku|fable)\b)'
    r'|(?<![\w/])(?P<task>/task:(?P<task_id>[a-z][a-z0-9-]*))(?![\w-])'
    r'|(?<![\w/])(?P<ui>'
    r'/model[ \t]+<M>|/effort[ \t]+<E>|'
    r'/model(?![ \t]+<)|/effort(?![ \t]+<)|/clear)(?![\w/-])',
    re.IGNORECASE,
)
_CODEX_UI_PROJECTIONS = {
    "/model <m>": "select session model class <M>",
    "/effort <e>": "select session effort <E>",
    "/model": "select the session model class",
    "/effort": "select the session effort",
    "/clear": "reset the session context",
}
_CODEX_RUNTIME_FORBIDDEN = (
    ("claude-model-selector", re.compile(r"\b(?:opus|sonnet|haiku|fable)\b", re.IGNORECASE)),
    ("claude-task-invocation", re.compile(r"(?<![\w/])/task:")),
    ("claude-session-control",
     re.compile(r"(?<![\w/])/(?:model|effort|clear)(?![\w/-])")),
    ("claude-workflow-carrier", re.compile(r"Workflow\(")),
    ("claude-plugin-root", re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}")),
    ("project-relative-task-runtime", re.compile(r"PYTHONPATH=packages/task/lib")),
)


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
    capability_catalog_version: str
    class_selectors: tuple[tuple[str, tuple[str, ...]], ...]
    effort_selectors: tuple[tuple[str, tuple[str, ...]], ...]
    capability_bindings: tuple[tuple[str, str], ...]
    invocation_template: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class PlanNextCarrier:
    """Provider-neutral plan handoff; provider syntax is rendered later."""
    kind: str
    command_id: str | None
    plan_id: str | None
    arguments: tuple[str, ...] = ()
    context_kind: str = "same-session"
    item_ids: tuple[str, ...] = ()
    cold_start_scope: tuple[tuple[str, str], ...] = ()
    orchestration_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in self.allowed_kinds():
            raise ValueError("CMD_INVOCATION_INVALID: unknown Next kind")
        expected = _PLAN_NEXT_COMMANDS.get(self.kind)
        if expected is not None and self.command_id != expected:
            raise ValueError("CMD_INVOCATION_INVALID: Next kind/command mismatch")
        if self.kind in _PLAN_NEXT_TERMINALS and self.command_id is not None:
            raise ValueError("CMD_INVOCATION_INVALID: terminal Next has a command")
        plan_argument = (self.arguments[1] if self.kind == "archive" and len(self.arguments) > 1
                         else self.arguments[0] if self.arguments else None)
        if expected is not None and (not self.plan_id or plan_argument != self.plan_id):
            raise ValueError("CMD_INVOCATION_INVALID: plan identity is missing")
        if self.context_kind not in {"same-session", "cold-start"}:
            raise ValueError("CMD_INVOCATION_INVALID: unknown context kind")

    @classmethod
    def allowed_kinds(cls) -> set[str]:
        return set(_PLAN_NEXT_COMMANDS) | set(_PLAN_NEXT_TERMINALS)

    def as_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "kind": self.kind,
            "command_id": self.command_id,
            "plan_id": self.plan_id,
            "arguments": list(self.arguments),
            "context_kind": self.context_kind,
            "item_ids": list(self.item_ids),
            "cold_start_scope": [list(item) for item in self.cold_start_scope],
        }
        if self.orchestration_capabilities:
            value["orchestration_capabilities"] = list(self.orchestration_capabilities)
        return value


@dataclass(frozen=True)
class PlanProviderInvocation:
    carrier: PlanNextCarrier
    invocation: str | None
    model_selector: str | None
    effort_selector: str | None
    diagnostics: tuple[CommandDiagnostic, ...]

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)


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


@dataclass(frozen=True)
class ClaudeCommandRenderPlan:
    artifacts: tuple[RenderedCommandArtifact, ...]
    diagnostics: tuple[CommandDiagnostic, ...]

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)


def mapping_from_catalog(catalog: CommandCatalog, provider_id: str, *,
                         manifest: ProviderCapabilityManifest | None = None,
                         manifest_path: Path | None = None) -> ProviderCommandMapping:
    """Resolve provider syntax while taking support levels only from the root manifest."""
    metadata = metadata_value(catalog)
    raw = metadata.get("mappings", {}).get(provider_id)
    if not isinstance(raw, dict) or set(raw) != _MAPPING_KEYS or raw.get("provider_id") != provider_id:
        raise ValueError(f"CMD_MAPPING_MISSING: {provider_id}")
    invocation = raw["invocation_binding"]
    if not isinstance(invocation, dict) or set(invocation) != {"template"}:
        raise ValueError(f"CMD_INVOCATION_INVALID: {provider_id}")
    if manifest is None:
        manifest_path = Path(manifest_path) if manifest_path is not None else (
            Path(__file__).resolve().parents[4] / "configs/provider-capabilities.json")
        manifest = load_provider_manifest(manifest_path)
    try:
        provider = ProviderId(provider_id)
    except ValueError as error:
        raise ValueError(f"CMD_PROVIDER_DISABLED: {provider_id}") from error
    declared_ids = _capability_ids(raw["capability_bindings"])
    manifest_support = provider_support_projection(manifest, provider)
    missing = tuple(item for item in declared_ids if item not in manifest_support)
    if missing:
        raise ValueError("CMD_CAPABILITY_UNSUPPORTED: " + ",".join(missing))
    return ProviderCommandMapping(
        provider_id, _required_string(raw["mapping_version"], "mapping_version"),
        manifest.catalog_version,
        _selector_pairs(raw["class_selectors"], MODEL_CLASSES, "class_selectors"),
        _selector_pairs(raw["effort_selectors"], EFFORTS, "effort_selectors"),
        tuple((item, manifest_support[item].value) for item in declared_ids),
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


def render_claude_invocation(record: CommandRecord, arguments: str,
                             mapping: ProviderCommandMapping) -> str:
    """Render the frozen Claude slash invocation from explicit validated values."""
    if mapping.provider_id != "claude-code" or not isinstance(arguments, str):
        raise ValueError("CMD_INVOCATION_INVALID")
    if "{command_id}" not in mapping.invocation_template or "{arguments}" not in mapping.invocation_template:
        raise ValueError("CMD_INVOCATION_INVALID")
    invocation = mapping.invocation_template.format(
        command_id=record.command_id, arguments=arguments).rstrip()
    if not invocation.startswith("/task:") or invocation.startswith("//"):
        raise ValueError("CMD_INVOCATION_INVALID")
    return invocation


def parse_next_carrier(declaration: str, *, context_kind: str = "same-session",
                       item_ids: list[str] | tuple[str, ...] = (),
                       cold_start_scope: list[list[str]] | tuple[tuple[str, str], ...] = (),
                       orchestration_capabilities: tuple[str, ...] = ()) -> PlanNextCarrier:
    """Parse the canonical `<kind>: task:<id> <arguments>` Next declaration."""
    if not isinstance(declaration, str):
        raise ValueError("CMD_INVOCATION_INVALID: Next declaration is not text")
    match = re.fullmatch(r"([a-z][a-z-]*):\s*(.*)", declaration.strip())
    if not match:
        raise ValueError("CMD_INVOCATION_INVALID: malformed semantic Next")
    kind, payload = match.groups()
    if kind not in PlanNextCarrier.allowed_kinds():
        raise ValueError("CMD_INVOCATION_INVALID: unknown Next kind")
    if kind in _PLAN_NEXT_TERMINALS:
        if kind == "terminal" and payload.strip().lower() != "план закрыт":
            raise ValueError("CMD_INVOCATION_INVALID: malformed terminal Next")
        if kind == "manual" and not re.fullmatch(
                r"(economy|implementation|frontier)/(low|medium|high|xhigh)"
                r"(?:\s+P\d+\.\d+)?",
                payload.strip()):
            raise ValueError("CMD_INVOCATION_INVALID: malformed manual Next")
        if kind == "waiting":
            condition, separator, target = payload.partition("→")
            if not separator or not condition.strip() or not target.strip():
                raise ValueError("CMD_INVOCATION_INVALID: malformed waiting Next")
            nested = parse_next_carrier(target.strip(), context_kind=context_kind)
            if nested.kind not in _PLAN_NEXT_COMMANDS:
                raise ValueError("CMD_INVOCATION_INVALID: waiting target is not runnable")
        try:
            arguments = tuple(shlex.split(payload))
        except ValueError as error:
            raise ValueError("CMD_INVOCATION_INVALID: malformed Next arguments") from error
        return PlanNextCarrier(
            kind, None, None, arguments, context_kind, tuple(item_ids),
            tuple(tuple(item) for item in cold_start_scope),
            tuple(orchestration_capabilities))
    command_id, separator, raw_arguments = payload.partition(" ")
    if not separator:
        raise ValueError("CMD_INVOCATION_INVALID: plan arguments are missing")
    try:
        arguments = tuple(shlex.split(raw_arguments or ""))
    except ValueError as error:
        raise ValueError("CMD_INVOCATION_INVALID: malformed Next arguments") from error
    scope = tuple(tuple(item) for item in cold_start_scope)
    if any(len(item) != 2 or not all(isinstance(part, str) for part in item)
           for item in scope):
        raise ValueError("CMD_INVOCATION_INVALID: malformed cold-start scope")
    plan_id = (arguments[1] if kind == "archive" and len(arguments) > 1
               else arguments[0] if arguments else None)
    return PlanNextCarrier(
        kind, command_id, plan_id, arguments, context_kind,
        tuple(item_ids), scope, tuple(orchestration_capabilities))


def plan_provider_invocation(
        catalog: CommandCatalog, carrier: PlanNextCarrier,
        mapping: ProviderCommandMapping, capability_support: Mapping[str, str] | None = None, *,
        observed_class: str, observed_effort: str,
        inherited_minimum: tuple[str, str] | None = None) -> PlanProviderInvocation:
    """Gate a semantic plan carrier, then render exactly one provider invocation."""
    capability_support = (dict(mapping.capability_bindings) if capability_support is None
                          else capability_support)
    record = catalog.by_id().get(carrier.command_id or "")
    if record is None or record.kind != "plan-protocol":
        diagnostic = _diag_raw(
            "CMD_ID_UNKNOWN", carrier.command_id or "", "/command_id",
            {"kind": "plan-protocol"}, {"command_id": carrier.command_id}, mapping,
            "semantic plan command is unknown")
        return PlanProviderInvocation(carrier, None, None, None, (diagnostic,))

    diagnostics = list(_mapping_diagnostics(record, mapping))
    required_class, required_effort = record.routing.model_class, record.routing.effort
    if record.routing.mode == "inherited-plan":
        if (not inherited_minimum or len(inherited_minimum) != 2
                or inherited_minimum[0] not in MODEL_CLASSES
                or inherited_minimum[1] not in EFFORTS):
            diagnostics.append(_diag(
                "CMD_MAPPING_MISSING", record, "/routing/inherited-minimum",
                {"model_class": MODEL_CLASSES, "effort": EFFORTS},
                {"minimum": inherited_minimum}, mapping,
                "inherited plan minimum is missing or unknown"))
        else:
            required_class, required_effort = inherited_minimum

    if required_class in MODEL_CLASSES and required_effort in EFFORTS:
        diagnostics.extend(_route_mapping_diagnostics(
            record, mapping, required_class, required_effort,
            observed_class, observed_effort))
        if observed_class in MODEL_CLASSES and observed_effort in EFFORTS:
            required = (MODEL_CLASSES.index(required_class), EFFORTS.index(required_effort))
            observed = (MODEL_CLASSES.index(observed_class), EFFORTS.index(observed_effort))
            if observed[0] < required[0] or observed[1] < required[1]:
                diagnostics.append(_diag(
                    "CMD_ROUTE_UNDERSHOOT", record, "/routing",
                    {"model_class": required_class, "effort": required_effort},
                    {"model_class": observed_class, "effort": observed_effort}, mapping,
                    "observed route is below the plan minimum"))
            elif observed[0] > required[0] or observed[1] > required[1]:
                diagnostics.append(_diag(
                    "CMD_ROUTE_OVERSHOOT", record, "/routing",
                    {"model_class": required_class, "effort": required_effort},
                    {"model_class": observed_class, "effort": observed_effort}, mapping,
                    "observed route exceeds the plan minimum", severity="info"))

    for requirement in record.capability_requirements:
        level = capability_support.get(requirement.capability_id)
        if level not in requirement.accepted_levels:
            diagnostics.append(_diag(
                "CMD_CAPABILITY_UNSUPPORTED", record,
                f"/capabilities/{requirement.capability_id}",
                {"accepted_levels": requirement.accepted_levels}, {"support_level": level},
                mapping, "required command capability is missing or unsupported"))
    for capability_id in carrier.orchestration_capabilities:
        level = capability_support.get(capability_id)
        if level not in {"native", "adapted"}:
            diagnostics.append(_diag(
                "CMD_CAPABILITY_UNSUPPORTED", record,
                f"/orchestration/capabilities/{capability_id}",
                {"accepted_levels": ("adapted", "native")}, {"support_level": level},
                mapping, "required orchestration capability is missing or unsupported"))

    diagnostics = _dedupe_diagnostics(diagnostics)
    if any(item.severity == "error" for item in diagnostics):
        return PlanProviderInvocation(carrier, None, None, None, tuple(diagnostics))

    arguments = " ".join(shlex.quote(value) for value in carrier.arguments)
    if mapping.provider_id == "claude-code":
        invocation = render_claude_invocation(record, arguments, mapping)
    elif mapping.provider_id == "codex":
        invocation = render_invocation(record, arguments, mapping)
    else:
        diagnostic = _diag(
            "CMD_PROVIDER_DISABLED", record, "/provider_id",
            {"provider_id": ("claude-code", "codex")},
            {"provider_id": mapping.provider_id}, mapping,
            "provider projection is not enabled")
        return PlanProviderInvocation(carrier, None, None, None,
                                      tuple(diagnostics + [diagnostic]))
    return PlanProviderInvocation(
        carrier, invocation, dict(mapping.class_selectors)[observed_class][0],
        dict(mapping.effort_selectors)[observed_effort][0], tuple(diagnostics))


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
        capability_support: Mapping[str, str] | None = None, *,
        observed_routes: Mapping[str, tuple[str, str]] | None = None) -> CodexCommandRenderPlan:
    """Return a complete no-write Codex render plan or only pre-write diagnostics."""
    diagnostics: list[CommandDiagnostic] = []
    if mapping.provider_id != "codex":
        return CodexCommandRenderPlan((), (_diag_raw(
            "CMD_PROVIDER_DISABLED", "task:catalog", "/provider_id", {"provider_id": "codex"},
            {"provider_id": mapping.provider_id}, mapping, "Codex projection is not selected"),))
    capability_support = (dict(mapping.capability_bindings) if capability_support is None
                          else capability_support)
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

    projected_runtime: dict[str, bytes] = {}
    projected_descriptions: dict[str, str] = {}
    for record in catalog.records:
        content = catalog.content_for(record.command_id)
        try:
            runtime = _codex_runtime_bytes(record, content)
            description = _project_codex_runtime_tokens(_frontmatter_description(content))
        except (UnicodeDecodeError, ValueError) as error:
            diagnostics.append(_diag(
                "CMD_SOURCE_DRIFT", record, "/source/runtime-projection",
                {"canonical_frontmatter": "UTF-8 fenced metadata"},
                {"error": str(error)}, mapping,
                "canonical command cannot be projected into a Codex runtime"))
            continue
        unsafe = tuple(sorted(set(
            _codex_runtime_unsafe_literals(runtime.decode("utf-8"))
            + _codex_runtime_unsafe_literals(description))))
        if unsafe:
            diagnostics.append(_diag(
                "CMD_INVOCATION_INVALID", record, "/source/runtime-projection",
                {"unsafe_execution_literals": ()},
                {"unsafe_execution_literals": unsafe}, mapping,
                "Codex runtime projection retains provider-specific execution literals"))
            continue
        projected_runtime[record.command_id] = runtime
        projected_descriptions[record.command_id] = description
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
                             catalog, mapping.capability_catalog_version,
                             {"publication_unit": "task", "kind": "plugin"}))

    for record in catalog.records:
        name = record.command_id.removeprefix("task:")
        base = f"packages/task/adapters/codex/skills/task-{name}"
        description = projected_descriptions[record.command_id]
        wrapper = _wrapper_bytes(record, description, mapping)
        capabilities = tuple(item.capability_id for item in record.capability_requirements)
        results.append(_artifact(f"task.codex.{name.replace('-', '.')}.skill", f"{base}/SKILL.md",
                                 wrapper, (_source(record),), capabilities, catalog,
                                 mapping.capability_catalog_version,
                                 {"command_id": record.command_id, "kind": "skill-wrapper"}))
        results.append(_artifact(f"task.codex.{name.replace('-', '.')}.runtime", f"{base}/command.md",
                                 projected_runtime[record.command_id], (_source(record),),
                                 capabilities, catalog,
                                 mapping.capability_catalog_version,
                                 {"command_id": record.command_id,
                                  "kind": "runtime-projection"}))

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
                             catalog, mapping.capability_catalog_version,
                             {"publication_unit": "task", "kind": "publication-lock"}))
    return CodexCommandRenderPlan(tuple(sorted(results, key=lambda item: item.target.path)),
                                  tuple(diagnostics))


def plan_claude_command_render(
        catalog: CommandCatalog, mapping: ProviderCommandMapping,
        capability_support: Mapping[str, str] | None = None, *,
        plugin_bytes: bytes) -> ClaudeCommandRenderPlan:
    """Return the complete no-write Claude projection over canonical command bytes."""
    diagnostics: list[CommandDiagnostic] = []
    if mapping.provider_id != "claude-code":
        return ClaudeCommandRenderPlan((), (_diag_raw(
            "CMD_PROVIDER_DISABLED", "task:catalog", "/provider_id",
            {"provider_id": "claude-code"}, {"provider_id": mapping.provider_id},
            mapping, "Claude projection is not selected"),))
    capability_support = (dict(mapping.capability_bindings) if capability_support is None
                          else capability_support)
    if not isinstance(capability_support, Mapping):
        raise TypeError("capability_support must be a mapping")
    if not isinstance(plugin_bytes, bytes):
        raise TypeError("plugin_bytes must be bytes")

    diagnostics.extend(_claude_plugin_diagnostics(catalog, mapping, plugin_bytes))
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
        diagnostics.extend(_claude_frontmatter_diagnostics(
            record, catalog.content_for(record.command_id), mapping))
    diagnostics = _dedupe_diagnostics(diagnostics)
    if any(item.severity == "error" for item in diagnostics):
        return ClaudeCommandRenderPlan((), tuple(diagnostics))

    artifacts = [_claude_artifact(
        "task.claude.plugin", "packages/task/.claude-plugin/plugin.json", plugin_bytes)]
    for record in catalog.records:
        name = record.command_id.removeprefix("task:").replace("-", ".")
        artifacts.append(_claude_artifact(
            f"task.claude.{name}.command", record.source.path,
            catalog.content_for(record.command_id), source_hash=record.source.content_hash))
    return ClaudeCommandRenderPlan(
        tuple(sorted(artifacts, key=lambda item: item.path)), tuple(diagnostics))


def apply_claude_command_plan(root: Path, render_plan: ClaudeCommandRenderPlan, *,
                              check: bool) -> tuple[str, ...]:
    """Check or write one already-validated Claude render plan under an explicit root."""
    if not render_plan.ok or not render_plan.artifacts:
        raise ValueError("render diagnostics must be resolved before check/write")
    root = Path(root).resolve()
    drift: list[str] = []
    targets: list[tuple[RenderedCommandArtifact, Path]] = []
    for artifact in render_plan.artifacts:
        pure = PurePosixPath(artifact.path)
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError("CMD_INVOCATION_INVALID: unsafe Claude target")
        target = root.joinpath(*pure.parts)
        targets.append((artifact, target))
        try:
            current = target.read_bytes()
        except OSError:
            current = None
        if current != artifact.managed_bytes:
            drift.append(artifact.path)
    if check:
        return tuple(drift)
    for artifact, target in targets:
        if artifact.path not in drift:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact.managed_bytes)
    return tuple(drift)


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


def build_provider_command_parity_report(
        catalog: CommandCatalog, claude_plan: ClaudeCommandRenderPlan,
        codex_plan: CodexCommandRenderPlan,
        mappings: Mapping[str, ProviderCommandMapping], *,
        expected_command_ids: tuple[str, ...],
        next_carriers: tuple[PlanNextCarrier, ...] = ()) -> dict[str, object]:
    """Build a deterministic report from an independently validated expected set.

    This is a conformance reporter, not another renderer: it consumes the two named
    provider plans and refuses any inventory/projection delta before producing rows.
    """
    if set(mappings) != {"claude-code", "codex"}:
        raise ValueError("CMD_PROVIDER_DISABLED: both provider mappings are required")
    if not claude_plan.ok or not codex_plan.ok:
        raise ValueError("CMD_SOURCE_DRIFT: provider render plans must be clean")

    catalog_ids = tuple(record.command_id for record in catalog.records)
    semantic_duplicates = _duplicates(catalog_ids)
    expected_set, catalog_set = set(expected_command_ids), set(catalog_ids)
    semantic_delta = {
        "missing": sorted(expected_set - catalog_set),
        "extra": sorted(catalog_set - expected_set),
        "duplicates": semantic_duplicates,
    }

    expected_claude = {"packages/task/.claude-plugin/plugin.json"}
    expected_codex = {
        "packages/task/.codex-plugin/plugin.json",
        "packages/task/adapters/codex/publication-lock.json",
    }
    for command_id in expected_command_ids:
        name = command_id.removeprefix("task:")
        expected_claude.add(f"packages/task/commands/{name}.md")
        expected_codex.add(
            f"packages/task/adapters/codex/skills/task-{name}/SKILL.md")
        expected_codex.add(
            f"packages/task/adapters/codex/skills/task-{name}/command.md")

    claude_paths = tuple(artifact.path for artifact in claude_plan.artifacts)
    codex_paths = tuple(artifact.path for artifact in codex_plan.artifacts)
    projections = {
        "claude-code": _projection_delta(expected_claude, claude_paths),
        "codex": _projection_delta(expected_codex, codex_paths),
    }
    if (any(semantic_delta.values())
            or any(any(delta.values()) for delta in projections.values())):
        raise ValueError("CMD_CATALOG_MISMATCH: semantic/provider projection delta")

    claude_artifacts = {item.path: item for item in claude_plan.artifacts}
    codex_artifacts = {item.path: item for item in codex_plan.artifacts}
    commands = []
    for record in catalog.records:
        route = record.routing
        name = record.command_id.removeprefix("task:")
        providers = {}
        for provider_id in ("claude-code", "codex"):
            mapping = mappings[provider_id]
            if route.mode == "fixed":
                selector = dict(mapping.class_selectors)[route.model_class][0]
                effort = dict(mapping.effort_selectors)[route.effort][0]
            else:
                selector = effort = "routing-required"
            invocation = (render_claude_invocation(record, "<arguments>", mapping)
                          if provider_id == "claude-code"
                          else render_invocation(record, "<arguments>", mapping))
            if provider_id == "claude-code":
                artifact = claude_artifacts[record.source.path]
                artifact_paths = [artifact.path]
                rendered_hashes = [artifact.rendered_hash]
            else:
                paths = [
                    f"packages/task/adapters/codex/skills/task-{name}/SKILL.md",
                    f"packages/task/adapters/codex/skills/task-{name}/command.md",
                ]
                artifacts = [codex_artifacts[path] for path in paths]
                artifact_paths = paths
                rendered_hashes = [artifact.rendered_hash for artifact in artifacts]
            providers[provider_id] = {
                "artifacts": artifact_paths,
                "rendered_hashes": rendered_hashes,
                "invocation": invocation,
                "model_selector": selector,
                "effort_selector": effort,
                "diagnostics": [],
            }
        commands.append({
            "command_id": record.command_id,
            "kind": record.kind,
            "source": record.source.path,
            "source_hash": record.source.content_hash,
            "routing": {
                "mode": route.mode,
                "model_class": route.model_class,
                "effort": route.effort,
            },
            "capabilities": [item.capability_id for item in record.capability_requirements],
            "providers": providers,
        })

    next_rows = []
    for carrier in next_carriers:
        providers = {}
        for provider_id in ("claude-code", "codex"):
            if carrier.command_id is None:
                providers[provider_id] = {
                    "invocation": None, "model_selector": None,
                    "effort_selector": None, "diagnostics": [],
                }
                continue
            record = catalog.by_id()[carrier.command_id]
            inherited = (("implementation", "high")
                         if record.routing.mode == "inherited-plan" else None)
            observed_class = (inherited[0] if inherited else record.routing.model_class)
            observed_effort = (inherited[1] if inherited else record.routing.effort)
            mapping = mappings[provider_id]
            rendered = plan_provider_invocation(
                catalog, carrier, mapping,
                observed_class=observed_class, observed_effort=observed_effort,
                inherited_minimum=inherited)
            providers[provider_id] = {
                "invocation": rendered.invocation,
                "model_selector": rendered.model_selector,
                "effort_selector": rendered.effort_selector,
                "diagnostics": [item.code for item in rendered.diagnostics],
            }
        next_rows.append({"carrier": carrier.as_dict(), "providers": providers})

    return {
        "contract_version": catalog.contract_version,
        "catalog_version": catalog.catalog_version,
        "inventory": semantic_delta,
        "projections": projections,
        "commands": commands,
        "next_forms": next_rows,
    }


def render_provider_commands_reference(report: Mapping[str, object]) -> bytes:
    """Render the operator reference from the already validated parity report."""
    lines = [
        "# Provider task commands",
        "",
        "Generated from the validated provider-command parity report. Do not edit manually.",
        "",
        f"Contract: `{report['contract_version']}` · Catalog: `{report['catalog_version']}`",
        "",
        "## Command matrix",
        "",
        "| Semantic ID | Canonical source / SHA-256 | Neutral route | Capabilities | Claude Code | Codex |",
        "|:--|:--|:--|:--|:--|:--|",
    ]
    for command in report["commands"]:
        route = command["routing"]
        neutral = f"{route['mode']} · {route['model_class']}/{route['effort']}"
        capabilities = "<br>".join(f"`{item}`" for item in command["capabilities"])
        source = f"`{command['source']}`<br>`{command['source_hash']}`"
        provider_cells = []
        for provider_id in ("claude-code", "codex"):
            projection = command["providers"][provider_id]
            provider_cells.append(
                f"`{projection['invocation']}`<br>"
                f"`{projection['model_selector']}/{projection['effort_selector']}`")
        lines.append(
            f"| `{command['command_id']}` | {source} | `{neutral}` | {capabilities} | "
            f"{provider_cells[0]} | {provider_cells[1]} |")

    lines.extend([
        "",
        "## Semantic Next forms",
        "",
        "| Kind | Semantic carrier | Claude Code | Codex | Diagnostics |",
        "|:--|:--|:--|:--|:--|",
    ])
    for row in report["next_forms"]:
        carrier = row["carrier"]
        claude = row["providers"]["claude-code"]
        codex = row["providers"]["codex"]
        diagnostics = sorted(set(claude["diagnostics"] + codex["diagnostics"]))
        lines.append(
            f"| `{carrier['kind']}` | `{json.dumps(carrier, ensure_ascii=False, sort_keys=True)}` "
            f"| `{claude['invocation'] or '—'}` | `{codex['invocation'] or '—'}` "
            f"| `{', '.join(diagnostics) or '—'}` |")

    lines.extend([
        "",
        "## Conformance result",
        "",
        "- Semantic inventory: `missing=[]`, `extra=[]`, `duplicates=[]`.",
        "- Claude Code projection: `missing=[]`, `extra=[]`, `duplicates=[]`.",
        "- Codex projection: `missing=[]`, `extra=[]`, `duplicates=[]`.",
        "- Unknown, ambiguous, unsupported, undershoot, invalid invocation and source drift are fail-closed before write.",
        "",
    ])
    return "\n".join(lines).encode("utf-8")


def _projection_delta(expected: set[str], actual: tuple[str, ...]) -> dict[str, list[str]]:
    actual_set = set(actual)
    return {
        "missing": sorted(expected - actual_set),
        "extra": sorted(actual_set - expected),
        "duplicates": _duplicates(actual),
    }


def _duplicates(values: tuple[str, ...]) -> list[str]:
    return sorted(value for value in set(values) if values.count(value) > 1)


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


def _route_mapping_diagnostics(
        record: CommandRecord, mapping: ProviderCommandMapping,
        required_class: str, required_effort: str,
        observed_class: str, observed_effort: str) -> tuple[CommandDiagnostic, ...]:
    """Require unique mappings for both plan minima and the observed session route."""
    diagnostics: list[CommandDiagnostic] = []
    classes, efforts = dict(mapping.class_selectors), dict(mapping.effort_selectors)
    axes = (
        ("/routing/model_class", "model_class", required_class, classes),
        ("/routing/effort", "effort", required_effort, efforts),
        ("/routing/observed/model_class", "model_class", observed_class, classes),
        ("/routing/observed/effort", "effort", observed_effort, efforts),
    )
    for path, label, value, selectors in axes:
        if value not in selectors:
            diagnostics.append(_diag(
                "CMD_MAPPING_MISSING", record, path,
                {f"known_{label}": tuple(selectors)}, {label: value}, mapping,
                "semantic route value is unknown"))
            continue
        values = selectors[value]
        if not values:
            diagnostics.append(_diag(
                "CMD_MAPPING_MISSING", record, path,
                {"semantic_value": value}, {"selectors": values}, mapping,
                "provider selector mapping is missing"))
        elif len(values) != 1:
            diagnostics.append(_diag(
                "CMD_MAPPING_AMBIGUOUS", record, path,
                {"selector_count": 1}, {"selectors": values}, mapping,
                "provider selector mapping is ambiguous"))
    return tuple(diagnostics)


def _artifact(artifact_id: str, target: str, rendered: bytes,
              sources: tuple[ArtifactSource, ...], capabilities: tuple[str, ...],
              catalog: CommandCatalog, capability_catalog_version: str,
              semantic_parameters: Mapping[str, object]) -> ArtifactRenderResult:
    requirements = tuple(CapabilityRequirement(CapabilityId(item),
                                                (SupportLevel.ADAPTED, SupportLevel.NATIVE))
                         for item in sorted(set(capabilities)))
    parameters = dict(semantic_parameters)
    parameters["plugin_version"] = catalog.plugin_version
    request = ArtifactRenderRequest(
        artifact_id, sources, ArtifactTarget(target, ("whole-file", ())),
        ArtifactAdapterIdentity("task.codex-command", ADAPTER_VERSION, ProviderId.CODEX,
                                capability_catalog_version, requirements),
        (), parameters, lambda _request: rendered,
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
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
'''
    return text.encode("utf-8")


def _codex_runtime_bytes(record: CommandRecord, content: bytes) -> bytes:
    """Project one canonical Claude command into a finite, provider-safe Codex runtime."""
    text = content.decode("utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError("canonical frontmatter opening fence is missing")
    closing = next(
        (index for index, line in enumerate(lines[1:], start=1)
         if line.rstrip("\r\n") == "---"),
        None,
    )
    if closing is None:
        raise ValueError("canonical frontmatter closing fence is missing")
    body = "".join(lines[closing + 1:])
    projected = _project_codex_runtime_tokens(body)
    provenance = (
        "<!-- Generated Codex runtime projection; do not edit as source.\n"
        f"Canonical source: {record.source.path}\n"
        f"Canonical SHA-256: {record.source.content_hash}\n"
        f"Adapter: task.codex-command/{ADAPTER_VERSION}\n"
        "-->\n"
    )
    return (provenance + projected).encode("utf-8")


def _project_codex_runtime_tokens(text: str) -> str:
    """Project the finite standalone Claude token set without touching slash notation."""
    task_root = codex_task_plugin_root_expression()
    text = text.replace('PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/lib"',
                        f'PYTHONPATH="{task_root}/lib"')
    text = text.replace('python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-lint.py"',
                        f'python3 "{task_root}/scripts/plan-lint.py"')
    def replacement(match: re.Match[str]) -> str:
        if match.group("workflow_path") or match.group("workflow"):
            return _CODEX_WORKFLOW_CARRIER
        if match.group("model_class"):
            return _CODEX_MODEL_CLASS_PROJECTIONS[match.group(0).lower()]
        if match.group("task"):
            return "$ task:" + match.group("task_id")
        if match.group("ui"):
            return _CODEX_UI_PROJECTIONS[match.group("ui").lower()]
        raise AssertionError("unreachable Codex runtime token")

    return _CODEX_RUNTIME_TOKEN.sub(replacement, text)


def _codex_runtime_unsafe_literals(runtime: str) -> tuple[str, ...]:
    return tuple(
        label for label, pattern in _CODEX_RUNTIME_FORBIDDEN
        if pattern.search(runtime)
    )


def _claude_artifact(artifact_id: str, path: str, managed_bytes: bytes, *,
                     source_hash: str | None = None) -> RenderedCommandArtifact:
    digest = "sha256:" + sha256(managed_bytes).hexdigest()
    return RenderedCommandArtifact(path, managed_bytes, source_hash or digest, digest, artifact_id)


def _claude_plugin_diagnostics(catalog: CommandCatalog, mapping: ProviderCommandMapping,
                               plugin_bytes: bytes) -> tuple[CommandDiagnostic, ...]:
    try:
        value = json.loads(plugin_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return (_diag_raw(
            "CMD_SOURCE_DRIFT", "task:catalog", "/plugin", {"valid_json": True},
            {"error": str(error)}, mapping, "Claude plugin descriptor is malformed"),)
    expected = {"name": "task", "version": catalog.plugin_version,
                "commands": ["./commands"]}
    observed = ({key: value.get(key) for key in expected} if isinstance(value, dict)
                else {"type": type(value).__name__})
    if observed != expected:
        return (_diag_raw(
            "CMD_SOURCE_DRIFT", "task:catalog", "/plugin/registration", expected,
            observed, mapping, "Claude plugin identity, version or command registration drifted"),)
    return ()


def _claude_frontmatter_diagnostics(
        record: CommandRecord, content: bytes,
        mapping: ProviderCommandMapping) -> tuple[CommandDiagnostic, ...]:
    try:
        fields = _frontmatter_fields(content)
    except ValueError as error:
        return (_diag("CMD_SOURCE_DRIFT", record, "/frontmatter", {"valid": True},
                      {"error": str(error)}, mapping,
                      "Claude command frontmatter is malformed"),)

    if record.routing.mode == "inherited-plan":
        observed = {key: fields.get(key) for key in ("model", "effort") if key in fields}
        if observed:
            return (_diag("CMD_SOURCE_DRIFT", record, "/frontmatter/routing", {}, observed,
                          mapping, "inherited-plan Claude command must not pin model or effort"),)
        return ()

    classes, efforts = dict(mapping.class_selectors), dict(mapping.effort_selectors)
    class_values = classes.get(record.routing.model_class, ())
    effort_values = efforts.get(record.routing.effort, ())
    if len(class_values) != 1 or len(effort_values) != 1:
        return ()  # the mapping diagnostic is authoritative; avoid a derivative drift error
    expected = {
        "model": class_values[0],
        "effort": effort_values[0],
    }
    observed = {key: fields.get(key) for key in expected}
    if observed != expected:
        return (_diag("CMD_SOURCE_DRIFT", record, "/frontmatter/routing", expected, observed,
                      mapping, "Claude frontmatter does not match the frozen neutral route"),)
    return ()


def _frontmatter_fields(content: bytes) -> dict[str, str]:
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("command source is not UTF-8") from error
    if not lines or lines[0] != "---":
        raise ValueError("opening delimiter is missing")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("closing delimiter is missing") from error
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            raise ValueError("frontmatter field is malformed")
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if not key or key in fields:
            raise ValueError("frontmatter field is empty or duplicated")
        fields[key] = value
    return fields


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


def _capability_ids(raw: object) -> tuple[str, ...]:
    """Validate the frozen P4 carrier but discard its legacy support-level values."""
    return tuple(key for key, _level in _capability_pairs(raw))


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
