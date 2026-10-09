"""Deterministic provider projections for the immutable planner command catalog."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
import shlex
from typing import Mapping

from core.provider.values import ProviderId
from core.provider.manifest import (ProviderCapabilityManifest, default_manifest_path,
                                    load_provider_manifest, provider_support_projection)
from core.provider.projection import ProjectionCatalog, load_projection_catalog, projection_spec
from core.provider.artifact import (ArtifactAdapterIdentity, ArtifactRenderResult,
                                    ArtifactSource)
from core.provider.lock import (ArtifactPlan, apply_plan, plan_artifact_lock)
from core.provider.runtime import codex_task_plugin_root_expression
from aicore.content.commands import (frontmatter_description, runtime_provenance, split_command,
                                     strict_frontmatter_fields)
from aicore.content.publication import (capability_requirements, codex_plugin_manifest,
                                        manifest_bytes, publication_lock, render_whole_file)
from planner import COMMAND_NAMESPACE, LEGACY_NAMESPACE, MODULE_ID
from planner.commands_compat import normalize_command_id, warn_deprecated
from planner.command_catalog import (CommandCatalog, CommandRecord, EFFORTS, MODEL_CLASSES,
                                     metadata_value)


ADAPTER_VERSION = "1.0.18"
_COMMAND_PREFIX = f"{COMMAND_NAMESPACE}:"
_MODULE_DIR = f"packages/{MODULE_ID}"
PROVIDER_LOCK_PATH = f"{_MODULE_DIR}/adapters/codex/provider-artifacts.lock.json"
PROVIDER_LOCK_OWNER = f"{MODULE_ID}.codex"
_MAPPING_KEYS = frozenset({
    "provider_id", "mapping_version", "class_selectors", "effort_selectors",
    "capability_bindings", "invocation_binding", "model_inventory", "evidence",
})
_PROVIDER_ORDER = tuple(item.value for item in ProviderId)
_PROVIDER_IDS = frozenset(_PROVIDER_ORDER)
_PLAN_NEXT_COMMANDS = {
    "exec-items": f"{COMMAND_NAMESPACE}:plan-run",  # legacy kind spelling, same command
    "run-items": f"{COMMAND_NAMESPACE}:plan-run",
    "audit-design": f"{COMMAND_NAMESPACE}:plan-audit",
    "design-phase": f"{COMMAND_NAMESPACE}:plan-design",
    "design-item": f"{COMMAND_NAMESPACE}:plan-design",
    "design-finish": f"{COMMAND_NAMESPACE}:plan-design",
    "design-roadmap": f"{COMMAND_NAMESPACE}:plan-design",
    "audit-phase": f"{COMMAND_NAMESPACE}:plan-audit",
    "close": f"{COMMAND_NAMESPACE}:plan-close",
    "archive": f"{COMMAND_NAMESPACE}:plan-close",
}
_PLAN_NEXT_TERMINALS = ("terminal", "manual", "waiting")
# Readers accept the legacy command spelling; carriers always hold the canonical one.
_LEGACY_COMMAND_IDS = {f"{COMMAND_NAMESPACE}:plan-exec": f"{COMMAND_NAMESPACE}:plan-run"}
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
    r'|(?<![\w/])(?P<command>/' + re.escape(_COMMAND_PREFIX) + r'(?P<command_id>[a-z][a-z0-9-]*))(?![\w-])'
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
    ("claude-slash-invocation", re.compile(r"(?<![\w/])/" + re.escape(_COMMAND_PREFIX))),
    ("claude-session-control",
     re.compile(r"(?<![\w/\[])/(?:model|effort|clear)(?![\w/-])")),
    ("claude-workflow-carrier", re.compile(r"Workflow\(")),
    ("claude-plugin-root", re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}")),
    ("project-relative-runtime", re.compile(r"PYTHONPATH=" + re.escape(_MODULE_DIR) + r"/lib")),
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
        if self.context_kind not in {
                "same-session", "cold-start", "continue-root",
                "isolated-child-return", "cold-start-root"}:
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

    def codex_launch(self, cwd: str | Path) -> str:
        """Render a complete fresh-process Codex launch for this validated carrier."""
        if not self.ok or not self.invocation or not self.model_selector or not self.effort_selector:
            raise ValueError("CMD_INVOCATION_INVALID")
        return render_codex_launch(
            self.invocation, self.model_selector, self.effort_selector, cwd)

    def cursor_launch(self, cwd: str | Path) -> str:
        """Render a complete fresh-process Cursor launch for this validated carrier."""
        if not self.ok or not self.invocation or not self.model_selector:
            raise ValueError("CMD_INVOCATION_INVALID")
        return render_cursor_launch(self.invocation, self.model_selector, cwd)


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


@dataclass(frozen=True)
class CursorCommandRenderPlan:
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
            default_manifest_path())
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
    if not invocation.startswith("$ ") or invocation.startswith(f"${_COMMAND_PREFIX}"):
        raise ValueError("CMD_INVOCATION_INVALID")
    return invocation


def render_cursor_invocation(record: CommandRecord, arguments: str,
                             mapping: ProviderCommandMapping) -> str:
    """Render the frozen Cursor semantic invocation from explicit validated values."""
    if mapping.provider_id != "cursor" or not isinstance(arguments, str):
        raise ValueError("CMD_INVOCATION_INVALID")
    if "{command_id}" not in mapping.invocation_template or "{arguments}" not in mapping.invocation_template:
        raise ValueError("CMD_INVOCATION_INVALID")
    invocation = mapping.invocation_template.format(
        command_id=record.command_id, arguments=arguments).rstrip()
    if not invocation.startswith(_COMMAND_PREFIX):
        raise ValueError("CMD_INVOCATION_INVALID")
    return invocation


def render_grok_launch(invocation: str, model_selector: str, cwd: str | Path) -> str:
    """Render a shell-safe Grok launch. ``agent`` on PATH is the same binary as ``grok``."""
    if (not isinstance(invocation, str) or not invocation.startswith(f"/{_COMMAND_PREFIX}")
            or not isinstance(model_selector, str) or not model_selector
            or not isinstance(cwd, (str, Path)) or not str(cwd)):
        raise ValueError("CMD_INVOCATION_INVALID")
    return (
        f"grok --cwd {shlex.quote(str(cwd))} "
        f"--model {shlex.quote(model_selector)} "
        f"--always-approve "
        f"{shlex.quote(invocation)}"
    )


def render_cursor_launch(invocation: str, model_selector: str, cwd: str | Path) -> str:
    """Render a shell-safe, fully routed native Cursor launch command."""
    if (not isinstance(invocation, str) or not invocation.startswith(_COMMAND_PREFIX)
            or not isinstance(model_selector, str) or not model_selector
            or not isinstance(cwd, (str, Path)) or not str(cwd)):
        raise ValueError("CMD_INVOCATION_INVALID")
    return (
        f"agent --workspace {shlex.quote(str(cwd))} "
        f"--model {shlex.quote(model_selector)} "
        f"--force --sandbox disabled --trust --approve-mcps "
        f"{shlex.quote(invocation)}"
    )


def render_codex_launch(invocation: str, model_selector: str, effort_selector: str,
                        cwd: str | Path) -> str:
    """Render a shell-safe, fully routed native Codex launch command.

    A `$ planner:…` invocation addresses a command inside an existing Codex session.  A
    handoff must instead start a new process with the mapped selector and reasoning
    effort explicitly pinned, so the route cannot be silently inherited from the
    previous session.
    """
    if (not isinstance(invocation, str) or not invocation.startswith(f"$ {_COMMAND_PREFIX}")
            or not isinstance(model_selector, str) or not model_selector
            or not isinstance(effort_selector, str) or not effort_selector
            or not isinstance(cwd, (str, Path)) or not str(cwd)):
        raise ValueError("CMD_INVOCATION_INVALID")
    reasoning_config = f'model_reasoning_effort="{effort_selector}"'
    return (
        f"codex -C {shlex.quote(str(cwd))} -m {shlex.quote(model_selector)} "
        f"-c {shlex.quote(reasoning_config)} -a never -s danger-full-access "
        f"{shlex.quote(invocation)}"
    )


def render_claude_invocation(record: CommandRecord, arguments: str,
                             mapping: ProviderCommandMapping) -> str:
    """Render the frozen Claude slash invocation from explicit validated values."""
    if mapping.provider_id not in {"claude-code", "grok"} or not isinstance(arguments, str):
        raise ValueError("CMD_INVOCATION_INVALID")
    if "{command_id}" not in mapping.invocation_template or "{arguments}" not in mapping.invocation_template:
        raise ValueError("CMD_INVOCATION_INVALID")
    invocation = mapping.invocation_template.format(
        command_id=record.command_id, arguments=arguments).rstrip()
    if not invocation.startswith(f"/{_COMMAND_PREFIX}") or invocation.startswith("//"):
        raise ValueError("CMD_INVOCATION_INVALID")
    return invocation


_PROJECTION_CATALOG: ProjectionCatalog | None = None
_INVOCATION_BY_STYLE = {
    "slash": render_claude_invocation,
    "dollar": render_invocation,
    "semantic": render_cursor_invocation,
}


def _projection_catalog():
    global _PROJECTION_CATALOG
    if _PROJECTION_CATALOG is None:
        _PROJECTION_CATALOG = load_projection_catalog()
    return _PROJECTION_CATALOG


def render_provider_invocation(record: CommandRecord, arguments: str,
                               mapping: ProviderCommandMapping) -> str:
    """Render native invocation via the provider projection catalog."""
    spec = projection_spec(_projection_catalog(), ProviderId(mapping.provider_id))
    if spec is None:
        raise ValueError("CMD_PROVIDER_DISABLED")
    renderer = _INVOCATION_BY_STYLE.get(spec.command_invocation.style)
    if renderer is None:
        raise ValueError("CMD_INVOCATION_INVALID")
    return renderer(record, arguments, mapping)


def parse_next_carrier(declaration: str, *, context_kind: str = "same-session",
                       item_ids: list[str] | tuple[str, ...] = (),
                       cold_start_scope: list[list[str]] | tuple[tuple[str, str], ...] = (),
                       orchestration_capabilities: tuple[str, ...] = (),
                       ) -> PlanNextCarrier:
    """Parse the canonical `<kind>: planner:<id> <arguments>` Next declaration."""
    if not isinstance(declaration, str):
        raise ValueError("CMD_INVOCATION_INVALID: Next declaration is not text")
    match = re.fullmatch(r"([a-z][a-z-]*):\s*(.*)", declaration.strip())
    if not match:
        raise ValueError("CMD_INVOCATION_INVALID: malformed semantic Next")
    kind, payload = match.groups()
    if kind not in PlanNextCarrier.allowed_kinds():
        raise ValueError("CMD_INVOCATION_INVALID: unknown Next kind")
    if kind in _PLAN_NEXT_TERMINALS:
        if kind == "terminal" and payload.strip().lower() != "plan closed":
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
    command_id, deprecated = normalize_command_id(command_id)  # Compatibility alias: remove in the next minor release.
    if deprecated:
        warn_deprecated(payload.partition(" ")[0])
    command_id = _LEGACY_COMMAND_IDS.get(command_id, command_id)
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
                # A stronger model is never a stop; overshoot is only recorded.
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
    try:
        invocation = render_provider_invocation(record, arguments, mapping)
    except ValueError:
        diagnostic = _diag(
            "CMD_PROVIDER_DISABLED", record, "/provider_id",
            {"provider_id": tuple(sorted(_PROVIDER_IDS))},
            {"provider_id": mapping.provider_id}, mapping,
            "provider projection is not enabled")
        return PlanProviderInvocation(carrier, None, None, None,
                                      tuple(diagnostics + [diagnostic]))
    model_selector = dict(mapping.class_selectors)[observed_class][0]
    effort_selector = dict(mapping.effort_selectors)[observed_effort][0]
    if record.command_id == f"{COMMAND_NAMESPACE}:plan-audit" and any(
            value == "--reviewer" or value.startswith("--reviewer=") for value in carrier.arguments):
        from planner import review_selection
        try:
            selected = review_selection.invocation_selection(f"{record.command_id} {arguments}")
            if selected["provider"] != mapping.provider_id or selected["effort"] != observed_effort:
                raise review_selection.ReviewError("REVIEW_ROUTE_MISMATCH", "render with the selected provider and effort")
            model_selector = selected["model"]
            effort_selector = dict(mapping.effort_selectors)[selected["effort"]][0]
        except review_selection.ReviewError as exc:
            diagnostic = _diag("CMD_REVIEWER_ROUTE_MISMATCH", record, "/routing/reviewer", {},
                               {"error": str(exc)}, mapping, "explicit reviewer cannot be substituted")
            return PlanProviderInvocation(carrier, None, None, None, tuple(diagnostics + [diagnostic]))
    return PlanProviderInvocation(carrier, invocation, model_selector, effort_selector, tuple(diagnostics))


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
            "CMD_PROVIDER_DISABLED", f"{COMMAND_NAMESPACE}:catalog", "/provider_id", {"provider_id": "codex"},
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
            runtime = _codex_runtime_bytes(record, content, mapping)
            description = _project_codex_runtime_tokens(frontmatter_description(content))
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
    plugin = codex_plugin_manifest(
        MODULE_ID, catalog.plugin_version,
        "Provider-neutral planner commands and executable plan protocol for Codex",
        ["./adapters/codex/skills", "./skills"])
    all_sources = tuple(_source(record) for record in catalog.records)
    results.append(_artifact(f"{MODULE_ID}.codex.plugin", f"{_MODULE_DIR}/.codex-plugin/plugin.json",
                             manifest_bytes(plugin, sort_keys=True), all_sources, ("skills.repository",),
                             catalog, mapping.capability_catalog_version,
                             {"publication_unit": MODULE_ID, "kind": "plugin"}))

    for record in catalog.records:
        name = record.command_id.removeprefix(_COMMAND_PREFIX)
        base = f"{_MODULE_DIR}/adapters/codex/skills/{MODULE_ID}-{name}"
        description = projected_descriptions[record.command_id]
        wrapper = _wrapper_bytes(record, description, mapping)
        capabilities = tuple(item.capability_id for item in record.capability_requirements)
        results.append(_artifact(f"{MODULE_ID}.codex.{name.replace('-', '.')}.skill", f"{base}/SKILL.md",
                                 wrapper, (_source(record),), capabilities, catalog,
                                 mapping.capability_catalog_version,
                                 {"command_id": record.command_id, "kind": "skill-wrapper"}))
        results.append(_artifact(f"{MODULE_ID}.codex.{name.replace('-', '.')}.runtime", f"{base}/command.md",
                                 projected_runtime[record.command_id], (_source(record),),
                                 capabilities, catalog,
                                 mapping.capability_catalog_version,
                                 {"command_id": record.command_id,
                                  "kind": "runtime-projection"}))
        results.append(_artifact(
            f"{MODULE_ID}.codex.{name.replace('-', '.')}.invocation-policy",
            f"{base}/agents/openai.yaml", b"policy:\n  allow_implicit_invocation: false\n",
            (_source(record),), ("skills.repository",), catalog,
            mapping.capability_catalog_version,
            {"command_id": record.command_id, "kind": "invocation-policy"}))

    records = [{
        "path": result.target.path,
        "source_hash": result.provenance.source_hash,
        "rendered_hash": result.provenance.rendered_hash,
        "artifact_id": result.provenance.artifact_id,
    } for result in sorted(results, key=lambda item: item.target.path)]
    lock = publication_lock(MODULE_ID, catalog.plugin_version, records)
    results.append(_artifact(f"{MODULE_ID}.codex.publication-lock",
                             f"{_MODULE_DIR}/adapters/codex/publication-lock.json",
                             manifest_bytes(lock, sort_keys=True), all_sources, ("skills.repository",),
                             catalog, mapping.capability_catalog_version,
                             {"publication_unit": MODULE_ID, "kind": "publication-lock"}))
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
            "CMD_PROVIDER_DISABLED", f"{COMMAND_NAMESPACE}:catalog", "/provider_id",
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
        f"{MODULE_ID}.claude.plugin", f"{_MODULE_DIR}/.claude-plugin/plugin.json", plugin_bytes)]
    for record in catalog.records:
        name = record.command_id.removeprefix(_COMMAND_PREFIX).replace("-", ".")
        artifacts.append(_claude_artifact(
            f"{MODULE_ID}.claude.{name}.command", record.source.path,
            catalog.content_for(record.command_id), source_hash=record.source.content_hash))
    return ClaudeCommandRenderPlan(
        tuple(sorted(artifacts, key=lambda item: item.path)), tuple(diagnostics))


ALIAS_PLUGIN_DIR = f"{_MODULE_DIR}/aliases/{LEGACY_NAMESPACE}"  # Compatibility alias: remove in the next minor release.


def plan_claude_alias_render(catalog: CommandCatalog, *, plugin_bytes: bytes
                             ) -> ClaudeCommandRenderPlan:
    """Return the no-write projection of the `task` compatibility alias plugin (one minor release).

    # Compatibility alias: remove in the next minor release.
    Every alias command is the planner command byte-for-byte except the `description` prefix and a
    deprecation first line in the body; the alias plugin carries commands only (skills stay in planner).
    """
    try:
        planner_plugin = json.loads(plugin_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"CMD_SOURCE_DRIFT: Claude plugin descriptor is malformed: {error}") from error
    plugin = {
        "name": LEGACY_NAMESPACE,
        "version": catalog.plugin_version,
        "description": (f"Deprecated compatibility alias of the {MODULE_ID} plugin: "
                        f"/{LEGACY_NAMESPACE}:* commands for one minor release; use /{COMMAND_NAMESPACE}:*."),
        "author": planner_plugin.get("author"),
        "commands": ["./commands"],
    }
    plugin_text = json.dumps(plugin, indent=2, ensure_ascii=False) + "\n"
    artifacts = [_claude_artifact(f"{MODULE_ID}.claude.alias.plugin",
                                  f"{ALIAS_PLUGIN_DIR}/.claude-plugin/plugin.json",
                                  plugin_text.encode("utf-8"))]
    for record in catalog.records:
        command = record.command_id.removeprefix(_COMMAND_PREFIX)
        artifacts.append(_claude_artifact(
            f"{MODULE_ID}.claude.alias.{command.replace('-', '.')}.command",
            f"{ALIAS_PLUGIN_DIR}/commands/{command}.md",
            _alias_command_bytes(command, catalog.content_for(record.command_id)),
            source_hash=record.source.content_hash))
    return ClaudeCommandRenderPlan(tuple(sorted(artifacts, key=lambda item: item.path)), ())


def _alias_command_bytes(command: str, content: bytes) -> bytes:
    """The planner command with a deprecated `description` and the deprecation line on top of its body."""
    frontmatter, body = split_command(content)
    description = frontmatter_description(content)
    lines = frontmatter.splitlines(keepends=True)
    index = next(i for i, line in enumerate(lines) if line.startswith("description:"))
    lines[index] = "description: " + json.dumps(
        f"Deprecated alias of /{COMMAND_NAMESPACE}:{command}. {description}", ensure_ascii=False) + "\n"
    notice = (f"> `/{LEGACY_NAMESPACE}:{command}` is deprecated and will be removed in the next minor "
              f"release: use `/{COMMAND_NAMESPACE}:{command}`. Say this to the user once, then follow "
              f"the instructions below; `<Planner package root>` is the root of the enabled "
              f"{MODULE_ID} plugin.")
    return f"---\n{''.join(lines)}---\n{notice}\n\n{body}".encode("utf-8")


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
    # Owner-scoped, so the lock drops records of commands that no longer exist.
    planned = plan_artifact_lock(Path(root), render_plan.results, lock_bytes=lock_bytes,
                                 repair_artifact_ids=repair_artifact_ids,
                                 owner_namespace=PROVIDER_LOCK_OWNER)
    return ArtifactPlan(planned.actions, planned.next_lock, PROVIDER_LOCK_PATH,
                        owner_namespace=planned.owner_namespace,
                        observed_lock=planned.observed_lock)


def apply_codex_command_plan(root: Path, artifact_plan: ArtifactPlan) -> ArtifactPlan:
    """Apply an already-classified P2 plan under one explicit root."""
    return apply_plan(Path(root), artifact_plan)


def _projection_gate(catalog: CommandCatalog, mapping: ProviderCommandMapping,
                     capability_support: Mapping[str, str] | None):
    """Shared pre-write diagnostics for providers that publish a render plan."""
    diagnostics: list[CommandDiagnostic] = []
    support = (dict(mapping.capability_bindings) if capability_support is None
               else capability_support)
    blocked: set[str] = set()
    for record in catalog.records:
        diagnostics.extend(_mapping_diagnostics(record, mapping))
        for requirement in record.capability_requirements:
            level = support.get(requirement.capability_id)
            if level not in requirement.accepted_levels:
                diagnostics.append(_diag(
                    "CMD_CAPABILITY_UNSUPPORTED", record,
                    f"/capabilities/{requirement.capability_id}",
                    {"accepted_levels": requirement.accepted_levels}, {"support_level": level},
                    mapping, "required command capability is missing or unsupported",
                    severity="info"))
                blocked.add(record.command_id)
    return _dedupe_diagnostics(diagnostics), blocked


def plan_cursor_command_render(
        catalog: CommandCatalog, mapping: ProviderCommandMapping,
        capability_support: Mapping[str, str] | None = None) -> CursorCommandRenderPlan:
    """Return a complete no-write Cursor render plan or only pre-write diagnostics."""
    if mapping.provider_id != "cursor":
        return CursorCommandRenderPlan((), (_diag_raw(
            "CMD_PROVIDER_DISABLED", f"{COMMAND_NAMESPACE}:catalog", "/provider_id", {"provider_id": "cursor"},
            {"provider_id": mapping.provider_id}, mapping, "Cursor projection is not selected"),))
    diagnostics, blocked = _projection_gate(catalog, mapping, capability_support)
    if any(item.severity == "error" for item in diagnostics):
        return CursorCommandRenderPlan((), tuple(diagnostics))

    results: list[ArtifactRenderResult] = []
    all_sources = tuple(_source(record) for record in catalog.records
                        if record.command_id not in blocked)
    for record in catalog.records:
        if record.command_id in blocked:
            continue
        name = record.command_id.removeprefix(_COMMAND_PREFIX)
        base = f"{_MODULE_DIR}/adapters/cursor/skills/{MODULE_ID}-{name}"
        description = frontmatter_description(catalog.content_for(record.command_id))
        wrapper = _cursor_wrapper_bytes(record, description, mapping)
        capabilities = tuple(item.capability_id for item in record.capability_requirements)
        runtime = _cursor_runtime_bytes(record, catalog.content_for(record.command_id), mapping)
        results.append(_artifact(f"{MODULE_ID}.cursor.{name.replace('-', '.')}.skill",
                                 f"{base}/SKILL.md", wrapper, (_source(record),),
                                 capabilities, catalog, mapping.capability_catalog_version,
                                 {"command_id": record.command_id, "kind": "skill-wrapper"},
                                 provider_id=ProviderId.CURSOR, adapter_id=f"{MODULE_ID}.cursor-command"))
        results.append(_artifact(f"{MODULE_ID}.cursor.{name.replace('-', '.')}.runtime",
                                 f"{base}/command.md", runtime, (_source(record),),
                                 capabilities, catalog, mapping.capability_catalog_version,
                                 {"command_id": record.command_id, "kind": "runtime-projection"},
                                 provider_id=ProviderId.CURSOR, adapter_id=f"{MODULE_ID}.cursor-command"))
    records = [{
        "path": result.target.path,
        "source_hash": result.provenance.source_hash,
        "rendered_hash": result.provenance.rendered_hash,
        "artifact_id": result.provenance.artifact_id,
    } for result in sorted(results, key=lambda item: item.target.path)]
    lock = publication_lock(MODULE_ID, catalog.plugin_version, records)
    results.append(_artifact(f"{MODULE_ID}.cursor.publication-lock",
                             f"{_MODULE_DIR}/adapters/cursor/publication-lock.json",
                             manifest_bytes(lock, sort_keys=True), all_sources, ("skills.repository",),
                             catalog, mapping.capability_catalog_version,
                             {"publication_unit": MODULE_ID, "kind": "publication-lock"},
                             provider_id=ProviderId.CURSOR, adapter_id=f"{MODULE_ID}.cursor-command"))
    return CursorCommandRenderPlan(tuple(sorted(results, key=lambda item: item.target.path)),
                                   tuple(diagnostics))


def plan_grok_command_render(
        catalog: CommandCatalog, mapping: ProviderCommandMapping,
        capability_support: Mapping[str, str] | None = None) -> CursorCommandRenderPlan:
    """Lock-only Grok plan: discover `.agents/skills`, never write a fourth skill tree."""
    if mapping.provider_id != "grok":
        return CursorCommandRenderPlan((), (_diag_raw(
            "CMD_PROVIDER_DISABLED", f"{COMMAND_NAMESPACE}:catalog", "/provider_id", {"provider_id": "grok"},
            {"provider_id": mapping.provider_id}, mapping, "Grok projection is not selected"),))
    diagnostics, blocked = _projection_gate(catalog, mapping, capability_support)
    if any(item.severity == "error" for item in diagnostics):
        return CursorCommandRenderPlan((), tuple(diagnostics))
    all_sources = tuple(_source(record) for record in catalog.records
                        if record.command_id not in blocked)
    lock = {
        "contract_version": "1.0.0", "publication_unit": MODULE_ID,
        "version": catalog.plugin_version,
        "discovery_surface": ".agents/skills",
        "writer": "none",
        "artifacts": [],
    }
    results = [_artifact(
        f"{MODULE_ID}.grok.publication-lock",
        f"{_MODULE_DIR}/adapters/grok/publication-lock.json",
        manifest_bytes(lock, sort_keys=True), all_sources, ("skills.repository",),
        catalog, mapping.capability_catalog_version,
        {"publication_unit": MODULE_ID, "kind": "publication-lock",
         "discovery_surface": ".agents/skills"},
        provider_id=ProviderId.GROK, adapter_id=f"{MODULE_ID}.grok-command")]
    return CursorCommandRenderPlan(tuple(results), tuple(diagnostics))


def build_provider_command_parity_report(
        catalog: CommandCatalog, claude_plan: ClaudeCommandRenderPlan,
        codex_plan: CodexCommandRenderPlan,
        cursor_plan: CursorCommandRenderPlan,
        grok_plan: CursorCommandRenderPlan,
        mappings: Mapping[str, ProviderCommandMapping], *,
        expected_command_ids: tuple[str, ...],
        next_carriers: tuple[PlanNextCarrier, ...] = ()) -> dict[str, object]:
    """Build a deterministic report from an independently validated expected set.

    This is a conformance reporter, not another renderer: it consumes the two named
    provider plans and refuses any inventory/projection delta before producing rows.
    """
    if set(mappings) != _PROVIDER_IDS:
        raise ValueError("CMD_PROVIDER_DISABLED: all provider mappings are required")
    if not claude_plan.ok or not codex_plan.ok or not cursor_plan.ok or not grok_plan.ok:
        raise ValueError("CMD_SOURCE_DRIFT: provider render plans must be clean")

    catalog_ids = tuple(record.command_id for record in catalog.records)
    semantic_duplicates = _duplicates(catalog_ids)
    expected_set, catalog_set = set(expected_command_ids), set(catalog_ids)
    semantic_delta = {
        "missing": sorted(expected_set - catalog_set),
        "extra": sorted(catalog_set - expected_set),
        "duplicates": semantic_duplicates,
    }

    expected_claude = {f"{_MODULE_DIR}/.claude-plugin/plugin.json"}
    expected_codex = {
        f"{_MODULE_DIR}/.codex-plugin/plugin.json",
        f"{_MODULE_DIR}/adapters/codex/publication-lock.json",
    }
    expected_cursor = {
        f"{_MODULE_DIR}/adapters/cursor/publication-lock.json",
    }
    expected_grok = {
        f"{_MODULE_DIR}/adapters/grok/publication-lock.json",
    }
    cursor_mapping = mappings["cursor"]
    cursor_support = dict(cursor_mapping.capability_bindings)
    for command_id in expected_command_ids:
        name = command_id.removeprefix(_COMMAND_PREFIX)
        expected_claude.add(f"{_MODULE_DIR}/commands/{name}.md")
        expected_codex.add(
            f"{_MODULE_DIR}/adapters/codex/skills/{MODULE_ID}-{name}/SKILL.md")
        expected_codex.add(
            f"{_MODULE_DIR}/adapters/codex/skills/{MODULE_ID}-{name}/command.md")
        expected_codex.add(
            f"{_MODULE_DIR}/adapters/codex/skills/{MODULE_ID}-{name}/agents/openai.yaml")
        record = catalog.by_id()[command_id]
        cursor_supported = all(
            cursor_support.get(requirement.capability_id) in requirement.accepted_levels
            for requirement in record.capability_requirements)
        if cursor_supported:
            expected_cursor.add(
                f"{_MODULE_DIR}/adapters/cursor/skills/{MODULE_ID}-{name}/SKILL.md")
            expected_cursor.add(
                f"{_MODULE_DIR}/adapters/cursor/skills/{MODULE_ID}-{name}/command.md")

    claude_paths = tuple(artifact.path for artifact in claude_plan.artifacts)
    codex_paths = tuple(artifact.path for artifact in codex_plan.artifacts)
    cursor_paths = tuple(artifact.path for artifact in cursor_plan.artifacts)
    grok_paths = tuple(artifact.path for artifact in grok_plan.artifacts)
    projections = {
        "claude-code": _projection_delta(expected_claude, claude_paths),
        "codex": _projection_delta(expected_codex, codex_paths),
        "cursor": _projection_delta(expected_cursor, cursor_paths),
        "grok": _projection_delta(expected_grok, grok_paths),
    }
    if (any(semantic_delta.values())
            or any(any(delta.values()) for delta in projections.values())):
        raise ValueError("CMD_CATALOG_MISMATCH: semantic/provider projection delta")

    claude_artifacts = {item.path: item for item in claude_plan.artifacts}
    codex_artifacts = {item.path: item for item in codex_plan.artifacts}
    commands = []
    for record in catalog.records:
        route = record.routing
        name = record.command_id.removeprefix(_COMMAND_PREFIX)
        providers = {}
        for provider_id in _PROVIDER_ORDER:
            mapping = mappings[provider_id]
            if route.mode == "fixed":
                selector = dict(mapping.class_selectors)[route.model_class][0]
                effort = dict(mapping.effort_selectors)[route.effort][0]
            else:
                selector = effort = "routing-required"
            invocation = render_provider_invocation(record, "<arguments>", mapping)
            if provider_id == "claude-code":
                artifact = claude_artifacts[record.source.path]
                artifact_paths = [artifact.path]
                rendered_hashes = [artifact.rendered_hash]
            elif provider_id == "codex":
                paths = [
                    f"{_MODULE_DIR}/adapters/codex/skills/{MODULE_ID}-{name}/SKILL.md",
                    f"{_MODULE_DIR}/adapters/codex/skills/{MODULE_ID}-{name}/command.md",
                ]
                artifacts = [codex_artifacts[path] for path in paths]
                artifact_paths = paths
                rendered_hashes = [artifact.rendered_hash for artifact in artifacts]
            elif provider_id == "grok":
                artifact_paths = []
                rendered_hashes = []
            else:
                cursor_supported = all(
                    dict(mapping.capability_bindings).get(requirement.capability_id)
                    in requirement.accepted_levels
                    for requirement in record.capability_requirements)
                if cursor_supported:
                    paths = [
                        f"{_MODULE_DIR}/adapters/cursor/skills/{MODULE_ID}-{name}/SKILL.md",
                        f"{_MODULE_DIR}/adapters/cursor/skills/{MODULE_ID}-{name}/command.md",
                    ]
                    cursor_artifacts = {item.path: item for item in cursor_plan.artifacts}
                    artifacts = [cursor_artifacts[path] for path in paths]
                    artifact_paths = paths
                    rendered_hashes = [artifact.rendered_hash for artifact in artifacts]
                else:
                    artifact_paths = []
                    rendered_hashes = []
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
        for provider_id in _PROVIDER_ORDER:
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
        "# Provider planner commands",
        "",
        "Generated from the validated provider-command parity report. Do not edit manually.",
        "",
        f"Contract: `{report['contract_version']}` · Catalog: `{report['catalog_version']}`",
        "",
        "## Command matrix",
        "",
        "| Semantic ID | Canonical source / SHA-256 | Neutral route | Capabilities | Claude Code | Codex | Cursor | Grok |",
        "|:--|:--|:--|:--|:--|:--|:--|:--|",
    ]
    for command in report["commands"]:
        route = command["routing"]
        neutral = f"{route['mode']} · {route['model_class']}/{route['effort']}"
        capabilities = "<br>".join(f"`{item}`" for item in command["capabilities"])
        source = f"`{command['source']}`<br>`{command['source_hash']}`"
        provider_cells = []
        for provider_id in _PROVIDER_ORDER:
            projection = command["providers"][provider_id]
            provider_cells.append(
                f"`{projection['invocation']}`<br>"
                f"`{projection['model_selector']}/{projection['effort_selector']}`")
        lines.append(
            f"| `{command['command_id']}` | {source} | `{neutral}` | {capabilities} | "
            + " | ".join(provider_cells) + " |")

    lines.extend([
        "",
        "## Semantic Next forms",
        "",
        "| Kind | Semantic carrier | Claude Code | Codex | Cursor | Grok | Diagnostics |",
        "|:--|:--|:--|:--|:--|:--|:--|",
    ])
    for row in report["next_forms"]:
        carrier = row["carrier"]
        claude = row["providers"]["claude-code"]
        codex = row["providers"]["codex"]
        cursor = row["providers"]["cursor"]
        grok = row["providers"]["grok"]
        diagnostics = sorted(set(claude["diagnostics"] + codex["diagnostics"]
                                 + cursor["diagnostics"] + grok["diagnostics"]))
        lines.append(
            f"| `{carrier['kind']}` | `{json.dumps(carrier, ensure_ascii=False, sort_keys=True)}` "
            f"| `{claude['invocation'] or '—'}` | `{codex['invocation'] or '—'}` "
            f"| `{cursor['invocation'] or '—'}` | `{grok['invocation'] or '—'}` "
            f"| `{', '.join(diagnostics) or '—'}` |")

    lines.extend([
        "",
        "## Conformance result",
        "",
        "- Semantic inventory: `missing=[]`, `extra=[]`, `duplicates=[]`.",
        "- Claude Code projection: `missing=[]`, `extra=[]`, `duplicates=[]`.",
        "- Codex projection: `missing=[]`, `extra=[]`, `duplicates=[]`.",
        "- Cursor projection: `missing=[]`, `extra=[]`, `duplicates=[]`.",
        "- Grok projection: `missing=[]`, `extra=[]`, `duplicates=[]`.",
        "- Unknown, ambiguous, unsupported, undershoot, invalid invocation and source drift are fail-closed before write.",
        "",
    ])
    return "\n".join(lines).encode("utf-8")


def render_provider_model_roles_reference(catalog: CommandCatalog) -> bytes:
    """Render the per-provider model role guide from validated routing mappings."""
    metadata = metadata_value(catalog)
    mappings = metadata.get("mappings", {})
    if set(mappings) != _PROVIDER_IDS:
        raise ValueError("CMD_PROVIDER_DISABLED: all provider mappings are required")
    lines = [
        "# Provider model roles",
        "",
        "Hand-verified model inventories and fixed class pins for the managed providers.",
        f"Neutral routing in `{_MODULE_DIR}/configs/command-routing.json` uses "
        "`model_class` (`economy` < `implementation` < `frontier`) plus `effort`; "
        "each provider block below maps those classes to native selectors.",
        "",
        "Generated from the validated command-routing mappings. Do not edit the tables manually.",
        "",
        "## Semantic roles",
        "",
        "| Work kind | Neutral class | Typical commands |",
        "|:--|:--|:--|",
        "| Economy / ad-hoc explore | `economy` | low-risk fixes, scans |",
        f"| Implementation / execution | `implementation` | `{_COMMAND_PREFIX}dev`, `{_COMMAND_PREFIX}plan-run`, `{_COMMAND_PREFIX}plan-close` |",
        f"| Design / audit / review | `frontier` | `{_COMMAND_PREFIX}design`, `{_COMMAND_PREFIX}plan-design`, `{_COMMAND_PREFIX}plan-audit`, `{_COMMAND_PREFIX}review` |",
        "",
        "Fixed commands and launch-blocks pin **one** default selector per class. The model pool below "
        "is the admission list: any entry whose roles cover the required class is admitted (roles "
        "overlap, the highest class wins, a stronger model is never a stop). Entries match by id, "
        "`aliases` or regex `patterns`; `status: retired` leaves the pool. A model outside the pool "
        "is `ROUTE_MODEL_UNKNOWN`: extend the pool, never the plan. `auto` never substitutes a pin.",
        "",
        "## Class pins",
        "",
        "| Provider | economy | implementation | frontier |",
        "|:--|:--|:--|:--|",
    ]
    pin_cells = []
    for provider_id in _PROVIDER_ORDER:
        mapping = mappings[provider_id]
        selectors = mapping["class_selectors"]
        pin_cells.append(
            f"| `{provider_id}` | `{selectors['economy'][0]}` | `{selectors['implementation'][0]}` "
            f"| `{selectors['frontier'][0]}` |")
    lines.extend(pin_cells)
    lines.extend(["", "## Model inventory", ""])
    for provider_id in _PROVIDER_ORDER:
        mapping = mappings[provider_id]
        inventory = mapping["model_inventory"]
        lines.append(f"### `{provider_id}`")
        lines.append("")
        lines.append(f"- `verified_at`: `{inventory['verified_at']}`")
        lines.append(f"- `source`: {inventory['source']}")
        if inventory.get("verification"):
            lines.append(f"- `verification`: {inventory['verification']}")
        lines.extend(["", "| Model id | Roles | Notes |", "|:--|:--|:--|"])
        for entry in inventory["entries"]:
            roles = ", ".join(entry["roles"])
            notes = []
            if entry.get("status"):
                notes.append(f"status={entry['status']}")
            if entry.get("policy"):
                notes.append(f"policy={entry['policy']}")
            if entry.get("aliases"):
                notes.append("aliases=" + ", ".join(f"`{item}`" for item in entry["aliases"]))
            if entry.get("patterns"):
                notes.append("patterns=" + ", ".join(f"`{item}`" for item in entry["patterns"]))
            if entry.get("notes"):
                notes.append(entry["notes"])
            note_cell = "; ".join(notes) if notes else "—"
            lines.append(f"| `{entry['id']}` | {roles} | {note_cell} |")
        auto_mode = inventory.get("auto_mode")
        if auto_mode:
            lines.extend([
                "",
                "**Auto policy** (`auto` routing-assist only):",
                "",
                f"- `allowed_for`: {', '.join(f'`{item}`' for item in auto_mode['allowed_for'])}",
                f"- `forbidden_for`: {', '.join(f'`{item}`' for item in auto_mode['forbidden_for'])}",
                "",
                "`auto` never substitutes a fixed `frontier` or `implementation` pin in a launch-block "
                "or fixed command.",
            ])
        lines.append("")
    lines.extend([
        "## Cursor launch contract (trusted self-host)",
        "",
        "Approval mode and IDE Run Mode are **not** project-configurable (see freeze E14.1). "
        "Autonomy comes from launch flags plus a documented IDE checklist; the `deny` floor in "
        "`.cursor/cli.json` survives `--force`.",
        "",
        "| Parameter | Value |",
        "|:--|:--|",
        "| Workspace (`cwd`) | repository root — `agent --workspace <repo-cwd>` (not `-C`) |",
        "| Model | class pin from table above |",
        "| Effort | from plan Routing / command frontmatter |",
        "| CLI autonomy | `--force --sandbox disabled --trust --approve-mcps` |",
        "| IDE Run Mode | **Run Everything** (trusted self-host only; UI-owned, not a repo file) |",
        "",
        "**Native Cursor command** (copy after the metadata table in a launch-block):",
        "",
        "```bash",
        f"agent --workspace <repo-cwd> --model <model-selector> --force --sandbox disabled --trust --approve-mcps '{_COMMAND_PREFIX}<command> <arguments>'",
        "```",
        "",
        "IDE checklist before an autonomous session:",
        "",
        "1. Open the intended repository root as the workspace.",
        "2. Set Run Mode to **Run Everything** (Settings → Run Mode).",
        "3. Confirm `.cursor/mcp.json` contains hub servers.",
        "4. Pin the routed model; do not substitute `auto` for fixed frontier/implementation pins.",
        "5. For CLI launches, pass the full flag set above; partial flags are not a trusted launch.",
        "",
        "Full install and profile shapes: see your environment's Cursor adapter setup.",
        "",
        "## Grok launch contract (trusted self-host)",
        "",
        "Grok Build CLI (`grok`, PATH alias `agent`) is a managed provider. Skills are "
        "discovered from `.agents/skills` (no `.grok/skills` writer). Project "
        "`.grok/config.toml` carries `[permission] deny` and MCP only; `[ui] permission_mode` "
        "is user-level in `~/.grok/config.toml` and is not read from the project file. "
        "`--always-approve` is a trusted-session launch flag. The deny floor still applies. "
        "Cursor's `agent --workspace` is a different binary (`cursor-agent`); identity is "
        "`GROK_SESSION_ID`.",
        "",
        "| Parameter | Value |",
        "|:--|:--|",
        "| Workspace (`cwd`) | repository root — `grok --cwd <repo-cwd>` |",
        "| Model | class pin from table above (`grok-4.5` / `grok-4.6` / `grok-4.7`) |",
        "| Effort | from plan Routing / command frontmatter; fallback `[models].default_reasoning_effort` |",
        "| CLI autonomy | `--permission-mode default|acceptEdits`, or `--always-approve` on trusted self-host |",
        "| Binary | `grok` or Grok `agent`; never Cursor `cursor-agent` |",
        "",
        "**Native Grok command** (copy after the metadata table in a launch-block):",
        "",
        "```bash",
        f"grok --cwd <repo-cwd> --model <model-selector> --always-approve '/{_COMMAND_PREFIX}<command> <arguments>'",
        "```",
        "",
        "1. Open the intended repository root (`--cwd`).",
        "2. Confirm `.grok/config.toml` and hub MCP.",
        "3. Pin the routed model; do not substitute Cursor-inventory grok-4.x ids for provider grok.",
        "4. Pass `--always-approve` only on a trusted self-host; the deny floor remains.",
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


def _extra_selectors_are_ambiguous(mapping: ProviderCommandMapping, values: tuple[str, ...]) -> bool:
    """The launch pin is selectors[0]. Cursor may recognize later live model names."""
    if len(values) <= 1:
        return False
    return mapping.provider_id not in {"cursor", "grok"}


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
            elif _extra_selectors_are_ambiguous(mapping, values):
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
        elif _extra_selectors_are_ambiguous(mapping, values):
            diagnostics.append(_diag(
                "CMD_MAPPING_AMBIGUOUS", record, path,
                {"selector_count": 1}, {"selectors": values}, mapping,
                "provider selector mapping is ambiguous"))
    return tuple(diagnostics)


def _artifact(artifact_id: str, target: str, rendered: bytes,
              sources: tuple[ArtifactSource, ...], capabilities: tuple[str, ...],
              catalog: CommandCatalog, capability_catalog_version: str,
              semantic_parameters: Mapping[str, object], *,
              provider_id: ProviderId = ProviderId.CODEX,
              adapter_id: str = f"{MODULE_ID}.codex-command") -> ArtifactRenderResult:
    parameters = dict(semantic_parameters)
    parameters["plugin_version"] = catalog.plugin_version
    adapter = ArtifactAdapterIdentity(adapter_id, ADAPTER_VERSION, provider_id,
                                      capability_catalog_version,
                                      capability_requirements(capabilities))
    return render_whole_file(artifact_id=artifact_id, target=target, sources=sources,
                             adapter=adapter, parameters=parameters, rendered=rendered)


def _source(record: CommandRecord) -> ArtifactSource:
    return ArtifactSource(record.source.source_id, record.source.path, record.source.content_hash)


def _cursor_wrapper_bytes(record: CommandRecord, description: str,
                          mapping: ProviderCommandMapping) -> bytes:
    name = record.command_id.removeprefix(_COMMAND_PREFIX)
    source_hash = record.source.content_hash
    invocation = render_cursor_invocation(record, "<arguments>", mapping)
    if record.routing.mode == "fixed":
        selector = dict(mapping.class_selectors)[record.routing.model_class][0]
        effort = dict(mapping.effort_selectors)[record.routing.effort][0]
        route = f"{record.routing.model_class}/{record.routing.effort} -> {selector}/{effort}"
    else:
        route = "inherited-plan -> validate the current session against the selected plan item"
    text = f'''---
name: {MODULE_ID}-{name}
description: {json.dumps('Only when explicitly invoked. ' + description, ensure_ascii=False)}
disable-model-invocation: true
---

# Planner {name}

Generated Cursor adapter for semantic command `{record.command_id}`.

- Invocation: `{invocation}`
- Routing: `{route}`
- Canonical source: `{record.source.path}`
- Canonical SHA-256: `{source_hash}`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as the user prompt.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
'''
    return text.encode("utf-8")


def _cursor_runtime_bytes(record: CommandRecord, content: bytes,
                          mapping: ProviderCommandMapping) -> bytes:
    text = content.decode("utf-8")
    if record.kind == "plan-protocol":
        text = _cursor_native_launch_rule(mapping) + text
    provenance = runtime_provenance("Cursor", record.source.path, record.source.content_hash,
                                    f"{MODULE_ID}.cursor-command/{ADAPTER_VERSION}")
    return (provenance + text).encode("utf-8")


def _cursor_native_launch_rule(mapping: ProviderCommandMapping) -> str:
    classes = dict(mapping.class_selectors)
    class_routes = ", ".join(f"{name}={classes[name][0]}" for name in MODEL_CLASSES)
    return f'''## Native Cursor launch-block — required only at a real user-facing boundary

This generated runtime is the Cursor provider projection. Render only the Cursor-native launch;
never copy Claude slash syntax or Codex `$ {_COMMAND_PREFIX}` as the executable invocation.

At a fresh-session boundary print `**Native Cursor command:**` and a fenced `bash` block which
explicitly pins the repository workspace, mapped model, and autonomy flags:

```bash
agent --workspace <repo-cwd> --model <model-selector> --force --sandbox disabled --trust --approve-mcps '{_COMMAND_PREFIX}<command> <arguments>'
```

`auto` never substitutes a fixed frontier or implementation pin. Current Cursor mapping: {class_routes}.

'''


def _wrapper_bytes(record: CommandRecord, description: str,
                   mapping: ProviderCommandMapping) -> bytes:
    name = record.command_id.removeprefix(_COMMAND_PREFIX)
    source_hash = record.source.content_hash
    invocation = render_invocation(record, "<arguments>", mapping)
    if record.routing.mode == "fixed":
        selector = dict(mapping.class_selectors)[record.routing.model_class][0]
        effort = dict(mapping.effort_selectors)[record.routing.effort][0]
        route = f"{record.routing.model_class}/{record.routing.effort} -> {selector}/{effort}"
    else:
        route = "inherited-plan -> validate the current session against the selected plan item"
    text = f'''---
name: {MODULE_ID}-{name}
description: {json.dumps('Only when explicitly invoked. ' + description, ensure_ascii=False)}
---

# Planner {name}

Generated Codex adapter for semantic command `{record.command_id}`.

- Invocation: `{invocation}`
- Routing: `{route}`
- Canonical source: `{record.source.path}`
- Canonical SHA-256: `{source_hash}`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this planner command or skill. Planner is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
'''
    return text.encode("utf-8")


def _codex_runtime_bytes(record: CommandRecord, content: bytes,
                         mapping: ProviderCommandMapping) -> bytes:
    """Project one canonical Claude command into a finite, provider-safe Codex runtime."""
    _frontmatter, body = split_command(content)
    projected = _project_codex_runtime_tokens(body)
    if record.kind == "plan-protocol":
        provider_rule = _codex_current_route_rule(record)
        projected = _codex_native_launch_rule(mapping) + provider_rule + projected
    provenance = runtime_provenance("Codex", record.source.path, record.source.content_hash,
                                    f"{MODULE_ID}.codex-command/{ADAPTER_VERSION}")
    return (provenance + projected).encode("utf-8")


def _codex_native_launch_rule(mapping: ProviderCommandMapping) -> str:
    """Return the native launch format for generated plan runtimes."""
    classes = dict(mapping.class_selectors)
    efforts = dict(mapping.effort_selectors)
    class_routes = ", ".join(
        f"{name}={classes[name][0]}" for name in MODEL_CLASSES)
    effort_routes = ", ".join(
        f"{name}={efforts[name][0]}" for name in EFFORTS)
    return f'''## Native Codex launch-block — required only at a real user-facing boundary

This generated runtime is the Codex provider projection. `$ {_COMMAND_PREFIX}…` runs inside the **current**
Codex session; never copy Claude Code slash syntax. Continue ready work of the requested scope in
this session: an item, a phase or a failed test is not a session boundary.

Only when the owner asks for a new session, print `**Native Codex command:**` and one fenced `bash`
line that pins the repository cwd, the model and effort mapped from the next item's route, approval
policy and sandbox (never put the command in a table cell):

```bash
codex -C <repo-cwd> -m <model-selector> -c 'model_reasoning_effort="<effort-selector>"' -a never -s danger-full-access '$ {_COMMAND_PREFIX}<command> <arguments>'
```

Current Codex mapping: {class_routes}; {effort_routes}.

'''


def _codex_current_route_rule(record: CommandRecord) -> str:
    """Tell Codex where the planner package root (and so ``plan.py``) lives."""
    planner_root = codex_task_plugin_root_expression()
    return f'''## Codex planner root — provider-specific

The planner package root is the installed Codex plugin:

```bash
export PLANNER_CODEX_PLUGIN_ROOT="{planner_root}"
```

`plan.py` means `python3 "$PLANNER_CODEX_PLUGIN_ROOT/scripts/plan.py"`. Declare the route with
`--actor codex/<model>/<reasoning effort>` from this session's settings.

'''


def _project_codex_runtime_tokens(text: str) -> str:
    """Project the finite standalone Claude token set without touching slash notation."""
    def replacement(match: re.Match[str]) -> str:
        if match.group("workflow_path") or match.group("workflow"):
            return _CODEX_WORKFLOW_CARRIER
        if match.group("model_class"):
            return _CODEX_MODEL_CLASS_PROJECTIONS[match.group(0).lower()]
        if match.group("command"):
            return f"$ {_COMMAND_PREFIX}" + match.group("command_id")
        if match.group("ui"):
            # A bracketed effort suffix is reviewer selector grammar, not a UI command.
            if match.start() > 0 and text[match.start() - 1] == "[" and text[match.end():].startswith("]"):
                return match.group(0)
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
            "CMD_SOURCE_DRIFT", f"{COMMAND_NAMESPACE}:catalog", "/plugin", {"valid_json": True},
            {"error": str(error)}, mapping, "Claude plugin descriptor is malformed"),)
    expected = {"name": MODULE_ID, "version": catalog.plugin_version,
                "commands": ["./commands"], "skills": ["./skills"]}
    observed = ({key: value.get(key) for key in expected} if isinstance(value, dict)
                else {"type": type(value).__name__})
    if observed != expected:
        return (_diag_raw(
            "CMD_SOURCE_DRIFT", f"{COMMAND_NAMESPACE}:catalog", "/plugin/registration", expected,
            observed, mapping, "Claude plugin identity, version or command registration drifted"),)
    return ()


def _claude_frontmatter_diagnostics(
        record: CommandRecord, content: bytes,
        mapping: ProviderCommandMapping) -> tuple[CommandDiagnostic, ...]:
    try:
        fields = strict_frontmatter_fields(content)
    except ValueError as error:
        return (_diag("CMD_SOURCE_DRIFT", record, "/frontmatter", {"valid": True},
                      {"error": str(error)}, mapping,
                      "Claude command frontmatter is malformed"),)

    if record.routing.mode == "inherited-plan" or record.command_id in {f"{COMMAND_NAMESPACE}:review", f"{COMMAND_NAMESPACE}:plan-audit"}:
        observed = {key: fields.get(key) for key in ("model", "effort") if key in fields}
        if observed:
            return (_diag("CMD_SOURCE_DRIFT", record, "/frontmatter/routing", {}, observed,
                          mapping, "inherited/explicit-reviewer Claude command must not pin model or effort"),)
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
