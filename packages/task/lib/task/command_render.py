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
        mapping: ProviderCommandMapping, capability_support: Mapping[str, str], *,
        observed_class: str, observed_effort: str,
        inherited_minimum: tuple[str, str] | None = None) -> PlanProviderInvocation:
    """Gate a semantic plan carrier, then render exactly one provider invocation."""
    record = catalog.by_id().get(carrier.command_id or "")
    if record is None or record.kind != "plan-protocol":
        diagnostic = _diag_raw(
            "CMD_COMMAND_UNKNOWN", carrier.command_id or "", "/command_id",
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


def plan_claude_command_render(
        catalog: CommandCatalog, mapping: ProviderCommandMapping,
        capability_support: Mapping[str, str], *,
        plugin_bytes: bytes) -> ClaudeCommandRenderPlan:
    """Return the complete no-write Claude projection over canonical command bytes."""
    diagnostics: list[CommandDiagnostic] = []
    if mapping.provider_id != "claude-code":
        return ClaudeCommandRenderPlan((), (_diag_raw(
            "CMD_PROVIDER_DISABLED", "task:catalog", "/provider_id",
            {"provider_id": "claude-code"}, {"provider_id": mapping.provider_id},
            mapping, "Claude projection is not selected"),))
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
